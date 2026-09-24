"""Rule-grounded application what-if analysis and deterministic assistant replies."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from app.critical_path_service import CriticalPathService
from app.models import Application, ApplicationApproval, IndustryType, PollutionCategory
from app.risk_service import RiskService
from app.workflow_service import WorkflowService

ALLOWED_CHANGES = {
    "industry_type", "pollution_category", "hazardous_materials", "hazardous_materials_details",
    "investment_amount", "built_up_area", "number_of_employees", "power_requirement",
    "water_requirement", "project_description", "factory_information", "fire_safety_information",
    "project_location", "midc_area", "gstin", "cin", "udyam_number",
}
DOCUMENT_NAMES = {
    "ENVIRONMENTAL_DOCUMENTS": "Environmental documents",
    "LAND_OWNERSHIP_LEASE": "Land ownership / lease documents",
    "BUILDING_PLAN": "Building plan",
    "FACTORY_DOCUMENTS": "Factory documents",
    "FIRE_SAFETY_DOCUMENTS": "Fire safety documents",
    "GST_CERTIFICATE": "GST certificate",
    "INCORPORATION_CERTIFICATE": "Incorporation certificate",
    "UDYAM_CERTIFICATE": "Udyam certificate",
}


class WhatIfService:
    def __init__(self) -> None:
        self.risk = RiskService()
        self.workflow = WorkflowService()
        self.critical_path = CriticalPathService()

    def analyze(self, application: Application, proposed_changes: dict[str, Any]) -> dict[str, Any]:
        unknown = set(proposed_changes) - ALLOWED_CHANGES
        if unknown:
            raise ValueError(f"Unsupported what-if fields: {', '.join(sorted(unknown))}")
        numeric_fields = {"investment_amount", "built_up_area", "power_requirement", "water_requirement", "number_of_employees"}
        for field in numeric_fields & proposed_changes.keys():
            value = proposed_changes[field]
            if isinstance(value, bool):
                raise ValueError(f"{field} must be a non-negative number")
            try:
                number = Decimal(str(value))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"{field} must be a non-negative number") from exc
            if not number.is_finite() or number < 0 or (field == "number_of_employees" and number != number.to_integral_value()):
                raise ValueError(f"{field} must be a non-negative {'integer' if field == 'number_of_employees' else 'number'}")
            proposed_changes[field] = int(number) if field == "number_of_employees" else float(number)
        for field in ("hazardous_materials", "midc_area"):
            if field in proposed_changes and not isinstance(proposed_changes[field], bool):
                raise ValueError(f"{field} must be true or false")
        if "industry_type" in proposed_changes and proposed_changes["industry_type"] not in {item.value for item in IndustryType}:
            raise ValueError("industry_type must match a configured industry")
        if "pollution_category" in proposed_changes and proposed_changes["pollution_category"] not in {item.value for item in PollutionCategory}:
            raise ValueError("pollution_category must match a configured category")
        before_risk = self.risk.assess(application)
        baseline_values = {column.name: getattr(application, column.name) for column in Application.__table__.columns}
        baseline_values["risk_tier"] = before_risk["risk_tier"]
        scenario_values = {**baseline_values, **proposed_changes}
        baseline = SimpleNamespace(**baseline_values, documents=application.documents)
        scenario_before_tier = SimpleNamespace(**scenario_values, documents=application.documents)
        after_risk = self.risk.assess(scenario_before_tier)
        scenario_values["risk_tier"] = after_risk["risk_tier"]
        scenario = SimpleNamespace(**scenario_values, documents=application.documents)
        before_codes = set(self.workflow.determine_required_departments(baseline))
        after_codes = set(self.workflow.determine_required_departments(scenario))
        added, removed = after_codes - before_codes, before_codes - after_codes
        before_days = self._workflow_duration(baseline, before_codes)
        after_days = self._workflow_duration(scenario, after_codes)
        existing_documents = {document.document_type for document in application.documents}
        document_rules = self.workflow.rules.get("document_requirements", {})
        additional_documents = sorted({
            document_type for code in added for document_type in document_rules.get(code, [])
            if document_type not in existing_documents
        })
        names = {item["code"]: item["name"] for item in self.workflow.departments}
        departments = [{"department_code": code, "department": names.get(code, code), "effect": "ADDED"}
                       for code in sorted(added)]
        departments += [{"department_code": code, "department": names.get(code, code), "effect": "REMOVED"}
                        for code in sorted(removed)]
        inspection_codes = {"DISH", "FIRE_SERVICES", "MPCB"}
        inspection_change = sorted((after_codes & inspection_codes) - (before_codes & inspection_codes))
        fee_schedule = self.workflow.rules.get("fee_schedule", {})
        fee_change = None
        fee_note = "No fee schedule is configured, so a fee change cannot be estimated."
        if fee_schedule:
            old_fee = sum(float(fee_schedule.get(code, 0)) for code in before_codes)
            new_fee = sum(float(fee_schedule.get(code, 0)) for code in after_codes)
            fee_change = round(new_fee - old_fee, 2)
            fee_note = "Fee delta uses the configured prototype fee schedule."
        risk_delta = after_risk["risk_score"] - before_risk["risk_score"]
        explanation = [
            f"Configured risk rules change the score from {before_risk['risk_score']}/100 ({before_risk['risk_tier']}) to {after_risk['risk_score']}/100 ({after_risk['risk_tier']}).",
            self._department_explanation(added, removed),
            f"Configured approval durations estimate {before_days} days currently and {after_days} days for this scenario.",
            fee_note,
        ]
        if additional_documents:
            explanation.append("Newly required department rules identify additional document types; check the list before relying on it.")
        if inspection_change:
            explanation.append("The changed scenario adds department reviews associated with environmental, factory-safety, or fire screening; inspection scheduling remains an officer decision.")
        return {
            "application_id": application.id,
            "proposed_changes": proposed_changes,
            "risk_change": {
                "score_before": before_risk["risk_score"], "score_after": after_risk["risk_score"],
                "score_delta": risk_delta, "tier_before": before_risk["risk_tier"], "tier_after": after_risk["risk_tier"],
                "factor_breakdown": after_risk["factor_breakdown"],
            },
            "affected_departments": departments,
            "additional_documents": [{"document_type": code, "name": DOCUMENT_NAMES.get(code, code)} for code in additional_documents],
            "inspection_implications": [{"department_code": code, "department": names.get(code, code)} for code in inspection_change],
            "estimated_time_change_days": after_days - before_days,
            "estimated_time_before_days": before_days,
            "estimated_time_after_days": after_days,
            "estimated_fee_change": fee_change,
            "explanation": explanation,
            "rule_versions": {"risk": self.risk.rules["version"], "workflow": self.workflow.rules["version"]},
            "source": "Configured MAHACLEAR-AI prototype rules; this is a planning estimate, not a government decision.",
        }

    def answer(self, question: str, application: Application,
               approvals: list[ApplicationApproval], inspections: list[Any] | None = None,
               audit_events: list[Any] | None = None) -> tuple[str, dict[str, Any] | None]:
        changes = self.parse_proposed_changes(question, application)
        if changes:
            result = self.analyze(application, changes)
            risk = result["risk_change"]
            direction = "increases" if risk["score_delta"] > 0 else "decreases" if risk["score_delta"] < 0 else "does not change"
            added = [item["department"] for item in result["affected_departments"] if item["effect"] == "ADDED"]
            docs = [item["name"] for item in result["additional_documents"]]
            reply = (
                f"Demo AI / Rule-based response. Under the configured rules, the risk score {direction} "
                f"by {abs(risk['score_delta'])} points ({risk['score_before']} → {risk['score_after']}); "
                f"the tier changes from {risk['tier_before']} to {risk['tier_after']}. "
                f"Estimated workflow duration changes by {result['estimated_time_change_days']:+d} days "
                f"({result['estimated_time_before_days']} → {result['estimated_time_after_days']} days). "
            )
            reply += f"Additional department reviews: {', '.join(added) if added else 'none under current configured rules'}. "
            reply += f"Potential additional documents: {', '.join(docs) if docs else 'none identified by configured rules'}. "
            reply += result["explanation"][-1]
            return reply, result
        lowered = question.casefold()
        if any(word in lowered for word in ("document", "certificate", "paperwork")):
            required_codes = set(self.workflow.determine_required_departments(application))
            requirements = self.workflow.rules.get("document_requirements", {})
            required_docs = sorted({code for department in required_codes for code in requirements.get(department, [])})
            saved_docs = {item.document_type for item in application.documents}
            missing = [code for code in required_docs if code not in saved_docs]
            statuses = [{"document_type": code, "name": DOCUMENT_NAMES.get(code, code),
                         "status": "PRESENT" if code in saved_docs else "MISSING"} for code in required_docs]
            response = ("Demo AI / Rule-based response. Current configured department rules identify these document types: "
                        + (", ".join(DOCUMENT_NAMES.get(code, code) for code in required_docs) or "none"))
            response += ". Missing from this application: " + (", ".join(DOCUMENT_NAMES.get(code, code) for code in missing) or "none among these department-specific requirements") + "."
            response += " The separate submission checklist may also require documents; consult the pre-validation page for its saved results."
            return response, {"required_documents": statuses, "rule_versions": {"workflow": self.workflow.rules["version"]}}
        if "inspection" in lowered or "site visit" in lowered:
            scheduled = inspections or []
            current_needed = [row.department_name for row in approvals if row.is_required and row.status == "INSPECTION_REQUIRED"]
            items = [{"department": getattr(item, "department_name", "Joint inspection"),
                      "status": item.status, "scheduled_at": item.scheduled_at.isoformat(),
                      "site": getattr(item, "site", None) or getattr(item, "location", None)} for item in scheduled]
            if items:
                summary = "; ".join(f"{row['department']} — {row['status']} at {row['site']} ({row['scheduled_at']})" for row in items)
                response = f"Demo AI / Rule-based response. Saved inspection records for this application: {summary}."
            elif current_needed:
                response = f"Demo AI / Rule-based response. Current saved approval statuses require inspection action from {', '.join(current_needed)}, but no inspection record is scheduled."
            else:
                response = "Demo AI / Rule-based response. No inspection is currently scheduled or marked required in the saved application workflow. Officers may still determine that an inspection is needed during review."
            return response, {"inspections": items, "inspection_required_departments": current_needed}
        if "timeline" in lowered or "what happened" in lowered or "history" in lowered:
            saved_events = sorted(audit_events or [], key=lambda event: (event.created_at, event.id))
            recent = saved_events[-8:]
            items = [{"action": event.action, "department": event.department_code,
                      "status": event.to_status, "message": event.message,
                      "occurred_at": event.created_at.isoformat()} for event in recent]
            response = ("Demo AI / Rule-based response. Recent saved application events: "
                        + ("; ".join(f"{item['action']} ({item['occurred_at']})" for item in items) or "there are no workflow events yet") + ".")
            return response, {"events": items}
        if "fee" in lowered or "cost" in lowered:
            return "Demo AI / Rule-based response. No government fee schedule is configured in this prototype, so I cannot estimate fees. No live fee or government API was queried.", {"estimated_fee_change": None, "fee_schedule_configured": False}
        if any(word in question.casefold() for word in ("delay", "delaying", "bottleneck", "waiting on", "blocking")):
            try:
                path = self.critical_path.calculate(application, approvals)
            except ValueError as exc:
                return f"Demo AI / Rule-based response. Current approval graph is incomplete: {exc}", None
            bottleneck = path.get("bottleneck")
            blocked = path.get("blocked_approvals", [])
            if not bottleneck:
                return "Demo AI / Rule-based response. No required approvals are currently delaying this application.", path
            blockers = ", ".join(f"{item['department_name']} (waiting on {', '.join(item['blocked_by'])})" for item in blocked[:4])
            text = f"Demo AI / Rule-based response. The saved critical path identifies {bottleneck['department_name']} ({bottleneck['current_status']}) as the current bottleneck; its configured duration is {bottleneck['estimated_duration_days']} days."
            if blockers:
                text += f" Blocked approvals: {blockers}."
            return text, path
        approval_summary = ", ".join(f"{row.department_name}: {row.status}" for row in approvals if row.is_required) or "no approvals have been initialized"
        return ("Demo AI / Rule-based response. This application's saved required approvals are " + approval_summary
                + ". I can compare factory area, hazardous-material declarations, industry, pollution category, investment, power, or location against configured rules. Ask about missing documents, scheduled inspections, saved timeline events, or fees (which are unconfigured).", None)

    @staticmethod
    def parse_proposed_changes(question: str, application: Application) -> dict[str, Any]:
        text = question.casefold()
        changes: dict[str, Any] = {}
        area_mentions = re.findall(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square\s+feet)", text)
        if area_mentions and any(term in text for term in ("increase", "change", "from", "to", "make it", "set it")):
            candidate = float(area_mentions[-1].replace(",", ""))
            if candidate != float(application.built_up_area or 0):
                changes["built_up_area"] = candidate
        if any(term in text for term in ("remove hazardous", "without hazardous", "no hazardous", "remove chemicals", "without chemicals", "remove chemical")):
            changes["hazardous_materials"] = False
            changes["hazardous_materials_details"] = None
        elif any(term in text for term in ("add hazardous", "use hazardous", "hazardous chemicals", "hazardous materials")):
            changes["hazardous_materials"] = True
        for field, pattern in (
            ("investment_amount", r"(?:investment|invest)\s+(?:to|of|at)\s+₹?\s*([\d,]+(?:\.\d+)?)"),
            ("number_of_employees", r"(?:employees|staff)\s+(?:to|of|at)\s+([\d,]+)"),
            ("power_requirement", r"(?:power|electricity)\s+(?:to|of|at)\s+([\d,]+(?:\.\d+)?)"),
        ):
            found = re.search(pattern, text)
            if found:
                changes[field] = int(found.group(1).replace(",", "")) if field == "number_of_employees" else float(found.group(1).replace(",", ""))
        return changes

    def _workflow_duration(self, application: Any, required_codes: set[str]) -> int:
        by_code = {item["code"]: item for item in self.workflow.departments}
        memo: dict[str, int] = {}

        def finish(code: str, visiting: set[str]) -> int:
            if code in memo:
                return memo[code]
            if code in visiting:
                raise ValueError("Configured approval dependency cycle")
            visiting.add(code)
            dependencies = [item for item in by_code[code].get("depends_on", []) if item in required_codes]
            result = int(by_code[code].get("estimated_duration_days", 0)) + max((finish(item, visiting) for item in dependencies), default=0)
            visiting.remove(code)
            memo[code] = result
            return result

        return max((finish(code, set()) for code in required_codes), default=0)

    @staticmethod
    def _department_explanation(added: set[str], removed: set[str]) -> str:
        if not added and not removed:
            return "Configured approval rules do not add or remove a department for these changes."
        fragments = []
        if added:
            fragments.append(f"Added: {', '.join(sorted(added))}")
        if removed:
            fragments.append(f"No longer selected: {', '.join(sorted(removed))}")
        return "Configured workflow rules indicate " + "; ".join(fragments) + "."
