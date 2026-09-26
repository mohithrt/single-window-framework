"""OpenAI-compatible chat completions provider with tool-call support."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings


class LLMProviderError(RuntimeError):
    """A safe-to-log provider error; credentials and response bodies are excluded."""


class OpenAICompatibleLLMProvider:
    """Works with OpenAI-compatible APIs, including OpenRouter."""

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *,
             tool_choice: str = "auto") -> dict[str, Any]:
        if not settings.llm_api_key:
            raise LLMProviderError("LLM_API_KEY is not configured")
        base_url = settings.llm_api_base_url.strip().rstrip("/")
        if not base_url:
            raise LLMProviderError("LLM_API_BASE_URL is not configured")
        endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        body = {
            "model": settings.llm_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": 0.2,
            "max_tokens": settings.llm_max_tokens,
        }
        request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {settings.llm_api_key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=settings.llm_timeout_seconds) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            raise LLMProviderError(f"LLM provider returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise LLMProviderError(f"LLM provider network error ({type(exc).__name__})") from None
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LLMProviderError(f"LLM provider returned malformed JSON ({type(exc).__name__})") from None

        try:
            choice = payload["choices"][0]
            message = choice["message"]
            if not isinstance(message, dict):
                raise TypeError
            content = message.get("content")
            calls = message.get("tool_calls", [])
            if content is not None and not isinstance(content, str):
                raise TypeError
            if not isinstance(calls, list):
                raise TypeError
            for call in calls:
                if (not isinstance(call, dict) or not isinstance(call.get("id"), str)
                        or not isinstance(call.get("function"), dict)):
                    raise TypeError
                function = call["function"]
                if not isinstance(function.get("name"), str) or not isinstance(function.get("arguments"), str):
                    raise TypeError
            if not content and not calls:
                raise ValueError
            return {"message": message, "finish_reason": choice.get("finish_reason")}
        except (KeyError, IndexError, TypeError, ValueError):
            raise LLMProviderError("LLM provider returned an invalid chat completion") from None


# Existing imports and tests can continue to use the former abstraction name.
OptionalLLMProvider = OpenAICompatibleLLMProvider
