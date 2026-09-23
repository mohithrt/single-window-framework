# MAHACLEAR-AI

**Faster, Smarter Industrial Approvals**  
Team North-Star · Smart India Hackathon 2026

MAHACLEAR-AI is a single-window industrial approval platform. The current foundation includes authentication, applicant applications, document management and pre-validation, plus a transparent risk tiering engine. Department review workflows and critical-path routing are not implemented yet.

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
│   ├── app/                 # API, models, auth, applicant applications, seed command
│   ├── migrations/          # Alembic environment and schema revisions
│   ├── app/config/          # Editable document and risk rules
│   └── tests/               # Auth, applications, document, and risk API tests
├── database/                # Database notes
├── docker/                  # Docker notes
├── docs/                    # Architecture notes
├── frontend/                # Login, registration, applicant dashboard and wizard
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
- `GET /api/officer/department` is limited to OFFICER.
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

The wizard saves draft edits after a short pause and also saves before changing steps or exiting. Company identity and submitted project details are stored as application snapshots. Documents are stored in the Compose `uploads_data` volume. The replaceable `DocumentProcessor` uses PyMuPDF text extraction and Tesseract OCR for scanned PDFs and images; Docker installs the English Tesseract data. Risk calculation is not part of this phase, so dashboard risk shows “Not assessed” and completion dates remain unscheduled.

Pre-validation requires PAN, land ownership/lease, building plan, project report, environmental, fire safety, factory, and identity documents. GST, Udyam, and incorporation certificates are checked when supplied, but are optional in this baseline checklist. Missing or inconsistent values, duplicate files, unreadable scans, and expired dates are shown before submission.

Risk scoring is additive and signed: each configured factor contributes positive points for risk or negative points for mitigating conditions, the total is clamped to 0–100, then configured thresholds assign LOW, MEDIUM, or HIGH. Industry, pollution, hazardous materials, investment, built-up area, employees, power, environmental impact, fire risk, and location each have a visible factor breakdown. Edit `backend/app/config/risk_rules.json` to adjust values and increment its `version`; set `RISK_RULES_PATH` to load an alternate JSON file. Each assessment saves its input and rule snapshots for audit and becomes stale after relevant draft changes or a rule-version change.

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

The API tests use a temporary SQLite database for isolated registration, login, JWT, draft autosave, ownership checks, document upload/download/replacement, signature and size validation, duplicate detection, PAN consistency, risk tiers, configurable thresholds, risk history, stale-input detection, submission validation, and dashboard counts. The application and Compose configuration use PostgreSQL.

## Current scope

The current database has `users`, `roles`, `companies`, `departments`, `applications`, `application_documents`, `application_validation_issues`, and `risk_assessments` tables. The applicant experience covers an eight-step Applicant, Company, Project, Location, Industry, Documents, Review, and Submit wizard, plus pre-validation and risk assessment pages. Department review, critical paths, and escalations remain for later phases.
