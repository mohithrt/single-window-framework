"""Opt-in, paid/network integration check; run with MAHACLEAR_RUN_LIVE_LLM=1."""

import os

import pytest

from app.core.config import settings
from test_conversational_assistant import _create_app

pytestmark = pytest.mark.skipif(
    os.getenv("MAHACLEAR_RUN_LIVE_LLM") != "1",
    reason="Set MAHACLEAR_RUN_LIVE_LLM=1 to call the configured real provider.",
)


def test_live_application_conversation_uses_llm_tools_and_memory(client):
    assert settings.llm_api_key, "Configure LLM_API_KEY in the backend environment first."
    application_id, headers = _create_app(client)
    prompts = [
        ("Where is my application right now?", {"get_application_summary"}),
        ("Why is it there?", {"get_application_summary", "get_application_approvals", "get_application_timeline"}),
        ("What documents am I missing?", {"get_missing_documents"}),
        ("What is causing the delay?", {"get_critical_path", "get_sla_status", "get_application_approvals"}),
        ("I removed hazardous chemicals from my project. What happens now?", {"run_what_if_analysis"}),
        ("What does MPCB do?", {"get_domain_guidance"}),
        ("What about that approval?", {"get_application_approvals", "request_clarification"}),
    ]
    session_id = None
    demonstrations = []
    for prompt, acceptable_tools in prompts:
        response = client.post(
            f"/api/applications/{application_id}/assistant/chat", headers=headers,
            json={"message": prompt, "session_id": session_id},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["mode"] == "AI_ASSISTED", data["message"]["content"]
        session_id = data["session_id"]
        used = {item["name"] for item in data["message"]["structured_data"]["tools_used"]}
        demo = f"USER: {prompt}\nTOOLS: {', '.join(sorted(used)) or 'prior retrieved evidence'}\nASSISTANT: {data['message']['content'][:450]}\n"
        print(demo.encode("ascii", "backslashreplace").decode("ascii"))
        if prompt == "Why is it there?" and not used:
            prior = client.get(f"/api/applications/{application_id}/assistant/sessions/{session_id}", headers=headers)
            assert any(message["role"] == "ASSISTANT" and message["structured_data"].get("tools_used")
                       for message in prior.json()["messages"]), "The follow-up has no prior retrieved evidence in memory."
        else:
            assert used & acceptable_tools, f"No expected retrieval tool for: {prompt}; got {used}"
        demonstrations.append((prompt, data["message"]["content"], sorted(used)))
    assert session_id is not None
    saved = client.get(f"/api/applications/{application_id}/assistant/sessions/{session_id}", headers=headers)
    assert saved.status_code == 200 and len(saved.json()["messages"]) == len(prompts) * 2
