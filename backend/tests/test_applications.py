from sqlalchemy import select

from app.database import SessionLocal
from app.document_processor import ProcessorResult, get_document_processor
from app.document_processor import TesseractPyMuPDFProcessor
from app.main import app
from app.models import Application, ApplicationStatus

PASSWORD = "SecurePassphrase2026!"


def pdf_bytes(text: str) -> bytes:
    import fitz

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text)
    content = pdf.tobytes()
    pdf.close()
    return content


def register_and_authenticate(client, email: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={"full_name": "Applicant Tester", "email": email, "password": PASSWORD},
    )
    assert response.status_code == 201
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    return login.json()["access_token"]


def complete_application_payload() -> dict[str, object]:
    return {
        "applicant_name": "Applicant Tester",
        "applicant_email": "flow.applicant@example.com",
        "applicant_phone": "+91 98765 43210",
        "company_name": "Flow Manufacturing Private Limited",
        "pan": "ABCDE1234F",
        "gstin": None,
        "cin": None,
        "udyam_number": None,
        "industry_type": "Manufacturing",
        "other_industry_name": None,
        "project_type": "Greenfield manufacturing plant",
        "project_description": "A new facility to manufacture industrial components for the domestic market.",
        "investment_amount": 12500000,
        "number_of_employees": 48,
        "built_up_area": 8600,
        "power_requirement": 340,
        "water_requirement": 1250,
        "project_location": "Plot 42, Chakan Industrial Area, Pune, Maharashtra",
        "land_details": "Industrial plot leased for 30 years; possession letter available.",
        "midc_area": True,
        "midc_area_name": "Chakan MIDC Phase II",
        "pollution_category": "Green",
        "hazardous_materials": False,
        "hazardous_materials_details": None,
        "factory_information": "Single shift plant with a proposed capacity of 2500 units per month.",
        "fire_safety_information": "Sprinkler system, fire alarms, and marked emergency exits are planned.",
    }


def test_create_autosave_and_ownership_of_draft(client) -> None:
    token = register_and_authenticate(client, "draft.owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/applications", headers=headers)
    assert created.status_code == 201
    draft = created.json()
    assert draft["application_number"].startswith("MCAI-")
    assert draft["status"] == "DRAFT"
    assert draft["applicant_name"] == "Applicant Tester"
    assert draft["progress_percent"] == 0

    saved = client.patch(
        f"/api/applications/{draft['id']}",
        headers=headers,
        json={"company_name": "Draft Industries", "pan": "ABCDE1234F", "industry_type": "IT / Software"},
    )
    assert saved.status_code == 200
    assert saved.json()["risk_tier"] is None
    assert saved.json()["company_name"] == "Draft Industries"
    assert client.get(f"/api/applications/{draft['id']}", headers=headers).json()["pan"] == "ABCDE1234F"

    other_token = register_and_authenticate(client, "draft.other@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert client.get(f"/api/applications/{draft['id']}", headers=other_headers).status_code == 404

    negative = client.patch(
        f"/api/applications/{draft['id']}", headers=headers, json={"investment_amount": -1}
    )
    assert negative.status_code == 422


def test_submit_requires_valid_data_and_document_then_locks_application(client) -> None:
    token = register_and_authenticate(client, "flow.applicant@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    application = client.post("/api/applications", headers=headers).json()
    application_id = application["id"]

    incomplete = client.post(f"/api/applications/{application_id}/submit", headers=headers)
    assert incomplete.status_code == 422
    assert incomplete.json()["detail"]["fields"]

    saved = client.patch(
        f"/api/applications/{application_id}",
        headers=headers,
        json=complete_application_payload(),
    )
    assert saved.status_code == 200
    assert saved.json()["progress_percent"] < 100

    invalid_document = client.post(
        f"/api/applications/{application_id}/documents",
        headers=headers,
        data={"document_type": "SITE_PLAN"},
        files={"file": ("plan.exe", b"not a supported file type", "application/octet-stream")},
    )
    assert invalid_document.status_code == 415

    content = pdf_bytes("MAHACLEAR sample site plan")
    upload = client.post(
        f"/api/applications/{application_id}/documents",
        headers=headers,
        data={"document_type": "SITE_PLAN"},
        files={"file": ("site-plan.pdf", content, "application/pdf")},
    )
    assert upload.status_code == 201
    document = upload.json()
    assert document["file_name"] == "site-plan.pdf"
    assert document["size_bytes"] == len(content)

    before_submit = client.get(f"/api/applications/{application_id}", headers=headers).json()
    assert before_submit["progress_percent"] == 88
    assert before_submit["risk_tier"] is None
    assert len(before_submit["documents"]) == 1
    downloaded = client.get(
        f"/api/applications/{application_id}/documents/{document['id']}/download", headers=headers
    )
    assert downloaded.status_code == 200
    assert downloaded.content == content

    for category, label in (
        ("PAN", "pan"),
        ("LAND_OWNERSHIP_LEASE", "land"),
        ("PROJECT_REPORT", "project"),
        ("ENVIRONMENTAL_DOCUMENTS", "environment"),
        ("FIRE_SAFETY_DOCUMENTS", "fire"),
        ("FACTORY_DOCUMENTS", "factory"),
        ("IDENTITY_DOCUMENT", "identity"),
    ):
        extra = client.post(
            f"/api/applications/{application_id}/documents",
            headers=headers,
            data={"document_type": category},
            files={"file": (f"{label}.pdf", pdf_bytes(f"unique {label}"), "application/pdf")},
        )
        assert extra.status_code == 201

    checked = client.post(f"/api/applications/{application_id}/prevalidation/run", headers=headers)
    assert checked.status_code == 200
    assert checked.json()["can_submit"] is True

    submitted = client.post(f"/api/applications/{application_id}/submit", headers=headers)
    assert submitted.status_code == 200
    data = submitted.json()
    assert data["status"] == "SUBMITTED"
    assert data["progress_percent"] == 100
    assert data["application_number"] == application["application_number"]
    assert data["submitted_at"] is not None
    assert data["expected_completion_at"] is None
    assert client.patch(f"/api/applications/{application_id}", headers=headers, json={"company_name": "Edit"}).status_code == 409
    assert client.post(f"/api/applications/{application_id}/submit", headers=headers).status_code == 409


def test_document_signature_size_duplicate_and_replace(client) -> None:
    token = register_and_authenticate(client, "documents.owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    application = client.post("/api/applications", headers=headers).json()
    application_id = application["id"]

    forged = client.post(
        f"/api/applications/{application_id}/documents", headers=headers,
        data={"document_type": "PAN"},
        files={"file": ("fake.pdf", b"not actually a PDF", "application/pdf")},
    )
    assert forged.status_code == 415
    damaged = client.post(
        f"/api/applications/{application_id}/documents", headers=headers,
        data={"document_type": "PAN"},
        files={"file": ("damaged.pdf", b"%PDF-1.4\\nnot a PDF structure", "application/pdf")},
    )
    assert damaged.status_code == 422
    too_large = client.post(
        f"/api/applications/{application_id}/documents", headers=headers,
        data={"document_type": "PAN"},
        files={"file": ("large.pdf", b"%PDF-" + b"x" * (15 * 1024 * 1024), "application/pdf")},
    )
    assert too_large.status_code == 413

    content = pdf_bytes("PAN file")
    first = client.post(
        f"/api/applications/{application_id}/documents", headers=headers,
        data={"document_type": "PAN"}, files={"file": ("pan.pdf", content, "application/pdf")},
    )
    assert first.status_code == 201
    document = first.json()
    duplicate = client.post(
        f"/api/applications/{application_id}/documents", headers=headers,
        data={"document_type": "IDENTITY_DOCUMENT"},
        files={"file": ("copy.pdf", content, "application/pdf")},
    )
    assert duplicate.status_code == 201
    result = client.post(f"/api/applications/{application_id}/prevalidation/run", headers=headers).json()
    assert any(issue["code"] == "DUPLICATE" for issue in result["issues"])

    replacement_content = pdf_bytes("Replacement copy")
    replacement = client.post(
        f"/api/applications/{application_id}/documents/{document['id']}/replace", headers=headers,
        files={"file": ("new-pan.pdf", replacement_content, "application/pdf")},
    )
    assert replacement.status_code == 200
    assert replacement.json()["id"] == document["id"]
    assert replacement.json()["file_name"] == "new-pan.pdf"
    download = client.get(
        f"/api/applications/{application_id}/documents/{document['id']}/download", headers=headers
    )
    assert download.content == replacement_content


def test_prevalidation_required_categories_and_read_endpoint(client) -> None:
    token = register_and_authenticate(client, "validation.owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    application = client.post("/api/applications", headers=headers).json()
    application_id = application["id"]
    result = client.get(f"/api/applications/{application_id}/prevalidation", headers=headers)
    assert result.status_code == 200
    payload = result.json()
    assert payload["overall_status"] == "MISSING"
    assert payload["can_submit"] is False
    assert payload["counts"]["MISSING"] == 8


def test_pan_consistency_is_reported_as_invalid(client) -> None:
    class MismatchProcessor:
        def process(self, path: str, media_type: str) -> ProcessorResult:
            return ProcessorResult(
                extracted_text="Permanent Account Number ABCDE1234F",
                fields={"pan": "ABCDE1234F"},
            )

    token = register_and_authenticate(client, "pan.check@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    application = client.post("/api/applications", headers=headers).json()
    application_id = application["id"]
    client.patch(f"/api/applications/{application_id}", headers=headers, json={"pan": "FGHIJ5678K"})
    app.dependency_overrides[get_document_processor] = MismatchProcessor
    try:
        uploaded = client.post(
            f"/api/applications/{application_id}/documents", headers=headers,
            data={"document_type": "PAN"},
            files={"file": ("pan.pdf", pdf_bytes("PAN content"), "application/pdf")},
        )
        assert uploaded.status_code == 201
        result = client.get(f"/api/applications/{application_id}/prevalidation", headers=headers).json()
        assert result["overall_status"] == "INVALID"
        assert any(issue["code"] == "PAN_MISMATCH" for issue in result["issues"])
    finally:
        app.dependency_overrides.pop(get_document_processor, None)


def test_pymupdf_processor_extracts_pdf_text_and_identifiers(tmp_path) -> None:
    import fitz

    path = tmp_path / "registration.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "PAN ABCDE1234F GSTIN 27ABCDE1234F1Z5")
    pdf.save(path)
    pdf.close()

    result = TesseractPyMuPDFProcessor().process(str(path), "application/pdf")
    assert result.readable is True
    assert result.fields["pan"] == "ABCDE1234F"
    assert result.fields["gstin"] == "27ABCDE1234F1Z5"


def test_dashboard_counters_and_application_list(client) -> None:
    token = register_and_authenticate(client, "dashboard.owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    app_ids = [client.post("/api/applications", headers=headers).json()["id"] for _ in range(6)]
    statuses = [
        ApplicationStatus.DRAFT.value,
        ApplicationStatus.SUBMITTED.value,
        ApplicationStatus.IN_REVIEW.value,
        ApplicationStatus.ACTION_REQUIRED.value,
        ApplicationStatus.APPROVED.value,
        ApplicationStatus.REJECTED.value,
    ]
    with SessionLocal.begin() as db:
        for application_id, application_status in zip(app_ids, statuses):
            application = db.scalar(select(Application).where(Application.id == application_id))
            application.status = application_status

    response = client.get("/api/applications", headers=headers)
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary == {
        "total_applications": 6,
        "pending": 2,
        "approved": 1,
        "rejected": 1,
        "action_required": 1,
    }
    assert len(response.json()["applications"]) == 6
    assert client.get("/api/applications").status_code == 401
