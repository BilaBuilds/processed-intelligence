"""
Outbound channel senders with safe fallbacks.
"""

from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any, Callable


def success_result(provider_response: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "sent", "provider_response": provider_response or {}, "error_message": None}


def failure_result(message: str, provider_response: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "failed", "provider_response": provider_response or {}, "error_message": message}


class EmailSender:
    def __init__(self, transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.transport = transport

    def send(self, destination: str, rendered_message: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        if self.transport is not None:
            return self.transport(destination, rendered_message)

        host = os.getenv("OUTREACH_EMAIL_SMTP_HOST")
        sender = os.getenv("OUTREACH_EMAIL_FROM")
        if not host or not sender:
            return failure_result("Email sender not configured.")

        port = int(os.getenv("OUTREACH_EMAIL_SMTP_PORT", "587"))
        username = os.getenv("OUTREACH_EMAIL_SMTP_USERNAME")
        password = os.getenv("OUTREACH_EMAIL_SMTP_PASSWORD")

        message = EmailMessage()
        message["From"] = sender
        message["To"] = destination
        message["Subject"] = rendered_message.get("subject") or "Weekly tender shortlist sample"
        message.set_content(rendered_message["body_text"])

        try:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                if username and password:
                    server.login(username, password)
                server.send_message(message)
            return success_result({"transport": "smtp", "to": destination})
        except Exception as exc:  # pragma: no cover
            return failure_result(str(exc))


class WhatsAppSender:
    def __init__(self, transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.transport = transport

    def send(self, destination: str, rendered_message: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        if self.transport is not None:
            return self.transport(destination, rendered_message)
        provider = str(os.getenv("OUTREACH_WHATSAPP_PROVIDER") or "").strip().lower()
        if provider != "stub":
            return failure_result("WhatsApp provider not configured.")
        return success_result({"transport": "stub", "to": destination})


class DiscordSender:
    def __init__(self, transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.transport = transport

    def send(self, destination: str, rendered_message: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        payload = rendered_message.get("payload") or {"content": rendered_message["body_text"]}
        if self.transport is not None:
            return self.transport(destination, payload)
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            destination,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return success_result({"status_code": response.status})
        except urllib.error.HTTPError as exc:
            return failure_result(f"Discord webhook HTTP {exc.code}", {"status_code": exc.code})
        except urllib.error.URLError as exc:
            return failure_result(str(exc.reason))


def build_default_sender_map(
    *,
    email_transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    whatsapp_transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    discord_transport: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "email": EmailSender(email_transport),
        "whatsapp": WhatsAppSender(whatsapp_transport),
        "discord": DiscordSender(discord_transport),
    }


def send_message(
    channel: str,
    destination: str,
    rendered_message: dict[str, Any],
    metadata: dict[str, Any],
    sender_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    senders = sender_map or build_default_sender_map()
    normalized = channel.strip().lower()
    sender = senders.get(normalized)
    if sender is None:
        return failure_result(f"Unsupported channel: {channel}")
    if not destination:
        return failure_result(f"Missing destination for channel: {channel}")
    return sender.send(destination, rendered_message, metadata)
