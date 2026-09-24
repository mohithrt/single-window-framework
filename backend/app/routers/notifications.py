from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import CurrentUser
from app.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])
Database = Annotated[Session, Depends(get_db)]


@router.get("")
def list_notifications(user: CurrentUser, db: Database,
                       unread_only: bool = False, limit: int = Query(default=50, ge=1, le=200),
                       offset: int = Query(default=0, ge=0)) -> dict:
    statement = select(Notification).where(Notification.user_id == user.id)
    count_statement = select(Notification.id).where(Notification.user_id == user.id)
    if unread_only:
        statement = statement.where(Notification.is_read.is_(False))
        count_statement = count_statement.where(Notification.is_read.is_(False))
    rows = db.scalars(statement.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(count_statement.subquery())) or 0
    unread_total = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.is_read.is_(False),
    )) or 0
    return {"total": total, "unread_count": unread_total, "items": [{
        "id": item.id, "application_id": item.application_id,
        "notification_type": item.notification_type, "message": item.message,
        "is_read": item.is_read, "created_at": item.created_at, "read_at": item.read_at,
    } for item in rows]}


@router.patch("/{notification_id}/read")
def mark_read(notification_id: int, user: CurrentUser, db: Database) -> dict:
    notification = db.scalar(select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user.id,
    ))
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    notification.read_at = datetime.now(UTC)
    db.commit()
    return {"id": notification.id, "is_read": notification.is_read, "read_at": notification.read_at}


@router.patch("/read-all")
def mark_all_read(user: CurrentUser, db: Database) -> dict:
    result = db.execute(update(Notification).where(
        Notification.user_id == user.id, Notification.is_read.is_(False),
    ).values(is_read=True, read_at=datetime.now(UTC)))
    db.commit()
    return {"updated": result.rowcount or 0}
