from datetime import date

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Application, ApplicationStatus, User, WorkflowAuditEvent
from app.models import ApplicationApproval
from app.critical_path_service import CriticalPathService
from app.workflow_service import WorkflowService


def test_rule_selection_and_initial_dependency_states() -> None:
    application = Application(
        industry_type="Chemical", pollution_category="Red", hazardous_materials=True,
        midc_area=True, risk_tier="HIGH", gstin="27ABCDE1234F1Z5", cin="U12345MH2020PTC123456",
    )
    service = WorkflowService()
    required = service.determine_required_departments(application)
    assert {"MPCB", "MIDC", "DISH", "FIRE_SERVICES", "GSTN", "MCA21"} <= set(required)
    office_only = Application(industry_type="IT / Software", pollution_category="White", hazardous_materials=False)
    assert service.determine_required_departments(office_only) == ["MCA21"]


def test_critical_path_and_parallel_scenarios_use_dependency_data() -> None:
    service = CriticalPathService()
    application = Application(id=901, application_number="MCAI-2026-000901")

    chain = [
        ApplicationApproval(id=101, application_id=901, department_code="MPCB", department_name="MPCB",
                            is_required=True, status="PENDING", depends_on=[]),
        ApplicationApproval(id=102, application_id=901, department_code="DISH", department_name="DISH",
                            is_required=True, status="NOT_STARTED", depends_on=["MPCB"]),
    ]
    chain_result = service.calculate(application, chain, as_of=date(2026, 1, 1))
    assert chain_result["critical_path"] == ["MPCB", "DISH", "FINAL_CLEARANCE"]
    assert chain_result["estimated_completion_days"] == 26
    assert chain_result["blocked_approvals"] == [{
        "id": "DISH", "department_code": "DISH", "department_name": "DISH",
        "status": "NOT_STARTED", "blocked_by": ["MPCB"],
    }]
    assert chain_result["bottleneck"]["department_code"] == "MPCB"

    parallel = [
        ApplicationApproval(id=201, application_id=901, department_code=code, department_name=name,
                            is_required=True, status="PENDING", depends_on=[])
        for code, name in (("GSTN", "GSTN"), ("MCA21", "MCA21"), ("UDYAM", "Udyam"))
    ]
    parallel_result = service.calculate(application, parallel, as_of=date(2026, 1, 1))
    assert parallel_result["estimated_completion_days"] == 5
    assert parallel_result["parallel_approvals"] == [{
        "start_day": 0,
        "approval_codes": ["GSTN", "MCA21", "UDYAM"],
        "department_names": ["GSTN", "MCA21", "Udyam"],
    }]


def test_critical_path_api_returns_graph_from_saved_approvals(client) -> None:
    registered = client.post("/api/auth/register", json={
        "full_name": "Graph Applicant", "email": "graph.applicant@example.com",
        "password": "SecurePassphrase2026!",
    })
    assert registered.status_code == 201
    token = client.post("/api/auth/login", json={
        "email": "graph.applicant@example.com", "password": "SecurePassphrase2026!",
    }).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    app = client.post("/api/applications", headers=headers).json()
    with SessionLocal.begin() as db:
        application = db.get(Application, app["id"])
        application.status = ApplicationStatus.SUBMITTED.value
        application.industry_type = "Chemical"
        application.midc_area = True
    initialized = client.get(f"/api/applications/{app['id']}/approvals", headers=headers)
    assert initialized.status_code == 200

    response = client.get(f"/api/applications/{app['id']}/critical-path", headers=headers)
    assert response.status_code == 200
    graph = response.json()
    codes = {node["id"] for node in graph["nodes"]}
    assert {"MPCB", "MIDC", "DISH", "FIRE_SERVICES", "FINAL_CLEARANCE"} <= codes
    assert {"source": "MPCB", "target": "MIDC"} in graph["edges"]
    assert {"source": "MPCB", "target": "FIRE_SERVICES"} in graph["edges"]
    assert graph["critical_path"][-1] == "FINAL_CLEARANCE"
    assert graph["estimated_completion_days"] > 0


def test_workflow_initialization_lifecycle_and_audit(client) -> None:
    registered = client.post("/api/auth/register", json={
        "full_name": "Workflow Applicant", "email": "workflow.applicant@example.com",
        "password": "SecurePassphrase2026!",
    })
    assert registered.status_code == 201
    applicant_token = client.post("/api/auth/login", json={
        "email": "workflow.applicant@example.com", "password": "SecurePassphrase2026!",
    }).json()["access_token"]
    applicant_headers = {"Authorization": f"Bearer {applicant_token}"}
    created = client.post("/api/applications", headers=applicant_headers)
    application_id = created.json()["id"]

    with SessionLocal.begin() as db:
        application = db.get(Application, application_id)
        application.industry_type = "Chemical"
        application.midc_area = True
        application.status = ApplicationStatus.SUBMITTED.value

    workflow_response = client.get(f"/api/applications/{application_id}/approvals", headers=applicant_headers)
    assert workflow_response.status_code == 200
    body = workflow_response.json()
    assert body["application_status"] == "SUBMITTED"
    assert body["initialized"] is True
    approvals = {row["department_code"]: row for row in body["approvals"]}
    assert approvals["MPCB"]["status"] == "PENDING"
    assert approvals["MIDC"]["status"] == "NOT_STARTED"
    assert approvals["MIDC"]["depends_on"] == ["MPCB"]

    officer_token = client.post("/api/auth/login", json={
        "email": "officer@example.com", "password": "TestPassphrase2026!",
    }).json()["access_token"]
    officer_headers = {"Authorization": f"Bearer {officer_token}"}
    mpcb_id = approvals["MPCB"]["id"]
    assert client.post(f"/api/approvals/{mpcb_id}/start-review", headers=applicant_headers).status_code == 403
    assert client.post(f"/api/approvals/{mpcb_id}/approve", headers=officer_headers).status_code == 409
    assert client.post(f"/api/approvals/{mpcb_id}/start-review", headers=officer_headers).status_code == 200
    assert client.post(f"/api/approvals/{mpcb_id}/request-correction", headers=officer_headers,
                       json={"message": "Upload the signed pollution control plan."}).status_code == 200
    assert client.patch(f"/api/applications/{application_id}", headers=applicant_headers,
                        json={"project_description": "Updated to address the pollution control plan clarification."}).status_code == 200
    correction = client.post(f"/api/approvals/{mpcb_id}/correction-submitted", headers=applicant_headers)
    assert correction.status_code == 200
    assert client.post(f"/api/approvals/{mpcb_id}/start-review", headers=officer_headers).status_code == 200
    approved = client.post(f"/api/approvals/{mpcb_id}/approve", headers=officer_headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    latest = client.get(f"/api/applications/{application_id}/approvals", headers=applicant_headers).json()
    updated = {row["department_code"]: row for row in latest["approvals"]}
    assert updated["MIDC"]["status"] == "PENDING"
    assert any(event["action"] == "CORRECTION_REQUESTED" for event in latest["audit_events"])
    assert any(event["action"] == "APPROVAL_ACTIVATED" for event in latest["audit_events"])

    midc_id = updated["MIDC"]["id"]
    assert client.post(f"/api/approvals/{midc_id}/start-review", headers=officer_headers).status_code == 200
    assert client.post(f"/api/approvals/{midc_id}/reject", headers=officer_headers, json={}).status_code == 422
    denied = client.post(f"/api/approvals/{midc_id}/reject", headers=officer_headers,
                         json={"reason": "Land occupancy certificate is not valid."})
    assert denied.status_code == 200

    with SessionLocal() as db:
        actions = db.scalars(select(WorkflowAuditEvent.action).where(
            WorkflowAuditEvent.application_id == application_id
        )).all()
        assert "REJECTED" in actions
