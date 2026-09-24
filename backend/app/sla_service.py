"""Configurable SLA countdown and persistent overdue escalation service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ApplicationApproval, ApprovalStatus, RoleCode, User, WorkflowAuditEvent
from app.notification_service import notify_applicant, notify_staff

DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "config" / "sla_rules.json"
TERMINAL_STATUSES = {ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value}


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SlaService:
    def __init__(self, rules_path: str | Path | None = None) -> None:
        configured = rules_path or os.getenv("SLA_RULES_PATH") or DEFAULT_RULES_PATH
        self.rules_path = Path(configured).expanduser().resolve()
        self.rules: dict[str, Any] = json.loads(self.rules_path.read_text(encoding="utf-8"))
        self.departments: dict[str, int] = self.rules["departments"]
        self.warning_days = int(self.rules.get("warning_days", 3))
        if self.warning_days < 0 or any(isinstance(days, bool) or int(days) <= 0 for days in self.departments.values()):
            raise ValueError("SLA durations must be positive and warning_days cannot be negative")

    def duration(self, department_code: str) -> int:
        return int(self.departments.get(department_code, self.rules.get("default_days", 7)))

    def prime(self, approval: ApplicationApproval, now: datetime | None = None) -> None:
        current = utc(now or datetime.now(UTC))
        if approval.sla_duration_days is None:
            approval.sla_duration_days = self.duration(approval.department_code)
        if approval.status != ApprovalStatus.NOT_STARTED.value and approval.sla_started_at is None:
            approval.sla_started_at = utc(approval.created_at) if approval.created_at else current
        if approval.sla_started_at is not None:
            approval.sla_expected_completion = utc(approval.sla_started_at) + timedelta(days=approval.sla_duration_days)

    def payload(self, approval: ApplicationApproval, now: datetime | None = None) -> dict[str, Any]:
        current = utc(now or datetime.now(UTC))
        self.prime(approval)
        if approval.status in TERMINAL_STATUSES:
            state, remaining = "CLOSED", 0
        elif approval.status == ApprovalStatus.NOT_STARTED.value or approval.sla_started_at is None:
            state, remaining = "BLOCKED", None
        elif approval.status == ApprovalStatus.ESCALATED.value:
            state = "ESCALATED"
            remaining = int((utc(approval.sla_expected_completion) - current).total_seconds())
        else:
            remaining = int((utc(approval.sla_expected_completion) - current).total_seconds())
            if remaining <= 0:
                state = "BREACHED"
            elif remaining <= self.warning_days * 86400:
                state = "WARNING"
            else:
                state = "ON_TRACK"
        return {
            "started_at": approval.sla_started_at,
            "duration_days": approval.sla_duration_days,
            "expected_completion": approval.sla_expected_completion,
            "remaining_seconds": remaining,
            "remaining_days": None if remaining is None else max(0, (remaining + 86399) // 86400),
            "status": state,
            "escalated_at": approval.escalated_at,
            "rules_version": str(self.rules.get("version", "unknown")),
        }

    def check_and_escalate(self, db: Session, now: datetime | None = None) -> list[ApplicationApproval]:
        from app.workflow_service import WorkflowService

        current = utc(now or datetime.now(UTC))
        rows = db.scalars(select(ApplicationApproval).options(
            joinedload(ApplicationApproval.application),
            joinedload(ApplicationApproval.assigned_reviewer),
        ).where(
            ApplicationApproval.is_required.is_(True),
            ApplicationApproval.status.notin_(list(TERMINAL_STATUSES | {
                ApprovalStatus.NOT_STARTED.value, ApprovalStatus.ESCALATED.value,
            })),
        )).all()
        changed: list[ApplicationApproval] = []
        snapshots_changed = False
        warnings_created = False
        system_actor: int | None = None
        for approval in rows:
            before = (approval.sla_duration_days, approval.sla_started_at, approval.sla_expected_completion)
            self.prime(approval, current)
            snapshots_changed = snapshots_changed or before != (
                approval.sla_duration_days, approval.sla_started_at, approval.sla_expected_completion,
            )
            if approval.sla_expected_completion is None:
                continue
            remaining = (utc(approval.sla_expected_completion) - current).total_seconds()
            if 0 < remaining <= self.warning_days * 86400:
                prior_warning = db.scalar(select(WorkflowAuditEvent.id).where(
                    WorkflowAuditEvent.approval_id == approval.id,
                    WorkflowAuditEvent.action == "SLA_WARNING",
                ).limit(1))
                if prior_warning is None:
                    if system_actor is None:
                        system_actor = self.system_actor_id(db, approval.assigned_reviewer_id or approval.application.owner_user_id)
                    message = f"The {approval.department_name} approval is approaching its SLA deadline."
                    WorkflowService.record_event(db, approval, system_actor, "SLA_WARNING",
                        approval.status, approval.status, message,
                        details={"system_actor": True, "sla_expected_completion": utc(approval.sla_expected_completion).isoformat()})
                    notify_applicant(db, approval.application, "SLA_WARNING",
                                     f"Your application is approaching its expected timeline with {approval.department_name}.")
                    notify_staff(db, approval.application, "SLA_WARNING", message, approval.assigned_reviewer_id)
                    warnings_created = True
            if remaining > 0:
                continue
            previous = approval.status
            approval.status = ApprovalStatus.ESCALATED.value
            approval.escalated_at = current
            approval.decision_message = f"The {approval.department_name} service level target has been exceeded."
            WorkflowService.record_event(
                db, approval, system_actor or self.system_actor_id(
                    db, approval.assigned_reviewer_id or approval.application.owner_user_id,
                ), "SLA_BREACHED", previous,
                ApprovalStatus.ESCALATED.value, approval.decision_message,
                details={"system_actor": True, "sla_duration_days": approval.sla_duration_days,
                         "sla_expected_completion": utc(approval.sla_expected_completion).isoformat()},
            )
            application = approval.application
            message = f"Your application has exceeded the expected timeline for {approval.department_name} and was escalated."
            notify_applicant(db, application, "APPLICATION_ESCALATED", message)
            notify_staff(db, application, "SLA_BREACHED",
                         f"{application.application_number}: {approval.department_name} SLA breached.",
                         approval.assigned_reviewer_id)
            changed.append(approval)
        if changed or snapshots_changed or warnings_created:
            db.commit()
        return changed

    @staticmethod
    def system_actor_id(db: Session, fallback_user_id: int | None = None) -> int:
        admin_id = db.scalar(select(User.id).where(User.role.has(code=RoleCode.ADMIN.value)).order_by(User.id).limit(1))
        return admin_id or fallback_user_id or 1
