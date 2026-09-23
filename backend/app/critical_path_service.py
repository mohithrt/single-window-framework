"""Critical-path scheduling over persisted application approval dependencies."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, date, datetime, timedelta
import math
from pathlib import Path
from typing import Any, Iterable

from app.models import Application, ApplicationApproval, ApprovalStatus, WorkflowAuditEvent
from app.workflow_service import DEFAULT_RULES_PATH


class CriticalPathService:
    """Calculate a dependency graph schedule without hard-coded department topology."""

    def __init__(self, rules_path: str | Path | None = None) -> None:
        import json
        import os

        configured_path = rules_path or os.getenv("WORKFLOW_RULES_PATH") or DEFAULT_RULES_PATH
        with Path(configured_path).expanduser().resolve().open("r", encoding="utf-8") as rules_file:
            rules = json.load(rules_file)
        self.rules_version = str(rules.get("version", "unknown"))
        self.department_rules = {item["code"]: item for item in rules.get("departments", [])}
        self.durations = {
            code: self._duration_days(rule.get("estimated_duration_days"), code)
            for code, rule in self.department_rules.items()
        }

    @staticmethod
    def _duration_days(value: Any, department_code: str) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"Estimated duration for {department_code} must be a positive number of days")
        return math.ceil(value)

    def calculate(
        self,
        application: Application,
        approvals: Iterable[ApplicationApproval] | None = None,
        audit_events: Iterable[WorkflowAuditEvent] | None = None,
        as_of: date | None = None,
    ) -> dict[str, Any]:
        approval_rows = list(approvals if approvals is not None else application.approvals)
        required = sorted((row for row in approval_rows if row.is_required), key=lambda row: row.id)
        required_by_code = {row.department_code: row for row in required}
        if len(required_by_code) != len(required):
            raise ValueError("Application workflow contains duplicate department approval records")
        for row in required:
            if row.department_code not in self.durations:
                raise ValueError(f"No estimated duration is configured for {row.department_code}")
            missing_dependencies = set(row.depends_on) - set(required_by_code)
            if missing_dependencies:
                raise ValueError(f"{row.department_code} depends on missing approvals: {sorted(missing_dependencies)}")

        ordered_codes = [row.department_code for row in required]
        dependencies = {row.department_code: list(row.depends_on) for row in required}
        dependents: dict[str, list[str]] = defaultdict(list)
        indegree = {code: len(dependencies[code]) for code in ordered_codes}
        for code in ordered_codes:
            for dependency in dependencies[code]:
                dependents[dependency].append(code)
        ready = deque(code for code in ordered_codes if indegree[code] == 0)
        topological: list[str] = []
        while ready:
            code = ready.popleft()
            topological.append(code)
            for dependent in dependents[code]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
        if len(topological) != len(ordered_codes):
            raise ValueError("Application approval dependencies contain a cycle")

        by_code = required_by_code
        approved = {code for code, row in by_code.items() if row.status == ApprovalStatus.APPROVED.value}
        durations = {
            code: (0 if code in approved else self.durations[code])
            for code in ordered_codes
        }
        start_offsets: dict[str, int] = {}
        finish_offsets: dict[str, int] = {}
        critical_predecessor: dict[str, str | None] = {}
        graph_levels: dict[str, int] = {}
        for code in topological:
            parents = dependencies[code]
            if parents:
                critical_parent = max(parents, key=lambda parent: (finish_offsets[parent], -ordered_codes.index(parent)))
                start_offsets[code] = finish_offsets[critical_parent]
                critical_predecessor[code] = critical_parent
                graph_levels[code] = max(graph_levels[parent] + 1 for parent in parents)
            else:
                start_offsets[code] = 0
                critical_predecessor[code] = None
                graph_levels[code] = 0
            finish_offsets[code] = start_offsets[code] + durations[code]

        terminal = max(ordered_codes, key=lambda code: (finish_offsets[code], -ordered_codes.index(code))) if ordered_codes else None
        critical_codes: list[str] = []
        cursor = terminal
        while cursor is not None:
            critical_codes.append(cursor)
            cursor = critical_predecessor[cursor]
        critical_codes.reverse()
        completion_days = finish_offsets[terminal] if terminal else 0
        critical_set = set(critical_codes)
        blocked: list[dict[str, Any]] = []
        schedule_groups: dict[int, list[str]] = defaultdict(list)
        for code in ordered_codes:
            row = by_code[code]
            unsatisfied = [dependency for dependency in dependencies[code] if dependency not in approved]
            if row.status != ApprovalStatus.APPROVED.value and unsatisfied:
                blocked.append({
                    "id": code,
                    "department_code": code,
                    "department_name": row.department_name,
                    "status": row.status,
                    "blocked_by": unsatisfied,
                })
            if code not in approved:
                schedule_groups[start_offsets[code]].append(code)
        parallel = [
            {"start_day": start_day, "approval_codes": codes,
             "department_names": [by_code[code].department_name for code in codes]}
            for start_day, codes in sorted(schedule_groups.items()) if len(codes) > 1
        ]
        parallel_codes = {code for group in parallel for code in group["approval_codes"]}

        event_rows = list(audit_events or [])
        actual_starts: dict[str, datetime] = {}
        for event in sorted(event_rows, key=lambda item: (item.created_at, item.id)):
            if event.approval_id is None or event.action not in {"REVIEW_STARTED", "APPROVAL_ACTIVATED"}:
                continue
            matched = next((row.department_code for row in required if row.id == event.approval_id), None)
            if matched is not None:
                actual_starts.setdefault(matched, event.created_at)

        base_date = as_of or datetime.now(UTC).date()
        nodes: list[dict[str, Any]] = []
        for code in topological:
            row = by_code[code]
            duration = self.durations[code]
            scheduled_start = base_date + timedelta(days=start_offsets[code])
            if code in actual_starts:
                scheduled_start = actual_starts[code].date()
            if row.status == ApprovalStatus.APPROVED.value and row.decided_at:
                expected_completion = row.decided_at.date()
            else:
                expected_completion = base_date + timedelta(days=finish_offsets[code])
            unsatisfied = [dependency for dependency in dependencies[code] if dependency not in approved]
            nodes.append({
                "id": code,
                "department_code": code,
                "department": row.department_name,
                "approval_name": f"{row.department_name} approval",
                "estimated_duration_days": duration,
                "current_status": row.status,
                "dependencies": dependencies[code],
                "start_date": scheduled_start.isoformat(),
                "expected_completion": expected_completion.isoformat(),
                "display_state": self._display_state(row.status, bool(unsatisfied)),
                "is_critical_path": code in critical_set,
                "is_parallel": code in parallel_codes,
                "is_blocked": row.status != ApprovalStatus.APPROVED.value and bool(unsatisfied),
                "graph_level": graph_levels[code],
            })

        final_status = ApprovalStatus.APPROVED.value if required and all(row.status == ApprovalStatus.APPROVED.value for row in required) else ApprovalStatus.NOT_STARTED.value
        final_level = max(graph_levels.values(), default=-1) + 1
        nodes.append({
            "id": "FINAL_CLEARANCE",
            "department_code": None,
            "department": "Final Clearance",
            "approval_name": "Final Clearance",
            "estimated_duration_days": 0,
            "current_status": final_status,
            "dependencies": ordered_codes,
            "start_date": (base_date + timedelta(days=completion_days)).isoformat(),
            "expected_completion": (base_date + timedelta(days=completion_days)).isoformat(),
            "display_state": "completed" if final_status == ApprovalStatus.APPROVED.value else (
                "blocked" if any(row.status != ApprovalStatus.APPROVED.value for row in required) else "pending"
            ),
            "is_critical_path": True,
            "is_parallel": False,
            "is_blocked": final_status != ApprovalStatus.APPROVED.value,
            "graph_level": final_level,
            "is_milestone": True,
        })
        edges = [
            {"source": dependency, "target": code}
            for code in ordered_codes for dependency in dependencies[code]
        ]
        edges.extend({"source": code, "target": "FINAL_CLEARANCE"} for code in ordered_codes)
        critical_path = critical_codes + ["FINAL_CLEARANCE"]
        bottleneck_code = max(
            (code for code in critical_codes if code not in approved),
            key=lambda code: (self.durations[code], -ordered_codes.index(code)),
            default=None,
        )
        bottleneck = None if bottleneck_code is None else {
            "department_code": bottleneck_code,
            "department_name": by_code[bottleneck_code].department_name,
            "estimated_duration_days": self.durations[bottleneck_code],
            "current_status": by_code[bottleneck_code].status,
        }
        return {
            "application_id": application.id,
            "application_number": application.application_number,
            "rules_version": self.rules_version,
            "nodes": nodes,
            "edges": edges,
            "critical_path": critical_path,
            "parallel_approvals": parallel,
            "blocked_approvals": blocked,
            "bottleneck": bottleneck,
            "estimated_completion_days": completion_days,
            "estimated_completion_date": (base_date + timedelta(days=completion_days)).isoformat(),
        }

    @staticmethod
    def _display_state(status: str, has_unsatisfied_dependencies: bool) -> str:
        if status == ApprovalStatus.APPROVED.value:
            return "completed"
        if status == ApprovalStatus.IN_REVIEW.value:
            return "current"
        if status != ApprovalStatus.APPROVED.value and has_unsatisfied_dependencies:
            return "blocked"
        if status in {ApprovalStatus.INSPECTION_REQUIRED.value, ApprovalStatus.ESCALATED.value,
                      ApprovalStatus.DOCUMENT_CORRECTION.value}:
            return "current"
        return "pending"
