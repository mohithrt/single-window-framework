from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.models import (
    Application, ApplicationApproval, ApplicationStatus,
    ApplicationValidationIssue, ApprovalStatus, Company, Department, Notification,
    RoleCode, User, WorkflowAuditEvent,
)

router = APIRouter(tags=["role dashboards"])


@router.get("/applicant/dashboard", dependencies=[Depends(require_roles(RoleCode.APPLICANT))])
def applicant_dashboard(user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, object]:
    """Return owner-scoped application state and the next useful action for each record."""
    applications = db.scalars(
        select(Application)
        .options(
            joinedload(Application.current_department),
            selectinload(Application.approvals),
        )
        .where(Application.owner_user_id == user.id)
        .order_by(Application.updated_at.desc(), Application.id.desc())
    ).all()
    app_ids = [application.id for application in applications]
    issues_by_app: dict[int, list[ApplicationValidationIssue]] = {}
    events_by_app: dict[int, list[WorkflowAuditEvent]] = {}
    if app_ids:
        for issue in db.scalars(select(ApplicationValidationIssue).where(
            ApplicationValidationIssue.application_id.in_(app_ids),
        ).order_by(ApplicationValidationIssue.id)).all():
            issues_by_app.setdefault(issue.application_id, []).append(issue)
        for event in db.scalars(select(WorkflowAuditEvent).where(
            WorkflowAuditEvent.application_id.in_(app_ids),
        ).order_by(WorkflowAuditEvent.created_at.desc(), WorkflowAuditEvent.id.desc())).all():
            # Mirror the applicant timeline's visibility boundary: officer-only
            # remarks must never appear in applicant dashboard summaries.
            if (event.details or {}).get("visibility") == "OFFICER":
                continue
            events_by_app.setdefault(event.application_id, []).append(event)

    now = datetime.now(UTC)
    active_statuses = {
        ApprovalStatus.PENDING.value, ApprovalStatus.IN_REVIEW.value,
        ApprovalStatus.DOCUMENT_CORRECTION.value, ApprovalStatus.INSPECTION_REQUIRED.value,
        ApprovalStatus.ESCALATED.value,
    }
    priority = {ApprovalStatus.DOCUMENT_CORRECTION.value: 0, ApprovalStatus.ESCALATED.value: 1,
                ApprovalStatus.IN_REVIEW.value: 2, ApprovalStatus.INSPECTION_REQUIRED.value: 3,
                ApprovalStatus.PENDING.value: 4}
    items = []
    for application in applications:
        required = [approval for approval in application.approvals if approval.is_required]
        active = sorted((approval for approval in required if approval.status in active_statuses),
                        key=lambda approval: (priority.get(approval.status, 9), approval.id))
        current = active[0] if active else None
        overdue = bool(current and current.sla_expected_completion and
                       current.sla_expected_completion.replace(tzinfo=current.sla_expected_completion.tzinfo or UTC) < now and
                       current.status not in {ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value})
        issues = issues_by_app.get(application.id, [])
        latest_event = (events_by_app.get(application.id) or [None])[0]
        missing = [issue for issue in issues if issue.status == "MISSING"]
        corrections = [approval for approval in active if approval.status == ApprovalStatus.DOCUMENT_CORRECTION.value]

        if application.status == ApplicationStatus.DRAFT.value:
            action_title, action_detail, action_href = "Complete your draft", "Add the remaining project details and required documents.", f"/applicant/applications/{application.id}/edit"
        elif application.status == ApplicationStatus.ACTION_REQUIRED.value:
            if corrections:
                action_title, action_detail, action_href = "Respond to a department correction", corrections[0].decision_message or "Review the officer's request and update the application or supporting documents.", f"/applicant/applications/{application.id}/edit?step=0"
            elif missing:
                action_title, action_detail, action_href = "Upload missing documents", "; ".join(dict.fromkeys(issue.message for issue in missing[:3])), f"/applicant/applications/{application.id}/prevalidation"
            else:
                action_title, action_detail, action_href = "Review requested information", "Check the application timeline for the latest request.", f"/applicant/applications/{application.id}/activity"
        elif application.status == ApplicationStatus.APPROVED.value:
            action_title, action_detail, action_href = "Clearance approved", "Your application has completed its approval workflow.", f"/applicant/applications/{application.id}/view"
        elif application.status == ApplicationStatus.REJECTED.value:
            action_title, action_detail, action_href = "Application decision issued", "Review the decision and department remarks.", f"/applicant/applications/{application.id}/approvals"
        elif overdue:
            action_title, action_detail, action_href = "Review is past its target date", f"{current.department_name} has passed its estimated completion date.", f"/applicant/applications/{application.id}/approvals"
        elif current and current.status == ApprovalStatus.INSPECTION_REQUIRED.value:
            action_title, action_detail, action_href = "Inspection is required", current.decision_message or "Check your inspection schedule and instructions.", f"/applicant/applications/{application.id}/activity"
        elif current:
            action_title, action_detail, action_href = "Department review in progress", f"{current.department_name} is {current.status.replace('_', ' ').lower()}.", f"/applicant/applications/{application.id}/approvals"
        else:
            action_title, action_detail, action_href = "Awaiting department assignment", "Your submitted application is waiting for its review workflow to begin.", f"/applicant/applications/{application.id}/approvals"

        items.append({
            "id": application.id, "application_number": application.application_number,
            "company_name": application.company_name, "industry_type": application.industry_type,
            "risk_tier": application.risk_tier, "status": application.status,
            "progress_percent": application.progress_percent,
            "expected_completion_at": application.expected_completion_at,
            "current_department_name": current.department_name if current else (
                application.current_department.name if application.current_department else None),
            "approval_status": current.status if current else None,
            "sla_expected_completion": current.sla_expected_completion if current else None,
            "sla_overdue": overdue,
            "approvals_total": len(required),
            "approvals_approved": sum(a.status == ApprovalStatus.APPROVED.value for a in required),
            "pending_departments": [a.department_name for a in active],
            "action_title": action_title, "action_detail": action_detail, "action_href": action_href,
            "latest_update": ({"action": latest_event.action, "message": latest_event.message,
                               "created_at": latest_event.created_at} if latest_event else None),
            "updated_at": application.updated_at,
        })
    status_counts = {}
    for item in items:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    unread_count = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read.is_(False),
    )) or 0
    urgent = next((item for item in items if item["status"] == ApplicationStatus.ACTION_REQUIRED.value or item["sla_overdue"]), None)
    focus = urgent or next((item for item in items if item["status"] in {
        ApplicationStatus.SUBMITTED.value, ApplicationStatus.IN_REVIEW.value,
    }), None)
    return {"area": "applicant", "applications": items,
            "summary": {"total": len(items), "status_counts": status_counts,
                        "active": sum(item["status"] in {ApplicationStatus.SUBMITTED.value,
                            ApplicationStatus.IN_REVIEW.value, ApplicationStatus.ACTION_REQUIRED.value} for item in items),
                        "unread_notifications": unread_count},
            "focus_application_id": focus["id"] if focus else None}


@router.get("/officer/department", dependencies=[Depends(require_roles(RoleCode.OFFICER))])
def officer_department(user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, object]:
    officer = db.scalar(
        select(User)
        .options(joinedload(User.department), joinedload(User.company))
        .where(User.id == user.id)
    )
    return {
        "area": "department",
        "department": officer.department.name if officer and officer.department else None,
        "company": officer.company.name if officer and officer.company else None,
    }


@router.get("/admin/overview", dependencies=[Depends(require_roles(RoleCode.ADMIN))])
def admin_overview(user: CurrentUser, db: Session = Depends(get_db)) -> dict[str, int | str]:
    escalated = db.scalar(select(func.count(ApplicationApproval.id)).where(
        ApplicationApproval.status == ApprovalStatus.ESCALATED.value,
    )) or 0
    return {
        "area": "government_administration",
        "user_count": db.scalar(select(func.count()).select_from(User)) or 0,
        "company_count": db.scalar(select(func.count()).select_from(Company)) or 0,
        "department_count": db.scalar(select(func.count()).select_from(Department)) or 0,
        "escalated_approvals": escalated,
    }


@router.get("/admin/escalations", dependencies=[Depends(require_roles(RoleCode.ADMIN))])
def admin_escalations(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(ApplicationApproval, Application).join(
        Application, ApplicationApproval.application_id == Application.id,
    ).where(ApplicationApproval.status == ApprovalStatus.ESCALATED.value).order_by(
        ApplicationApproval.escalated_at.desc(), ApplicationApproval.id.desc(),
    )).all()
    return {"total": len(rows), "items": [{
        "approval_id": approval.id, "application_id": application.id,
        "application_number": application.application_number,
        "company_name": application.company_name, "department_code": approval.department_code,
        "department_name": approval.department_name, "message": approval.decision_message,
        "escalated_at": approval.escalated_at,
    } for approval, application in rows]}
