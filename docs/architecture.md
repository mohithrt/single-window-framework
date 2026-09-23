# Starter architecture

```text
Browser ── Vite / React / TypeScript :5173
                 │ /api proxy
                 ▼
             FastAPI :8000 ─── PostgreSQL :5432
                         └──── Redis :6379
```

Docker Compose provides local development services and persistent named volumes for PostgreSQL and Redis. The frontend proxies `/api` requests to FastAPI. Alembic manages schema changes. SQLAlchemy relates users to roles, companies, and departments. JWTs authenticate API clients; access guards check each account's current role against the requested role dashboard.

Public registration always assigns APPLICANT. OFFICER and ADMIN accounts are provisioned by authorized administrators or the local demo seeder. Applicant applications are scoped by owner user ID. Drafts are saved through a partial-update API; submission validates required fields and locks the record as SUBMITTED. Supporting files are stored outside the database with private metadata records and owner-checked download routes. Uploads are limited to 15 MB PDF, JPEG, and PNG files; media signatures are checked before storage, file names are sanitized, and opaque storage keys prevent user-controlled paths.

Document processing is behind the `DocumentProcessor` protocol. The current `TesseractPyMuPDFProcessor` extracts embedded PDF text with PyMuPDF and uses Tesseract for scanned PDF pages and images. It extracts PAN, GSTIN, CIN, Udyam IDs, and labelled expiry dates. Processing failures or unreadable scans create warnings so applicants can inspect and replace uploads. Another OCR provider can implement the same protocol.

Pre-validation findings are persisted in `application_validation_issues` and refreshed on upload, replacement, deletion, explicit recheck, and submission. Required baseline categories are PAN, land ownership/lease, building plan, project report, environmental documents, fire safety documents, factory documents, and identity documents. GST, Udyam, and incorporation certificates are optional unless supplied; supplied identifiers are checked against the application. Duplicate content and expired documents are blocking problems. Unreadable scans and unverifiable identifiers are warnings. Submission is blocked while any required document is missing or any finding is INVALID; warnings remain reviewable.

Risk scoring is provided by `RiskService` using the editable `backend/app/config/risk_rules.json` ruleset (override with `RISK_RULES_PATH`). The score sums disclosed signed point contributions for industry, pollution category, hazardous materials, investment, built-up area, employees, power, environmental impact, fire risk, and location. Positive points raise the score, negative points reduce it, and configured thresholds map the clamped 0–100 result to LOW, MEDIUM, or HIGH. Location uses a clearly disclosed MIDC planning-context proxy and configured sensitive-location keywords; it is not a geospatial or regulatory determination.

Each call to `POST /api/applications/{id}/risk/recalculate` creates a `risk_assessments` history row with factor breakdown, explanations, input snapshot, full rule snapshot, and rule version. `GET /api/applications/{id}/risk` returns the latest result and marks it stale when relevant draft inputs or the rules version changed. The applicant dashboard tier clears when risk inputs are edited. This screening aid is not a statutory clearance or final environmental determination. Critical-path routing is not implemented; expected completion dates remain unset.
