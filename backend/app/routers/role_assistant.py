from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import CurrentUser
from app.models import RoleCode

router = APIRouter(prefix="/assistant", tags=["Role-aware AI assistant"])


class RoleChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    page: str | None = Field(default=None, max_length=120)


def _reply(role: str, message: str, page: str | None) -> str:
    text = message.lower()
    page_label = (page or "").replace("-", " ").replace("/", " ").strip()

    if role == RoleCode.APPLICANT.value:
        if any(word in text for word in ("delay", "late", "pending", "status")):
            return "I can help you understand your application status, current department, pending approvals, SLA delays and the next action. Open the application from your register for application-specific details."
        if any(word in text for word in ("document", "upload", "certificate", "file")):
            return "For documents, I can help explain required uploads, prevalidation issues and what needs correction. Open the relevant application to get document-specific answers."
        if any(word in text for word in ("fee", "payment", "charge")):
            return "You can review the current fee ledger from the Fees page. Fee amounts are shown only when they are configured by the workflow."
        return f"You're in the Applicant workspace{f' · {page_label}' if page_label else ''}. I can help with applications, documents, prevalidation, risk, approvals, critical-path delays, fees and next steps. For application-specific answers, open that application and ask me there."

    if role == RoleCode.OFFICER.value:
        if any(word in text for word in ("queue", "pending", "application", "review")):
            return "As an Officer, I can help you navigate the application queue, review records, inspect submitted documents, understand prevalidation/risk context, and record department decisions."
        if any(word in text for word in ("inspection", "site", "joint")):
            return "Use Inspections or Joint Inspections to review schedules, participants, checklists, findings and recommendations. I can also explain what information is available on the current review record."
        if any(word in text for word in ("sla", "escalat", "delay", "overdue")):
            return "Use the queue and Escalations views to identify SLA status, overdue approvals and escalation records. Application-specific timing is available when you open the review."
        return f"You're in the Officer workspace{f' · {page_label}' if page_label else ''}. I can guide you through queue review, documents, risk/prevalidation context, inspections, SLA/escalations and reports. Open an application review for record-specific questions."

    if role == RoleCode.ADMIN.value:
        if any(word in text for word in ("health", "system", "redis", "ocr", "llm", "integration")):
            return "The Admin workspace provides System Health for dependency status, OCR/LLM configuration, cache/queue state and configured integration providers. Open System Health for the live checks."
        if any(word in text for word in ("analytics", "department", "bottleneck", "sla", "risk")):
            return "The Admin dashboard provides application volume, department workload, approval/rejection counts, SLA breaches, risk distribution, processing bottlenecks and audit activity."
        if any(word in text for word in ("audit", "log", "trace")):
            return "Use Audit Log to inspect saved workflow events and trace actions against applications and departments."
        return f"You're in the Admin workspace{f' · {page_label}' if page_label else ''}. I can guide you through analytics, departments, applications, audit activity, integrations and system health."

    raise HTTPException(status_code=403, detail="This assistant is not available for the current role.")


@router.post("/chat")
def role_chat(payload: RoleChatRequest, user: CurrentUser) -> dict:
    return {
        "role": user.role.code,
        "message": {
            "role": "assistant",
            "content": _reply(user.role.code, payload.message, payload.page),
        },
        "mode": "ROLE_GUIDANCE",
    }
