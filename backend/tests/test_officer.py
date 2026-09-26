from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Application, ApplicationApproval, ApplicationStatus, Inspection, InspectionParticipant,
    WorkflowAuditEvent,
)


def _login(client, email: str) -> dict[str, str]:
    result = client.post("/api/auth/login", json={
        "email": email, "password": "TestPassphrase2026!",
    })
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def _submitted_application(client, email: str = "officer-queue-owner@example.com") -> tuple[int, int, dict[str, str]]:
    registered = client.post("/api/auth/register", json={
        "full_name": "Queue Applicant", "email": email,
        "password": "SecurePassphrase2026!",
    })
    assert registered.status_code == 201
    login = client.post("/api/auth/login", json={
        "email": email, "password": "SecurePassphrase2026!",
    })
    assert login.status_code == 200
    applicant_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    draft = client.post("/api/applications", headers=applicant_headers)
    assert draft.status_code == 201
    application_id = draft.json()["id"]
    with SessionLocal.begin() as db:
        application = db.get(Application, application_id)
        application.status = ApplicationStatus.SUBMITTED.value
        application.company_name = "Queue Manufacturing"
        application.applicant_name = "Queue Applicant"
        application.applicant_email = email
        application.industry_type = "Chemical"
        application.risk_tier = "HIGH"
        application.submitted_at = datetime.now(UTC)
    approvals = client.get(f"/api/applications/{application_id}/approvals", headers=applicant_headers)
    assert approvals.status_code == 200
    mpcb_id = next(item["id"] for item in approvals.json()["approvals"] if item["department_code"] == "MPCB")
    return application_id, mpcb_id, applicant_headers


def test_officer_portal_requires_officer_role_and_queue_filters(client) -> None:
    application_id, approval_id, applicant_headers = _submitted_application(client)
    assert client.get("/api/officer/dashboard", headers=applicant_headers).status_code == 403
    assert client.get(f"/api/officer/approvals/{approval_id}", headers=applicant_headers).status_code == 403

    officer_headers = _login(client, "officer@example.com")
    dashboard = client.get("/api/officer/dashboard", headers=officer_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["pending_applications"] >= 1
    assert dashboard.json()["high_risk"] >= 1

    response = client.get("/api/officer/queue?search=Queue%20Manufacturing&risk=HIGH&status=PENDING", headers=officer_headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert all(item["application_id"] == application_id for item in response.json()["items"])
    assert any(item["approval_id"] == approval_id for item in response.json()["items"])
    assert client.get("/api/officer/queue?risk=INVALID", headers=officer_headers).status_code == 422


def test_review_actions_persist_and_internal_remarks_are_private(client) -> None:
    application_id, approval_id, applicant_headers = _submitted_application(client, "officer-action-owner@example.com")
    officer_headers = _login(client, "officer@example.com")

    detail = client.get(f"/api/officer/approvals/{approval_id}", headers=officer_headers)
    assert detail.status_code == 200
    assert detail.json()["applicant"]["email"] == "officer-action-owner@example.com"
    assert detail.json()["application"]["company_name"] == "Queue Manufacturing"
    assert "documents" in detail.json() and "prevalidation" in detail.json()
    assert "other_department_statuses" in detail.json() and "audit_history" in detail.json()

    assert client.post(f"/api/approvals/{approval_id}/start-review", headers=officer_headers).status_code == 200
    assert client.post(f"/api/approvals/{approval_id}/reject", headers=officer_headers, json={}).status_code == 422
    assert client.post(f"/api/approvals/{approval_id}/request-correction", headers=officer_headers, json={}).status_code == 422

    remark = client.post(f"/api/officer/approvals/{approval_id}/remarks", headers=officer_headers,
                         json={"message": "Check the pollution control board consent details."})
    assert remark.status_code == 201
    applicant_view = client.get(f"/api/applications/{application_id}/approvals", headers=applicant_headers)
    assert applicant_view.status_code == 200
    assert all(event["action"] != "REMARK_ADDED" for event in applicant_view.json()["audit_events"])

    correction = client.post(f"/api/approvals/{approval_id}/request-correction", headers=officer_headers,
                             json={"message": "Please provide the signed consent document."})
    assert correction.status_code == 200
    assert correction.json()["status"] == "DOCUMENT_CORRECTION"
    with SessionLocal() as db:
        approval = db.get(ApplicationApproval, approval_id)
        assert approval.status == "DOCUMENT_CORRECTION"
        events = db.scalars(select(WorkflowAuditEvent).where(
            WorkflowAuditEvent.application_id == application_id,
        )).all()
        private_remark = next(event for event in events if event.action == "REMARK_ADDED")
        assert private_remark.details == {"visibility": "OFFICER"}
        assert any(event.action == "CORRECTION_REQUESTED" for event in events)

    premature = client.post(f"/api/approvals/{approval_id}/correction-submitted", headers=applicant_headers)
    assert premature.status_code == 409
    updated = client.patch(f"/api/applications/{application_id}", headers=applicant_headers,
                           json={"project_description": "Updated project details addressing the department clarification request."})
    assert updated.status_code == 200
    status_after_edit = client.get(f"/api/applications/{application_id}/approvals", headers=applicant_headers).json()
    mpcb = next(item for item in status_after_edit["approvals"] if item["id"] == approval_id)
    assert mpcb["correction_can_submit"] is True
    assert client.post(f"/api/approvals/{approval_id}/correction-submitted", headers=applicant_headers).status_code == 200
    assert client.post(f"/api/approvals/{approval_id}/start-review", headers=officer_headers).status_code == 200
    rejected = client.post(f"/api/approvals/{approval_id}/reject", headers=officer_headers,
                           json={"reason": "The submitted consent certificate is expired."})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    with SessionLocal() as db:
        saved = db.get(ApplicationApproval, approval_id)
        assert saved.status == "REJECTED"
        assert saved.decision_message == "The submitted consent certificate is expired."


def test_officer_can_schedule_and_list_single_and_joint_inspections(client) -> None:
    application_id, approval_id, applicant_headers = _submitted_application(client, "officer-inspection-owner@example.com")
    officer_headers = _login(client, "officer@example.com")
    assert client.post(f"/api/approvals/{approval_id}/start-review", headers=officer_headers).status_code == 200

    scheduled_at = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    inspection = client.post(f"/api/officer/approvals/{approval_id}/inspections", headers=officer_headers, json={
        "inspection_type": "SINGLE", "scheduled_at": scheduled_at,
        "location": "Chakan MIDC, Pune", "instructions": "Bring fire and environment officers.",
    })
    assert inspection.status_code == 201, inspection.text
    assert inspection.json()["inspection_type"] == "SINGLE"
    assert inspection.json()["status"] == "SCHEDULED"

    listed = client.get("/api/officer/inspections?inspection_type=SINGLE", headers=officer_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["location"] == "Chakan MIDC, Pune"
    joint = client.get("/api/officer/inspections?inspection_type=JOINT", headers=officer_headers)
    assert joint.status_code == 200 and joint.json()["total"] == 0
    image = b"\x89PNG\r\n\x1a\n" + b"demo-png-content"
    uploaded_photo = client.post(f"/api/officer/inspections/{inspection.json()['id']}/photos",
                                 headers=officer_headers,
                                 files=[("files", ("visit.png", image, "image/png"))])
    assert uploaded_photo.status_code == 201, uploaded_photo.text
    photo = client.get(f"/api/officer/inspections/{inspection.json()['id']}/photos/0", headers=officer_headers)
    assert photo.status_code == 200 and photo.content == image
    applicant_photos = client.get(f"/api/applications/{application_id}/inspections", headers=applicant_headers)
    assert applicant_photos.status_code == 200
    photo_url = applicant_photos.json()["items"][0]["photos"][0]["download_url"]
    assert photo_url.endswith(f"/single/{inspection.json()['id']}/photos/0")
    assert client.get(photo_url, headers=applicant_headers).content == image
    in_progress = client.patch(f"/api/officer/inspections/{inspection.json()['id']}", headers=officer_headers,
                               json={"status": "IN_PROGRESS", "findings": "Site walk-through started."})
    assert in_progress.status_code == 200
    completed = client.patch(f"/api/officer/inspections/{inspection.json()['id']}", headers=officer_headers,
                             json={"status": "COMPLETED", "recommendation": "Approve after checklist closure."})
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    with SessionLocal() as db:
        saved = db.scalar(select(Inspection).where(Inspection.approval_id == approval_id))
        assert saved is not None and saved.inspection_type == "SINGLE"
        approval = db.get(ApplicationApproval, approval_id)
        assert approval.status == "IN_REVIEW"
        event = db.scalar(select(WorkflowAuditEvent).where(
            WorkflowAuditEvent.approval_id == approval_id,
            WorkflowAuditEvent.action == "INSPECTION_SCHEDULED",
        ))
        assert event is not None


def test_joint_inspection_participants_completion_audit_and_notifications(client) -> None:
    application_id, _approval_id, applicant_headers = _submitted_application(client, "joint-owner@example.com")
    officer_headers = _login(client, "officer@example.com")
    with SessionLocal() as db:
        approval_ids = db.scalars(select(ApplicationApproval.id).where(
            ApplicationApproval.application_id == application_id,
            ApplicationApproval.department_code.in_(["MPCB", "DISH"]),
        )).all()
    assert len(approval_ids) == 2
    scheduled_at = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    response = client.post("/api/officer/joint-inspections", headers=officer_headers, json={
        "application_id": application_id, "approval_ids": approval_ids,
        "scheduled_at": scheduled_at, "site": "Chakan MIDC, Pune",
        "instructions": "Fire, safety, and pollution review in one visit.",
        "checklist": [{"item": "PPE available", "required": True}],
    })
    assert response.status_code == 201, response.text
    joint_id = response.json()["id"]
    assert {row["department_code"] for row in response.json()["participants"]} == {"MPCB", "DISH"}
    listed = client.get("/api/officer/inspections?inspection_type=JOINT", headers=officer_headers)
    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == joint_id

    running = client.patch(f"/api/officer/joint-inspections/{joint_id}", headers=officer_headers,
                           json={"status": "IN_PROGRESS", "findings": "Site walk-through started."})
    assert running.status_code == 200 and running.json()["status"] == "IN_PROGRESS"
    complete = client.patch(f"/api/officer/joint-inspections/{joint_id}", headers=officer_headers, json={
        "status": "COMPLETED", "findings": "All safety exits were verified.",
        "recommendation": "Approve subject to the submitted fire plan.",
        "remarks": "Inspectors agreed the site is ready.",
    })
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "COMPLETED"
    applicant_notice = client.get("/api/notifications", headers=applicant_headers).json()
    assert any(item["notification_type"] == "JOINT_INSPECTION_SCHEDULED" for item in applicant_notice["items"])
    assert any(item["notification_type"] == "INSPECTION_COMPLETED" for item in applicant_notice["items"])
    assert client.patch(f"/api/notifications/{applicant_notice['items'][0]['id']}/read",
                        headers=applicant_headers).status_code == 200
    timeline = client.get(f"/api/applications/{application_id}/timeline", headers=applicant_headers).json()
    assert any(row["action"] == "INSPECTION_COMPLETED" for row in timeline["events"])
    with SessionLocal() as db:
        participants = db.scalars(select(InspectionParticipant).where(
            InspectionParticipant.joint_inspection_id == joint_id
        )).all()
        assert len(participants) == 2 and all(participant.status == "COMPLETED" for participant in participants)
        statuses = db.scalars(select(ApplicationApproval.status).where(
            ApplicationApproval.id.in_(approval_ids)
        )).all()
        assert statuses == ["IN_REVIEW", "IN_REVIEW"]
