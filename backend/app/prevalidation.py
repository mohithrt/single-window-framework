from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Application, ApplicationDocument, ApplicationValidationIssue

DOCUMENT_LABELS = {
    "PAN": "PAN",
    "GST_CERTIFICATE": "GST certificate",
    "UDYAM_CERTIFICATE": "Udyam certificate",
    "INCORPORATION_CERTIFICATE": "Incorporation certificate",
    "LAND_OWNERSHIP_LEASE": "Land ownership / lease documents",
    "BUILDING_PLAN": "Building plan",
    "PROJECT_REPORT": "Project report",
    "ENVIRONMENTAL_DOCUMENTS": "Environmental documents",
    "FIRE_SAFETY_DOCUMENTS": "Fire safety documents",
    "FACTORY_DOCUMENTS": "Factory documents",
    "IDENTITY_DOCUMENT": "Identity documents",
    "OTHER_SUPPORTING": "Other supporting documents",
}

# Baseline submission checklist. GST/Udyam/incorporation are optional where the
# applicant does not have those registrations; submitted files are still checked.
REQUIRED_DOCUMENTS = {
    "PAN", "LAND_OWNERSHIP_LEASE", "BUILDING_PLAN", "PROJECT_REPORT",
    "ENVIRONMENTAL_DOCUMENTS", "FIRE_SAFETY_DOCUMENTS", "FACTORY_DOCUMENTS",
    "IDENTITY_DOCUMENT",
}
EXPECTED_FIELDS = {
    "PAN": "pan",
    "GST_CERTIFICATE": "gstin",
    "INCORPORATION_CERTIFICATE": "cin",
    "UDYAM_CERTIFICATE": "udyam_number",
}
SEVERITY = {"VALID": 0, "WARNING": 1, "INVALID": 2, "MISSING": 2}


def run_prevalidation(db: Session, application: Application) -> list[ApplicationValidationIssue]:
    documents = list(application.documents)
    db.execute(delete(ApplicationValidationIssue).where(ApplicationValidationIssue.application_id == application.id))
    issues: list[ApplicationValidationIssue] = []

    def add(document_type: str, code: str, status: str, message: str,
            document: ApplicationDocument | None = None, detected: str | None = None,
            expected: str | None = None) -> None:
        issues.append(ApplicationValidationIssue(
            application_id=application.id,
            document_id=document.id if document else None,
            document_type=document_type,
            code=code,
            status=status,
            message=message,
            detected_value=detected,
            expected_value=expected,
        ))

    by_type: dict[str, list[ApplicationDocument]] = {}
    for document in documents:
        by_type.setdefault(document.document_type, []).append(document)
        if document.status == "INVALID":
            add(document.document_type, "FILE_INVALID", "INVALID", "File validation failed.", document)
        if document.sha256 and sum(other.sha256 == document.sha256 for other in documents) > 1:
            add(document.document_type, "DUPLICATE", "INVALID", "Duplicate file uploaded to this application.", document)
        if not document.extracted_text or len(document.extracted_text.strip()) < 8:
            add(document.document_type, "OCR_UNREADABLE", "WARNING", "Text could not be read; verify this document manually.", document)
        for field, expected in EXPECTED_FIELDS.items():
            if document.document_type != field:
                continue
            app_value = getattr(application, expected, None)
            detected = (document.extracted_fields or {}).get(expected)
            if detected and app_value and detected.upper() != app_value.upper():
                add(document.document_type, f"{expected.upper()}_MISMATCH", "INVALID",
                    f"{field} does not match the application details.", document, detected, app_value)
            elif not detected or not app_value:
                add(document.document_type, f"{expected.upper()}_NOT_READ", "WARNING",
                    f"Could not verify {field} against the application details.", document,
                    detected=detected, expected=app_value)

        expiry = (document.extracted_fields or {}).get("expiry_date")
        if expiry:
            try:
                if date.fromisoformat(expiry) < datetime.now(timezone.utc).date():
                    add(document.document_type, "EXPIRED", "INVALID", "Document appears to have expired.", document, expiry)
            except ValueError:
                add(document.document_type, "EXPIRY_UNCLEAR", "WARNING", "Expiry date could not be interpreted.", document, expiry)

    for document_type in sorted(REQUIRED_DOCUMENTS - by_type.keys()):
        add(document_type, "REQUIRED_MISSING", "MISSING", f"{DOCUMENT_LABELS[document_type]} is required.")

    db.add_all(issues)
    db.flush()
    by_id: dict[int, list[str]] = {}
    for issue in issues:
        if issue.document_id:
            by_id.setdefault(issue.document_id, []).append(issue.status)
    for document in documents:
        document.status = max(by_id.get(document.id, ["VALID"]), key=SEVERITY.__getitem__)
    db.flush()
    return issues


def prevalidation_payload(application: Application, issues: list[ApplicationValidationIssue]) -> dict:
    issue_dicts = [{
        "id": item.id,
        "document_id": item.document_id,
        "document_type": item.document_type,
        "document_label": DOCUMENT_LABELS.get(item.document_type, item.document_type),
        "code": item.code,
        "status": item.status,
        "message": item.message,
        "detected_value": item.detected_value,
        "expected_value": item.expected_value,
        "created_at": item.created_at,
    } for item in issues]
    result = []
    for code, label in DOCUMENT_LABELS.items():
        matching = [item for item in issue_dicts if item["document_type"] == code]
        docs = [doc for doc in application.documents if doc.document_type == code]
        statuses = [item["status"] for item in matching]
        status = max(statuses, key=SEVERITY.__getitem__) if statuses else ("VALID" if docs else ("MISSING" if code in REQUIRED_DOCUMENTS else "WARNING"))
        result.append({
            "document_type": code,
            "document_label": label,
            "status": status,
            "required": code in REQUIRED_DOCUMENTS,
            "documents": [{"id": d.id, "file_name": d.file_name, "status": d.status} for d in docs],
            "issues": matching,
        })
    counts = {key: sum(1 for item in result if item["status"] == key) for key in SEVERITY}
    return {
        "application_id": application.id,
        "application_number": application.application_number,
        "overall_status": "INVALID" if counts["INVALID"] else "MISSING" if counts["MISSING"] else "WARNING" if counts["WARNING"] else "VALID",
        "counts": counts,
        "can_submit": not counts["INVALID"] and not counts["MISSING"],
        "documents": result,
        "issues": issue_dicts,
        "checked_at": datetime.now(timezone.utc),
    }
