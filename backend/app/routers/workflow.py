from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.critical_path_service import CriticalPathService
from app.models import (
    Application, ApplicationApproval, ApplicationStatus, ApprovalStatus, RoleCode,
    User, WorkflowAuditEvent,
)
from app.workflow_schemas import CorrectionRequest, RejectionRequest
from app.workflow_service import WorkflowService
from app.notification_service import notify_applicant, notify_staff
from app.sla_service import SlaService

applicant_router = APIRouter(prefix="/applications", tags=["approval workflow"])
approval_router = APIRouter(prefix="/approvals", tags=["approval workflow"])
Database = Annotated[Session, Depends(get_db)]
OfficerUser = Annotated[User, Depends(require_roles(RoleCode.OFFICER, RoleCode.ADMIN))]
workflow = WorkflowService()
critical_path = CriticalPathService()


def _application(db: Session, application_id: int) -> Application:
    application = db.scalar(select(Application).options(
        selectinload(Application.approvals),
        selectinload(Application.workflow_events).joinedload(WorkflowAuditEvent.actor),
    ).where(Application.id == application_id))
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


def _approval(db: Session, approval_id: int) -> ApplicationApproval:
    approval = db.scalar(select(ApplicationApproval).options(
        joinedload(ApplicationApproval.application).selectinload(Application.approvals)
    ).where(ApplicationApproval.id == approval_id))
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval record not found")
    return approval


def _transition(db: Session, approval: ApplicationApproval, actor_id: int,
                new_status: ApprovalStatus, action: str, message: str | None = None) -> None:
    previous = approval.status
    approval.status = new_status.value
    approval.decision_message = message
    approval.updated_at = datetime.now(UTC)
    if new_status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}:
        approval.decided_at = datetime.now(UTC)
    WorkflowService.record_event(db, approval, actor_id, action, previous, new_status.value, message)


def _refresh_application_status(db: Session, application: Application) -> None:
    required = [approval for approval in application.approvals if approval.is_required]
    if any(approval.status == ApprovalStatus.REJECTED.value for approval in required):
        application.status = ApplicationStatus.REJECTED.value
    elif any(approval.status == ApprovalStatus.DOCUMENT_CORRECTION.value for approval in required):
        application.status = ApplicationStatus.ACTION_REQUIRED.value
    elif required and all(approval.status == ApprovalStatus.APPROVED.value for approval in required):
        application.status = ApplicationStatus.APPROVED.value
    else:
        application.status = ApplicationStatus.IN_REVIEW.value


def _activate_ready(db: Session, application: Application, actor_id: int) -> None:
    states = {approval.department_code: approval.status for approval in application.approvals}
    changed = True
    while changed:
        changed = False
        for approval in application.approvals:
            if approval.is_required and approval.status == ApprovalStatus.NOT_STARTED.value and all(
                states.get(dependency) == ApprovalStatus.APPROVED.value for dependency in approval.depends_on
            ):
                _transition(db, approval, actor_id, ApprovalStatus.PENDING, "APPROVAL_ACTIVATED")
                SlaService().prime(approval)
                states[approval.department_code] = ApprovalStatus.PENDING.value
                changed = True


def _serialize(application: Application) -> dict:
    approvals = sorted(application.approvals, key=lambda item: item.id)
    events = sorted(application.workflow_events, key=lambda item: (item.created_at, item.id))
    return {
        "application_id": application.id,
        "application_number": application.application_number,
        "application_status": application.status,
        "initialized": bool(approvals),
        "approvals": [{
            "id": item.id, "department_code": item.department_code,
            "department_name": item.department_name, "is_required": item.is_required,
            "status": item.status, "depends_on": item.depends_on,
            "decision_message": item.decision_message,
            "created_at": item.created_at, "updated_at": item.updated_at,
            "decided_at": item.decided_at,
        } for item in approvals],
        "audit_events": [{
            "id": event.id, "approval_id": event.approval_id,
            "actor_name": "System" if (event.details or {}).get("system_actor") else event.actor.full_name if event.actor else "System",
            "action": event.action, "from_status": event.from_status,
            "to_status": event.to_status, "message": event.message,
            "details": event.details, "created_at": event.created_at,
        } for event in events if (event.details or {}).get("visibility") != "OFFICER"],
    }


@applicant_router.get("/{application_id}/approvals")
def get_application_approvals(application_id: int, user: CurrentUser, db: Database) -> dict:
    application = _application(db, application_id)
    if user.role.code == RoleCode.APPLICANT.value and application.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.status == ApplicationStatus.DRAFT.value:
        return _serialize(application)
    if not application.approvals:
        workflow.initialize(db, application, user.id)
        db.commit()
        db.expire(application, ["approvals", "workflow_events"])
        application = _application(db, application_id)
    return _serialize(application)


@applicant_router.get("/{application_id}/critical-path")
def get_critical_path(application_id: int, user: CurrentUser, db: Database) -> dict:
    application = _application(db, application_id)
    if user.role.code == RoleCode.APPLICANT.value and application.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.status == ApplicationStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="Critical path is available after application submission")
    if not application.approvals:
        workflow.initialize(db, application, user.id)
        db.commit()
        db.expire(application, ["approvals", "workflow_events"])
        application = _application(db, application_id)
    try:
        return critical_path.calculate(application, application.approvals, application.workflow_events)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Unable to calculate the approval schedule: {exc}") from exc


@approval_router.post("/{approval_id}/start-review")
def start_review(approval_id: int, user: OfficerUser, db: Database) -> dict:
    approval = _approval(db, approval_id)
    if not approval.is_required:
        raise HTTPException(status_code=409, detail="This department is not required")
    if any(next((x.status for x in approval.application.approvals if x.department_code == dep), None) != ApprovalStatus.APPROVED.value for dep in approval.depends_on):
        raise HTTPException(status_code=409, detail="Required department dependencies are not approved")
    if approval.status not in {ApprovalStatus.PENDING.value, ApprovalStatus.INSPECTION_REQUIRED.value, ApprovalStatus.ESCALATED.value}:
        raise HTTPException(status_code=409, detail=f"Cannot start review from {approval.status}")
    approval.assigned_reviewer_id = user.id
    SlaService().prime(approval)
    _transition(db, approval, user.id, ApprovalStatus.IN_REVIEW, "REVIEW_STARTED")
    approval.application.status = ApplicationStatus.IN_REVIEW.value
    db.commit()
    return {"approval_id": approval.id, "status": approval.status}


@approval_router.post("/{approval_id}/approve")
def approve(approval_id: int, user: OfficerUser, db: Database) -> dict:
    approval = _approval(db, approval_id)
    if approval.status != ApprovalStatus.IN_REVIEW.value:
        raise HTTPException(status_code=409, detail="Approval must be in review before it can be approved")
    _transition(db, approval, user.id, ApprovalStatus.APPROVED, "APPROVED")
    notify_applicant(db, approval.application, "APPROVAL_GRANTED", f"Your {approval.department_name} application was approved.")
    _activate_ready(db, approval.application, user.id)
    _refresh_application_status(db, approval.application)
    db.commit()
    return {"approval_id": approval.id, "status": approval.status, "application_status": approval.application.status}


@approval_router.post("/{approval_id}/reject")
def reject(approval_id: int, payload: RejectionRequest, user: OfficerUser, db: Database) -> dict:
    approval = _approval(db, approval_id)
    if approval.status != ApprovalStatus.IN_REVIEW.value:
        raise HTTPException(status_code=409, detail="Approval must be in review before it can be rejected")
    _transition(db, approval, user.id, ApprovalStatus.REJECTED, "REJECTED", payload.reason)
    notify_applicant(db, approval.application, "APPROVAL_REJECTED", f"{approval.department_name} rejected the approval: {payload.reason}")
    _refresh_application_status(db, approval.application)
    db.commit()
    return {"approval_id": approval.id, "status": approval.status, "application_status": approval.application.status}


@approval_router.post("/{approval_id}/request-correction")
def request_correction(approval_id: int, payload: CorrectionRequest, user: OfficerUser, db: Database) -> dict:
    approval = _approval(db, approval_id)
    if approval.status != ApprovalStatus.IN_REVIEW.value:
        raise HTTPException(status_code=409, detail="Approval must be in review before requesting a correction")
    _transition(db, approval, user.id, ApprovalStatus.DOCUMENT_CORRECTION, "CORRECTION_REQUESTED", payload.message)
    notify_applicant(db, approval.application, "CORRECTION_REQUIRED", f"{approval.department_name} requested additional information: {payload.message}")
    _refresh_application_status(db, approval.application)
    db.commit()
    return {"approval_id": approval.id, "status": approval.status, "application_status": approval.application.status}


@approval_router.post("/{approval_id}/correction-submitted")
def correction_submitted(approval_id: int, user: CurrentUser, db: Database) -> dict:
    approval = _approval(db, approval_id)
    if approval.application.owner_user_id != user.id or user.role.code != RoleCode.APPLICANT.value:
        raise HTTPException(status_code=404, detail="Approval record not found")
    if approval.status != ApprovalStatus.DOCUMENT_CORRECTION.value:
        raise HTTPException(status_code=409, detail="This approval is not waiting for a correction")
    _transition(db, approval, user.id, ApprovalStatus.PENDING, "CORRECTION_SUBMITTED", "Applicant submitted the requested correction.")
    notify_staff(db, approval.application, "CORRECTION_SUBMITTED",
                 f"The applicant submitted a correction for {approval.department_name}.", approval.assigned_reviewer_id)
    _refresh_application_status(db, approval.application)
    db.commit()
    return {"approval_id": approval.id, "status": approval.status, "application_status": approval.application.status}


@approval_router.post("/{approval_id}/request-inspection")
def request_inspection(approval_id: int, payload: CorrectionRequest, user: OfficerUser, db: Database) -> dict:
    approval = _approval(db, approval_id)
    if approval.status != ApprovalStatus.IN_REVIEW.value:
        raise HTTPException(status_code=409, detail="Approval must be in review to require inspection")
    _transition(db, approval, user.id, ApprovalStatus.INSPECTION_REQUIRED, "INSPECTION_REQUIRED", payload.message)
    notify_applicant(db, approval.application, "INSPECTION_REQUIRED", f"{approval.department_name} requires a site inspection.")
    approval.application.status = ApplicationStatus.IN_REVIEW.value
    db.commit()
    return {"approval_id": approval.id, "status": approval.status}


@approval_router.post("/{approval_id}/escalate")
def escalate(approval_id: int, payload: CorrectionRequest, user: OfficerUser, db: Database) -> dict:
    approval = _approval(db, approval_id)
    if approval.status not in {ApprovalStatus.PENDING.value, ApprovalStatus.IN_REVIEW.value}:
        raise HTTPException(status_code=409, detail=f"Cannot escalate from {approval.status}")
    _transition(db, approval, user.id, ApprovalStatus.ESCALATED, "ESCALATED", payload.message)
    notify_applicant(db, approval.application, "APPLICATION_ESCALATED", f"Your application was escalated by {approval.department_name}.")
    approval.application.status = ApplicationStatus.IN_REVIEW.value
    db.commit()
    return {"approval_id": approval.id, "status": approval.status}
