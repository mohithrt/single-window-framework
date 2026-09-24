from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.models import Application, RiskAssessment, RoleCode, WorkflowAuditEvent
from app.risk_service import RiskService

router = APIRouter(
    prefix="/applications",
    tags=["applicant risk assessment"],
    dependencies=[Depends(require_roles(RoleCode.APPLICANT))],
)
Database = Annotated[Session, Depends(get_db)]


def load_owned_application(db: Session, application_id: int, user_id: int) -> Application:
    application = db.scalar(
        select(Application)
        .options(selectinload(Application.documents))
        .where(Application.id == application_id, Application.owner_user_id == user_id)
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


def assessment_payload(assessment: RiskAssessment | None, application: Application, service: RiskService) -> dict:
    if assessment is None:
        return {"assessment": None, "is_stale": True}
    is_stale = (
        assessment.input_snapshot != service.input_snapshot(application)
        or assessment.rules_version != service.rules["version"]
    )
    data = dict(assessment.assessment_data)
    data.update({
        "id": assessment.id,
        "application_id": assessment.application_id,
        "risk_score": assessment.risk_score,
        "risk_tier": assessment.risk_tier,
        "rules_version": assessment.rules_version,
        "created_at": assessment.created_at,
        "is_stale": is_stale,
    })
    return {"assessment": data, "is_stale": is_stale}


@router.get("/{application_id}/risk")
def get_risk_assessment(application_id: int, user: CurrentUser, db: Database) -> dict:
    application = load_owned_application(db, application_id, user.id)
    latest = db.scalar(
        select(RiskAssessment)
        .where(RiskAssessment.application_id == application.id)
        .order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc())
        .limit(1)
    )
    return assessment_payload(latest, application, RiskService())


@router.post("/{application_id}/risk/recalculate")
def recalculate_risk_assessment(application_id: int, user: CurrentUser, db: Database) -> dict:
    application = load_owned_application(db, application_id, user.id)
    service = RiskService()
    result = service.assess(application)
    assessment_data = {key: value for key, value in result.items()
                       if key not in {"input_snapshot", "rules_snapshot", "rules_version", "risk_tier", "risk_score"}}
    assessment = RiskAssessment(
        application_id=application.id,
        assessed_by_user_id=user.id,
        risk_score=result["risk_score"],
        risk_tier=result["risk_tier"],
        rules_version=result["rules_version"],
        assessment_data=assessment_data,
        input_snapshot=result["input_snapshot"],
        rules_snapshot=result["rules_snapshot"],
    )
    db.add(assessment)
    application.risk_tier = result["risk_tier"]
    db.add(WorkflowAuditEvent(application_id=application.id, actor_user_id=user.id,
        action="RISK_ASSESSED", message=f"Application risk assessed as {result['risk_tier']} ({result['risk_score']}/100).",
        details={"assessment_id": assessment.id, "risk_score": result["risk_score"],
                 "risk_tier": result["risk_tier"], "rules_version": result["rules_version"]}))
    db.commit()
    db.refresh(assessment)
    return assessment_payload(assessment, application, service)
