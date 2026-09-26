# Applicant document requirements

`GET /api/applications/{application_id}/requirements` runs the deterministic `DocumentRequirementEngine` against the latest saved application fields, current configured department rules, uploaded `ApplicationDocument` rows, and saved `ApplicationValidationIssue` rows. The endpoint uses the same service as the submission check and the assistant's `get_missing_documents` tool.

## Configuration

Edit `backend/app/config/workflow_rules.json`:

- `baseline_required_documents` lists the prototype's unconditional submission checklist.
- `departments[].required_when_any` selects applicable approvals. Conditions can use `equals`, `in`, `not_in`, numeric comparisons, `present`, `truthy`, and case-insensitive string `contains`.
- `document_requirements` maps each department code to categories already supported by `ApplicationDocument.document_type`.

The document labels and supported types live in `backend/app/document_catalog.py`. Keep rule document values aligned with those categories. Draft updates rerun rule-based document checks against saved OCR fields; upload, replace, delete, manual validation, and submit all refresh the existing validation records. No database migration is required: requirements are computed from the existing application, document, approval, and validation tables.

## Statuses and readiness

`MISSING`, `INVALID`, `EXPIRED`, and `NEEDS_CORRECTION` block a required category. A category is `VALID` when at least one associated upload passed the current saved checks; `UPLOADED` means a file exists but checks are not recorded; optional categories without a file are `NOT_REQUIRED`. A warning such as unreadable OCR is surfaced as `NEEDS_CORRECTION` for required categories so applicants can inspect or replace the file.

All results are indicative prototype guidance based on `workflow_rules.json`. They are not statutory/legal advice. Department document associations and baseline categories require review by the relevant government departments before production use.

## Current catalog limits

The application currently has `factory_information` and `fire_safety_information` text fields, but no separate `factory=true` or `fire_safety_required` boolean. The configured department rules therefore use existing industry, project type, hazard, area, pollution, MIDC, and registration fields; they do not claim to infer those missing flags. Chemical/manufacturing/factory project-type text can trigger the configured rules via case-insensitive substring conditions. Add explicit form fields and reviewed rules if the product later needs those flags independently.
