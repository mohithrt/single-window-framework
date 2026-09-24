"""Database-backed government approval analytics."""

from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    Application, ApplicationApproval, ApplicationStatus, ApprovalStatus,
    RiskAssessment, WorkflowAuditEvent,
)

FINAL_APPROVALS = {ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value}
FINAL_APPLICATIONS = {ApplicationStatus.APPROVED.value, ApplicationStatus.REJECTED.value}
ACTIVE_APPLICATIONS = {ApplicationStatus.SUBMITTED.value, ApplicationStatus.IN_REVIEW.value, ApplicationStatus.ACTION_REQUIRED.value}
ACTIVE_APPROVALS = {
    ApprovalStatus.PENDING.value, ApprovalStatus.IN_REVIEW.value,
    ApprovalStatus.DOCUMENT_CORRECTION.value, ApprovalStatus.INSPECTION_REQUIRED.value,
    ApprovalStatus.ESCALATED.value,
}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


class AnalyticsService:
    def dashboard(self, db: Session, now: datetime | None = None) -> dict:
        current = _utc(now or datetime.now(UTC))
        applications = db.scalars(select(Application).options(
            selectinload(Application.approvals), selectinload(Application.risk_assessments),
        ).order_by(Application.created_at.desc(), Application.id.desc())).unique().all()
        approvals = db.scalars(select(ApplicationApproval).options(
            joinedload(ApplicationApproval.application),
        ).where(ApplicationApproval.is_required.is_(True))).unique().all()
        events = db.scalars(select(WorkflowAuditEvent).options(
            joinedload(WorkflowAuditEvent.actor), joinedload(WorkflowAuditEvent.application),
            joinedload(WorkflowAuditEvent.approval),
        ).order_by(WorkflowAuditEvent.created_at.desc(), WorkflowAuditEvent.id.desc()).limit(30)).unique().all()
        rejection_events = db.scalars(select(WorkflowAuditEvent).where(
            WorkflowAuditEvent.action == "REJECTED",
        )).all()

        eligible = [item for item in applications if item.status != ApplicationStatus.DRAFT.value]
        submitted = [item for item in applications if item.submitted_at is not None]
        counts = Counter(item.status for item in applications)
        resolved_durations: list[float] = []
        delayed_days: list[float] = []
        for application in applications:
            if application.status in FINAL_APPLICATIONS and application.submitted_at:
                decisions = [row.decided_at for row in application.approvals if row.is_required and row.decided_at]
                if decisions:
                    resolved_durations.append(max(0.0, (_utc(max(decisions)) - _utc(application.submitted_at)).total_seconds() / 86400))
            if application.status in ACTIVE_APPLICATIONS and application.expected_completion_at:
                late = (current - _utc(application.expected_completion_at)).total_seconds() / 86400
                if late > 0:
                    delayed_days.append(late)

        department_rows: dict[str, dict] = {}
        department_times: dict[str, list[float]] = defaultdict(list)
        for approval in approvals:
            code = approval.department_code
            item = department_rows.setdefault(code, {
                "department_code": code, "department": approval.department_name,
                "total": 0, "pending": 0, "sla_breaches": 0,
                "approved": 0, "rejected": 0, "durations": [], "sla_eligible": 0,
            })
            item["total"] += 1
            if approval.status in ACTIVE_APPROVALS:
                item["pending"] += 1
            if approval.status != ApprovalStatus.NOT_STARTED.value:
                item["sla_eligible"] += 1
            breached = approval.status == ApprovalStatus.ESCALATED.value or (
                approval.status not in FINAL_APPROVALS
                and approval.sla_expected_completion is not None
                and _utc(approval.sla_expected_completion) <= current
            )
            if breached:
                item["sla_breaches"] += 1
            if approval.status == ApprovalStatus.APPROVED.value:
                item["approved"] += 1
            elif approval.status == ApprovalStatus.REJECTED.value:
                item["rejected"] += 1
            if approval.status in FINAL_APPROVALS and approval.decided_at:
                start = approval.sla_started_at or approval.created_at
                if start:
                    elapsed = max(0.0, (_utc(approval.decided_at) - _utc(start)).total_seconds() / 86400)
                    item["durations"].append(elapsed)
                    department_times[code].append(elapsed)

        departments = []
        for item in department_rows.values():
            decisions = item["approved"] + item["rejected"]
            avg_days = _average(item["durations"])
            departments.append({
                "department_code": item["department_code"], "department": item["department"],
                "total": item["total"], "average_time_days": avg_days,
                "pending": item["pending"], "sla_breaches": item["sla_breaches"],
                "approval_rate": round(item["approved"] / decisions * 100, 1) if decisions else None,
                "approval_count": item["approved"], "rejection_count": item["rejected"],
                "sla_breach_rate": round(item["sla_breaches"] / item["sla_eligible"] * 100, 1) if item["sla_eligible"] else None,
            })
        departments.sort(key=lambda row: (-(row["average_time_days"] or 0), -row["pending"], row["department"]))

        risk_counts = Counter(item.risk_tier or "UNASSESSED" for item in eligible)
        final_decisions = counts[ApplicationStatus.APPROVED.value] + counts[ApplicationStatus.REJECTED.value]
        approval_breaches = sum(row["sla_breaches"] for row in departments)
        approval_total = sum(item["sla_eligible"] for item in department_rows.values())
        monthly = Counter()
        for application in submitted:
            stamp = _utc(application.submitted_at)
            month = stamp.strftime("%Y-%m")
            monthly[month] += 1
        current_month = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        months = []
        for ago in range(11, -1, -1):
            year, month_num = current_month.year, current_month.month - ago
            while month_num <= 0:
                month_num += 12
                year -= 1
            months.append({"month": f"{year:04d}-{month_num:02d}", "count": monthly[f"{year:04d}-{month_num:02d}"]})

        reasons = Counter()
        for event in rejection_events:
            reason = (event.message or (event.details or {}).get("reason") or "Reason not recorded").strip()
            if reason:
                reasons[reason] += 1

        active = [item for item in applications if item.status in ACTIVE_APPLICATIONS]
        latest_risk = {}
        for application in applications:
            if application.risk_assessments:
                latest_risk[application.id] = max(application.risk_assessments, key=lambda row: (row.created_at, row.id))
        application_items = [{
            "id": item.id, "application_number": item.application_number,
            "company_name": item.company_name or "Company not provided",
            "applicant_name": item.applicant_name or item.owner.full_name if item.owner else item.applicant_name,
            "industry_type": item.industry_type, "status": item.status,
            "risk_tier": latest_risk[item.id].risk_tier if item.id in latest_risk else item.risk_tier,
            "submitted_at": item.submitted_at, "expected_completion_at": item.expected_completion_at,
            "departments": [row.department_code for row in item.approvals if row.is_required],
        } for item in eligible[:30]]

        bottleneck = departments[0] if departments else None
        return {
            "generated_at": current,
            "kpis": {
                "total_applications": len(applications), "active_applications": len(active),
                "approved": counts[ApplicationStatus.APPROVED.value],
                "average_clearance_time_days": _average(resolved_durations),
                "sla_breaches": approval_breaches,
                "high_risk_applications": sum(1 for item in eligible if (latest_risk.get(item.id).risk_tier if latest_risk.get(item.id) else item.risk_tier) == "HIGH"),
                "sla_breach_rate": round(approval_breaches / approval_total * 100, 1) if approval_total else None,
                "approval_rate": round(counts[ApplicationStatus.APPROVED.value] / final_decisions * 100, 1) if final_decisions else None,
                "rejection_rate": round(counts[ApplicationStatus.REJECTED.value] / final_decisions * 100, 1) if final_decisions else None,
                "critical_path_delay_days": _average(delayed_days),
                "applications_with_critical_path_delay": len(delayed_days),
            },
            "applications_by_department": [{"department": item["department"], "department_code": item["department_code"], "count": item["total"]} for item in sorted(departments, key=lambda row: row["department"])],
            "average_approval_time": [{"department": item["department"], "department_code": item["department_code"], "days": item["average_time_days"]} for item in departments],
            "approval_vs_rejection": {
                "approved": counts[ApplicationStatus.APPROVED.value],
                "rejected": counts[ApplicationStatus.REJECTED.value],
                "active": len(active),
            },
            "sla_breach_by_department": [{"department": item["department"], "department_code": item["department_code"], "rate": item["sla_breach_rate"], "count": item["sla_breaches"]} for item in departments],
            "risk_distribution": [{"tier": tier, "count": risk_counts[tier]} for tier in ("LOW", "MEDIUM", "HIGH", "UNASSESSED") if risk_counts[tier]],
            "monthly_volume": months,
            "bottlenecks": [{"department": item["department"], "department_code": item["department_code"], "average_time_days": item["average_time_days"], "pending": item["pending"], "sla_breaches": item["sla_breaches"]} for item in departments[:5]],
            "rejection_reasons": [{"reason": reason, "count": count} for reason, count in reasons.most_common(8)],
            "departments": departments,
            "applications": application_items,
            "audit_events": [{
                "id": event.id, "application_id": event.application_id,
                "application_number": event.application.application_number if event.application else None,
                "department": event.approval.department_name if event.approval else event.department_code,
                "action": event.action, "actor": "System" if (event.details or {}).get("system_actor") else event.actor.full_name,
                "status": event.to_status, "message": event.message, "created_at": event.created_at,
            } for event in events],
            "bottleneck_department": bottleneck["department"] if bottleneck else None,
        }
