"""Configuration-driven application fee calculation.

No statutory amount is invented here. Rules are read from workflow_rules.json.
An empty fee_schedule therefore safely returns no fees.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.workflow_service import WorkflowService


class FeeService:
    def __init__(self) -> None:
        self.rules: dict[str, Any] = WorkflowService().rules.get("fee_schedule", {})

    @staticmethod
    def _amount(value: Any) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"))

    def calculate(self, application: Any) -> list[dict[str, Any]]:
        if not self.rules:
            return []
        rows: list[dict[str, Any]] = []
        for code, rule in self.rules.items():
            if not isinstance(rule, dict):
                continue
            conditions = rule.get("when", {})
            if conditions and not self._matches(application, conditions):
                continue
            amount = self._amount(rule.get("amount", 0))
            if amount <= 0:
                continue
            rows.append({
                "fee_code": code,
                "description": str(rule.get("description") or code.replace("_", " ").title()),
                "amount": amount,
                "currency": str(rule.get("currency") or "INR"),
            })
        return rows

    @staticmethod
    def _matches(application: Any, conditions: dict[str, Any]) -> bool:
        for field, expected in conditions.items():
            actual = getattr(application, field, None)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False
        return True
