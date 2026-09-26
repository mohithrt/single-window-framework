"""Deterministic, application-specific approval and document requirement engine.

Department applicability comes from WorkflowService's existing configurable
workflow_rules.json. Department document associations come from that same
catalog. General document categories preserve the existing prototype checklist.
These results are indicative prototype guidance, not a legal determination.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.document_catalog import BASE_MANDATORY_DOCUMENTS, DOCUMENT_LABELS
from app.models import Application, ApplicationApproval, ApplicationDocument, ApplicationValidationIssue
from app.workflow_service import WorkflowService


class DocumentRequirementEngine:
    def __init__(self, workflow: WorkflowService | None = None) -> None:
        self.workflow = workflow or WorkflowService()
        known = set(DOCUMENT_LABELS)
        configured = self.workflow.rules.get("document_requirements", {})
        referenced = set(self.workflow.rules.get("baseline_required_documents", BASE_MANDATORY_DOCUMENTS))
        referenced.update(code for values in configured.values() for code in values)
        unknown = referenced - known
        if unknown:
            raise ValueError(f"Requirement rules refer to unsupported document categories: {sorted(unknown)}")

    def required_document_types(self, application: Application) -> set[str]:
        departments = set(self.workflow.determine_required_departments(application))
        configured = self.workflow.rules.get("document_requirements", {})
        return set(self.workflow.rules.get("baseline_required_documents", BASE_MANDATORY_DOCUMENTS)) | {
            code for department in departments for code in configured.get(department, [])
        }

    def evaluate(self, db: Session, application: Application) -> dict[str, Any]:
        rules = self.workflow.rules
        departments_by_code = {row["code"]: row for row in self.workflow.departments}
        applicable_codes = self.workflow.determine_required_departments(application)
        approvals_saved = {
            row.department_code: row
            for row in db.scalars(select(ApplicationApproval).where(
                ApplicationApproval.application_id == application.id
            )).all()
        }
        configured_docs = rules.get("document_requirements", {})
        docs_by_type: dict[str, list[ApplicationDocument]] = defaultdict(list)
        for document in application.documents:
            docs_by_type[document.document_type].append(document)
        issue_rows = db.scalars(select(ApplicationValidationIssue).where(
            ApplicationValidationIssue.application_id == application.id
        ).order_by(ApplicationValidationIssue.id)).all()
        issues_by_document: dict[int, list[ApplicationValidationIssue]] = defaultdict(list)
        issues_by_type: dict[str, list[ApplicationValidationIssue]] = defaultdict(list)
        for issue in issue_rows:
            issues_by_type[issue.document_type].append(issue)
            if issue.document_id is not None:
                issues_by_document[issue.document_id].append(issue)

        departments_for_doc: dict[str, list[str]] = defaultdict(list)
        reasons_for_doc: dict[str, list[str]] = defaultdict(list)
        for code in applicable_codes:
            department = departments_by_code[code]
            reason = self._department_reason(application, department)
            for doc_type in configured_docs.get(code, []):
                departments_for_doc[doc_type].append(code)
                reasons_for_doc[doc_type].append(reason)

        documents: list[dict[str, Any]] = []
        baseline_codes = set(rules.get("baseline_required_documents", BASE_MANDATORY_DOCUMENTS))
        for code, name in DOCUMENT_LABELS.items():
            attached_departments = departments_for_doc.get(code, [])
            is_baseline = code in baseline_codes
            required = is_baseline or bool(attached_departments)
            docs = docs_by_type.get(code, [])
            requirement_type = "MANDATORY" if is_baseline else "CONDITIONAL" if required else "OPTIONAL" if docs else "NOT_REQUIRED"
            if is_baseline:
                reason = "Included in the prototype's general application submission checklist."
            elif required:
                reason = " ".join(dict.fromkeys(reasons_for_doc[code]))
            else:
                reason = "No currently applicable configured department rule requires this category."
            status_value, status_reason, selected = self._document_status(docs, issues_by_document, issues_by_type.get(code, []), required)
            documents.append({
                "document_type": code,
                "document_name": name,
                "description": reason,
                "required": required,
                "requirement_type": requirement_type,
                "reason": reason,
                "applicable_department": attached_departments[0] if attached_departments else None,
                "applicable_departments": attached_departments,
                "status": status_value,
                "status_reason": status_reason,
                "uploaded_document_id": selected.id if selected else None,
                "validation_status": selected.status if selected else None,
                "uploaded_documents": [{
                    "id": doc.id, "file_name": doc.file_name, "status": doc.status,
                    "uploaded_at": doc.uploaded_at,
                } for doc in docs],
            })

        approval_results = []
        for dept in self.workflow.departments:
            code = dept["code"]
            applicable = code in applicable_codes
            approval = approvals_saved.get(code)
            reason = self._department_reason(application, dept) if applicable else "No configured department applicability rule matched the current application data."
            approval_results.append({
                "department": code,
                "approval_name": dept["name"],
                "applicable": applicable,
                "reason": reason,
                "required_documents": configured_docs.get(code, []) if applicable else [],
                "status": (approval.status if approval else "NOT_STARTED") if applicable else "NOT_REQUIRED",
                "recorded_status": approval.status if approval else None,
            })

        required = [item for item in documents if item["required"]]
        complete_statuses = {"VALID"}
        completed = sum(item["status"] in complete_statuses for item in required)
        counts = {
            "required": len(required),
            "uploaded": sum(bool(item["uploaded_documents"]) for item in required),
            "valid": sum(item["status"] == "VALID" for item in required),
            "missing": sum(item["status"] == "MISSING" for item in required),
            "needs_correction": sum(item["status"] in {"INVALID", "NEEDS_CORRECTION", "EXPIRED"} for item in required),
        }
        blocked = [item for item in required if item["status"] != "VALID"]
        return {
            "application_id": application.id,
            "application_number": application.application_number,
            "rules_version": rules.get("version", "unversioned"),
            "indicative": True,
            "disclaimer": "Indicative requirement based on the information provided and configured prototype rules; subject to applicable department rules.",
            "approvals": approval_results,
            "documents": documents,
            "required_documents": required,
            "missing_documents": [item for item in blocked if item["status"] == "MISSING"],
            "invalid_documents": [item for item in documents if item["status"] in {"INVALID", "EXPIRED"}],
            "correction_required_documents": [item for item in documents if item["status"] == "NEEDS_CORRECTION"],
            "counts": counts,
            "completion_percentage": round(100 * completed / len(required)) if required else 100,
            "submission_ready": not blocked,
        }

    @staticmethod
    def _document_status(docs, issues_by_document, type_issues, required):
        if not docs:
            return ("MISSING", "No document of this category is uploaded.", None) if required else ("NOT_REQUIRED", "This category is not currently required.", None)
        for doc in docs:
            linked = issues_by_document.get(doc.id, [])
            codes = {item.code for item in linked}
            if doc.status == "EXPIRED" or "EXPIRED" in codes:
                continue
            if doc.status == "INVALID" or any(item.status == "INVALID" for item in linked):
                continue
            if doc.status == "VALID" and not any(item.status == "WARNING" for item in linked):
                return "VALID", "An uploaded file passed the available checks.", doc
        newest = docs[-1]
        linked = issues_by_document.get(newest.id, [])
        all_issues = linked or type_issues
        if newest.status == "EXPIRED" or any(item.code == "EXPIRED" for item in all_issues):
            return "EXPIRED", next((item.message for item in all_issues if item.code == "EXPIRED"), "The uploaded document appears expired."), newest
        if newest.status == "INVALID" or any(item.status == "INVALID" for item in all_issues):
            return "INVALID", next((item.message for item in all_issues if item.status == "INVALID"), "The uploaded document failed validation."), newest
        if newest.status in {"WARNING"} or any(item.status == "WARNING" for item in all_issues):
            return "NEEDS_CORRECTION", next((item.message for item in all_issues if item.status == "WARNING"), "Document checks need applicant review."), newest
        if newest.status == "PROCESSING":
            return "VALIDATING", "Document processing is in progress.", newest
        if newest.status in {"UPLOADED", "VALIDATING"}:
            return newest.status, "File uploaded; validation has not yet been recorded.", newest
        return "UPLOADED", "File uploaded; validation has not yet been recorded.", newest

    def _department_reason(self, application: Application, department: dict[str, Any]) -> str:
        matches = [condition for condition in department.get("required_when_any", [])
                   if self.workflow._matches(application, condition)]
        if department.get("default_required") and not matches:
            return f"{department['name']} is included by the configured default applicability rule."
        if matches:
            condition = matches[0]
            field = condition["field"].replace("_", " ")
            value = getattr(application, condition["field"])
            return f"{department['name']} applies because the configured rule matched {field}: {value}."
        return f"{department['name']} applies under the configured department rules."
