"""Create persisted in-app notifications for application workflow events."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, Notification, RoleCode, User


def notify_users(db: Session, user_ids: set[int], application_id: int | None,
                 notification_type: str, message: str) -> list[Notification]:
    if not user_ids:
        return []
    rows = [Notification(
        user_id=user_id,
        application_id=application_id,
        notification_type=notification_type,
        message=message,
    ) for user_id in sorted(user_ids)]
    db.add_all(rows)
    return rows


def notify_applicant(db: Session, application: Application, notification_type: str, message: str) -> list[Notification]:
    return notify_users(db, {application.owner_user_id}, application.id, notification_type, message)


def notify_staff(db: Session, application: Application, notification_type: str,
                 message: str, reviewer_user_id: int | None = None) -> list[Notification]:
    ids = set(db.scalars(select(User.id).where(User.role.has(code=RoleCode.ADMIN.value))).all())
    if reviewer_user_id is not None:
        ids.add(reviewer_user_id)
    return notify_users(db, ids, application.id, notification_type, message)
