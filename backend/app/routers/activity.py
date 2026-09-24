from typing import Annotated
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import CurrentUser
from app.core.config import settings
from app.models import Application, ApplicationApproval, Inspection, InspectionParticipant, JointInspection, RoleCode, WorkflowAuditEvent
from app.sla_service import SlaService

router = APIRouter(prefix="/applications", tags=["application activity"])
Database = Annotated[Session, Depends(get_db)]


def owned_or_authorized(application_id: int, user: CurrentUser, db: Session) -> Application:
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if user.role.code == RoleCode.APPLICANT.value and application.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.get("/{application_id}/sla")
def application_sla(application_id: int, user: CurrentUser, db: Database) -> dict:
    application = owned_or_authorized(application_id, user, db)
    approvals = db.scalars(select(ApplicationApproval).where(
        ApplicationApproval.application_id == application.id,
        ApplicationApproval.is_required.is_(True),
    ).order_by(ApplicationApproval.id)).all()
    service = SlaService()
    return {"application_id": application.id, "items": [{
        "approval_id": row.id, "department_code": row.department_code,
        "department_name": row.department_name, "approval_status": row.status,
        **service.payload(row),
    } for row in approvals]}


@router.get("/{application_id}/timeline")
def application_timeline(application_id: int, user: CurrentUser, db: Database) -> dict:
    application = owned_or_authorized(application_id, user, db)
    events = db.scalars(select(WorkflowAuditEvent).options(
        joinedload(WorkflowAuditEvent.actor),
        joinedload(WorkflowAuditEvent.approval),
    ).where(WorkflowAuditEvent.application_id == application.id).order_by(
        WorkflowAuditEvent.created_at, WorkflowAuditEvent.id,
    )).all()
    public = user.role.code == RoleCode.APPLICANT.value
    values = [{
        "id": event.id, "occurred_at": event.created_at,
        "department_code": event.department_code,
        "department_name": event.approval.department_name if event.approval else None,
        "action": event.action,
        "officer": "System" if (event.details or {}).get("system_actor") else event.actor.full_name if event.actor else "System",
        "from_status": event.from_status, "status": event.to_status,
        "message": event.message, "metadata": event.details,
    } for event in events if not (public and (event.details or {}).get("visibility") == "OFFICER")]
    return {"application_id": application.id, "application_number": application.application_number,
            "status": application.status, "events": values}


@router.get("/{application_id}/audit")
def application_audit(application_id: int, user: CurrentUser, db: Database) -> dict:
    return application_timeline(application_id, user, db)


@router.get("/{application_id}/inspections")
def applicant_inspections(application_id: int, user: CurrentUser, db: Database) -> dict:
    application = owned_or_authorized(application_id, user, db)
    singles = db.scalars(select(Inspection).options(
        joinedload(Inspection.approval), joinedload(Inspection.scheduled_by),
    ).where(Inspection.application_id == application.id, Inspection.joint_inspection_id.is_(None)).order_by(Inspection.scheduled_at)).all()
    joints = db.scalars(select(JointInspection).options(
        joinedload(JointInspection.scheduled_by),
    ).where(JointInspection.application_id == application.id).order_by(JointInspection.scheduled_at)).all()
    participant_rows = db.scalars(select(InspectionParticipant).options(
        joinedload(InspectionParticipant.approval), joinedload(InspectionParticipant.officer),
    ).join(JointInspection).where(JointInspection.application_id == application.id)).all()
    participants: dict[int, list[dict]] = {}
    for item in participant_rows:
        participants.setdefault(item.joint_inspection_id, []).append({
            "department_code": item.approval.department_code,
            "department_name": item.approval.department_name,
            "officer": item.officer.full_name if item.officer else None,
            "status": item.status,
        })
    items = [{
        "id": item.id, "kind": "SINGLE", "department_name": item.approval.department_name,
        "scheduled_at": item.scheduled_at, "site": item.site or item.location,
        "status": item.status, "instructions": item.instructions,
        "checklist": item.checklist, "findings": item.findings,
        "photos": _photo_links(item.photos, application_id, "single", item.id),
        "remarks": item.remarks, "recommendation": item.recommendation,
    } for item in singles]
    items.extend({
        "id": item.id, "kind": "JOINT", "department_name": "Joint inspection",
        "scheduled_at": item.scheduled_at, "site": item.site,
        "status": item.status, "instructions": item.instructions,
        "participants": participants.get(item.id, []), "checklist": item.checklist,
        "findings": item.findings, "photos": _photo_links(item.photos, application_id, "joint", item.id),
        "remarks": item.remarks, "recommendation": item.recommendation,
    } for item in joints)
    items.sort(key=lambda row: str(row["scheduled_at"]))
    return {"total": len(items), "items": items}


def _photo_links(photos: list[dict] | None, application_id: int, kind: str, inspection_id: int) -> list[dict]:
    return [{**photo, "download_url": f"/api/applications/{application_id}/inspections/{kind}/{inspection_id}/photos/{index}"}
            for index, photo in enumerate(photos or [])]


@router.get("/{application_id}/inspections/{kind}/{inspection_id}/photos/{photo_index}")
def applicant_inspection_photo(application_id: int, kind: str, inspection_id: int,
                               photo_index: int, user: CurrentUser, db: Database) -> FileResponse:
    application = owned_or_authorized(application_id, user, db)
    if kind == "single":
        record = db.scalar(select(Inspection).where(
            Inspection.id == inspection_id, Inspection.application_id == application.id,
        ))
    elif kind == "joint":
        record = db.scalar(select(JointInspection).where(
            JointInspection.id == inspection_id, JointInspection.application_id == application.id,
        ))
    else:
        raise HTTPException(status_code=404, detail="Inspection photo not found")
    photos = record.photos or [] if record is not None else []
    if record is None or photo_index < 0 or photo_index >= len(photos):
        raise HTTPException(status_code=404, detail="Inspection photo not found")
    photo = photos[photo_index]
    root = Path(settings.upload_dir).resolve()
    path = (root / photo["storage_key"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Inspection photo not found")
    return FileResponse(path, media_type=photo["media_type"], filename=photo["file_name"])
