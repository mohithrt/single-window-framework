"""Application-scoped, role-authorized conversational assistant API."""

import json
from datetime import UTC, datetime
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.conversation_manager import ConversationalAssistant
from app.database import get_db
from app.dependencies import CurrentUser
from app.models import (
    AIChatMessage, AIChatSession, Application, ApplicationApproval, Department,
    RoleCode,
)
from app.what_if_service import WhatIfService

router = APIRouter(prefix="/applications", tags=["MahaClear AI assistant"])
Database = Annotated[Session, Depends(get_db)]
logger = logging.getLogger(__name__)


class WhatIfRequest(BaseModel):
    proposed_changes: dict[str, Any] = Field(max_length=20)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: int | None = None
    proposed_changes: dict[str, Any] | None = Field(default=None, max_length=20)


def _application(db: Session, application_id: int, user: CurrentUser) -> Application:
    query = select(Application).options(
        selectinload(Application.documents), selectinload(Application.approvals),
        selectinload(Application.risk_assessments), selectinload(Application.workflow_events),
    ).where(Application.id == application_id)
    if user.role.code == RoleCode.APPLICANT.value:
        query = query.where(Application.owner_user_id == user.id)
    elif user.role.code == RoleCode.OFFICER.value:
        conditions = [ApplicationApproval.assigned_reviewer_id == user.id]
        if user.department_id:
            department_code = db.scalar(select(Department.code).where(Department.id == user.department_id))
            if department_code:
                conditions.append(ApplicationApproval.department_code == department_code)
        authorized_application_ids = select(ApplicationApproval.application_id).where(
            ApplicationApproval.is_required.is_(True), or_(*conditions),
        )
        query = query.where(Application.id.in_(authorized_application_ids))
    elif user.role.code != RoleCode.ADMIN.value:
        raise HTTPException(status_code=403, detail="Your role is not allowed to use the assistant")
    application = db.scalar(query)
    if application is None:
        # Do not reveal whether another applicant's application exists.
        raise HTTPException(status_code=404, detail="Application not found or not available to this user")
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
    if payload.session_id is None:
        session = AIChatSession(user_id=user.id, application_id=application.id,
                                title=payload.message.strip()[:200])
        db.add(session)
        db.flush()
        history: list[AIChatMessage] = []
    else:
        session = db.scalar(select(AIChatSession).where(
            AIChatSession.id == payload.session_id,
            AIChatSession.user_id == user.id,
            AIChatSession.application_id == application.id,
        ))
        if session is None:
            raise HTTPException(status_code=404, detail="Assistant session not found")
        history_limit = max(0, min(settings.llm_max_history_messages, 30))
        history = list(reversed(db.scalars(select(AIChatMessage).where(
            AIChatMessage.session_id == session.id,
        ).order_by(AIChatMessage.created_at.desc(), AIChatMessage.id.desc()).limit(history_limit)).all())) if history_limit else []

    question = payload.message.strip()
    if payload.proposed_changes:
        question += "\nFor the what-if scenario, evaluate these exact proposed changes: " + json.dumps(payload.proposed_changes)
    response, mode, metadata = ConversationalAssistant().respond(
        message=question, history=history, db=db, application=application, user=user,
    )
    session.updated_at = datetime.now(UTC)
    db.add(AIChatMessage(session=session, role="USER", content=payload.message.strip()))
    answer = AIChatMessage(session=session, role="ASSISTANT", content=response, structured_data=metadata)
    db.add(answer)
    db.commit()
    db.refresh(answer)
    return {"session_id": session.id, "message": {
        "id": answer.id, "role": answer.role, "content": answer.content,
        "structured_data": answer.structured_data, "created_at": answer.created_at,
    }, "mode": mode, "llm_used": mode == "AI_ASSISTED"}


@router.get("/{application_id}/assistant/sessions/{session_id}")
def get_session(application_id: int, session_id: int, user: CurrentUser, db: Database) -> dict:
    _application(db, application_id, user)
    session = db.scalar(select(AIChatSession).options(selectinload(AIChatSession.messages)).where(
        AIChatSession.id == session_id, AIChatSession.application_id == application_id,
        AIChatSession.user_id == user.id,
    ))
    if session is None:
        raise HTTPException(status_code=404, detail="Assistant session not found")
    messages = sorted(session.messages, key=lambda item: (item.created_at, item.id))
    return {"id": session.id, "title": session.title, "messages": [{
        "id": message.id, "role": message.role, "content": message.content,
        "structured_data": message.structured_data, "created_at": message.created_at,
    } for message in messages]}
