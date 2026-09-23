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
from app.models import Application, ApplicationDocument, ApplicationStatus, RoleCode
from app.models import IndustryType, PollutionCategory
from app.document_processor import DocumentProcessor, get_document_processor
from app.prevalidation import DOCUMENT_LABELS, prevalidation_payload, run_prevalidation
from app.models import ApplicationValidationIssue
from app.workflow_service import WorkflowService

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
}
DOCUMENT_TYPES = set(DOCUMENT_LABELS)
DOCUMENT_TYPE_ALIASES = {"LAND_DOCUMENT": "LAND_OWNERSHIP_LEASE", "SITE_PLAN": "BUILDING_PLAN", "OTHER": "OTHER_SUPPORTING"}
RISK_INPUT_FIELDS = {
    "industry_type", "pollution_category", "hazardous_materials", "hazardous_materials_details",
    "investment_amount", "built_up_area", "number_of_employees", "power_requirement",
    "project_description", "factory_information", "fire_safety_information", "project_location", "midc_area",
}


def check_file_signature(content: bytes, media_type: str) -> None:
    signatures = {
        "application/pdf": content.startswith(b"%PDF-"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
    }
    if not signatures.get(media_type, False):
        raise HTTPException(status_code=415, detail="The file content does not match its PDF, JPEG, or PNG type")
    try:
        if media_type == "application/pdf":
            import fitz

            with fitz.open(stream=content, filetype="pdf") as document:
                if not document.page_count:
                    raise ValueError("PDF has no pages")
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
    ensure_draft(application)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(application, field, normalize_draft_value(field, value))
    if RISK_INPUT_FIELDS.intersection(changes):
        application.risk_tier = None
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
    ensure_draft(application)
    document_type = DOCUMENT_TYPE_ALIASES.get(document_type, document_type)
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail="Choose a supported document type")
    extension = ALLOWED_DOCUMENT_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=415, detail="Upload a PDF, JPEG, or PNG document")

    content = file.file.read(MAX_DOCUMENT_SIZE + 1)
    if not content:
        raise HTTPException(status_code=422, detail="The selected document is empty")
    if len(content) > MAX_DOCUMENT_SIZE:
        raise HTTPException(status_code=413, detail="Each document must be 15 MB or smaller")

    source_name = (file.filename or "document").replace("\\", "/").split("/")[-1]
    safe_name = re.sub(r"[\x00-\x1f\x7f]", "", source_name).strip()[:255] or "document"
    storage_key = f"{application.application_number}/{uuid4().hex}{extension}"
    upload_root = Path(settings.upload_dir).resolve()
    file_path = (upload_root / storage_key).resolve()
    if not file_path.is_relative_to(upload_root):
        raise HTTPException(status_code=400, detail="Invalid document path")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    check_file_signature(content, file.content_type or "")
    file_path.write_bytes(content)

    document = ApplicationDocument(
        application_id=application.id,
        document_type=document_type,
        file_name=safe_name,
        storage_key=storage_key,
        media_type=file.content_type or "application/octet-stream",
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
        run_prevalidation(db, application)
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
    ensure_draft(application)
    document = db.scalar(select(ApplicationDocument).where(
        ApplicationDocument.id == document_id, ApplicationDocument.application_id == application.id
    ))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    extension = ALLOWED_DOCUMENT_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=415, detail="Upload a PDF, JPEG, or PNG document")
    content = file.file.read(MAX_DOCUMENT_SIZE + 1)
    if not content:
        raise HTTPException(status_code=422, detail="The selected document is empty")
    if len(content) > MAX_DOCUMENT_SIZE:
        raise HTTPException(status_code=413, detail="Each document must be 15 MB or smaller")
    check_file_signature(content, file.content_type or "")
    source_name = (file.filename or "document").replace("\\", "/").split("/")[-1]
    safe_name = re.sub(r"[\x00-\x1f\x7f]", "", source_name).strip()[:255] or "document"
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
        document.media_type = file.content_type or "application/octet-stream"
        document.size_bytes = len(content)
        document.sha256 = hashlib.sha256(content).hexdigest()
        document.status = "PROCESSING"
        if document.document_type == "ENVIRONMENTAL_DOCUMENTS":
            application.risk_tier = None
        process_document(document, new_path, processor)
        run_prevalidation(db, application)
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


@router.post("/{application_id}/prevalidation/run")
def validate_application_documents(
    application_id: int,
    user: CurrentUser,
    db: Database,
    processor: Annotated[DocumentProcessor, Depends(get_document_processor)],
) -> dict:
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
    ensure_draft(application)
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
    run_prevalidation(db, application)
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
    run_prevalidation(db, application)
    db.flush()
    validation_issues = db.scalars(select(ApplicationValidationIssue).where(
        ApplicationValidationIssue.application_id == application.id
    )).all()
    blocking = [issue for issue in validation_issues if issue.status in {"INVALID", "MISSING"}]
    errors = submission_errors(application, len(application.documents))
    if blocking:
        errors.append("prevalidation")
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Complete the required fields and upload at least one document before submitting.",
                "fields": errors,
                "prevalidation_issues": [issue.message for issue in blocking],
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
    db.commit()
    db.refresh(application)
    return to_read(load_owned_application(db, application.id, user.id))
