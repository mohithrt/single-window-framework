# MahaClear-AI architecture

MahaClear-AI is a single-window industrial approval platform. An applicant enters a project once, uploads supporting documents, and receives a coordinated workflow across the departments actually required for that project. Officers review the same application in their departmental workspace, while an apex-authority dashboard provides workload, SLA, risk, bottleneck, integration and audit visibility.

## End-to-end flow

1. **Applicant access** — registration/login, one application wizard, draft saving and tracking.
2. **Document pre-validation** — file signature/size checks, PDF/image extraction, OCR, required-document checks, identifier/expiry checks and duplicate detection. Blocking findings stop submission.
3. **Risk assessment** — transparent rule-based scoring produces a score and LOW/MEDIUM/HIGH tier with factor-level explanations.
4. **Workflow initialization** — project facts select required departments and dependency relationships from workflow_rules.json.
5. **Critical path** — the dependency DAG is evaluated with NetworkX when installed, with the existing pure-Python fallback. The result exposes parallel approvals, blocked work, critical path, bottleneck and ETA.
6. **Department review** — officers can start review, approve, reject, request correction, require inspection or escalate.
7. **Inspection** — department and joint inspections can be scheduled and tracked with evidence.
8. **SLA monitoring** — the worker checks deadlines, creates warning/escalation audit events and in-app notifications.
9. **Communication** — notifications are persisted in PostgreSQL. SMTP email and webhook/SMS delivery are optional and failures never break a workflow transaction.
10. **What-if assistant** — deterministic risk/workflow simulation is authoritative. An optional LLM only improves conversational wording.
11. **Government integrations** — mock providers are the default. Each provider can be switched to a configurable authenticated HTTP adapter by environment variables when an authorized endpoint is available.
12. **Fees** — fee calculation is configuration-driven. The default schedule is empty rather than inventing statutory amounts.
13. **Administration** — analytics, applications, audit history, rules, integration history and system health are available to administrators.

## Technology

- **Frontend:** React 19 + Vite + TypeScript.
- **Backend:** FastAPI + SQLAlchemy + PostgreSQL.
- **Document processing:** PyMuPDF + Tesseract + Pillow.
- **Workflow:** dependency DAG, NetworkX, SLA worker and audit events.
- **Risk:** versioned JSON rules with persisted assessment history.
- **AI:** deterministic What-If/assistant logic + optional LLM rewrite.
- **Storage:** PostgreSQL metadata and private local document storage.
- **Cache:** optional Redis with a safe in-process fallback.
- **Integrations:** replaceable mock/HTTP provider contract.
- **Notifications:** in-app plus optional SMTP/webhook delivery.

## Safety and local development

External systems are never contacted by default. Set INTEGRATION_MODE=live (or configured/http) and configure a specific INTEGRATION_<CODE>_URL only after the endpoint and credentials have been authorized.

Redis is opt-in with REDIS_ENABLED=false by default, so the no-Docker local workflow remains functional.

Run without Docker:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```
