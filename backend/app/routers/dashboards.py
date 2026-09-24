from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.models import Application, ApplicationApproval, ApprovalStatus, Company, Department, RoleCode, User

router = APIRouter(tags=["role dashboards"])


@router.get("/applicant/dashboard", dependencies=[Depends(require_roles(RoleCode.APPLICANT))])
def applicant_dashboard(user: CurrentUser) -> dict[str, str | int]:
    return {"area": "applicant", "message": "Applicant workspace is ready.", "user_id": user.id}


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
