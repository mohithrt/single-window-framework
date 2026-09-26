# MahaClear AI Assistant

The application assistant now uses an OpenAI-compatible LLM for natural-language intent, multi-turn conversation, tool selection, and explanations. It does not query PostgreSQL itself. The backend exposes a fixed set of authorized tools that read existing application services and records; risk and What-If calculations remain deterministic.

## Provider configuration

Set these variables in the backend `.env` file. Do not put the key in frontend variables or commit it.

```dotenv
LLM_PROVIDER=openai_compatible
LLM_API_KEY=your-provider-key
LLM_API_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openrouter/free
LLM_TIMEOUT_SECONDS=20
LLM_MAX_TOKENS=700
LLM_MAX_HISTORY_MESSAGES=12
LLM_MAX_TOOL_ROUNDS=3
```

`openai_compatible` is the provider adapter. It supports chat completions with function/tool calling at either a provider root URL or a complete `/chat/completions` URL. OpenRouter is the current example configuration; any compatible provider/model must support tool calls. Restart the FastAPI backend after changing these values. The key is sent only from the backend to the configured provider.

## Available tools

- `get_application_summary`
- `get_application_approvals`
- `get_missing_documents`
- `get_risk_assessment`
- `get_critical_path`
- `get_sla_status`
- `get_inspections`
- `get_application_timeline`
- `get_notifications`
- `run_what_if_analysis`
- `get_domain_guidance`
- `request_clarification`

The route first verifies the authenticated user can access the selected application. Applicants are limited to owned applications; officers need a reviewer assignment or a required approval in their department; admins can access applications. Session history is additionally scoped to its creating user. Each tool receives the already-authorized application object, never an application ID supplied by the model.

## Grounding and memory

The model sees a small application identity context and only the tool results relevant to a question. Business facts come from PostgreSQL and existing rule/services. The model cannot mutate the application. What-If inputs are checked by `WhatIfService`; calculated outcomes do not update application state. Tax identifiers, applicant contact details, document OCR contents, and whole-table database data are not included in tool context.

Conversation turns are stored in the existing `ai_chat_sessions` and `ai_chat_messages` tables. Assistant messages keep tool names/results in the existing JSON field so relevant evidence can be used for follow-ups. The LLM request includes only the most recent configured number of messages (default 12), with per-message and tool-result size limits.

If the key is missing, the provider fails, or a response is malformed, the response is labeled as built-in fallback and explicitly says the AI service is unavailable. It never labels a deterministic answer as LLM-generated. Chat responses are non-streaming; the UI shows a loading indicator while the backend retrieves data and generates a response.

## Verification

From `backend`, run the deterministic/fake-provider and RBAC tests:

```powershell
$env:PYTHONPATH = ".;.venv312\Lib\site-packages"
python -m pytest tests\test_conversational_assistant.py tests\test_admin_ai_integrations.py -q
```

The live-provider conversation suite is opt-in because it makes external model requests and may incur provider usage:

```powershell
$env:PYTHONPATH = ".;.venv312\Lib\site-packages"
$env:MAHACLEAR_RUN_LIVE_LLM = "1"
python -m pytest tests\test_real_assistant_live.py -q -s
```
