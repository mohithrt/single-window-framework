from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Application, ApplicationApproval, ApplicationStatus, Notification, WorkflowAuditEvent
from app.sla_service import SlaService


def _new_workflow(client, email: str) -> tuple[int, int, dict[str, str], dict[str, str]]:
    register = client.post("/api/auth/register", json={
        "full_name": "SLA Applicant", "email": email, "password": "SecurePassphrase2026!",
    })
    assert register.status_code == 201
    applicant_login = client.post("/api/auth/login", json={
        "email": email, "password": "SecurePassphrase2026!",
    })
    applicant_headers = {"Authorization": f"Bearer {applicant_login.json()['access_token']}"}
    created = client.post("/api/applications", headers=applicant_headers).json()
    with SessionLocal.begin() as db:
        app = db.get(Application, created["id"])
        app.status = ApplicationStatus.SUBMITTED.value
        app.company_name = "SLA Test Company"
        app.industry_type = "Chemical"
    initialized = client.get(f"/api/applications/{created['id']}/approvals", headers=applicant_headers)
    mpcb_id = next(item["id"] for item in initialized.json()["approvals"] if item["department_code"] == "MPCB")
    officer_login = client.post("/api/auth/login", json={
        "email": "officer@example.com", "password": "TestPassphrase2026!",
    })
    officer_headers = {"Authorization": f"Bearer {officer_login.json()['access_token']}"}
    return created["id"], mpcb_id, applicant_headers, officer_headers


def test_sla_countdown_warns_then_escalates_once_and_notifies(client) -> None:
    now = datetime.now(UTC)
    service = SlaService()
    approval = ApplicationApproval(department_code="MPCB", department_name="MPCB", is_required=True,
                                   status="IN_REVIEW", sla_duration_days=15,
                                   sla_started_at=now - timedelta(days=13))
    assert service.payload(approval, now)["status"] == "WARNING"
    approval.sla_started_at = now - timedelta(days=16)
    assert service.payload(approval, now)["status"] == "BREACHED"
    approval.sla_expected_completion = now
    approval.sla_started_at = now - timedelta(days=15)
    assert service.payload(approval, now)["status"] == "BREACHED"
    assert service.duration("MIDC") == 10
    assert service.duration("FIRE_SERVICES") == 7
    assert service.duration("DISH") == 12

    application_id, approval_id, applicant_headers, officer_headers = _new_workflow(client, "sla-owner@example.com")
    assert client.post(f"/api/approvals/{approval_id}/start-review", headers=officer_headers).status_code == 200
    with SessionLocal.begin() as db:
        saved = db.get(ApplicationApproval, approval_id)
        saved.sla_started_at = now - timedelta(days=13)
        saved.sla_duration_days = 15
        saved.sla_expected_completion = now + timedelta(days=2)
    with SessionLocal() as db:
        assert SlaService().check_and_escalate(db, now) == []
    with SessionLocal() as db:
        warnings = db.scalars(select(WorkflowAuditEvent).where(
            WorkflowAuditEvent.application_id == application_id,
            WorkflowAuditEvent.action == "SLA_WARNING",
        )).all()
        assert len(warnings) == 1
    with SessionLocal() as db:
        assert SlaService().check_and_escalate(db, now) == []
    with SessionLocal() as db:
        warnings = db.scalars(select(WorkflowAuditEvent).where(
            WorkflowAuditEvent.application_id == application_id,
            WorkflowAuditEvent.action == "SLA_WARNING",
        )).all()
        assert len(warnings) == 1
    with SessionLocal.begin() as db:
        saved = db.get(ApplicationApproval, approval_id)
        saved.sla_started_at = now - timedelta(days=16)
        saved.sla_duration_days = 15
        saved.sla_expected_completion = now - timedelta(days=1)

    with SessionLocal() as db:
        changed = SlaService().check_and_escalate(db, now)
        assert len(changed) == 1
    with SessionLocal() as db:
        saved = db.get(ApplicationApproval, approval_id)
        assert saved.status == "ESCALATED" and saved.escalated_at is not None
        events = db.scalars(select(WorkflowAuditEvent).where(
            WorkflowAuditEvent.application_id == application_id,
            WorkflowAuditEvent.action == "SLA_BREACHED",
        )).all()
        assert len(events) == 1 and events[0].details["system_actor"] is True
        notice = db.scalar(select(Notification).where(
            Notification.user_id == db.get(Application, application_id).owner_user_id,
            Notification.notification_type == "APPLICATION_ESCALATED",
        ))
        assert notice is not None and notice.is_read is False
    with SessionLocal() as db:
        assert SlaService().check_and_escalate(db, now) == []

    notices = client.get("/api/notifications?unread_only=true", headers=applicant_headers)
    assert notices.status_code == 200
    assert notices.json()["unread_count"] == 2
    notification_id = next(item["id"] for item in notices.json()["items"] if item["notification_type"] == "APPLICATION_ESCALATED")
    marked = client.patch(f"/api/notifications/{notification_id}/read", headers=applicant_headers)
    assert marked.status_code == 200 and marked.json()["is_read"] is True
    assert client.get("/api/notifications?unread_only=true", headers=applicant_headers).json()["unread_count"] == 1
    assert client.patch("/api/notifications/read-all", headers=applicant_headers).json()["updated"] == 1
    assert client.get("/api/notifications?unread_only=true", headers=applicant_headers).json()["unread_count"] == 0
    assert client.patch("/api/notifications/read-all", headers=officer_headers).status_code == 200

    applicant_sla = client.get(f"/api/applications/{application_id}/sla", headers=applicant_headers)
    assert applicant_sla.status_code == 200
    row = next(item for item in applicant_sla.json()["items"] if item["approval_id"] == approval_id)
    assert row["status"] == "ESCALATED"
    admin_login = client.post("/api/auth/login", json={
        "email": "admin@example.com", "password": "TestPassphrase2026!",
    }).json()
    admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
    assert client.get("/api/admin/escalations", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/admin/escalations", headers=applicant_headers).status_code == 403


def test_timeline_and_audit_use_saved_events_and_hide_officer_only_notes(client) -> None:
    application_id, approval_id, applicant_headers, officer_headers = _new_workflow(client, "timeline-owner@example.com")
    remark = client.post(f"/api/officer/approvals/{approval_id}/remarks", headers=officer_headers,
                         json={"message": "Internal department note."})
    assert remark.status_code == 201
    timeline = client.get(f"/api/applications/{application_id}/timeline", headers=applicant_headers)
    assert timeline.status_code == 200
    actions = [event["action"] for event in timeline.json()["events"]]
    assert "APPLICATION_CREATED" in actions and "WORKFLOW_INITIALIZED" in actions
    assert "REMARK_ADDED" not in actions
    audit = client.get(f"/api/applications/{application_id}/audit", headers=officer_headers)
    assert audit.status_code == 200
    assert "REMARK_ADDED" in [event["action"] for event in audit.json()["events"]]
