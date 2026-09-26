"""Focused tests for the application-grounded assistant conversation path."""

from datetime import UTC, datetime, timedelta
import json
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.database import SessionLocal
from app.models import (
    AIChatMessage, AIChatSession, Application, ApplicationApproval,
    ApplicationStatus, RoleCode, User,
)


def _login(client, email: str, password: str = "TestPassphrase2026!") -> dict[str, str]:
    result = client.post("/api/auth/login", json={"email": email, "password": password})
    assert result.status_code == 200, result.text
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def _create_app(client, *, submit: bool = True) -> tuple[int, dict[str, str]]:
    email = f"assistant-{uuid4().hex[:12]}@example.com"
    created = client.post("/api/auth/register", json={
        "full_name": "Assistant Applicant", "email": email, "password": "SecurePassphrase2026!",
    })
    assert created.status_code == 201, created.text
    headers = _login(client, email, "SecurePassphrase2026!")
    created = client.post("/api/applications", headers=headers)
    assert created.status_code == 201, created.text
    application_id = created.json()["id"]
    with SessionLocal.begin() as db:
        app = db.get(Application, application_id)
        app.company_name = "North Star Components"
        app.industry_type = "Manufacturing"
        app.project_type = "Precision component unit"
        app.status = ApplicationStatus.SUBMITTED.value if submit else ApplicationStatus.DRAFT.value
        app.submitted_at = datetime.now(UTC) - timedelta(days=3) if submit else None
        app.built_up_area = 8000
        app.pollution_category = "Orange"
        app.hazardous_materials = True
        app.midc_area = True
        app.gstin = "27AAAAA0000A1Z5"
    if submit:
        initialized = client.get(f"/api/applications/{application_id}/approvals", headers=headers)
        assert initialized.status_code == 200, initialized.text
    return application_id, headers


def _tool(name: str, arguments: dict) -> dict:
    return {"message": {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"tool-{uuid4().hex[:8]}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }]}}


def test_llm_retrieves_actual_status_then_uses_conversation_history(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "fake-test-key")
    monkeypatch.setattr(settings, "llm_provider", "openai_compatible")
    application_id, headers = _create_app(client)
    from app.conversation_manager import ConversationalAssistant

    observed = []

    def fake_chat(_self, messages, _tools, *, tool_choice="auto"):
        observed.append(messages)
        if len(observed) in {1, 3}:
            return _tool("get_application_summary", {})
        if len(observed) == 2:
            tool_result = json.loads(messages[-1]["content"])
            assert tool_result["status"] == "SUBMITTED"
            return {"message": {"role": "assistant", "content": "The application is submitted and under its saved department review workflow."}}
        assert any(item["role"] == "assistant" and "submitted" in (item.get("content") or "").lower()
                   for item in messages)
        return {"message": {"role": "assistant", "content": "It refers to the application: its saved record is SUBMITTED."}}

    monkeypatch.setattr("app.conversation_manager.OpenAICompatibleLLMProvider.chat", fake_chat)
    first = client.post(f"/api/applications/{application_id}/assistant/chat", headers=headers,
                        json={"message": "Where is my application right now?"})
    assert first.status_code == 201, first.text
    assert first.json()["mode"] == "AI_ASSISTED"
    assert first.json()["message"]["structured_data"]["tools_used"][0]["name"] == "get_application_summary"
    session_id = first.json()["session_id"]
    second = client.post(f"/api/applications/{application_id}/assistant/chat", headers=headers,
                         json={"session_id": session_id, "message": "Why is it there?"})
    assert second.status_code == 201, second.text
    assert "It refers to the application" in second.json()["message"]["content"]
    assert any(item["role"] == "user" and item["content"] == "Where is my application right now?"
               for item in observed[-1])
    saved = client.get(f"/api/applications/{application_id}/assistant/sessions/{session_id}", headers=headers)
    assert saved.status_code == 200 and len(saved.json()["messages"]) == 4
    with SessionLocal() as db:
        assert db.scalar(select(AIChatSession.id).where(AIChatSession.id == session_id)) == session_id
        assert len(db.scalars(select(AIChatMessage).where(AIChatMessage.session_id == session_id)).all()) == 4


def test_tools_ground_documents_risk_sla_and_what_if_in_existing_services(client):
    application_id, headers = _create_app(client)
    from app.assistant_tools import execute_assistant_tool

    with SessionLocal() as db:
        app = db.scalar(select(Application).options(
            # These relationships are loaded by the chat endpoint; use the same data here.
        ).where(Application.id == application_id))
        # Force relationship materialization while the session is open.
        _ = app.approvals, app.documents
        approval_clock_before = [(item.sla_started_at, item.sla_duration_days, item.sla_expected_completion)
                                 for item in app.approvals]
        applicant = db.scalar(select(User).where(User.email.like("assistant-%@example.com")).order_by(User.id.desc()))
        docs = execute_assistant_tool("get_missing_documents", {}, db=db, application=app, user_id=applicant.id)
        risk = execute_assistant_tool("get_risk_assessment", {}, db=db, application=app, user_id=applicant.id)
        sla = execute_assistant_tool("get_sla_status", {}, db=db, application=app, user_id=applicant.id)
        approvals = execute_assistant_tool("get_application_approvals", {}, db=db, application=app, user_id=applicant.id)
        critical = execute_assistant_tool("get_critical_path", {}, db=db, application=app, user_id=applicant.id)
        inspections = execute_assistant_tool("get_inspections", {}, db=db, application=app, user_id=applicant.id)
        timeline = execute_assistant_tool("get_application_timeline", {}, db=db, application=app, user_id=applicant.id)
        notifications = execute_assistant_tool("get_notifications", {}, db=db, application=app, user_id=applicant.id)
        scenario = execute_assistant_tool("run_what_if_analysis", {
            "proposed_changes": {"hazardous_materials": False, "hazardous_materials_details": None},
        }, db=db, application=app, user_id=applicant.id)
        assert approval_clock_before == [(item.sla_started_at, item.sla_duration_days, item.sla_expected_completion)
                                         for item in app.approvals]
    assert "BUILDING_PLAN" in docs["missing_document_categories"]
    assert risk["tier"] in {"LOW", "MEDIUM", "HIGH"} and risk["factor_breakdown"]
    assert sla["approvals"]
    assert approvals["approvals"] and critical["nodes"]
    assert inspections["recorded_count"] == 0 and timeline["events"]
    assert "notifications" in notifications
    assert scenario["risk_change"]["score_delta"] <= 0
    assert scenario["source"].startswith("Configured MAHACLEAR-AI prototype rules")


def test_general_information_uses_general_guidance_tool(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "fake-test-key")
    application_id, headers = _create_app(client)
    calls = iter([
        _tool("get_domain_guidance", {"topic": "MPCB"}),
        {"message": {"role": "assistant", "content": "MPCB is Maharashtra's state pollution-control body. This is general information, not a saved approval decision for your application."}},
    ])
    monkeypatch.setattr("app.conversation_manager.OpenAICompatibleLLMProvider.chat",
                        lambda *_args, **_kwargs: next(calls))
    result = client.post(f"/api/applications/{application_id}/assistant/chat", headers=headers,
                         json={"message": "What does MPCB do?"})
    assert result.status_code == 201 and result.json()["mode"] == "AI_ASSISTED"
    trace = result.json()["message"]["structured_data"]["tools_used"][0]
    assert trace["result"]["scope"] == "GENERAL_INFORMATION_NOT_APPLICATION_SPECIFIC"


def test_missing_or_failed_llm_is_disclosed_and_uses_builtin_fallback(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    application_id, headers = _create_app(client)
    result = client.post(f"/api/applications/{application_id}/assistant/chat", headers=headers,
                         json={"message": "What is delaying my application?"})
    assert result.status_code == 201
    assert result.json()["mode"] == "AI_UNAVAILABLE" and result.json()["llm_used"] is False
    answer = result.json()["message"]["content"]
    assert "AI service is temporarily unavailable" in answer
    assert "built-in application assistant" in answer
    assert "MPCB" in answer or "approval" in answer


def test_malformed_llm_completion_is_not_mislabeled_as_ai(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "fake-test-key")
    application_id, headers = _create_app(client)
    monkeypatch.setattr("app.conversation_manager.OpenAICompatibleLLMProvider.chat",
                        lambda *_args, **_kwargs: {})
    result = client.post(f"/api/applications/{application_id}/assistant/chat", headers=headers,
                         json={"message": "What is my current application status?"})
    assert result.status_code == 201
    assert result.json()["mode"] == "AI_UNAVAILABLE"
    assert "AI service is temporarily unavailable" in result.json()["message"]["content"]


def test_applicants_cannot_query_another_application_or_session(client):
    application_id, _ = _create_app(client)
    foreign_id, foreign_headers = _create_app(client)
    from app.conversation_manager import ConversationalAssistant
    from app.models import Application as AppModel

    with SessionLocal() as db:
        app = db.get(AppModel, application_id)
        applicant = db.scalar(select(User).where(User.id == app.owner_user_id))
        session = AIChatSession(user_id=applicant.id, application_id=application_id, title="Private")
        db.add(session); db.commit(); db.refresh(session)
        session_id = session.id
    assert client.post(f"/api/applications/{application_id}/assistant/chat", headers=foreign_headers,
                       json={"message": "Where is this?"}).status_code == 404
    assert client.get(f"/api/applications/{foreign_id}/assistant/sessions/{session_id}", headers=foreign_headers).status_code == 404


def test_department_officer_requires_application_assignment(client, monkeypatch):
    application_id, _ = _create_app(client)
    officer_headers = _login(client, "officer@example.com")
    with SessionLocal.begin() as db:
        officer = db.scalar(select(User).where(User.email == "officer@example.com"))
        approval = db.scalar(select(ApplicationApproval).where(
            ApplicationApproval.application_id == application_id,
            ApplicationApproval.is_required.is_(True),
        ).limit(1))
        approval.assigned_reviewer_id = officer.id
    monkeypatch.setattr(settings, "llm_api_key", "")
    allowed = client.get(f"/api/applications/{application_id}/assistant/sessions", headers=officer_headers)
    assert allowed.status_code == 200
    admin_headers = _login(client, "admin@example.com")
    assert client.get(f"/api/applications/{application_id}/assistant/sessions", headers=admin_headers).status_code == 200
    other_id, _ = _create_app(client)
    denied = client.get(f"/api/applications/{other_id}/assistant/sessions", headers=officer_headers)
    assert denied.status_code == 404
