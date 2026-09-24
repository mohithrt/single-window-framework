from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.database import SessionLocal
from app.integration_service import MockMPCBProvider, get_provider
from app.models import (
    AIChatMessage, AIChatSession, Application, ApplicationApproval, ApplicationStatus,
    IntegrationTransaction, RoleCode, WorkflowAuditEvent,
)
from app.what_if_service import WhatIfService


def _login(client, email: str, password: str = "TestPassphrase2026!") -> dict[str, str]:
    result = client.post("/api/auth/login", json={"email": email, "password": password})
    assert result.status_code == 200, result.text
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def _application(client, email: str | None = None, *, submit: bool = False) -> tuple[int, dict[str, str]]:
    email = email or f"admin-ai-{uuid4().hex[:10]}@example.com"
    registered = client.post("/api/auth/register", json={
        "full_name": "Analytics Applicant", "email": email, "password": "SecurePassphrase2026!",
    })
    assert registered.status_code == 201
    headers = _login(client, email, "SecurePassphrase2026!")
    result = client.post("/api/applications", headers=headers)
    assert result.status_code == 201
    application_id = result.json()["id"]
    with SessionLocal.begin() as db:
        app = db.get(Application, application_id)
        app.company_name = "Scenario Manufacturing"
        app.applicant_name = "Analytics Applicant"
        app.industry_type = "IT / Software"
        app.built_up_area = 1000
        app.pollution_category = "White"
        app.hazardous_materials = False
        app.project_location = "Pune"
        app.midc_area = False
        if submit:
            app.status = ApplicationStatus.SUBMITTED.value
            app.submitted_at = datetime.now(UTC) - timedelta(days=20)
    if submit:
        result = client.get(f"/api/applications/{application_id}/approvals", headers=headers)
        assert result.status_code == 200, result.text
    return application_id, headers


def test_what_if_recalculates_risk_departments_docs_and_duration_from_rules(client) -> None:
    application_id, headers = _application(client)
    response = client.post(f"/api/applications/{application_id}/what-if", headers=headers,
                           json={"proposed_changes": {"built_up_area": 30000}})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["risk_change"]["score_after"] > result["risk_change"]["score_before"]
    assert result["risk_change"]["tier_after"] in {"LOW", "MEDIUM", "HIGH"}
    assert {item["department_code"] for item in result["affected_departments"]} == {"DISH", "FIRE_SERVICES"}
    assert {item["document_type"] for item in result["additional_documents"]} >= {"FIRE_SAFETY_DOCUMENTS", "BUILDING_PLAN"}
    assert result["estimated_time_change_days"] > 0
    assert result["estimated_fee_change"] is None
    assert any("No fee schedule" in item for item in result["explanation"])
    assert client.post(f"/api/applications/{application_id}/what-if", headers=headers,
                       json={"proposed_changes": {"admin": True}}).status_code == 422


def test_assistant_uses_saved_workflow_and_persists_sessions_with_rule_fallback(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "")
    application_id, applicant_headers = _application(client, submit=True)
    ask = client.post(f"/api/applications/{application_id}/assistant/chat", headers=applicant_headers,
                      json={"message": "What if I increase my factory size from 1,000 sq ft to 30,000 sq ft?"})
    assert ask.status_code == 201, ask.text
    result = ask.json()
    assert result["mode"] == "DEMO_RULE_BASED" and result["llm_used"] is False
    assert "Demo AI / Rule-based response" in result["message"]["content"]
    assert result["message"]["structured_data"]["risk_change"]["score_after"] > result["message"]["structured_data"]["risk_change"]["score_before"]
    session_id = result["session_id"]
    second = client.post(f"/api/applications/{application_id}/assistant/chat", headers=applicant_headers,
                         json={"session_id": session_id, "message": "Which approval is currently delaying my application?"})
    assert second.status_code == 201 and "current bottleneck" in second.json()["message"]["content"]
    history = client.get(f"/api/applications/{application_id}/assistant/sessions/{session_id}", headers=applicant_headers)
    assert history.status_code == 200 and len(history.json()["messages"]) == 4
    monkeypatch.setattr(settings, "llm_api_key", "configured-but-unavailable")
    from app.routers.assistant import OptionalLLMProvider
    monkeypatch.setattr(OptionalLLMProvider, "rewrite", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider offline")))
    documents = client.post(f"/api/applications/{application_id}/assistant/chat", headers=applicant_headers,
                            json={"session_id": session_id, "message": "Which documents are missing?"})
    assert documents.status_code == 201
    assert documents.json()["mode"] == "DEMO_RULE_BASED"
    assert "Missing from this application" in documents.json()["message"]["content"]
    assert documents.json()["message"]["structured_data"]["required_documents"]
    history = client.get(f"/api/applications/{application_id}/assistant/sessions/{session_id}", headers=applicant_headers)
    assert history.status_code == 200 and len(history.json()["messages"]) == 6
    with SessionLocal() as db:
        saved = db.scalar(select(AIChatSession).where(AIChatSession.id == session_id))
        assert saved is not None and len(saved.messages) == 6
        assert all(isinstance(row, AIChatMessage) for row in saved.messages)
    foreign_id, foreign_headers = _application(client)
    assert client.get(f"/api/applications/{application_id}/assistant/sessions/{session_id}", headers=foreign_headers).status_code == 404
    assert client.get(f"/api/applications/{foreign_id}/assistant/sessions/{session_id}", headers=applicant_headers).status_code == 404


def test_admin_analytics_and_inspection_api_use_persisted_data(client) -> None:
    application_id, applicant_headers = _application(client, submit=True)
    admin = _login(client, "admin@example.com")
    with SessionLocal.begin() as db:
        app = db.get(Application, application_id)
        app.status = ApplicationStatus.APPROVED.value
        rows = db.scalars(select(ApplicationApproval).where(ApplicationApproval.application_id == application_id)).all()
        now = datetime.now(UTC)
        for row in rows:
            if row.is_required:
                row.status = "APPROVED"
                row.sla_started_at = now - timedelta(days=7)
                row.decided_at = now - timedelta(days=2)
        first = next(row for row in rows if row.is_required)
        db.add(WorkflowAuditEvent(application_id=application_id, approval_id=first.id,
            actor_user_id=app.owner_user_id, department_code=first.department_code,
            action="REJECTED", message="Missing safety certificate", details={}))
    analytics = client.get("/api/admin/analytics", headers=admin)
    assert analytics.status_code == 200, analytics.text
    data = analytics.json()
    assert data["kpis"]["total_applications"] >= 1
    assert data["kpis"]["approved"] >= 1
    assert data["kpis"]["average_clearance_time_days"] is not None
    assert data["departments"] and data["average_approval_time"]
    assert data["rejection_reasons"][0]["reason"] == "Missing safety certificate"
    details = client.get(f"/api/admin/applications/{application_id}", headers=admin)
    assert details.status_code == 200 and details.json()["critical_path"]["nodes"]
    assert client.get("/api/admin/departments", headers=admin).json()["total"] > 0
    assert client.get("/api/admin/audit", headers=admin).status_code == 200
    assert client.get("/api/admin/analytics", headers=applicant_headers).status_code == 403


def test_mock_integrations_store_request_and_response_without_external_claims(client) -> None:
    admin = _login(client, "admin@example.com")
    catalog = client.get("/api/admin/integrations/providers", headers=admin)
    assert catalog.status_code == 200 and catalog.json()["notice"]
    assert {item["code"] for item in catalog.json()["items"]} >= {"MPCB", "MIDC", "DISH", "FIRE", "GST", "MCA", "UDYAM", "DIGILOCKER", "EMAIL", "SMS"}
    submitted = client.post("/api/admin/integrations/GST/submit", headers=admin,
                            json={"request_payload": {"gstin": "27DEMO0000A1Z5"}})
    assert submitted.status_code == 201, submitted.text
    transaction = submitted.json()
    assert transaction["status"] == "VERIFIED_DEMO"
    assert transaction["response"]["connected_to_government"] is False
    assert transaction["request"]["demo_only"] is True
    assert client.get(f"/api/admin/integrations/{transaction['id']}/status", headers=admin).json()["status"] == "VERIFIED_DEMO"
    assert client.get(f"/api/admin/integrations/{transaction['id']}/response", headers=admin).json()["stored_response"]
    assert client.get("/api/admin/integrations", headers=admin).json()["items"]
    with SessionLocal() as db:
        row = db.get(IntegrationTransaction, transaction["id"])
        assert row is not None and row.provider_code == "GST" and row.request_payload["demo_only"]
    provider = MockMPCBProvider()
    response = provider.submit({"application_number": "MCAI-DEMO"})
    assert provider.check_status(response["reference"])["demo"] is True
    assert provider.get_response(response["reference"])["connected_to_government"] is False
    assert get_provider("MPCB").code == "MPCB"
