import pytest

from app.database import SessionLocal
from app.models import Application, ApplicationDocument

PASSWORD = "SecurePassphrase2026!"


def applicant_headers(client, email):
    created = client.post("/api/auth/register", json={
        "full_name": "Requirements Tester", "email": email, "password": PASSWORD,
    })
    assert created.status_code == 201
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def create_draft(client, headers):
    return client.post("/api/applications", headers=headers).json()["id"]


def ready_payload(**overrides):
    return {
        "applicant_name": "Requirements Tester", "applicant_email": "requirements@example.com",
        "applicant_phone": "+91 98765 43210", "company_name": "North Star Components Private Limited",
        "pan": "ABCDE1234F", "industry_type": "Chemical", "project_type": "Chemical manufacturing",
        "project_description": "A chemical manufacturing project with controlled process equipment and safety controls.",
        "investment_amount": 15000000, "number_of_employees": 44, "built_up_area": 6200,
        "power_requirement": 400, "water_requirement": 900,
        "project_location": "Plot 18, Taloja Industrial Area, Navi Mumbai, Maharashtra",
        "land_details": "Long-term industrial lease with possession records available.",
        "midc_area": True, "midc_area_name": "Taloja MIDC", "pollution_category": "Red",
        "hazardous_materials": True, "hazardous_materials_details": "Solvents and process chemicals stored in controlled areas.",
        "factory_information": "Proposed factory includes production and storage areas.",
        "fire_safety_information": "Fire alarm, hydrants, suppression and marked egress are proposed.",
        **overrides,
    }


def requirement_payload(client, application_id, headers):
    response = client.get(f"/api/applications/{application_id}/requirements", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_basic_profile_is_limited_to_configured_baseline(client):
    headers = applicant_headers(client, "requirements.basic@example.com")
    application_id = create_draft(client, headers)
    result = requirement_payload(client, application_id, headers)
    assert {item["document_type"] for item in result["required_documents"]} == {
        "PAN", "LAND_OWNERSHIP_LEASE", "BUILDING_PLAN", "PROJECT_REPORT", "IDENTITY_DOCUMENT",
    }
    assert not [item for item in result["approvals"] if item["applicable"]]
    assert result["submission_ready"] is False
    assert result["counts"]["missing"] == 5


def test_chemical_hazardous_mipc_midc_factory_fire_conditions_are_dynamic(client):
    headers = applicant_headers(client, "requirements.chemical@example.com")
    application_id = create_draft(client, headers)
    saved = client.patch(f"/api/applications/{application_id}", headers=headers, json=ready_payload())
    assert saved.status_code == 200, saved.text
    result = requirement_payload(client, application_id, headers)
    applicable = {item["department"] for item in result["approvals"] if item["applicable"]}
    assert applicable == {"MPCB", "MIDC", "DISH", "FIRE_SERVICES"}
    required = {item["document_type"] for item in result["required_documents"]}
    assert {"ENVIRONMENTAL_DOCUMENTS", "LAND_OWNERSHIP_LEASE", "BUILDING_PLAN",
            "FACTORY_DOCUMENTS", "FIRE_SAFETY_DOCUMENTS", "PROJECT_REPORT"}.issubset(required)
    assert all(item["reason"] for item in result["required_documents"])
    assert result["submission_ready"] is False


def test_profile_edit_adds_and_removes_conditional_requirements(client):
    headers = applicant_headers(client, "requirements.dynamic@example.com")
    application_id = create_draft(client, headers)
    client.patch(f"/api/applications/{application_id}", headers=headers, json={
        "industry_type": "IT / Software", "pollution_category": "White", "midc_area": False,
        "hazardous_materials": False, "project_type": "Software office",
    })
    it_result = requirement_payload(client, application_id, headers)
    assert "FIRE_SAFETY_DOCUMENTS" not in {row["document_type"] for row in it_result["required_documents"]}
    client.patch(f"/api/applications/{application_id}", headers=headers, json={
        "industry_type": "Manufacturing", "pollution_category": "Green", "project_type": "Component factory",
    })
    factory_result = requirement_payload(client, application_id, headers)
    assert {"MPCB", "DISH", "FIRE_SERVICES"}.issubset({row["department"] for row in factory_result["approvals"] if row["applicable"]})
    assert "FIRE_SAFETY_DOCUMENTS" in {row["document_type"] for row in factory_result["required_documents"]}


def test_location_registration_and_pollution_conditions_change_approval_set(client):
    headers = applicant_headers(client, "requirements.conditions@example.com")
    application_id = create_draft(client, headers)
    client.patch(f"/api/applications/{application_id}", headers=headers, json={
        "industry_type": "IT / Software", "pollution_category": "White", "midc_area": False,
        "gstin": "27ABCDE1234F1Z5", "cin": "U12345MH2020PTC123456", "udyam_number": "UDYAM-MH-01-0000001",
    })
    result = requirement_payload(client, application_id, headers)
    depts = {row["department"] for row in result["approvals"] if row["applicable"]}
    assert depts == {"GSTN", "MCA21", "UDYAM"}
    client.patch(f"/api/applications/{application_id}", headers=headers, json={"midc_area": True})
    result = requirement_payload(client, application_id, headers)
    assert "MIDC" in {row["department"] for row in result["approvals"] if row["applicable"]}


@pytest.mark.parametrize(("values", "expected"), [
    ({"industry_type": "IT / Software", "pollution_category": "Green"}, {"MPCB"}),
    ({"industry_type": "IT / Software", "pollution_category": "White", "hazardous_materials": True}, {"MPCB", "DISH", "FIRE_SERVICES"}),
    ({"industry_type": "IT / Software", "pollution_category": "White", "project_type": "Chemical processing unit"}, {"MPCB", "DISH", "FIRE_SERVICES"}),
    ({"industry_type": "IT / Software", "pollution_category": "White", "project_type": "Factory expansion"}, {"DISH", "FIRE_SERVICES"}),
    ({"industry_type": "IT / Software", "pollution_category": "White", "built_up_area": 25000}, {"DISH", "FIRE_SERVICES"}),
    ({"industry_type": "IT / Software", "pollution_category": "White", "number_of_employees": 20}, {"DISH"}),
    ({"industry_type": "Logistics", "pollution_category": "White", "midc_area": True}, {"MIDC"}),
])
def test_configured_profile_triggers(client, values, expected):
    headers = applicant_headers(client, f"requirements.triggers.{abs(hash(str(values)))}@example.com")
    application_id = create_draft(client, headers)
    defaults = {"industry_type": "IT / Software", "pollution_category": "White", "hazardous_materials": False,
                "project_type": "Office", "built_up_area": 1000, "number_of_employees": 5, "midc_area": False}
    response = client.patch(f"/api/applications/{application_id}", headers=headers, json={**defaults, **values})
    assert response.status_code == 200, response.text
    result = requirement_payload(client, application_id, headers)
    assert {row["department"] for row in result["approvals"] if row["applicable"]} == expected


def test_uploaded_correction_and_expired_statuses_are_distinct(client):
    from app.models import ApplicationValidationIssue

    headers = applicant_headers(client, "requirements.document-states@example.com")
    application_id = create_draft(client, headers)
    with SessionLocal.begin() as db:
        db.add_all([
            ApplicationDocument(application_id=application_id, document_type="PAN", file_name="pan.pdf",
                storage_key="unused-uploaded-key", media_type="application/pdf", size_bytes=64,
                sha256="c" * 64, status="UPLOADED"),
            ApplicationDocument(application_id=application_id, document_type="IDENTITY_DOCUMENT", file_name="id.pdf",
                storage_key="unused-warning-key", media_type="application/pdf", size_bytes=64,
                sha256="d" * 64, status="WARNING"),
            ApplicationDocument(application_id=application_id, document_type="PROJECT_REPORT", file_name="project.pdf",
                storage_key="unused-expired-key", media_type="application/pdf", size_bytes=64,
                sha256="e" * 64, status="INVALID"),
        ])
        db.flush()
        docs = db.query(ApplicationDocument).filter(ApplicationDocument.application_id == application_id).all()
        db.add(ApplicationValidationIssue(application_id=application_id, document_id=docs[2].id,
            document_type="PROJECT_REPORT", code="EXPIRED", status="INVALID", message="Document appears to have expired."))
    rows = {row["document_type"]: row["status"] for row in requirement_payload(client, application_id, headers)["documents"]}
    assert rows["PAN"] == "UPLOADED"
    assert rows["IDENTITY_DOCUMENT"] == "NEEDS_CORRECTION"
    assert rows["PROJECT_REPORT"] == "EXPIRED"


def test_document_statuses_include_missing_optional_and_current_upload(client):
    headers = applicant_headers(client, "requirements.status@example.com")
    application_id = create_draft(client, headers)
    result = requirement_payload(client, application_id, headers)
    by_type = {row["document_type"]: row for row in result["documents"]}
    assert by_type["PAN"]["status"] == "MISSING"
    assert by_type["GST_CERTIFICATE"]["status"] == "NOT_REQUIRED"
    assert by_type["GST_CERTIFICATE"]["requirement_type"] == "NOT_REQUIRED"
    with SessionLocal.begin() as db:
        db.add(ApplicationDocument(application_id=application_id, document_type="PAN", file_name="pan.pdf",
            storage_key="unused-test-key", media_type="application/pdf", size_bytes=64,
            sha256="a" * 64, status="VALID"))
    result = requirement_payload(client, application_id, headers)
    by_type = {row["document_type"]: row for row in result["documents"]}
    assert by_type["PAN"]["status"] == "VALID"
    assert by_type["PAN"]["uploaded_document_id"] is not None
    assert result["counts"]["valid"] == 1


def test_invalid_document_validation_is_reported_and_blocks_submission(client):
    from app.models import ApplicationValidationIssue

    headers = applicant_headers(client, "requirements.invalid@example.com")
    application_id = create_draft(client, headers)
    client.patch(f"/api/applications/{application_id}", headers=headers, json=ready_payload())
    with SessionLocal.begin() as db:
        application = db.get(Application, application_id)
        document = ApplicationDocument(application_id=application_id, document_type="PAN", file_name="wrong-pan.pdf",
            storage_key="unused-invalid-key", media_type="application/pdf", size_bytes=64,
            sha256="b" * 64, status="INVALID")
        db.add(document)
        db.flush()
        db.add(ApplicationValidationIssue(application_id=application_id, document_id=document.id, document_type="PAN",
            code="PAN_MISMATCH", status="INVALID", message="PAN does not match the application details."))
    result = requirement_payload(client, application_id, headers)
    assert next(row for row in result["documents"] if row["document_type"] == "PAN")["status"] == "INVALID"
    submitted = client.post(f"/api/applications/{application_id}/submit", headers=headers)
    assert submitted.status_code == 422
    detail = submitted.json()["detail"]
    assert any(row["document_type"] == "PAN" for row in detail["invalid_documents"])
    assert detail["upload_url"].endswith("/prevalidation")


def test_submission_block_returns_exact_dynamic_missing_types(client):
    headers = applicant_headers(client, "requirements.submit@example.com")
    application_id = create_draft(client, headers)
    client.patch(f"/api/applications/{application_id}", headers=headers, json=ready_payload())
    response = client.post(f"/api/applications/{application_id}/submit", headers=headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    missing = {row["document_type"] for row in detail["missing_documents"]}
    assert {"ENVIRONMENTAL_DOCUMENTS", "FIRE_SAFETY_DOCUMENTS", "FACTORY_DOCUMENTS"}.issubset(missing)
    assert detail["message"].startswith("Application cannot be submitted")


def test_applicant_cannot_read_another_users_requirements(client):
    owner_headers = applicant_headers(client, "requirements.owner@example.com")
    other_headers = applicant_headers(client, "requirements.other@example.com")
    application_id = create_draft(client, owner_headers)
    assert client.get(f"/api/applications/{application_id}/requirements", headers=other_headers).status_code == 404


def test_requirements_api_is_role_protected(client):
    token = client.post("/api/auth/login", json={"email": "officer@example.com", "password": "TestPassphrase2026!"}).json()["access_token"]
    response = client.get("/api/applications/1/requirements", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
