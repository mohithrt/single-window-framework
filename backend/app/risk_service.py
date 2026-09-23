"""Config-driven, additive risk scoring with inspectable point contributions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any

from app.models import Application

DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "config" / "risk_rules.json"


@dataclass
class Factor:
    key: str
    label: str
    value: str
    points: int
    explanation: str
    signals: list[str]


class RiskService:
    """Score an application using editable JSON rules and retain auditable inputs."""

    def __init__(self, rules_path: str | Path | None = None) -> None:
        configured_path = rules_path or os.getenv("RISK_RULES_PATH") or DEFAULT_RULES_PATH
        self.rules_path = Path(configured_path).expanduser().resolve()
        with self.rules_path.open("r", encoding="utf-8") as rules_file:
            self.rules: dict[str, Any] = json.load(rules_file)

    def input_snapshot(self, application: Application) -> dict[str, Any]:
        environmental_docs = sorted(
            ({"status": doc.status, "size_bytes": doc.size_bytes}
             for doc in application.documents if doc.document_type == "ENVIRONMENTAL_DOCUMENTS"),
            key=lambda item: (item["status"], item["size_bytes"]),
        )
        return {
            "industry_type": application.industry_type,
            "pollution_category": application.pollution_category,
            "hazardous_materials": application.hazardous_materials,
            "hazardous_materials_details": application.hazardous_materials_details,
            "investment_amount": self._json_number(application.investment_amount),
            "built_up_area": self._json_number(application.built_up_area),
            "number_of_employees": application.number_of_employees,
            "power_requirement": self._json_number(application.power_requirement),
            "project_description": application.project_description,
            "factory_information": application.factory_information,
            "fire_safety_information": application.fire_safety_information,
            "project_location": application.project_location,
            "midc_area": application.midc_area,
            "environmental_documents": environmental_docs,
        }

    def assess(self, application: Application) -> dict[str, Any]:
        rules = self.rules["factors"]
        factors: list[Factor] = []
        factors.append(self._industry(application, rules["industry"]))
        factors.append(self._pollution(application, rules["pollution_category"]))
        factors.append(self._hazardous(application, rules["hazardous_materials"]))
        factors.append(self._range_factor(application.investment_amount, rules["investment_amount"], "investment_amount"))
        factors.append(self._range_factor(application.built_up_area, rules["built_up_area"], "built_up_area"))
        factors.append(self._range_factor(application.number_of_employees, rules["number_of_employees"], "number_of_employees"))
        factors.append(self._range_factor(application.power_requirement, rules["power_requirement"], "power_requirement"))
        factors.append(self._environmental(application, rules["environmental_impact"]))
        factors.append(self._fire(application, rules["fire_risk"]))
        factors.append(self._location(application, rules["location"]))

        raw_score = sum(factor.points for factor in factors)
        score = max(0, min(100, raw_score))
        thresholds = self.rules["tier_thresholds"]
        if score <= int(thresholds["LOW"]["max_score"]):
            tier = "LOW"
        elif score <= int(thresholds["MEDIUM"]["max_score"]):
            tier = "MEDIUM"
        else:
            tier = "HIGH"

        positive_factors = [asdict(factor) for factor in factors if factor.points > 0]
        low_risk_factors = [asdict(factor) for factor in factors if factor.points < 0]
        return {
            "risk_score": score,
            "raw_score": raw_score,
            "risk_tier": tier,
            "positive_factors": positive_factors,
            "low_risk_factors": low_risk_factors,
            "factor_breakdown": [asdict(factor) for factor in factors],
            "explanation": [
                f"The score is the sum of the factor points ({raw_score}) clamped to the 0–100 range.",
                f"A score of {score} falls in the {tier} band under rules version {self.rules['version']}.",
                "This rules-based screening aid supports review; it is not a statutory clearance or final environmental determination.",
            ],
            "rules_version": self.rules["version"],
            "input_snapshot": self.input_snapshot(application),
            "rules_snapshot": self.rules,
        }

    def _industry(self, application: Application, rule: dict) -> Factor:
        value = application.industry_type
        if not value:
            points = int(rule["missing_score"])
            detail = "Industry is not selected; a conservative unknown-industry allowance applies."
        else:
            points = int(rule["scores"].get(value, rule["missing_score"]))
            detail = f"{value} industry contributes {points:+d} points under the configured industry table."
        return Factor("industry", rule["label"], value or "Not provided", points, detail, [])

    def _pollution(self, application: Application, rule: dict) -> Factor:
        value = application.pollution_category
        points = int(rule["scores"].get(value, rule["missing_score"])) if value else int(rule["missing_score"])
        label = value or "Not provided"
        detail = f"{label} pollution category contributes {points:+d} points under the configured category table."
        return Factor("pollution_category", rule["label"], label, points, detail, [])

    def _hazardous(self, application: Application, rule: dict) -> Factor:
        if application.hazardous_materials is True:
            points, value = int(rule["yes_score"]), "Yes"
        elif application.hazardous_materials is False:
            points, value = int(rule["no_score"]), "No"
        else:
            points, value = int(rule["unknown_score"]), "Not provided"
        return Factor("hazardous_materials", "Hazardous materials", value, points,
                      f"Declared hazardous-material use contributes {points:+d} points.", [])

    @staticmethod
    def _range_factor(value: Any, rule: dict, key: str) -> Factor:
        label = rule["label"]
        if value is None:
            points = int(rule["missing_score"])
            return Factor(key, label, "Not provided", points,
                          f"{label} is missing; the configured unknown-input allowance is {points:+d} points.", [])
        numeric = Decimal(str(value))
        selected = rule["ranges"][-1]
        for candidate in rule["ranges"]:
            if "max" not in candidate or numeric <= Decimal(str(candidate["max"])):
                selected = candidate
                break
        points = int(selected["score"])
        unit = rule.get("unit", "")
        display_value = f"{numeric:,.0f} {unit}".strip()
        bound = selected.get("max")
        band = f"up to {Decimal(str(bound)):,.0f}" if bound is not None else "above the prior band"
        return Factor(key, label, display_value, points,
                      f"{label} falls in the {band} {unit} band and contributes {points:+d} points.".replace("  ", " "), [])

    def _environmental(self, application: Application, rule: dict) -> Factor:
        docs = [doc for doc in application.documents if doc.document_type == "ENVIRONMENTAL_DOCUMENTS"]
        doc_valid = any(doc.status == "VALID" for doc in docs)
        points = int(rule["present_environmental_document_score"] if doc_valid
                     else rule["missing_environmental_document_score"])
        reasons: list[str] = []
        signals: list[str] = []
        text = " ".join((application.project_description or "", application.hazardous_materials_details or "",
                         application.factory_information or "")).casefold()
        for signal in rule["risk_signals"]:
            matched = self._matched_terms(text, signal["terms"])
            if matched:
                points += int(signal["points"])
                reasons.append(signal["reason"])
                signals.extend(matched)
        for signal in rule["mitigation_signals"]:
            matched = self._matched_terms(text, signal["terms"])
            if matched:
                points += int(signal["points"])
                reasons.append(signal["reason"])
                signals.extend(matched)
        points = max(int(rule["minimum_score"]), min(int(rule["maximum_score"]), points))
        doc_text = "A readable environmental document is attached" if doc_valid else "No readable environmental document is attached"
        details = [doc_text, *reasons] or ["No configured environmental risk or mitigation phrases matched the project details"]
        return Factor("environmental_impact", rule["label"], doc_text, points,
                      f"{'; '.join(details)}; contribution is {points:+d} points.", sorted(set(signals)))

    def _fire(self, application: Application, rule: dict) -> Factor:
        info = (application.fire_safety_information or "").casefold()
        points = 0
        reasons: list[str] = []
        signals: list[str] = []
        if not info.strip():
            points += int(rule["missing_safety_information_score"])
            reasons.append("Fire-safety information is missing")
        if application.hazardous_materials is True:
            points += int(rule["hazardous_materials_score"])
            reasons.append("Hazardous materials increase fire-load screening points")
        for group_name in ("risk_signals", "mitigation_signals"):
            for signal in rule[group_name]:
                matched = self._matched_terms(info, signal["terms"])
                if matched:
                    points += int(signal["points"])
                    reasons.append(signal["reason"])
                    signals.extend(matched)
        points = max(int(rule["minimum_score"]), min(int(rule["maximum_score"]), points))
        detail = "; ".join(reasons) if reasons else "No configured fire-risk or mitigation phrases matched"
        return Factor("fire_risk", rule["label"], application.fire_safety_information or "Not provided", points,
                      f"{detail}; contribution is {points:+d} points.", sorted(set(signals)))

    def _location(self, application: Application, rule: dict) -> Factor:
        if application.midc_area is True:
            points, context = int(rule["midc_score"]), "MIDC area"
        elif application.midc_area is False:
            points, context = int(rule["outside_midc_score"]), "Outside MIDC"
        else:
            points, context = int(rule["unknown_score"]), "MIDC status not provided"
        text = (application.project_location or "").casefold()
        reasons = []
        matched_terms = []
        for signal in rule["sensitive_location_signals"]:
            matched = self._matched_terms(text, signal["terms"])
            if matched:
                points += int(signal["points"])
                reasons.append(signal["reason"])
                matched_terms.extend(matched)
        points = min(points, int(rule["maximum_signal_score"]))
        details = [context, *reasons]
        return Factor("location", rule["label"], application.project_location or "Not provided", points,
                      f"{'; '.join(details)}; {rule['proxy_note']} Contribution: {points:+d} points.",
                      sorted(set(matched_terms)))

    @staticmethod
    def _matched_terms(text: str, terms: list[str]) -> list[str]:
        return [term for term in terms if term.casefold() in text]

    @staticmethod
    def _json_number(value: Any) -> int | float | str | None:
        if value is None:
            return None
        return str(value) if isinstance(value, Decimal) else value
