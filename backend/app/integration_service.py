"""Configurable integration adapters with safe mock defaults.

Real government connectors are intentionally configuration-driven because each
department can expose a different authenticated API contract. When a provider
URL is configured, the generic adapter sends JSON and records the response;
otherwise the existing deterministic mock provider is used.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from app.core.config import settings


class IntegrationProvider(Protocol):
    code: str
    display_name: str

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def check_status(self, reference: str) -> dict[str, Any]: ...
    def get_response(self, reference: str) -> dict[str, Any]: ...


@dataclass
class MockIntegrationProvider:
    code: str
    display_name: str
    demo_status: str
    demo_message: str

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        reference = f"{self.code}-DEMO-{uuid4().hex[:8].upper()}"
        return {
            "reference": reference, "status": self.demo_status,
            "provider_name": f"Mock {self.display_name} Provider",
            "message": self.demo_message, "demo": True,
            "connected_to_government": False,
            "submitted_fields": sorted(payload.keys()),
        }

    def check_status(self, reference: str) -> dict[str, Any]:
        return {"reference": reference, "status": self.demo_status,
                "message": self.demo_message, "demo": True,
                "connected_to_government": False}

    def get_response(self, reference: str) -> dict[str, Any]:
        return {"reference": reference, "provider": self.code,
                "status": self.demo_status, "message": self.demo_message,
                "demo": True, "connected_to_government": False}


class ConfiguredHttpIntegrationProvider:
    def __init__(self, code: str, display_name: str, base_url: str, api_key: str = "") -> None:
        self.code = code
        self.display_name = display_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    @property
    def mode(self) -> str:
        return "CONFIGURED_HTTP"

    def _request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json", "User-Agent": "MahaClear-AI/1.0"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=max(2, settings.integration_timeout_seconds)) as response:
                raw = response.read().decode("utf-8", errors="replace")
                try:
                    body = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    body = {"raw": raw[:4000]}
                return {"http_status": response.status, **body} if isinstance(body, dict) else {"http_status": response.status, "data": body}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.code} integration returned HTTP {exc.code}: {raw[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"{self.code} integration is unreachable: {exc.reason}") from exc

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", self.base_url, payload)
        reference = str(response.get("reference") or response.get("id") or response.get("application_id") or f"{self.code}-{uuid4().hex[:10].upper()}")
        return {
            "reference": reference,
            "status": str(response.get("status") or "SUBMITTED"),
            "provider_name": self.display_name,
            "message": str(response.get("message") or f"{self.display_name} response received."),
            "demo": False,
            "connected_to_government": True,
            "provider_response": response,
        }

    def check_status(self, reference: str) -> dict[str, Any]:
        response = self._request("GET", f"{self.base_url}/{quote(reference, safe='')}")
        return {
            "reference": reference,
            "status": str(response.get("status") or "UNKNOWN"),
            "message": str(response.get("message") or f"{self.display_name} status received."),
            "demo": False,
            "connected_to_government": True,
            "provider_response": response,
        }

    def get_response(self, reference: str) -> dict[str, Any]:
        return self.check_status(reference)


def _mock_providers() -> dict[str, MockIntegrationProvider]:
    return {
        "MPCB": MockIntegrationProvider("MPCB", "MPCB", "SUBMITTED_DEMO", "Demo environmental review request was received."),
        "MIDC": MockIntegrationProvider("MIDC", "MIDC", "SUBMITTED_DEMO", "Demo industrial-area request was received."),
        "DISH": MockIntegrationProvider("DISH", "DISH", "SUBMITTED_DEMO", "Demo factory safety request was received."),
        "FIRE": MockIntegrationProvider("FIRE", "Fire Services", "SUBMITTED_DEMO", "Demo fire review request was received."),
        "GST": MockIntegrationProvider("GST", "GSTN", "VERIFIED_DEMO", "GST identifier format was accepted by the demo provider."),
        "MCA": MockIntegrationProvider("MCA", "MCA21", "VERIFIED_DEMO", "Company identifier format was accepted by the demo provider."),
        "UDYAM": MockIntegrationProvider("UDYAM", "Udyam", "VERIFIED_DEMO", "Udyam identifier format was accepted by the demo provider."),
        "DIGILOCKER": MockIntegrationProvider("DIGILOCKER", "DigiLocker", "DOCUMENTS_AVAILABLE_DEMO", "Demo document exchange is ready; no DigiLocker account was contacted."),
        "EMAIL": MockIntegrationProvider("EMAIL", "Email", "QUEUED_DEMO", "Demo email was queued locally; no email was sent."),
        "SMS": MockIntegrationProvider("SMS", "SMS", "QUEUED_DEMO", "Demo SMS was queued locally; no carrier was contacted."),
    }


DISPLAY_NAMES = {
    "MPCB": "MPCB", "MIDC": "MIDC", "DISH": "DISH", "FIRE": "Fire Services",
    "GST": "GSTN", "MCA": "MCA21", "UDYAM": "Udyam", "DIGILOCKER": "DigiLocker",
    "EMAIL": "Email", "SMS": "SMS",
}
PROVIDERS = _mock_providers()


def _configured_url(code: str) -> str:
    return os.getenv(f"INTEGRATION_{code}_URL", "").strip()


def _configured_key(code: str) -> str:
    return os.getenv(f"INTEGRATION_{code}_API_KEY", "").strip()


def get_provider(provider_code: str) -> IntegrationProvider:
    normalized = provider_code.upper()
    if normalized not in DISPLAY_NAMES:
        raise KeyError(provider_code)
    url = _configured_url(normalized)
    if settings.integration_mode in {"live", "configured", "http"} and url:
        return ConfiguredHttpIntegrationProvider(normalized, DISPLAY_NAMES[normalized], url, _configured_key(normalized))
    return PROVIDERS[normalized]


def provider_catalog() -> list[dict[str, Any]]:
    rows = []
    for code, name in DISPLAY_NAMES.items():
        configured = bool(_configured_url(code))
        live = settings.integration_mode in {"live", "configured", "http"} and configured
        rows.append({
            "code": code, "name": name,
            "mode": "CONFIGURED_HTTP" if live else "MOCK",
            "configured": configured,
            "connected_to_government": live,
        })
    return rows
