"""Optional language layer constrained to deterministic what-if evidence."""

import json
from urllib.request import Request, urlopen

from app.core.config import settings


class OptionalLLMProvider:
    def rewrite(self, question: str, structured_result: dict, fallback: str) -> str:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is not configured")
        request = Request(
            settings.llm_api_base_url,
            data=json.dumps({
                "model": settings.llm_model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": (
                        "Rewrite the supplied deterministic industrial approval analysis in clear language. "
                        "Use only facts and values present in the JSON evidence. Never invent government "
                        "requirements, fees, approvals, timeframes, or decisions. If the evidence says a value "
                        "is unconfigured, say it cannot be estimated. Preserve that this is a prototype estimate."
                    )},
                    {"role": "user", "content": json.dumps({
                        "question": question, "evidence": structured_result,
                        "deterministic_fallback": fallback,
                    }, default=str)},
                ],
            }).encode("utf-8"),
            headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read())
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM returned an empty response")
        return content.strip()
