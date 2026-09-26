from datetime import UTC, datetime
import hashlib
from io import BytesIO
from pathlib import Path
import re
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.application_progress import application_progress, submission_errors
from app.application_schemas import (
    ApplicantApplicationsResponse,
    ApplicationDocumentRead,
    ApplicationDraftWrite,
    ApplicationRead,
    ApplicationSubmission,
    ApplicationSummary,
)
from app.core.config import settings
from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.models import (
    Application, ApplicationApproval, ApplicationDocument, ApplicationStatus,
    ApprovalStatus, RoleCode, WorkflowAuditEvent,
)
from app.models import IndustryType, PollutionCategory
from app.document_processor import DocumentProcessor, get_document_processor
from app.prevalidation import DOCUMENT_LABELS, prevalidation_payload, run_prevalidation
from app.models import ApplicationValidationIssue
from app.workflow_service import WorkflowService
from app.requirement_engine import DocumentRequirementEngine

router = APIRouter(
    prefix="/applications",
    tags=["applicant applications"],
    dependencies=[Depends(require_roles(RoleCode.APPLICANT))],
)
Database = Annotated[Session, Depends(get_db)]

MAX_DOCUMENT_SIZE = 15 * 1024 * 1024
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
DOCUMENT_TYPES = set(DOCUMENT_LABELS)
DOCUMENT_TYPE_ALIASES = {"LAND_DOCUMENT": "LAND_OWNERSHIP_LEASE", "SITE_PLAN": "BUILDING_PLAN", "OTHER": "OTHER_SUPPORTING"}
RISK_INPUT_FIELDS = {
    "industry_type", "pollution_category", "hazardous_materials", "hazardous_materials_details",
    "investment_amount", "built_up_area", "number_of_employees", "power_requirement",
    "project_description", "factory_information", "fire_safety_information", "project_location", "midc_area",
}


def detect_document_media_type(content: bytes, filename: str | None, declared_type: str | None) -> str | None:
    """Detect the real document type even when the browser sends a generic MIME type."""
    normalized = (declared_type or "").split(";")[0].strip().lower()
    suffix = Path(filename or "").suffix.lower()

    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if suffix == ".docx" or normalized == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            import zipfile
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if "word/document.xml" in archive.namelist() and archive.testzip() is None:
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except zipfile.BadZipFile:
            return None
    return None


def check_file_signature(content: bytes, media_type: str) -> None:
    try:
        if media_type == "application/pdf":
            import fitz

            with fitz.open(stream=content, filetype="pdf") as document:
                if not document.page_count:
                    raise ValueError("PDF has no pages")
        elif media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            import zipfile
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("DOCX document body is missing")
                archive.testzip()
        else:
            from PIL import Image

            with Image.open(BytesIO(content)) as image:
                image.verify()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The document is damaged or cannot be opened") from exc


def process_document(document: ApplicationDocument, path: Path, processor: DocumentProcessor) -> None:
    result = processor.process(str(path), document.media_type)
    document.extracted_text = result.extracted_text[:200_000]
    document.extracted_fields = result.fields
    document.processed_at = datetime.now(UTC)
    document.status = "PROCESSING" if result.readable else "WARNING"


def load_owned_application(db: Session, application_id: int, user_id: int) -> Application:
    application = db.scalar(
        select(Application)
        .options(
            joinedload(Application.current_department),
            selectinload(Application.documents),
        )
        .where(Application.id == application_id, Application.owner_user_id == user_id)
    )
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return application


def ensure_draft(application: Application) -> None:
    if application.status != ApplicationStatus.DRAFT.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Submitted applications can no longer be edited",
        )


def ensure_draft_or_correction(db: Session, application: Application) -> bool:
    """Allow applicant edits only for drafts or while a department correction is open."""
    if application.status == ApplicationStatus.DRAFT.value:
        return False
    if application.status != ApplicationStatus.ACTION_REQUIRED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only drafts or applications awaiting applicant action can be edited",
        )
    correction_open = db.scalar(select(ApplicationApproval.id).where(
        ApplicationApproval.application_id == application.id,
        ApplicationApproval.is_required.is_(True),
        ApplicationApproval.status == ApprovalStatus.DOCUMENT_CORRECTION.value,
    ).limit(1)) is not None
    if not correction_open:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Submitted applications can only be edited while a department correction is open",
        )
    return True


def to_read(application: Application) -> ApplicationRead:
    application.progress_percent = application_progress(application, len(application.documents))
    return ApplicationRead.model_validate(application)


def normalize_draft_value(field: str, value: object) -> object:
    if isinstance(value, (IndustryType, PollutionCategory)):
        return value.value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        if field in {"pan", "gstin", "cin", "udyam_number"}:
            return value.upper()
        if field == "applicant_email":
            return value.lower()
    return value


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(user: CurrentUser, db: Database) -> ApplicationRead:
    application = Application(
        owner_user_id=user.id,
        company_id=user.company_id,
        applicant_name=user.full_name,
        applicant_email=user.email,
        company_name=user.company.name if user.company else None,
        status=ApplicationStatus.DRAFT.value,
    )
    db.add(application)
    db.flush()
    application.application_number = f"MCAI-{datetime.now(UTC).year}-{application.id:06d}"
    application.progress_percent = application_progress(application, 0)
    db.add(WorkflowAuditEvent(application_id=application.id, actor_user_id=user.id,
        action="APPLICATION_CREATED", message="Application draft created.", details={}))
    db.commit()
    db.refresh(application)
    return to_read(application)


@router.get("", response_model=ApplicantApplicationsResponse)
def list_applications(user: CurrentUser, db: Database) -> ApplicantApplicationsResponse:
    applications = db.scalars(
        select(Application)
        .options(joinedload(Application.current_department), selectinload(Application.documents))
        .where(Application.owner_user_id == user.id)
        .order_by(Application.created_at.desc(), Application.id.desc())
    ).all()
    status_counts = dict(
        db.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.owner_user_id == user.id)
            .group_by(Application.status)
        ).all()
    )
    summary = ApplicationSummary(
        total_applications=len(applications),
        pending=status_counts.get(ApplicationStatus.SUBMITTED.value, 0)
        + status_counts.get(ApplicationStatus.IN_REVIEW.value, 0),
        approved=status_counts.get(ApplicationStatus.APPROVED.value, 0),
        rejected=status_counts.get(ApplicationStatus.REJECTED.value, 0),
        action_required=status_counts.get(ApplicationStatus.ACTION_REQUIRED.value, 0),
    )
    return ApplicantApplicationsResponse(
        summary=summary,
        applications=[to_read(application) for application in applications],
    )


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(application_id: int, user: CurrentUser, db: Database) -> ApplicationRead:
    return to_read(load_owned_application(db, application_id, user.id))


@router.patch("/{application_id}", response_model=ApplicationRead)
def save_application_draft(
    application_id: int,
    payload: ApplicationDraftWrite,
    user: CurrentUser,
    db: Database,
) -> ApplicationRead:
    application = load_owned_application(db, application_id, user.id)
    correction_open = ensure_draft_or_correction(db, application)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(application, field, normalize_draft_value(field, value))
    if RISK_INPUT_FIELDS.intersection(changes):
        application.risk_tier = None
    if correction_open and changes:
        db.add(WorkflowAuditEvent(
            application_id=application.id, actor_user_id=user.id,
            action="CORRECTION_DETAILS_UPDATED",
            message="Applicant updated application details in response to a correction request.",
            details={"updated_fields": sorted(changes)},
        ))
    if changes:
        # Requirements and value-comparison validation follow the latest saved
        # draft fields, even before another file is uploaded.
        run_prevalidation(db, application)
    application.progress_percent = application_progress(application, len(application.documents))
    db.commit()
    db.refresh(application)
    return to_read(load_owned_application(db, application.id, user.id))


@router.post("/{application_id}/documents", response_model=ApplicationDocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    application_id: int,
    user: CurrentUser,
    db: Database,
    document_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    processor: Annotated[DocumentProcessor, Depends(get_document_processor)],
) -> ApplicationDocumentRead:
    application = load_owned_application(db, application_id, user.id)
    ensure_draft_or_correction(db, application)
    document_type = DOCUMENT_TYPE_ALIASES.get(document_type, document_type)
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail="Choose a supported document type")
    content = file.file.read(MAX_DOCUMENT_SIZE + 1)
    if not content:
        raise HTTPException(status_code=422, detail="The selected document is empty")
    if len(content) > MAX_DOCUMENT_SIZE:
        raise HTTPException(status_code=413, detail="Each document must be 15 MB or smaller")

    source_name = (file.filename or "document").replace("\\", "/").split("/")[-1]
    safe_name = re.sub(r"[\x00-\x1f\x7f]", "", source_name).strip()[:255] or "document"
    media_type = detect_document_media_type(content, safe_name, file.content_type)
    extension = ALLOWED_DOCUMENT_TYPES.get(media_type or "")
    if extension is None:
        raise HTTPException(status_code=415, detail="The file content does not match a supported PDF, JPEG, PNG, or DOCX document")
    storage_key = f"{application.application_number}/{uuid4().hex}{extension}"
    upload_root = Path(settings.upload_dir).resolve()
    file_path = (upload_root / storage_key).resolve()
    if not file_path.is_relative_to(upload_root):
        raise HTTPException(status_code=400, detail="Invalid document path")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    check_file_signature(content, media_type)
    file_path.write_bytes(content)

    document = ApplicationDocument(
        application_id=application.id,
        document_type=document_type,
        file_name=safe_name,
        storage_key=storage_key,
        media_type=media_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    application.documents.append(document)
    if document_type == "ENVIRONMENTAL_DOCUMENTS":
        application.risk_tier = None
    application.progress_percent = application_progress(application, len(application.documents))
    try:
        process_document(document, file_path, processor)
        db.flush()
        issues = run_prevalidation(db, application)
        db.add(WorkflowAuditEvent(application_id=application.id, actor_user_id=user.id,
            action="DOCUMENT_UPLOADED", message=f"{safe_name} uploaded and processed.",
            details={"document_id": document.id, "document_type": document_type,
                     "file_name": safe_name, "status": document.status}))
        db.add(WorkflowAuditEvent(application_id=application.id, actor_user_id=user.id,
            action="DOCUMENT_VALIDATED", message="Document pre-validation completed.",
            details={"issue_count": len(issues), "document_id": document.id}))
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise
    return ApplicationDocumentRead.model_validate(document)


@router.post("/{application_id}/documents/{document_id}/replace", response_model=ApplicationDocumentRead)
def replace_document(
    application_id: int,
    document_id: int,
    user: CurrentUser,
    db: Database,
    file: Annotated[UploadFile, File()],
    processor: Annotated[DocumentProcessor, Depends(get_document_processor)],
) -> ApplicationDocumentRead:
    application = load_owned_application(db, application_id, user.id)
    ensure_draft_or_correction(db, application)
    document = db.scalar(select(ApplicationDocument).where(
        ApplicationDocument.id == document_id, ApplicationDocument.application_id == application.id
    ))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    content = file.file.read(MAX_DOCUMENT_SIZE + 1)
    if not content:
        raise HTTPException(status_code=422, detail="The selected document is empty")
    if len(content) > MAX_DOCUMENT_SIZE:
        raise HTTPException(status_code=413, detail="Each document must be 15 MB or smaller")
    source_name = (file.filename or "document").replace("\\", "/").split("/")[-1]
    safe_name = re.sub(r"[\x00-\x1f\x7f]", "", source_name).strip()[:255] or "document"
    media_type = detect_document_media_type(content, safe_name, file.content_type)
    extension = ALLOWED_DOCUMENT_TYPES.get(media_type or "")
    if extension is None:
        raise HTTPException(status_code=415, detail="The file content does not match a supported PDF, JPEG, PNG, or DOCX document")
    check_file_signature(content, media_type)
    root = Path(settings.upload_dir).resolve()
    old_path = (root / document.storage_key).resolve()
    storage_key = f"{application.application_number}/{uuid4().hex}{extension}"
    new_path = (root / storage_key).resolve()
    if not new_path.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Invalid document path")
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_bytes(content)
    try:
        document.file_name = safe_name
        document.storage_key = storage_key
        document.media_type = media_type
        document.size_bytes = len(content)
        document.sha256 = hashlib.sha256(content).hexdigest()
        document.status = "PROCESSING"
        if document.document_type == "ENVIRONMENTAL_DOCUMENTS":
            application.risk_tier = None
        process_document(document, new_path, processor)
        issues = run_prevalidation(db, application)
        db.add(WorkflowAuditEvent(application_id=application.id, actor_user_id=user.id,
            action="DOCUMENT_RESUBMITTED", message=f"{safe_name} replaced a previous upload.",
            details={"document_id": document.id, "document_type": document.document_type,
                     "issue_count": len(issues)}))
        db.commit()
        db.refresh(document)
    except Exception:
        db.rollback()
        new_path.unlink(missing_ok=True)
        raise
    if old_path.is_relative_to(root):
        old_path.unlink(missing_ok=True)
    return ApplicationDocumentRead.model_validate(document)


@router.get("/{application_id}/prevalidation")
def get_prevalidation(application_id: int, user: CurrentUser, db: Database) -> dict:
    application = load_owned_application(db, application_id, user.id)
    issues = db.scalars(select(ApplicationValidationIssue).where(
        ApplicationValidationIssue.application_id == application.id
    ).order_by(ApplicationValidationIssue.id)).all()
    return prevalidation_payload(application, issues)


@router.get("/{application_id}/requirements")
def get_application_requirements(application_id: int, user: CurrentUser, db: Database) -> dict:
    """Return current, owner-scoped approval and document requirements."""
    application = load_owned_application(db, application_id, user.id)
    return DocumentRequirementEngine().evaluate(db, application)


@router.post("/{application_id}/prevalidation/run")
def validate_application_documents(
    application_id: int,
    user: CurrentUser,
    db: Database,
    processor: Annotated[DocumentProcessor, Depends(get_document_processor)],
) -> dict:
    application = load_owned_application(db, application_id, user.id)
    ensure_draft_or_correction(db, application)
    for document in application.documents:
        path = (Path(settings.upload_dir).resolve() / document.storage_key).resolve()
        root = Path(settings.upload_dir).resolve()
        if path.is_relative_to(root) and path.is_file():
            try:
                process_document(document, path, processor)
            except Exception:
                document.status = "WARNING"
        else:
            document.status = "INVALID"
    issues = run_prevalidation(db, application)
    db.commit()
    return prevalidation_payload(application, issues)


@router.get("/{application_id}/documents/{document_id}/download")
def download_document(
    application_id: int,
    document_id: int,
    user: CurrentUser,
    db: Database,
) -> FileResponse:
    application = load_owned_application(db, application_id, user.id)
    document = db.scalar(
        select(ApplicationDocument).where(
            ApplicationDocument.id == document_id,
            ApplicationDocument.application_id == application.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    root = Path(settings.upload_dir).resolve()
    path = (root / document.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Document file not found")
    return FileResponse(path, media_type=document.media_type, filename=document.file_name)


@router.delete("/{application_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    application_id: int,
    document_id: int,
    user: CurrentUser,
    db: Database,
) -> Response:
    application = load_owned_application(db, application_id, user.id)
    ensure_draft_or_correction(db, application)
    document = db.scalar(
        select(ApplicationDocument).where(
            ApplicationDocument.id == document_id,
            ApplicationDocument.application_id == application.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    root = Path(settings.upload_dir).resolve()
    path = (root / document.storage_key).resolve()
    if document.document_type == "ENVIRONMENTAL_DOCUMENTS":
        application.risk_tier = None
    application.documents.remove(document)
    db.delete(document)
    db.flush()
    application.progress_percent = application_progress(application, len(application.documents))
    issues = run_prevalidation(db, application)
    db.add(WorkflowAuditEvent(application_id=application.id, actor_user_id=user.id,
        action="DOCUMENT_DELETED", message=f"{document.file_name} removed from the application.",
        details={"document_id": document_id, "issue_count": len(issues)}))
    db.commit()
    if path.is_relative_to(root):
        path.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{application_id}/submit", response_model=ApplicationRead)
def submit_application(
    application_id: int,
    user: CurrentUser,
    db: Database,
    processor: Annotated[DocumentProcessor, Depends(get_document_processor)],
) -> ApplicationRead:
    application = load_owned_application(db, application_id, user.id)
    ensure_draft(application)
    for document in application.documents:
        path = (Path(settings.upload_dir).resolve() / document.storage_key).resolve()
        root = Path(settings.upload_dir).resolve()
        if path.is_relative_to(root) and path.is_file():
            try:
                process_document(document, path, processor)
            except Exception:
                document.status = "WARNING"
        else:
            document.status = "INVALID"
    issues = run_prevalidation(db, application)
    db.add(WorkflowAuditEvent(application_id=application.id, actor_user_id=user.id,
        action="DOCUMENT_VALIDATED", message="Application documents were pre-validated.",
        details={"issue_count": len(issues), "document_count": len(application.documents)}))
    db.flush()
    requirements = DocumentRequirementEngine().evaluate(db, application)
    errors = submission_errors(application, len(application.documents))
    if not requirements["submission_ready"]:
        errors.append("prevalidation")
    if errors:
        blockers = [item for item in requirements["required_documents"] if item["status"] != "VALID"]
        # Keep the latest OCR and validation result visible after a blocked
        # submit attempt; the application itself remains an editable draft.
        db.commit()
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Application cannot be submitted until the required documents are uploaded and pass validation." if blockers else "Complete the required application fields before submitting.",
                "fields": errors,
                "missing_documents": [{"document_type": item["document_type"], "document_name": item["document_name"], "reason": item["reason"]} for item in blockers if item["status"] == "MISSING"],
                "invalid_documents": [{"document_type": item["document_type"], "document_name": item["document_name"], "status": item["status"], "reason": item["status_reason"], "requirement_reason": item["reason"]} for item in blockers if item["status"] != "MISSING"],
                "upload_url": f"/applicant/applications/{application.id}/prevalidation",
            },
        )

    validated = ApplicationSubmission.model_validate(
        {field: getattr(application, field) for field in ApplicationSubmission.model_fields}
    )
    for field, value in validated.model_dump().items():
        if isinstance(value, (IndustryType, PollutionCategory)):
            value = value.value
        setattr(application, field, value)
    application.status = ApplicationStatus.SUBMITTED.value
    application.submitted_at = datetime.now(UTC)
    application.progress_percent = 100
    WorkflowService().initialize(db, application, user.id)
    db.add(WorkflowAuditEvent(application_id=application.id, actor_user_id=user.id,
        action="APPLICATION_SUBMITTED", message="Application submitted for department review.",
        details={"application_number": application.application_number}))
    db.commit()
    db.refresh(application)
    return to_read(load_owned_application(db, application.id, user.id))
