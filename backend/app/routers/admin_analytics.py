from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.analytics_service import AnalyticsService
from app.critical_path_service import CriticalPathService
from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.integration_service import get_provider, provider_catalog
from app.models import (
    Application, ApplicationApproval, ApplicationStatus, IntegrationTransaction, RoleCode, WorkflowAuditEvent,
)
from app.workflow_service import WorkflowService
from app.risk_service import RiskService
from app.routers.system import system_health

router = APIRouter(prefix="/admin", tags=["government administration"],
                   dependencies=[Depends(require_roles(RoleCode.ADMIN))])
Database = Annotated[Session, Depends(get_db)]


class IntegrationSubmit(BaseModel):
    application_id: int | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict, max_length=30)


@router.get("/system-health")
def admin_system_health(db: Database) -> dict:
    return system_health(db)


@router.get("/analytics")
def admin_analytics(db: Database) -> dict:
    return AnalyticsService().dashboard(db)


@router.get("/departments")
def admin_departments(db: Database) -> dict:
    report = AnalyticsService().dashboard(db)
    return {"total": len(report["departments"]), "items": report["departments"]}


@router.get("/rules")
def admin_rules() -> dict:
    workflow = WorkflowService()
    risk = RiskService()
    return {
        "workflow_version": workflow.rules["version"],
        "risk_version": risk.rules["version"],
        "departments": [{
            "code": row["code"], "name": row["name"],
            "estimated_duration_days": row["estimated_duration_days"],
            "depends_on": row.get("depends_on", []),
            "required_documents": workflow.rules.get("document_requirements", {}).get(row["code"], []),
        } for row in workflow.departments],
        "fee_schedule": workflow.rules.get("fee_schedule", {}),
        "fee_schedule_configured": bool(workflow.rules.get("fee_schedule", {})),
        "risk_tiers": risk.rules["tier_thresholds"],
    }


@router.get("/applications")
def admin_applications(db: Database, limit: int = Query(default=100, ge=1, le=250), offset: int = Query(default=0, ge=0)) -> dict:
    total = db.scalar(select(func.count(Application.id)).where(Application.status != ApplicationStatus.DRAFT.value)) or 0
    rows = db.scalars(select(Application).options(
        joinedload(Application.owner), selectinload(Application.approvals),
        selectinload(Application.risk_assessments),
    ).where(Application.status != ApplicationStatus.DRAFT.value).order_by(
        Application.submitted_at.desc(), Application.id.desc(),
    ).limit(limit).offset(offset)).unique().all()
    items = []
    for item in rows:
        saved_risks = item.risk_assessments
        latest_risk = max(saved_risks, key=lambda row: (row.created_at, row.id), default=None)
        items.append({
            "id": item.id, "application_number": item.application_number,
            "company_name": item.company_name or "Company not provided",
            "applicant_name": item.applicant_name or item.owner.full_name,
            "industry_type": item.industry_type, "status": item.status,
            "risk_tier": latest_risk.risk_tier if latest_risk else item.risk_tier,
            "submitted_at": item.submitted_at, "expected_completion_at": item.expected_completion_at,
            "departments": [row.department_code for row in item.approvals if row.is_required],
        })
    return {"total": total, "items": items}


@router.get("/applications/{application_id}")
def admin_application(application_id: int, db: Database) -> dict:
    application = db.scalar(select(Application).options(
        joinedload(Application.owner), selectinload(Application.documents),
        selectinload(Application.approvals), selectinload(Application.risk_assessments),
        selectinload(Application.workflow_events).joinedload(WorkflowAuditEvent.actor),
    ).where(Application.id == application_id))
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    critical_path = CriticalPathService().calculate(application, application.approvals, application.workflow_events)
    latest_risk = max(application.risk_assessments, key=lambda row: (row.created_at, row.id), default=None)
    return {
        "application": {
            "id": application.id, "application_number": application.application_number,
            "company_name": application.company_name, "applicant_name": application.applicant_name or application.owner.full_name,
            "applicant_email": application.applicant_email or application.owner.email,
            "industry_type": application.industry_type, "status": application.status,
            "risk_tier": application.risk_tier, "submitted_at": application.submitted_at,
            "expected_completion_at": application.expected_completion_at,
            "project_location": application.project_location,
        },
        "approvals": [{"id": row.id, "department_code": row.department_code,
                       "department_name": row.department_name, "required": row.is_required,
                       "status": row.status, "depends_on": row.depends_on,
                       "sla_expected_completion": row.sla_expected_completion,
                       "escalated_at": row.escalated_at, "decision_message": row.decision_message}
                      for row in application.approvals],
        "risk": ({"score": latest_risk.risk_score, "tier": latest_risk.risk_tier,
                  "assessed_at": latest_risk.created_at} if latest_risk else None),
        "documents": [{"id": doc.id, "name": doc.file_name, "type": doc.document_type, "status": doc.status}
                      for doc in application.documents],
        "critical_path": critical_path,
        "audit": [{"id": event.id, "action": event.action, "department_code": event.department_code,
                   "actor": "System" if (event.details or {}).get("system_actor") else event.actor.full_name,
                   "status": event.to_status, "message": event.message, "created_at": event.created_at}
                  for event in sorted(application.workflow_events, key=lambda item: (item.created_at, item.id))],
    }


@router.get("/audit")
def admin_audit(db: Database, limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)) -> dict:
    base = select(WorkflowAuditEvent).options(
        joinedload(WorkflowAuditEvent.actor), joinedload(WorkflowAuditEvent.application),
        joinedload(WorkflowAuditEvent.approval),
    )
    rows = db.scalars(base.order_by(WorkflowAuditEvent.created_at.desc(), WorkflowAuditEvent.id.desc())
                      .limit(limit).offset(offset)).unique().all()
    return {"items": [{"id": event.id, "application_id": event.application_id,
                        "application_number": event.application.application_number if event.application else None,
                        "department": event.approval.department_name if event.approval else event.department_code,
                        "action": event.action,
                        "actor": "System" if (event.details or {}).get("system_actor") else event.actor.full_name,
                        "from_status": event.from_status, "to_status": event.to_status,
                        "message": event.message, "details": event.details,
                        "created_at": event.created_at} for event in rows]}


@router.get("/integrations/providers")
def integration_providers() -> dict:
    items = provider_catalog()
    return {
        "items": items,
        "notice": "Providers are mock by default. A provider becomes live only when explicitly configured.",
        "live_count": sum(1 for item in items if item["connected_to_government"]),
    }


@router.post("/integrations/{provider_code}/submit", status_code=201)
def submit_integration(provider_code: str, payload: IntegrationSubmit, user: CurrentUser, db: Database) -> dict:
    try:
        provider = get_provider(provider_code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Integration provider not found") from exc
    request_payload = dict(payload.request_payload)
    if payload.application_id is not None:
        application = db.get(Application, payload.application_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        request_payload = {
            "application_id": application.id,
            "application_number": application.application_number,
            "company_name": application.company_name,
            **request_payload,
        }
    request_payload["demo_only"] = not any(
        item["code"] == provider.code and item["connected_to_government"] for item in provider_catalog()
    )
    response = provider.submit(request_payload)
    row = IntegrationTransaction(
        provider_code=provider.code, application_id=payload.application_id,
        submitted_by_user_id=user.id, reference=response["reference"],
        status=response["status"], request_payload=request_payload, response_payload=response,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _transaction(row)


@router.get("/integrations")
def integration_history(db: Database, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    rows = db.scalars(select(IntegrationTransaction).options(
        joinedload(IntegrationTransaction.application), joinedload(IntegrationTransaction.submitted_by),
    ).order_by(IntegrationTransaction.created_at.desc(), IntegrationTransaction.id.desc()).limit(limit)).all()
    return {"items": [_transaction(row) for row in rows]}


@router.get("/integrations/{transaction_id}/status")
def integration_status(transaction_id: int, db: Database) -> dict:
    row = db.get(IntegrationTransaction, transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Integration transaction not found")
    return get_provider(row.provider_code).check_status(row.reference)


@router.get("/integrations/{transaction_id}/response")
def integration_response(transaction_id: int, db: Database) -> dict:
    row = db.get(IntegrationTransaction, transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Integration transaction not found")
    return {"transaction_id": row.id, **get_provider(row.provider_code).get_response(row.reference),
            "stored_response": row.response_payload}


def _transaction(row: IntegrationTransaction) -> dict:
    return {"id": row.id, "provider_code": row.provider_code,
            "application_id": row.application_id,
            "application_number": row.application.application_number if row.application else None,
            "reference": row.reference, "status": row.status,
            "request": row.request_payload, "response": row.response_payload,
            "created_at": row.created_at}
