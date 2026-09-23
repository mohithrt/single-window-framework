from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.critical_path_service import CriticalPathService
from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.models import (
    Application, ApplicationApproval, ApplicationDocument, ApplicationStatus,
    ApplicationValidationIssue, ApprovalStatus, Inspection, RiskAssessment,
    RoleCode, User, WorkflowAuditEvent,
)
from app.officer_schemas import InspectionScheduleRequest, OfficerRemarkRequest
from app.prevalidation import prevalidation_payload

router = APIRouter(
    prefix="/officer",
    tags=["department officer portal"],
    dependencies=[Depends(require_roles(RoleCode.OFFICER))],
)
Database = Annotated[Session, Depends(get_db)]
SLA_TERMINAL = {ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value}
SLA_PAUSED = {ApprovalStatus.NOT_STARTED.value}
SLA_START_ACTIONS = {"APPROVAL_ACTIVATED", "REVIEW_STARTED", "CORRECTION_SUBMITTED"}
schedule = CriticalPathService()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _sla_data(approval: ApplicationApproval, now: datetime | None = None) -> dict:
    if approval.status in SLA_PAUSED:
        return {"sla_status": "BLOCKED", "sla_due_at": None, "sla_days": schedule.durations.get(approval.department_code, 5), "days_overdue": 0}
    if approval.status in SLA_TERMINAL:
        return {"sla_status": "CLOSED", "sla_due_at": None, "sla_days": schedule.durations.get(approval.department_code, 5), "days_overdue": 0}
    start = _utc(approval.created_at) if approval.created_at else datetime.now(UTC)
    starts = [event.created_at for event in approval.audit_events if event.action in SLA_START_ACTIONS and event.created_at]
    if starts:
        start = max(_utc(value) for value in starts)
    sla_days = schedule.durations.get(approval.department_code, 5)
    due = start + timedelta(days=sla_days)
    current = now or datetime.now(UTC)
    overdue = max(0, int((current - due).total_seconds() // 86400)) if current > due else 0
    return {
        "sla_status": "BREACHED" if current > due else "ON_TRACK",
        "sla_due_at": due,
        "sla_days": sla_days,
        "days_overdue": overdue,
    }


def _approval_query():
    return select(ApplicationApproval).join(Application).options(
        joinedload(ApplicationApproval.application).joinedload(Application.owner),
        selectinload(ApplicationApproval.audit_events),
    ).where(
        ApplicationApproval.is_required.is_(True),
        Application.status.notin_([ApplicationStatus.DRAFT.value, ApplicationStatus.APPROVED.value, ApplicationStatus.REJECTED.value]),
        ApplicationApproval.status.notin_(list(SLA_TERMINAL)),
    )


def _queue_item(approval: ApplicationApproval, now: datetime | None = None) -> dict:
    application = approval.application
    owner = application.owner
    return {
        "approval_id": approval.id,
        "application_id": application.id,
        "application_number": application.application_number,
        "department_code": approval.department_code,
        "department_name": approval.department_name,
        "applicant_name": application.applicant_name or owner.full_name,
        "applicant_email": application.applicant_email or owner.email,
        "company_name": application.company_name or "Company not provided",
        "industry_type": application.industry_type,
        "risk_tier": application.risk_tier,
        "application_status": application.status,
        "approval_status": approval.status,
        "progress_percent": application.progress_percent,
        "submitted_at": application.submitted_at,
        "expected_completion_at": application.expected_completion_at,
        "dependencies": approval.depends_on,
        **_sla_data(approval, now),
    }


def _list_queue(db: Session, *, search: str | None = None, status: str | None = None,
                risk: str | None = None, sla: str = "ALL", sort_by: str = "SUBMITTED",
                sort_order: str = "DESC", limit: int = 100, offset: int = 0) -> dict:
    statement = _approval_query()
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(or_(
            Application.application_number.ilike(term), Application.company_name.ilike(term),
            Application.applicant_name.ilike(term), Application.applicant_email.ilike(term),
            ApplicationApproval.department_name.ilike(term),
        ))
    if status:
        statement = statement.where(ApplicationApproval.status == status)
    if risk:
        statement = statement.where(Application.risk_tier == risk)
    rows = db.scalars(statement).unique().all()
    now = datetime.now(UTC)
    items = [_queue_item(row, now) for row in rows]
    if sla != "ALL":
        items = [item for item in items if item["sla_status"] == sla]
    risk_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, None: 0}
    sort_keys = {
        "SUBMITTED": lambda item: item["submitted_at"] or datetime.min.replace(tzinfo=UTC),
        "RISK": lambda item: risk_rank.get(item["risk_tier"], 0),
        "SLA": lambda item: item["sla_due_at"] or datetime.max.replace(tzinfo=UTC),
        "COMPANY": lambda item: item["company_name"].casefold(),
        "STATUS": lambda item: item["approval_status"],
    }
    items.sort(key=sort_keys[sort_by], reverse=sort_order == "DESC")
    total = len(items)
    return {"total": total, "items": items[offset:offset + limit]}


@router.get("/dashboard")
def officer_dashboard(user: CurrentUser, db: Database) -> dict:
    rows = db.scalars(_approval_query()).unique().all()
    now = datetime.now(UTC)
    items = [_queue_item(row, now) for row in rows]
    distinct = lambda entries: len({item["application_id"] for item in entries})
    dashboard_user = db.scalar(select(User).options(joinedload(User.department)).where(User.id == user.id))
    return {
        "department": dashboard_user.department.name if dashboard_user and dashboard_user.department else "All departments",
        "pending_applications": distinct([item for item in items if item["approval_status"] == ApprovalStatus.PENDING.value]),
        "in_review": distinct([item for item in items if item["approval_status"] == ApprovalStatus.IN_REVIEW.value]),
        "high_risk": distinct([item for item in items if item["risk_tier"] == "HIGH"]),
        "sla_breached": distinct([item for item in items if item["sla_status"] == "BREACHED"]),
        "action_required": distinct([item for item in items if item["application_status"] == ApplicationStatus.ACTION_REQUIRED.value or item["approval_status"] in {
            ApprovalStatus.DOCUMENT_CORRECTION.value, ApprovalStatus.INSPECTION_REQUIRED.value, ApprovalStatus.ESCALATED.value,
        }]),
        "active_queue": len(items),
    }


@router.get("/queue")
def officer_queue(
    db: Database,
    search: str | None = Query(default=None, max_length=160),
    status: str | None = Query(default=None, pattern="^(PENDING|IN_REVIEW|DOCUMENT_CORRECTION|INSPECTION_REQUIRED|ESCALATED|NOT_STARTED)$"),
    risk: str | None = Query(default=None, pattern="^(LOW|MEDIUM|HIGH)$"),
    sla: Literal["ALL", "BREACHED", "ON_TRACK", "BLOCKED", "CLOSED"] = "ALL",
    sort_by: Literal["SUBMITTED", "RISK", "SLA", "COMPANY", "STATUS"] = "SUBMITTED",
    sort_order: Literal["ASC", "DESC"] = "DESC",
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return _list_queue(db, search=search, status=status, risk=risk, sla=sla,
                       sort_by=sort_by, sort_order=sort_order, limit=limit, offset=offset)


def _load_review(db: Session, approval_id: int) -> ApplicationApproval:
    approval = db.scalar(select(ApplicationApproval).options(
        joinedload(ApplicationApproval.application).joinedload(Application.owner),
        joinedload(ApplicationApproval.application).selectinload(Application.documents),
        joinedload(ApplicationApproval.application).selectinload(Application.approvals),
        joinedload(ApplicationApproval.application).selectinload(Application.risk_assessments),
        selectinload(ApplicationApproval.audit_events).joinedload(WorkflowAuditEvent.actor),
        selectinload(ApplicationApproval.inspections).joinedload(Inspection.scheduled_by),
    ).where(ApplicationApproval.id == approval_id))
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval record not found")
    if not approval.is_required:
        raise HTTPException(status_code=404, detail="Required approval record not found")
    return approval


@router.get("/approvals/{approval_id}")
def get_review(approval_id: int, db: Database) -> dict:
    approval = _load_review(db, approval_id)
    application = approval.application
    issues = db.scalars(select(ApplicationValidationIssue).where(
        ApplicationValidationIssue.application_id == application.id
    ).order_by(ApplicationValidationIssue.id)).all()
    latest_risk = db.scalar(select(RiskAssessment).where(
        RiskAssessment.application_id == application.id
    ).order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc()).limit(1))
    events = db.scalars(select(WorkflowAuditEvent).options(
        joinedload(WorkflowAuditEvent.actor)
    ).where(WorkflowAuditEvent.application_id == application.id).order_by(
        WorkflowAuditEvent.created_at, WorkflowAuditEvent.id
    )).all()
    inspections = db.scalars(select(Inspection).options(
        joinedload(Inspection.scheduled_by)
    ).where(Inspection.application_id == application.id).order_by(Inspection.scheduled_at)).all()
    return {
        "approval": {
            "id": approval.id, "department_code": approval.department_code,
            "department_name": approval.department_name, "status": approval.status,
            "dependencies": approval.depends_on, "decision_message": approval.decision_message,
            "sla": _sla_data(approval),
        },
        "applicant": {
            "name": application.applicant_name or application.owner.full_name,
            "email": application.applicant_email or application.owner.email,
            "phone": application.applicant_phone,
        },
        "application": {
            "id": application.id, "application_number": application.application_number,
            "status": application.status, "company_name": application.company_name,
            "industry_type": application.industry_type, "project_type": application.project_type,
            "project_description": application.project_description,
            "investment_amount": application.investment_amount,
            "number_of_employees": application.number_of_employees,
            "built_up_area": application.built_up_area,
            "power_requirement": application.power_requirement,
            "water_requirement": application.water_requirement,
            "project_location": application.project_location, "land_details": application.land_details,
            "midc_area": application.midc_area, "midc_area_name": application.midc_area_name,
            "pan": application.pan, "gstin": application.gstin, "cin": application.cin,
            "udyam_number": application.udyam_number,
            "pollution_category": application.pollution_category,
            "hazardous_materials": application.hazardous_materials,
            "hazardous_materials_details": application.hazardous_materials_details,
            "factory_information": application.factory_information,
            "fire_safety_information": application.fire_safety_information,
            "submitted_at": application.submitted_at,
        },
        "risk_assessment": ({
            **latest_risk.assessment_data,
            "risk_score": latest_risk.risk_score,
            "risk_tier": latest_risk.risk_tier,
            "assessed_at": latest_risk.created_at,
        } if latest_risk else {"risk_tier": application.risk_tier, "assessment": None}),
        "documents": [{
            "id": item.id, "document_type": item.document_type, "file_name": item.file_name,
            "media_type": item.media_type, "size_bytes": item.size_bytes, "status": item.status,
            "uploaded_at": item.uploaded_at, "ocr_text": (item.extracted_text or "")[:12000],
            "ocr_fields": item.extracted_fields or {},
        } for item in application.documents],
        "prevalidation": prevalidation_payload(application, issues),
        "other_department_statuses": [{
            "department_code": row.department_code, "department_name": row.department_name,
            "is_required": row.is_required, "status": row.status,
            "decision_message": row.decision_message,
        } for row in sorted(application.approvals, key=lambda item: item.id)],
        "previous_remarks": [{
            "id": event.id, "message": event.message,
            "author": event.actor.full_name if event.actor else "Unknown officer",
            "created_at": event.created_at,
        } for event in events if event.action == "REMARK_ADDED"],
        "inspections": [_inspection_payload(item) for item in inspections],
        "audit_history": [{
            "id": event.id, "action": event.action, "from_status": event.from_status,
            "to_status": event.to_status, "message": event.message,
            "actor": event.actor.full_name if event.actor else "System",
            "created_at": event.created_at, "details": event.details,
        } for event in events],
    }


def _inspection_payload(item: Inspection) -> dict:
    return {
        "id": item.id, "application_id": item.application_id,
        "approval_id": item.approval_id, "application_number": item.application.application_number,
        "department_name": item.approval.department_name, "inspection_type": item.inspection_type,
        "status": item.status, "scheduled_at": item.scheduled_at, "location": item.location,
        "instructions": item.instructions,
        "scheduled_by": item.scheduled_by.full_name if item.scheduled_by else None,
    }


@router.post("/approvals/{approval_id}/remarks", status_code=201)
def add_remark(approval_id: int, payload: OfficerRemarkRequest, user: CurrentUser, db: Database) -> dict:
    approval = _load_review(db, approval_id)
    event = WorkflowAuditEvent(
        application_id=approval.application_id,
        approval_id=approval.id,
        actor_user_id=user.id,
        action="REMARK_ADDED",
        message=payload.message,
        details={"visibility": "OFFICER"},
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"id": event.id, "message": event.message, "created_at": event.created_at}


@router.post("/approvals/{approval_id}/inspections", status_code=201)
def schedule_inspection(approval_id: int, payload: InspectionScheduleRequest, user: CurrentUser, db: Database) -> dict:
    approval = _load_review(db, approval_id)
    if approval.status != ApprovalStatus.IN_REVIEW.value:
        raise HTTPException(status_code=409, detail="Start review before scheduling an inspection")
    inspection = Inspection(
        application_id=approval.application_id,
        approval_id=approval.id,
        inspection_type=payload.inspection_type,
        scheduled_at=payload.scheduled_at,
        location=payload.location,
        instructions=payload.instructions,
        scheduled_by_user_id=user.id,
    )
    db.add(inspection)
    db.flush()
    previous = approval.status
    approval.status = ApprovalStatus.INSPECTION_REQUIRED.value
    approval.decision_message = payload.instructions or f"{payload.inspection_type.title()} inspection scheduled."
    approval.updated_at = datetime.now(UTC)
    db.add(WorkflowAuditEvent(
        application_id=approval.application_id,
        approval_id=approval.id,
        actor_user_id=user.id,
        action="INSPECTION_SCHEDULED",
        from_status=previous,
        to_status=approval.status,
        message=approval.decision_message,
        details={"inspection_id": inspection.id, "inspection_type": inspection.inspection_type,
                 "scheduled_at": inspection.scheduled_at.isoformat(), "location": inspection.location},
    ))
    db.commit()
    db.refresh(inspection)
    return _inspection_payload(inspection)


@router.get("/inspections")
def list_inspections(
    db: Database,
    inspection_type: Literal["SINGLE", "JOINT"] | None = None,
    status: Literal["SCHEDULED", "COMPLETED", "CANCELLED"] | None = None,
) -> dict:
    statement = select(Inspection).options(
        joinedload(Inspection.application), joinedload(Inspection.approval), joinedload(Inspection.scheduled_by)
    )
    if inspection_type:
        statement = statement.where(Inspection.inspection_type == inspection_type)
    if status:
        statement = statement.where(Inspection.status == status)
    rows = db.scalars(statement.order_by(Inspection.scheduled_at)).all()
    return {"total": len(rows), "items": [_inspection_payload(item) for item in rows]}


@router.get("/documents")
def officer_documents(
    db: Database,
    search: str | None = Query(default=None, max_length=160),
    status: str | None = Query(default=None, max_length=24),
) -> dict:
    statement = select(ApplicationDocument).join(Application).options(
        joinedload(ApplicationDocument.application).selectinload(Application.approvals)
    ).where(
        Application.status.notin_([ApplicationStatus.DRAFT.value])
    )
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(or_(Application.application_number.ilike(term),
                                        Application.company_name.ilike(term),
                                        ApplicationDocument.file_name.ilike(term)))
    if status:
        statement = statement.where(ApplicationDocument.status == status)
    rows = db.scalars(statement.order_by(ApplicationDocument.uploaded_at.desc()).limit(500)).unique().all()
    return {"total": len(rows), "items": [{
        "id": item.id, "application_id": item.application_id,
        "approval_id": next((approval.id for approval in item.application.approvals if approval.is_required), None),
        "application_number": item.application.application_number,
        "company_name": item.application.company_name, "document_type": item.document_type,
        "file_name": item.file_name, "status": item.status,
        "media_type": item.media_type, "size_bytes": item.size_bytes,
        "uploaded_at": item.uploaded_at,
    } for item in rows]}


@router.get("/reports")
def officer_reports(user: CurrentUser, db: Database) -> dict:
    rows = db.scalars(_approval_query()).unique().all()
    items = [_queue_item(row) for row in rows]
    status_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for item in items:
        status_counts[item["approval_status"]] = status_counts.get(item["approval_status"], 0) + 1
        risk = item["risk_tier"] or "UNASSESSED"
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
    return {"total_active_approvals": len(items), "by_status": status_counts, "by_risk": risk_counts,
            "sla_breached": sum(1 for item in items if item["sla_status"] == "BREACHED")}


@router.get("/profile")
def officer_profile(user: CurrentUser, db: Database) -> dict:
    profile = db.scalar(select(User).options(joinedload(User.department), joinedload(User.company)).where(User.id == user.id))
    return {"id": user.id, "name": user.full_name, "email": user.email,
            "role": user.role.code, "department": profile.department.name if profile and profile.department else None,
            "company": profile.company.name if profile and profile.company else None}
