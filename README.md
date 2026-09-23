# MAHACLEAR-AI

**Faster, Smarter Industrial Approvals**  
Team North-Star · Smart India Hackathon 2026

MAHACLEAR-AI is a single-window industrial approval platform. The current foundation includes authentication, applicant applications, document management and pre-validation, a transparent risk tiering engine, a configurable department approval workflow, a dependency-driven critical-path schedule, and an officer portal for queue review and persisted department actions.

## Stack

- Frontend: React, TypeScript, Vite
- Backend: FastAPI, SQLAlchemy 2, Alembic
- Database: PostgreSQL
- Authentication: JWT bearer tokens and Argon2 password hashes
- File handling: application support documents (PDF/JPEG/PNG, up to 15 MB each)
- Local orchestration: Docker Compose

## Project layout

```text
mahaclear-ai/
├── backend/
│   ├── app/                 # API, models, auth, applicant workflows, seed command
│   ├── migrations/          # Alembic environment and schema revisions
│   ├── app/config/          # Editable risk and department workflow rules
│   └── tests/               # Auth, applications, document, risk, and workflow tests
├── database/                # Database notes
├── docker/                  # Docker notes
├── docs/                    # Architecture notes
├── frontend/                # Auth, applicant workflow, and department officer portal
├── .env.example
└── docker-compose.yml
```

## Run the application with Docker Compose

Requirements: Docker Desktop (or Docker Engine) with the Compose plugin.

From this directory:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose starts PostgreSQL and Redis, waits for them to be healthy, applies Alembic migrations, seeds the demo roles and accounts, then starts the API and frontend.

- Frontend: <http://localhost:5173>
- API docs: <http://localhost:8000/docs>
- API liveness: <http://localhost:8000/health>
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

To stop: Ctrl+C, then `docker compose down`. Add `--volumes` only when you also want to delete the local PostgreSQL and Redis data.

### Demo accounts

All three seeded demo users share this development password:

```text
MahaClearDemo2026!
```

| Role | Email |
|---|---|
| APPLICANT | applicant@demo.com |
| OFFICER | officer@demo.com |
| ADMIN | admin@demo.com |

`DEMO_PASSWORD` in `.env` changes the password used when the seed command first creates each account. The idempotent seed command does not overwrite an existing account's password. These credentials are for local development only.

## Authentication and access

- `POST /api/auth/register` creates an applicant account. Public registration cannot assign officer or admin roles.
- `POST /api/auth/login` verifies the password and returns a signed bearer token.
- `GET /api/auth/me` requires a valid token.
- `GET /api/applicant/dashboard` is limited to APPLICANT.
- `/api/officer/*` provides the OFFICER-only dashboard, searchable application queue, review details, inspection lists, documents, reports, and profile.
- `GET /api/admin/overview` is limited to ADMIN.
- `POST /api/applications` creates an applicant-owned draft and a generated `MCAI-YYYY-NNNNNN` application ID.
- `GET /api/applications` returns the applicant's application table and total/pending/approved/rejected/action-required counts.
- `GET /api/applications/{id}` and `PATCH /api/applications/{id}` read and autosave a draft owned by the signed-in applicant.
- `POST /api/applications/{id}/documents` uploads a PDF, JPEG, or PNG (up to 15 MB), verifies its signature, hashes it, extracts text, and stores private metadata with the application.
- `POST /api/applications/{id}/documents/{document_id}/replace` replaces a file while preserving the document record; `DELETE` removes it.
- `GET /api/applications/{id}/prevalidation` reads findings; `POST /api/applications/{id}/prevalidation/run` reruns OCR and document checks.
- `GET /api/applications/{id}/risk` returns the latest saved risk assessment and whether its inputs or rules are stale.
- `POST /api/applications/{id}/risk/recalculate` scores the current application, saves an assessment history record, and updates the current dashboard tier.
- `POST /api/applications/{id}/submit` validates application fields and blocks INVALID or MISSING document results before locking the record as SUBMITTED. Warnings can be reviewed and submitted.
- A successful submission creates one approval record for each configured department; the application remains SUBMITTED until a reviewer starts work.
- `GET /api/applications/{id}/approvals` returns department statuses and an audit history for the applicant's own application.
- `GET /api/applications/{id}/critical-path` returns the saved approval dependency graph, critical path, estimated remaining days/date, parallel approval groups, blocked approvals, and bottleneck.
- Department review actions are restricted to OFFICER and ADMIN: `POST /api/approvals/{id}/start-review`, `/approve`, `/reject`, `/request-correction`, `/request-inspection`, and `/escalate`.
- Rejection requires a non-empty `reason`; correction, inspection, and escalation actions require a non-empty `message`. Applicants can acknowledge an uploaded correction with `POST /api/approvals/{id}/correction-submitted`.
- Officer review details combine applicant and project data, saved risk assessment, document/OCR metadata, pre-validation findings, department statuses, inspections, remarks, and audit history. `POST /api/officer/approvals/{id}/remarks` saves an officer-only audit entry. `POST /api/officer/approvals/{id}/inspections` saves a single or joint inspection and updates the approval status; inspection rows are listed through `GET /api/officer/inspections`.

The wizard saves draft edits after a short pause and also saves before changing steps or exiting. Company identity and submitted project details are stored as application snapshots. Documents are stored in the Compose `uploads_data` volume. The replaceable `DocumentProcessor` uses PyMuPDF text extraction and Tesseract OCR for scanned PDFs and images; Docker installs the English Tesseract data. Risk is assessed from saved rules and application data; expected completion is derived from the approval dependency schedule.

Pre-validation requires PAN, land ownership/lease, building plan, project report, environmental, fire safety, factory, and identity documents. GST, Udyam, and incorporation certificates are checked when supplied, but are optional in this baseline checklist. Missing or inconsistent values, duplicate files, unreadable scans, and expired dates are shown before submission.

Risk scoring is additive and signed: each configured factor contributes positive points for risk or negative points for mitigating conditions, the total is clamped to 0–100, then configured thresholds assign LOW, MEDIUM, or HIGH. Industry, pollution, hazardous materials, investment, built-up area, employees, power, environmental impact, fire risk, and location each have a visible factor breakdown. Edit `backend/app/config/risk_rules.json` to adjust values and increment its `version`; set `RISK_RULES_PATH` to load an alternate JSON file. Each assessment saves its input and rule snapshots for audit and becomes stale after relevant draft changes or a rule-version change.

Workflow department selection, dependencies, and estimated review durations live in `backend/app/config/workflow_rules.json`; set `WORKFLOW_RULES_PATH` to use an alternate JSON file. The configured MPCB, MIDC, DISH, Fire Services, GSTN, MCA21, and Udyam records start as PENDING when ready, or NOT_STARTED while dependencies remain. OFFICER and ADMIN transitions, correction requests, inspection requirements, escalations, and dependency activation are recorded in `workflow_audit_events`. Applicants can see department statuses and activity history from the Approvals link, and the computed graph and schedule from the Critical path link.

The critical-path service topologically sorts the application's saved approval dependencies, computes longest-path completion estimates, identifies ready approvals that can run in parallel, marks approvals blocked by unfinished dependencies, and reports the longest remaining department review as a bottleneck. It uses an internal DAG algorithm, so no graph package is required by the backend. The frontend draws nodes and dependency edges from the API response as an SVG; department order and graph shape are not embedded in the page.

The frontend stores the access token in browser local storage and routes each signed-in user to their role dashboard. A user with a different role cannot open another role's dashboard.

## Run backend outside Docker

Requirements: Python 3.12+ and a reachable PostgreSQL instance.

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://mahaclear:change-this-local-password@localhost:5432/mahaclear"
$env:SECRET_KEY = "replace-this-with-a-random-secret-before-deployment"
alembic upgrade head
python -m app.seed_demo_users
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Do not use the example signing key or demo credentials outside local development. If you change `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB` in `.env`, update the matching credentials/database name inside `DATABASE_URL` too.

## Run frontend outside Docker

Requirements: Node.js 20.19+ or 22.12+.

```powershell
Set-Location frontend
npm install
npm run dev
```

The frontend proxies `/api/*` to `http://localhost:8000` when run outside Compose.

## Run the API tests

From `backend/`, after installing the development requirements:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The API tests use a temporary SQLite database for isolated registration, login, JWT, draft autosave, ownership checks, document upload/download/replacement, signature and size validation, duplicate detection, PAN consistency, risk tiers, configurable thresholds, risk history, stale-input detection, workflow selection, dependency activation, role protection, audit events, chained and parallel critical-path schedules, submission validation, dashboard counts, officer queue filtering, persisted review decisions, internal remarks, and single/joint inspection scheduling. The application and Compose configuration use PostgreSQL.

## Current scope

The current database has `users`, `roles`, `companies`, `departments`, `applications`, `application_documents`, `application_validation_issues`, `risk_assessments`, `application_approvals`, `workflow_audit_events`, and `inspections` tables. The applicant experience covers an eight-step Applicant, Company, Project, Location, Industry, Documents, Review, and Submit wizard, plus pre-validation, risk assessment, approval status, and critical-path pages. The officer portal includes dashboard metrics, a filterable queue, review pages, inspections, documents, escalations, reports, and profile. Critical-path schedules are calculated on request from current approval records and do not require additional persisted graph tables.
