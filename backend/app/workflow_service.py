"""Configurable department selection, dependencies, and workflow initialization."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    ApplicationApproval,
    ApprovalStatus,
    WorkflowAuditEvent,
)

DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "config" / "workflow_rules.json"
SUPPORTED_OPERATORS = {"equals", "in", "not_in", "gte", "gt", "lte", "lt", "present", "truthy"}


class WorkflowService:
    def __init__(self, rules_path: str | Path | None = None) -> None:
        configured_path = rules_path or os.getenv("WORKFLOW_RULES_PATH") or DEFAULT_RULES_PATH
        self.rules_path = Path(configured_path).expanduser().resolve()
        with self.rules_path.open("r", encoding="utf-8") as rules_file:
            self.rules: dict[str, Any] = json.load(rules_file)
        self.departments: list[dict[str, Any]] = self.rules["departments"]
        self._validate_rules()

    def determine_required_departments(self, application: Application) -> list[str]:
        return [
            department["code"]
            for department in self.departments
            if department.get("default_required", False)
            or any(self._matches(application, condition) for condition in department.get("required_when_any", []))
        ]

    def initialize(self, db: Session, application: Application, actor_user_id: int) -> list[ApplicationApproval]:
        existing = db.scalars(
            select(ApplicationApproval)
            .where(ApplicationApproval.application_id == application.id)
            .order_by(ApplicationApproval.id)
        ).all()
        if existing:
            return list(existing)

        required_codes = set(self.determine_required_departments(application))
        by_code = {department["code"]: department for department in self.departments}
        approvals: list[ApplicationApproval] = []
        dependencies_by_code = {
            code: [dependency for dependency in by_code[code].get("depends_on", []) if dependency in required_codes]
            for code in required_codes
        }
        for department in self.departments:
            code = department["code"]
            is_required = code in required_codes
            dependencies = dependencies_by_code.get(code, [])
            initial_status = (
                ApprovalStatus.PENDING.value
                if is_required and not dependencies
                else ApprovalStatus.NOT_STARTED.value
            )
            approvals.append(ApplicationApproval(
                application_id=application.id,
                department_code=code,
                department_name=department["name"],
                is_required=is_required,
                status=initial_status,
                depends_on=dependencies,
            ))
        db.add_all(approvals)
        db.flush()
        db.add(WorkflowAuditEvent(
            application_id=application.id,
            actor_user_id=actor_user_id,
            action="WORKFLOW_INITIALIZED",
            message="Department approval workflow initialized from configured rules.",
            details={
                "rules_version": self.rules["version"],
                "required_departments": [item["code"] for item in self.departments if item["code"] in required_codes],
                "dependencies": dependencies_by_code,
            },
        ))
        db.flush()
        return approvals

    @staticmethod
    def record_event(
        db: Session,
        approval: ApplicationApproval,
        actor_user_id: int,
        action: str,
        from_status: str | None,
        to_status: str | None,
        message: str | None = None,
        details: dict | None = None,
    ) -> WorkflowAuditEvent:
        event = WorkflowAuditEvent(
            application_id=approval.application_id,
            approval_id=approval.id,
            actor_user_id=actor_user_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            message=message,
            details=details or {},
        )
        db.add(event)
        return event

    def _matches(self, application: Application, condition: dict[str, Any]) -> bool:
        field = condition.get("field")
        operator = condition.get("op")
        if not isinstance(field, str) or operator not in SUPPORTED_OPERATORS or not hasattr(application, field):
            raise ValueError(f"Invalid workflow condition: {condition}")
        value = getattr(application, field)
        expected = condition.get("value")
        if operator == "present":
            return value is not None and (not isinstance(value, str) or bool(value.strip()))
        if operator == "truthy":
            return bool(value)
        if operator == "equals":
            return value == expected
        if operator == "in":
            return value in expected
        if operator == "not_in":
            return value not in expected
        if value is None:
            return False
        left = self._decimal(value)
        right = self._decimal(expected)
        return {
            "gte": left >= right,
            "gt": left > right,
            "lte": left <= right,
            "lt": left < right,
        }[operator]

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Workflow numeric condition received a non-numeric value: {value!r}") from exc

    def _validate_rules(self) -> None:
        codes = [department.get("code") for department in self.departments]
        if len(set(codes)) != len(codes) or not all(isinstance(code, str) for code in codes):
            raise ValueError("Workflow rule department codes must be unique strings")
        known_codes = set(codes)
        graph: dict[str, list[str]] = {}
        for department in self.departments:
            code = department["code"]
            dependencies = department.get("depends_on", [])
            if not set(dependencies).issubset(known_codes):
                raise ValueError(f"Unknown workflow dependency for {code}")
            graph[code] = dependencies
            for condition in department.get("required_when_any", []):
                if condition.get("op") not in SUPPORTED_OPERATORS:
                    raise ValueError(f"Unsupported workflow condition operator: {condition.get('op')}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(code: str) -> None:
            if code in visiting:
                raise ValueError("Workflow department dependencies must be acyclic")
            if code in visited:
                return
            visiting.add(code)
            for dependency in graph[code]:
                visit(dependency)
            visiting.remove(code)
            visited.add(code)

        for code in graph:
            visit(code)
