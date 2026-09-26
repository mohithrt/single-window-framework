"""Authorized, read-only data tools for the conversational assistant."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.critical_path_service import CriticalPathService
from app.models import (
    Application, ApplicationApproval,
    Inspection, JointInspection, Notification, RiskAssessment, WorkflowAuditEvent,
)
from app.requirement_engine import DocumentRequirementEngine
from app.risk_service import RiskService
from app.sla_service import SlaService
from app.what_if_service import WhatIfService

logger = logging.getLogger(__name__)


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def _function(name: str, description: str, properties: dict[str, Any] | None = None,
              required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {},
                       "required": required or [], "additionalProperties": False},
    }}


_WHAT_IF_FIELDS = {
    "industry_type": {"type": "string", "enum": ["IT / Software", "Manufacturing", "Food Processing", "Textile", "Chemical", "Pharmaceutical", "Automobile", "Electronics", "Logistics", "Other"]},
    "pollution_category": {"type": "string", "enum": ["White", "Green", "Orange", "Red", "Not sure"]},
    "hazardous_materials": {"type": "boolean"},
    "hazardous_materials_details": {"type": ["string", "null"]},
    "investment_amount": {"type": "number", "minimum": 0},
    "built_up_area": {"type": "number", "minimum": 0},
    "number_of_employees": {"type": "integer", "minimum": 0},
    "power_requirement": {"type": "number", "minimum": 0},
    "water_requirement": {"type": "number", "minimum": 0},
    "project_description": {"type": "string"},
    "factory_information": {"type": "string"},
    "fire_safety_information": {"type": "string"},
    "project_location": {"type": "string"},
    "midc_area": {"type": "boolean"},
    "gstin": {"type": "string"},
    "cin": {"type": "string"},
    "udyam_number": {"type": "string"},
}

ASSISTANT_TOOLS = [
    _function("get_application_summary", "Retrieve current status, progress, company, industry, current department, and expected completion from this application.", required=[]),
    _function("get_application_approvals", "Retrieve actual required department approvals, statuses, dependencies, remarks, and SLA clock details.", required=[]),
    _function("get_missing_documents", "Retrieve configured required documents, saved pre-validation issues, and which document categories are missing.", required=[]),
    _function("get_risk_assessment", "Retrieve the saved risk assessment or calculate a non-persisted estimate using the existing deterministic risk rules.", required=[]),
    _function("get_critical_path", "Calculate the application critical path, dependencies, bottleneck, parallel and blocked approvals from saved records.", required=[]),
    _function("get_sla_status", "Retrieve computed SLA state and remaining/overdue time for each required department approval.", required=[]),
    _function("get_inspections", "Retrieve saved single and joint inspection status, schedule, site, and recorded findings.", required=[]),
    _function("get_application_timeline", "Retrieve recent saved audit/timeline events for the application.", required=[]),
    _function("get_notifications", "Retrieve recent notifications visible to the authenticated user for this application.", required=[]),
    _function("run_what_if_analysis", "Run a proposed change through the existing deterministic What-If, risk, workflow, and critical-path rules; never estimate with the LLM.", {"proposed_changes": {"type": "object", "properties": _WHAT_IF_FIELDS, "minProperties": 1, "maxProperties": 12, "additionalProperties": False}}, ["proposed_changes"]),
    _function("get_domain_guidance", "Return general, non-application-specific explanations of MAHACLEAR domain terms.", {"topic": {"type": "string", "enum": ["MPCB", "Udyam registration", "risk tiering", "joint inspection", "SLA", "critical path", "general document guidance"]}}, ["topic"]),
    _function("request_clarification", "Use when the user's question is ambiguous and must be clarified before retrieving or explaining application data.", {"question": {"type": "string", "maxLength": 500}}, ["question"]),
]


def execute_assistant_tool(name: str, arguments: dict[str, Any], *, db: Session,
                           application: Application, user_id: int) -> dict[str, Any]:
    """Run a whitelisted tool against an already-authorized application."""
    approvals = [row for row in application.approvals if row.is_required]

    if name == "get_application_summary":
        current = next((row for row in approvals if row.status in {"IN_REVIEW", "PENDING", "DOCUMENT_CORRECTION", "INSPECTION_REQUIRED", "ESCALATED"}), None)
        if application.current_department_id:
            from app.models import Department
            dept_name = db.scalar(select(Department.name).where(Department.id == application.current_department_id))
        else:
            dept_name = None
        return _json({"application_number": application.application_number, "company": application.company_name,
                      "industry": application.industry_type, "project_type": application.project_type,
                      "status": application.status, "progress_percent": application.progress_percent,
                      "current_department": dept_name or (current.department_name if current else None),
                      "current_approval_status": current.status if current else None,
                      "submitted_at": application.submitted_at,
                      "expected_completion_at": application.expected_completion_at})

    if name in {"get_application_approvals", "get_sla_status"}:
        sla = SlaService()
        results = []
        for row in sorted(approvals, key=lambda item: item.id):
            # SlaService.payload primes missing clock fields; use a value-only view
            # so a read-only assistant tool cannot persist incidental changes.
            view = SimpleNamespace(
                status=row.status, sla_started_at=row.sla_started_at,
                sla_duration_days=row.sla_duration_days, sla_expected_completion=row.sla_expected_completion,
                created_at=row.created_at, escalated_at=row.escalated_at, department_code=row.department_code,
            )
            clock = sla.payload(view)
            include_sla = name == "get_sla_status"
            record = {"department": row.department_name, "department_code": row.department_code,
                      "status": row.status, "dependencies": row.depends_on or [],
                      "decision_message": row.decision_message,
                      "started_at": clock["started_at"], "sla_duration_days": clock["duration_days"],
                      "expected_completion": clock["expected_completion"],
                      "sla_status": clock["status"], "remaining_days": clock["remaining_days"]}
            if not include_sla:
                record.pop("started_at"); record.pop("sla_duration_days"); record.pop("expected_completion")
                record.pop("remaining_days")
            results.append(_json(record))
        return {"approvals": results}

    if name == "get_missing_documents":
        result = DocumentRequirementEngine().evaluate(db, application)
        return _json({
            "checklist": result["required_documents"],
            "applicable_approvals": [row for row in result["approvals"] if row["applicable"]],
            "missing_document_categories": [row["document_type"] for row in result["missing_documents"]],
            "invalid_document_categories": [row["document_type"] for row in result["invalid_documents"]],
            "correction_required_categories": [row["document_type"] for row in result["correction_required_documents"]],
            "counts": result["counts"],
            "completion_percentage": result["completion_percentage"],
            "submission_ready": result["submission_ready"],
            "rules_version": result["rules_version"],
            "note": result["disclaimer"],
        })

    if name == "get_risk_assessment":
        saved = db.scalar(select(RiskAssessment).where(
            RiskAssessment.application_id == application.id,
        ).order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc()).limit(1))
        if saved:
            assessment = saved.assessment_data or {}
            return _json({"source": "SAVED_ASSESSMENT", "score": saved.risk_score, "tier": saved.risk_tier,
                          "assessed_at": saved.created_at,
                          "positive_factors": assessment.get("positive_factors", []),
                          "low_risk_factors": assessment.get("low_risk_factors", []),
                          "explanation": assessment.get("explanation", []),
                          "factor_breakdown": assessment.get("factor_breakdown", [])})
        estimate = RiskService().assess(application)
        return _json({"source": "CURRENT_RULE_CALCULATION_NOT_SAVED", "score": estimate["risk_score"],
                      "tier": estimate["risk_tier"], "positive_factors": estimate["positive_factors"],
                      "low_risk_factors": estimate["low_risk_factors"],
                      "explanation": estimate["explanation"], "factor_breakdown": estimate["factor_breakdown"],
                      "note": "No persisted risk assessment exists; this is a live calculation from configured rules."})

    if name == "get_critical_path":
        if not approvals:
            return {"available": False, "reason": "No required approval records are saved for this application."}
        try:
            return _json(CriticalPathService().calculate(application, application.approvals, application.workflow_events))
        except ValueError as exc:
            return {"available": False, "reason": str(exc)}

    if name == "get_inspections":
        singles = db.scalars(select(Inspection).where(Inspection.application_id == application.id).order_by(Inspection.scheduled_at)).all()
        joints = db.scalars(select(JointInspection).where(JointInspection.application_id == application.id).order_by(JointInspection.scheduled_at)).all()
        return _json({"single_inspections": [{"department": item.approval.department_name, "status": item.status,
                    "scheduled_at": item.scheduled_at, "site": item.site or item.location,
                    "findings": item.findings, "recommendation": item.recommendation} for item in singles],
                    "joint_inspections": [{"status": item.status, "scheduled_at": item.scheduled_at,
                    "site": item.site, "findings": item.findings, "recommendation": item.recommendation}
                    for item in joints], "recorded_count": len(singles) + len(joints)})

    if name == "get_application_timeline":
        events = db.scalars(select(WorkflowAuditEvent).where(
            WorkflowAuditEvent.application_id == application.id,
        ).order_by(WorkflowAuditEvent.created_at.desc(), WorkflowAuditEvent.id.desc()).limit(12)).all()
        return _json({"events": [{"action": event.action, "department": event.department_code,
                    "from_status": event.from_status, "to_status": event.to_status,
                    "message": event.message, "occurred_at": event.created_at}
                    for event in reversed(events)]})

    if name == "get_notifications":
        rows = db.scalars(select(Notification).where(
            Notification.application_id == application.id, Notification.user_id == user_id,
        ).order_by(Notification.created_at.desc(), Notification.id.desc()).limit(10)).all()
        return _json({"notifications": [{"type": row.notification_type, "message": row.message,
                    "is_read": row.is_read, "created_at": row.created_at} for row in rows]})

    if name == "run_what_if_analysis":
        changes = arguments.get("proposed_changes")
        if not isinstance(changes, dict) or not changes:
            return {"error": "A specific proposed change is required before running a scenario."}
        try:
            return _json(WhatIfService().analyze(application, changes))
        except (ValueError, TypeError) as exc:
            return {"error": str(exc)}

    if name == "get_domain_guidance":
        topic = arguments.get("topic")
        guidance = {
            "MPCB": "MPCB stands for Maharashtra Pollution Control Board. It is the state body associated with pollution prevention and environmental regulation in Maharashtra. This is general context, not a statement that this application needs MPCB approval.",
            "Udyam registration": "Udyam is India's registration system for Micro, Small and Medium Enterprises (MSMEs). Whether it applies to a particular business depends on that business's circumstances; this assistant does not verify registration with government systems.",
            "risk tiering": "Risk tiering groups an application into levels using the configured prototype factors. It supports review and is not a statutory environmental classification or final government decision.",
            "joint inspection": "A joint inspection is a coordinated site visit involving multiple participating departments. This prototype can show scheduled records and recorded outcomes; officers control whether one is required.",
            "SLA": "SLA means service-level target: the configured expected time for a review step. The prototype's clock is an estimate and does not guarantee a government decision date.",
            "critical path": "A critical path is the longest dependency chain in the saved approval graph and therefore determines the graph's estimated completion duration. Independent approvals can proceed in parallel.",
            "general document guidance": "Industrial application document requirements vary by project, location, department, and current rules. Use this application's saved pre-validation checklist for its configured requirements; this general explanation is not a legal checklist.",
        }
        if topic not in guidance:
            return {"error": "No configured general guidance exists for that topic."}
        return {"topic": topic, "scope": "GENERAL_INFORMATION_NOT_APPLICATION_SPECIFIC", "guidance": guidance[topic]}

    if name == "request_clarification":
        question = str(arguments.get("question", "")).strip()[:500]
        return {"clarification_needed": True, "question": question or "What part would you like me to clarify?"}

    logger.warning("Assistant requested an unregistered tool: %s", name[:80])
    return {"error": "The requested assistant tool is not available."}
