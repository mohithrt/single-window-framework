# Database foundation

The PostgreSQL schema is managed by Alembic under `backend/migrations/`.
Revision `20260923_01` creates the identity foundation:

- `roles` — APPLICANT, OFFICER, and ADMIN role codes
- `companies` — optional user organizations
- `departments` — departments associated with a company
- `users` — login identity, Argon2 password hash, role, and optional company/department relationships

Revision `20260923_02` adds:

- `applications` — applicant-owned drafts and submitted application snapshots, project/location details, pollution and factory/fire-safety information, status, progress, and future assessment fields
- `application_documents` — metadata for user-uploaded supporting documents, with file bytes stored in the configured upload volume

Email, role code, company name, ownership/status, application number, company/department membership, and unique department/company code lookups have supporting indexes and constraints. PostgreSQL data is stored in the Compose `postgres_data` volume; uploaded files use `uploads_data`. To apply schema changes, run `alembic upgrade head` from `backend/`; Compose applies migrations before starting the API.
