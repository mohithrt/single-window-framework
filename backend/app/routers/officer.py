from datetime import UTC, datetime
import hashlib
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.critical_path_service import CriticalPathService
from app.database import get_db
from app.core.config import settings
from app.dependencies import CurrentUser, require_roles
from app.models import (
    Application, ApplicationApproval, ApplicationDocument, ApplicationStatus,
    ApplicationValidationIssue, ApprovalStatus, Inspection, InspectionParticipant,
    JointInspection, Notification, RiskAssessment, Role, RoleCode, User, WorkflowAuditEvent,
)
from app.inspection_schemas import InspectionUpdateRequest, JointInspectionCreate, JointInspectionUpdateRequest
from app.officer_schemas import InspectionScheduleRequest, OfficerRemarkRequest
from app.notification_service import notify_applicant, notify_staff
from app.prevalidation import prevalidation_payload
from app.sla_service import SlaService, utc

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
sla_service = SlaService()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _sla_data(approval: ApplicationApproval, now: datetime | None = None) -> dict:
    data = sla_service.payload(approval, now)
    remaining = data["remaining_seconds"]
    return {**data, "sla_status": data["status"], "sla_due_at": data["expected_completion"],
            "sla_days": data["duration_days"],
            "days_overdue": 0 if remaining is None or remaining >= 0 else ((-remaining) + 86399) // 86400}


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
        "sla_breached": distinct([item for item in items if item["sla_status"] in {"BREACHED", "ESCALATED"}]),
        "sla_warning": distinct([item for item in items if item["sla_status"] == "WARNING"]),
        "escalated": distinct([item for item in items if item["approval_status"] == ApprovalStatus.ESCALATED.value]),
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
    sla: Literal["ALL", "BREACHED", "WARNING", "ESCALATED", "ON_TRACK", "BLOCKED", "CLOSED"] = "ALL",
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
def get_review(approval_id: int, user: CurrentUser, db: Database) -> dict:
    approval = _load_review(db, approval_id)
    application = approval.application
    db.add(WorkflowAuditEvent(
        application_id=application.id, approval_id=approval.id,
        actor_user_id=user.id, department_code=approval.department_code,
        action="OFFICER_OPENED_APPLICATION", details={"approval_id": approval.id},
    ))
    db.commit()
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
            "author": "System" if (event.details or {}).get("system_actor") else event.actor.full_name if event.actor else "System",
            "created_at": event.created_at,
        } for event in events if event.action == "REMARK_ADDED"],
        "inspections": [_inspection_payload(item) for item in inspections],
        "audit_history": [{
            "id": event.id, "action": event.action, "from_status": event.from_status,
            "to_status": event.to_status, "message": event.message,
            "actor": "System" if (event.details or {}).get("system_actor") else event.actor.full_name if event.actor else "System",
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
        "site": item.site or item.location, "checklist": item.checklist or [],
        "findings": item.findings, "photos": item.photos or [],
        "remarks": item.remarks, "recommendation": item.recommendation,
        "scheduled_by": item.scheduled_by.full_name if item.scheduled_by else None,
    }


def _joint_payload(item: JointInspection) -> dict:
    participants = [{
        "participant_id": participant.id, "approval_id": participant.approval_id,
        "department_code": participant.approval.department_code,
        "department_name": participant.approval.department_name,
        "officer_id": participant.officer_user_id,
        "officer": participant.officer.full_name if participant.officer else None,
        "status": participant.status,
    } for participant in item.participants]
    return {
        "id": item.id, "application_id": item.application_id,
        "application_number": item.application.application_number,
        "department_name": "Joint inspection", "inspection_type": "JOINT",
        "approval_id": participants[0]["approval_id"] if participants else None,
        "approval_ids": [entry["approval_id"] for entry in participants],
        "scheduled_at": item.scheduled_at, "site": item.site, "location": item.site,
        "status": item.status, "instructions": item.instructions,
        "participants": participants, "checklist": item.checklist or [],
        "findings": item.findings, "photos": item.photos or [],
        "remarks": item.remarks, "recommendation": item.recommendation,
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
        department_code=approval.department_code,
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
        site=payload.location,
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
    notify_applicant(db, approval.application, "INSPECTION_SCHEDULED",
                     f"{approval.department_name} scheduled an inspection for {payload.scheduled_at:%d %B %Y %H:%M} at {payload.location}.")
    db.commit()
    db.refresh(inspection)
    return _inspection_payload(inspection)


@router.get("/inspections")
def list_inspections(
    db: Database,
    inspection_type: Literal["SINGLE", "JOINT"] | None = None,
    status: Literal["SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"] | None = None,
) -> dict:
    if inspection_type == "JOINT":
        statement = select(JointInspection).options(
            joinedload(JointInspection.application), joinedload(JointInspection.scheduled_by),
            selectinload(JointInspection.participants).joinedload(InspectionParticipant.approval),
            selectinload(JointInspection.participants).joinedload(InspectionParticipant.officer),
        )
        if status:
            statement = statement.where(JointInspection.status == status)
        rows = db.scalars(statement.order_by(JointInspection.scheduled_at)).unique().all()
        return {"total": len(rows), "items": [_joint_payload(item) for item in rows]}
    statement = select(Inspection).options(
        joinedload(Inspection.application), joinedload(Inspection.approval), joinedload(Inspection.scheduled_by)
    )
    if inspection_type:
        statement = statement.where(Inspection.inspection_type == inspection_type)
    if status:
        statement = statement.where(Inspection.status == status)
    rows = db.scalars(statement.order_by(Inspection.scheduled_at)).all()
    return {"total": len(rows), "items": [_inspection_payload(item) for item in rows]}


@router.post("/joint-inspections", status_code=201)
def schedule_joint_inspection(payload: JointInspectionCreate, user: CurrentUser, db: Database) -> dict:
    application = db.get(Application, payload.application_id)
    if application is None or application.status == ApplicationStatus.DRAFT.value:
        raise HTTPException(status_code=404, detail="Submitted application not found")
    approvals = db.scalars(select(ApplicationApproval).where(
        ApplicationApproval.id.in_(payload.approval_ids),
        ApplicationApproval.application_id == application.id,
        ApplicationApproval.is_required.is_(True),
    )).all()
    if len(approvals) != len(payload.approval_ids):
        raise HTTPException(status_code=422, detail="Select required departments on this application")
    if not set(payload.officer_assignments).issubset(set(payload.approval_ids)):
        raise HTTPException(status_code=422, detail="Officer assignments must match participating departments")
    for approval in approvals:
        if approval.status not in {ApprovalStatus.INSPECTION_REQUIRED.value, ApprovalStatus.IN_REVIEW.value,
                                   ApprovalStatus.PENDING.value, ApprovalStatus.ESCALATED.value}:
            raise HTTPException(status_code=409, detail=f"{approval.department_name} is not ready for inspection")
    officers = {}
    if payload.officer_assignments:
        officers = {row.id: row for row in db.scalars(select(User).options(
            joinedload(User.role), joinedload(User.department),
        ).where(
            User.id.in_(set(payload.officer_assignments.values()))
        )).all()}
        if set(officers) != set(payload.officer_assignments.values()) or any(
            officer.role.code != RoleCode.OFFICER.value for officer in officers.values()
        ):
            raise HTTPException(status_code=422, detail="Assigned inspection participants must be officer accounts")
        approval_by_id = {approval.id: approval for approval in approvals}
        if any(
            officers[officer_id].department is not None
            and officers[officer_id].department.code != approval_by_id[approval_id].department_code
            for approval_id, officer_id in payload.officer_assignments.items()
        ):
            raise HTTPException(status_code=422, detail="Assigned officers must belong to the participating department")
    joint = JointInspection(
        application_id=application.id, scheduled_at=payload.scheduled_at,
        site=payload.site, instructions=payload.instructions,
        checklist=payload.checklist, scheduled_by_user_id=user.id,
    )
    db.add(joint)
    db.flush()
    for approval in approvals:
        prior = approval.status
        approval.status = ApprovalStatus.INSPECTION_REQUIRED.value
        approval.decision_message = payload.instructions or "Participate in the scheduled joint inspection."
        if approval.assigned_reviewer_id is None:
            approval.assigned_reviewer_id = payload.officer_assignments.get(approval.id)
        db.add(InspectionParticipant(
            joint_inspection_id=joint.id, approval_id=approval.id,
            officer_user_id=payload.officer_assignments.get(approval.id), status="INVITED",
        ))
        db.add(WorkflowAuditEvent(
            application_id=application.id, approval_id=approval.id,
            actor_user_id=user.id, department_code=approval.department_code,
            action="JOINT_INSPECTION_SCHEDULED", from_status=prior,
            to_status=approval.status, message=payload.instructions or "Joint inspection scheduled.",
            details={"joint_inspection_id": joint.id, "scheduled_at": payload.scheduled_at.isoformat(),
                     "site": payload.site},
        ))
    notify_applicant(db, application, "JOINT_INSPECTION_SCHEDULED",
                     f"A joint inspection is scheduled for {payload.scheduled_at:%d %B %Y %H:%M} at {payload.site}.")
    db.commit()
    result = db.scalar(select(JointInspection).options(
        joinedload(JointInspection.application), joinedload(JointInspection.scheduled_by),
        selectinload(JointInspection.participants).joinedload(InspectionParticipant.approval),
        selectinload(JointInspection.participants).joinedload(InspectionParticipant.officer),
    ).where(JointInspection.id == joint.id))
    return _joint_payload(result)


@router.get("/inspection-officers")
def inspection_officers(db: Database) -> dict:
    officers = db.scalars(select(User).join(User.role).options(
        joinedload(User.department),
    ).where(Role.code == RoleCode.OFFICER.value, User.is_active.is_(True)).order_by(User.full_name)).all()
    return {"items": [{"id": officer.id, "name": officer.full_name,
                        "department_code": officer.department.code if officer.department else None,
                        "department_name": officer.department.name if officer.department else None}
                       for officer in officers]}


def _save_photos(photo_owner: Inspection | JointInspection, files: list[UploadFile], user: User) -> list[dict]:
    if not files or len(files) > 10:
        raise HTTPException(status_code=422, detail="Upload between 1 and 10 inspection photos")
    root = Path(settings.upload_dir).resolve()
    folder = root / "inspections"
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[dict] = []
    for file in files:
        content = file.file.read(10 * 1024 * 1024 + 1)
        content_type = file.content_type or ""
        signatures = {"image/jpeg": content.startswith(b"\xff\xd8\xff"),
                      "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
                      "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP"}
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Each inspection photo must be 10 MB or smaller")
        if not signatures.get(content_type):
            raise HTTPException(status_code=415, detail="Inspection photos must be JPEG, PNG, or WebP images")
        extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
        key = f"inspections/{uuid4().hex}{extension}"
        path = (root / key).resolve()
        if not path.is_relative_to(root):
            raise HTTPException(status_code=400, detail="Invalid photo path")
        path.write_bytes(content)
        saved.append({"storage_key": key, "file_name": Path(file.filename or f"photo{extension}").name,
                      "media_type": content_type, "size_bytes": len(content),
                      "sha256": hashlib.sha256(content).hexdigest(), "uploaded_by": user.full_name})
    photo_owner.photos = [*(photo_owner.photos or []), *saved]
    return saved


@router.get("/inspections/{inspection_id}")
def get_inspection(inspection_id: int, db: Database) -> dict:
    item = db.scalar(select(Inspection).options(
        joinedload(Inspection.application), joinedload(Inspection.approval),
        joinedload(Inspection.scheduled_by),
    ).where(Inspection.id == inspection_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return _inspection_payload(item)


@router.patch("/inspections/{inspection_id}")
def update_inspection(inspection_id: int, payload: InspectionUpdateRequest, user: CurrentUser, db: Database) -> dict:
    item = db.scalar(select(Inspection).options(joinedload(Inspection.application), joinedload(Inspection.approval),
                       joinedload(Inspection.scheduled_by)).where(Inspection.id == inspection_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    previous = item.status
    _check_inspection_transition(previous, payload.status)
    completing = payload.status == "COMPLETED" and previous != "COMPLETED"
    for name, value in payload.model_dump(exclude_unset=True).items():
        if name == "status" and value == "COMPLETED" and not (payload.recommendation or item.recommendation):
            raise HTTPException(status_code=422, detail="Add a recommendation before completing the inspection")
        setattr(item, name, value)
    item.updated_by_user_id = user.id
    if payload.status == "IN_PROGRESS":
        item.approval.status = ApprovalStatus.INSPECTION_REQUIRED.value
    action = "INSPECTION_COMPLETED" if completing else "INSPECTION_UPDATED"
    if completing and item.approval.status == ApprovalStatus.INSPECTION_REQUIRED.value:
        item.approval.status = ApprovalStatus.IN_REVIEW.value
        item.approval.decision_message = item.recommendation
    db.add(WorkflowAuditEvent(
        application_id=item.application_id, approval_id=item.approval_id,
        actor_user_id=user.id, department_code=item.approval.department_code,
        action=action, from_status=previous, to_status=item.status,
        message=item.recommendation or item.remarks or item.findings,
        details={"inspection_id": item.id, "inspection_type": "SINGLE",
                 "approval_status": item.approval.status},
    ))
    if completing:
        notify_applicant(db, item.application, "INSPECTION_COMPLETED",
                         f"The {item.approval.department_name} site inspection is complete. Recommendation: {item.recommendation}")
    db.commit()
    db.refresh(item)
    return _inspection_payload(item)


@router.post("/inspections/{inspection_id}/photos", status_code=201)
def upload_inspection_photos(inspection_id: int, user: CurrentUser, db: Database,
                             files: Annotated[list[UploadFile], File()]) -> dict:
    item = db.get(Inspection, inspection_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    saved = _save_photos(item, files, user)
    item.updated_by_user_id = user.id
    approval = db.get(ApplicationApproval, item.approval_id)
    db.add(WorkflowAuditEvent(application_id=item.application_id, approval_id=item.approval_id,
        actor_user_id=user.id, department_code=approval.department_code,
        action="INSPECTION_PHOTOS_UPLOADED", details={"inspection_id": item.id, "photo_count": len(saved)}))
    db.commit()
    return {"uploaded": len(saved), "photos": saved}


@router.get("/inspections/{inspection_id}/photos/{photo_index}")
def download_inspection_photo(inspection_id: int, photo_index: int, db: Database) -> FileResponse:
    item = db.get(Inspection, inspection_id)
    if item is None or photo_index < 0 or photo_index >= len(item.photos or []):
        raise HTTPException(status_code=404, detail="Inspection photo not found")
    photo = item.photos[photo_index]
    root = Path(settings.upload_dir).resolve()
    path = (root / photo["storage_key"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Inspection photo not found")
    return FileResponse(path, media_type=photo["media_type"], filename=photo["file_name"])


@router.get("/joint-inspections/{joint_id}")
def get_joint_inspection(joint_id: int, db: Database) -> dict:
    item = db.scalar(select(JointInspection).options(
        joinedload(JointInspection.application), joinedload(JointInspection.scheduled_by),
        selectinload(JointInspection.participants).joinedload(InspectionParticipant.approval),
        selectinload(JointInspection.participants).joinedload(InspectionParticipant.officer),
    ).where(JointInspection.id == joint_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Joint inspection not found")
    return _joint_payload(item)


@router.patch("/joint-inspections/{joint_id}")
def update_joint_inspection(joint_id: int, payload: JointInspectionUpdateRequest,
                            user: CurrentUser, db: Database) -> dict:
    item = db.scalar(select(JointInspection).options(
        joinedload(JointInspection.application), joinedload(JointInspection.scheduled_by),
        selectinload(JointInspection.participants).joinedload(InspectionParticipant.approval),
        selectinload(JointInspection.participants).joinedload(InspectionParticipant.officer),
    ).where(JointInspection.id == joint_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Joint inspection not found")
    previous = item.status
    _check_inspection_transition(previous, payload.status)
    completing = payload.status == "COMPLETED" and previous != "COMPLETED"
    for name, value in payload.model_dump(exclude_unset=True).items():
        if name == "status" and value == "COMPLETED" and not (payload.recommendation or item.recommendation):
            raise HTTPException(status_code=422, detail="Add a final recommendation before completing the joint inspection")
        setattr(item, name, value)
    item.updated_by_user_id = user.id
    if payload.status == "IN_PROGRESS" and previous != "IN_PROGRESS":
        for participant in item.participants:
            participant.status = "IN_PROGRESS"
    if completing:
        for participant in item.participants:
            participant.status = "COMPLETED"
            approval = participant.approval
            old_status = approval.status
            if old_status == ApprovalStatus.INSPECTION_REQUIRED.value:
                approval.status = ApprovalStatus.IN_REVIEW.value
                approval.decision_message = item.recommendation
            db.add(WorkflowAuditEvent(
                application_id=item.application_id, approval_id=approval.id,
                actor_user_id=user.id, department_code=approval.department_code,
                action="INSPECTION_COMPLETED", from_status=old_status,
                to_status=approval.status, message=item.recommendation,
                details={"joint_inspection_id": item.id, "site": item.site},
            ))
        notify_applicant(db, item.application, "INSPECTION_COMPLETED",
                         f"The joint site inspection is complete. Recommendation: {item.recommendation}")
    elif payload.status is not None or payload.model_fields_set - {"status"}:
        for participant in item.participants:
            db.add(WorkflowAuditEvent(
                application_id=item.application_id, approval_id=participant.approval_id,
                actor_user_id=user.id, department_code=participant.approval.department_code,
                action="JOINT_INSPECTION_UPDATED", from_status=previous, to_status=item.status,
                message=item.remarks or item.findings,
                details={"joint_inspection_id": item.id, "site": item.site},
            ))
    db.commit()
    return _joint_payload(item)


def _check_inspection_transition(previous: str, target: str | None) -> None:
    if target is None or target == previous:
        return
    allowed = {
        "SCHEDULED": {"IN_PROGRESS", "CANCELLED"},
        "IN_PROGRESS": {"COMPLETED", "CANCELLED"},
        "COMPLETED": set(), "CANCELLED": set(),
    }
    if target not in allowed.get(previous, set()):
        raise HTTPException(status_code=409, detail=f"Cannot change an inspection from {previous} to {target}")


@router.post("/joint-inspections/{joint_id}/photos", status_code=201)
def upload_joint_inspection_photos(joint_id: int, user: CurrentUser, db: Database,
                                   files: Annotated[list[UploadFile], File()]) -> dict:
    item = db.get(JointInspection, joint_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Joint inspection not found")
    saved = _save_photos(item, files, user)
    item.updated_by_user_id = user.id
    for participant in item.participants:
        db.add(WorkflowAuditEvent(application_id=item.application_id, approval_id=participant.approval_id,
            actor_user_id=user.id, department_code=participant.approval.department_code,
            action="INSPECTION_PHOTOS_UPLOADED", details={"joint_inspection_id": item.id, "photo_count": len(saved)}))
    db.commit()
    return {"uploaded": len(saved), "photos": saved}


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
            "sla_breached": sum(1 for item in items if item["sla_status"] in {"BREACHED", "ESCALATED"}),
            "sla_warning": sum(1 for item in items if item["sla_status"] == "WARNING"),
            "escalated": sum(1 for item in items if item["approval_status"] == ApprovalStatus.ESCALATED.value)}


@router.get("/profile")
def officer_profile(user: CurrentUser, db: Database) -> dict:
    profile = db.scalar(select(User).options(joinedload(User.department), joinedload(User.company)).where(User.id == user.id))
    return {"id": user.id, "name": user.full_name, "email": user.email,
            "role": user.role.code, "department": profile.department.name if profile and profile.department else None,
            "company": profile.company.name if profile and profile.company else None}
