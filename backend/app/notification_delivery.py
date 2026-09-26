"""Optional external notification delivery.

Default mode is mock/no-op. SMTP and webhook delivery are enabled only through
explicit environment configuration, and delivery failures never break workflow
transactions.
"""

from __future__ import annotations

import json
import smtplib
import urllib.request
from email.message import EmailMessage
from typing import Any

from app.core.config import settings


class NotificationDelivery:
    def __init__(self) -> None:
        self.mode = settings.notification_mode

    def deliver(
        self,
        *,
        email: str | None,
        phone: str | None,
        subject: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if self.mode in {"smtp", "all"} and email and settings.smtp_host:
            results.append(self._email(email, subject, message))
        if self.mode in {"webhook", "all"} and phone and settings.sms_webhook_url:
            results.append(self._sms(phone, message, metadata or {}))
        if not results:
            results.append({"channel": "mock", "status": "SKIPPED", "reason": "external delivery not configured"})
        return results

    def _email(self, recipient: str, subject: str, message: str) -> dict[str, Any]:
        try:
            mail = EmailMessage()
            mail["Subject"] = subject
            mail["From"] = settings.smtp_from or settings.smtp_username
            mail["To"] = recipient
            mail.set_content(message)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(mail)
            return {"channel": "email", "status": "SENT", "recipient": recipient}
        except Exception as exc:
            return {"channel": "email", "status": "FAILED", "error": type(exc).__name__}

    def _sms(self, phone: str, message: str, metadata: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = json.dumps({"to": phone, "message": message, **metadata}).encode("utf-8")
            request = urllib.request.Request(
                settings.sms_webhook_url,
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "MahaClear-AI/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                return {"channel": "sms", "status": "SENT", "http_status": response.status}
        except Exception as exc:
            return {"channel": "sms", "status": "FAILED", "error": type(exc).__name__}
