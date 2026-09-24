"""Replaceable government and utility provider contracts with explicit demo mocks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4


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


class MockMPCBProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("MPCB", "MPCB", "SUBMITTED_DEMO", "Demo environmental review request was received.")


class MockMIDCProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("MIDC", "MIDC", "SUBMITTED_DEMO", "Demo industrial-area request was received.")


class MockDISHProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("DISH", "DISH", "SUBMITTED_DEMO", "Demo factory safety request was received.")


class MockFireProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("FIRE", "Fire Services", "SUBMITTED_DEMO", "Demo fire review request was received.")


class MockGSTProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("GST", "GSTN", "VERIFIED_DEMO", "GST identifier format was accepted by the demo provider.")


class MockMCAProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("MCA", "MCA21", "VERIFIED_DEMO", "Company identifier format was accepted by the demo provider.")


class MockUdyamProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("UDYAM", "Udyam", "VERIFIED_DEMO", "Udyam identifier format was accepted by the demo provider.")


class MockDigiLockerProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("DIGILOCKER", "DigiLocker", "DOCUMENTS_AVAILABLE_DEMO", "Demo document exchange is ready; no DigiLocker account was contacted.")


class MockEmailProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("EMAIL", "Email", "QUEUED_DEMO", "Demo email was queued locally; no email was sent.")


class MockSMSProvider(MockIntegrationProvider):
    def __init__(self): super().__init__("SMS", "SMS", "QUEUED_DEMO", "Demo SMS was queued locally; no carrier was contacted.")


PROVIDERS: dict[str, MockIntegrationProvider] = {
    "MPCB": MockMPCBProvider(), "MIDC": MockMIDCProvider(), "DISH": MockDISHProvider(),
    "FIRE": MockFireProvider(), "GST": MockGSTProvider(), "MCA": MockMCAProvider(),
    "UDYAM": MockUdyamProvider(), "DIGILOCKER": MockDigiLockerProvider(),
    "EMAIL": MockEmailProvider(), "SMS": MockSMSProvider(),
}


def get_provider(provider_code: str) -> MockIntegrationProvider:
    normalized = provider_code.upper()
    provider = PROVIDERS.get(normalized)
    if provider is None:
        raise KeyError(provider_code)
    return provider


def provider_catalog() -> list[dict[str, Any]]:
    return [{"code": provider.code, "name": provider.display_name,
             "mode": "MOCK", "connected_to_government": False}
            for provider in PROVIDERS.values()]
