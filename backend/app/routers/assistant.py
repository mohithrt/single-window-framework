from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.dependencies import CurrentUser
from app.core.config import settings
from app.llm_provider import OptionalLLMProvider
from app.models import (
    AIChatMessage, AIChatSession, Application, ApplicationApproval,
    Inspection, JointInspection, RoleCode, WorkflowAuditEvent,
)
from app.what_if_service import WhatIfService

router = APIRouter(prefix="/applications", tags=["MahaClear AI assistant"])
Database = Annotated[Session, Depends(get_db)]


class WhatIfRequest(BaseModel):
    proposed_changes: dict[str, Any] = Field(max_length=20)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: int | None = None
    proposed_changes: dict[str, Any] | None = Field(default=None, max_length=20)


def _application(db: Session, application_id: int, user: CurrentUser) -> Application:
    query = select(Application).options(
        selectinload(Application.documents), selectinload(Application.approvals),
        selectinload(Application.risk_assessments),
    ).where(Application.id == application_id)
    if user.role.code == RoleCode.APPLICANT.value:
        query = query.where(Application.owner_user_id == user.id)
    application = db.scalar(query)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.post("/{application_id}/what-if")
def what_if(application_id: int, payload: WhatIfRequest, user: CurrentUser, db: Database) -> dict:
    application = _application(db, application_id, user)
    try:
        return WhatIfService().analyze(application, payload.proposed_changes)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{application_id}/assistant/sessions")
def list_sessions(application_id: int, user: CurrentUser, db: Database) -> dict:
    _application(db, application_id, user)
    rows = db.scalars(select(AIChatSession).where(
        AIChatSession.application_id == application_id, AIChatSession.user_id == user.id,
    ).order_by(AIChatSession.updated_at.desc(), AIChatSession.id.desc())).all()
    return {"items": [{"id": row.id, "title": row.title, "created_at": row.created_at,
                       "updated_at": row.updated_at} for row in rows]}


@router.post("/{application_id}/assistant/chat", status_code=201)
def chat(application_id: int, payload: ChatRequest, user: CurrentUser, db: Database) -> dict:
    application = _application(db, application_id, user)
    service = WhatIfService()
    if payload.session_id is None:
        session = AIChatSession(user_id=user.id, application_id=application.id,
                                title=payload.message.strip()[:200])
        db.add(session)
        db.flush()
    else:
        session = db.scalar(select(AIChatSession).where(
            AIChatSession.id == payload.session_id,
            AIChatSession.user_id == user.id,
            AIChatSession.application_id == application.id,
        ))
        if session is None:
            raise HTTPException(status_code=404, detail="Assistant session not found")
    if payload.proposed_changes is not None:
        try:
            structured = service.analyze(application, payload.proposed_changes)
            risk = structured["risk_change"]
            response = (
                "Demo AI / Rule-based response. The configured risk score changes "
                f"from {risk['score_before']}/100 ({risk['tier_before']}) to {risk['score_after']}/100 ({risk['tier_after']}); "
                f"the configured workflow duration changes by {structured['estimated_time_change_days']:+d} days. "
                + " ".join(structured["explanation"])
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        singles = db.scalars(select(Inspection).options(joinedload(Inspection.approval)).where(
            Inspection.application_id == application.id,
        )).all()
        joints = db.scalars(select(JointInspection).where(
            JointInspection.application_id == application.id,
        )).all()
        inspection_context = [SimpleNamespace(
            department_name=item.approval.department_name, status=item.status,
            scheduled_at=item.scheduled_at, site=item.site or item.location,
        ) for item in singles]
        inspection_context.extend(SimpleNamespace(
            department_name="Joint inspection", status=item.status,
            scheduled_at=item.scheduled_at, site=item.site,
        ) for item in joints)
        event_context = db.scalars(select(WorkflowAuditEvent).where(
            WorkflowAuditEvent.application_id == application.id,
        ).order_by(WorkflowAuditEvent.created_at, WorkflowAuditEvent.id)).all()
        response, structured = service.answer(
            payload.message, application, application.approvals, inspection_context, event_context,
        )
    mode = "DEMO_RULE_BASED"
    if structured is not None and settings.llm_api_key:
        try:
            response = OptionalLLMProvider().rewrite(payload.message, structured, response)
            mode = "LLM_ASSISTED"
        except Exception:
            # External provider errors never block or replace the deterministic result.
            mode = "DEMO_RULE_BASED"
    session.updated_at = datetime.now(UTC)
    db.add(AIChatMessage(session=session, role="USER", content=payload.message.strip()))
    answer = AIChatMessage(session=session, role="ASSISTANT", content=response, structured_data=structured)
    db.add(answer)
    db.commit()
    db.refresh(answer)
    return {"session_id": session.id, "message": {
        "id": answer.id, "role": answer.role, "content": answer.content,
        "structured_data": answer.structured_data, "created_at": answer.created_at,
    }, "mode": mode, "llm_used": mode == "LLM_ASSISTED"}


@router.get("/{application_id}/assistant/sessions/{session_id}")
def get_session(application_id: int, session_id: int, user: CurrentUser, db: Database) -> dict:
    _application(db, application_id, user)
    session = db.scalar(select(AIChatSession).options(selectinload(AIChatSession.messages)).where(
        AIChatSession.id == session_id, AIChatSession.application_id == application_id,
        AIChatSession.user_id == user.id,
    ))
    if session is None:
        raise HTTPException(status_code=404, detail="Assistant session not found")
    return {"id": session.id, "title": session.title, "messages": [{
        "id": message.id, "role": message.role, "content": message.content,
        "structured_data": message.structured_data, "created_at": message.created_at,
    } for message in session.messages]}
