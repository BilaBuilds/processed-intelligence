"""
Channel-specific rendering from a shared sample payload.
"""

from __future__ import annotations

from typing import Any


def greeting(contact: dict[str, Any]) -> str:
    if contact.get("contact_name"):
        return f"Hi {contact['contact_name']}"
    if contact.get("company_name"):
        return f"Hi {contact['company_name']} team"
    return "Hi"


def strongest_live_items(sample_payload: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    shortlist = list(sample_payload.get("shortlist") or [])
    review = list(sample_payload.get("review_candidates") or [])
    return (shortlist + review)[:limit]


def intelligence_items(sample_payload: dict[str, Any], limit: int = 2) -> list[dict[str, Any]]:
    return list(sample_payload.get("market_intelligence") or [])[:limit]


def format_item(item: dict[str, Any]) -> str:
    parts = [str(item.get("title") or "Untitled opportunity")]
    buyer = item.get("buyer_name")
    if buyer:
        parts.append(f"buyer: {buyer}")
    region = item.get("region")
    if region:
        parts.append(f"region: {region}")
    deadline = item.get("deadline_at")
    if deadline:
        parts.append(f"deadline: {deadline}")
    value = item.get("value_amount")
    currency = item.get("value_currency")
    if value not in (None, ""):
        parts.append(f"value: {value} {currency or ''}".strip())
    url = item.get("source_url")
    if url:
        parts.append(f"url: {url}")
    return " | ".join(parts)


def render_email(contact: dict[str, Any], sample_payload: dict[str, Any]) -> dict[str, Any]:
    live_lines = [f"- {format_item(item)}" for item in strongest_live_items(sample_payload)]
    intel_lines = [f"- {format_item(item)}" for item in intelligence_items(sample_payload)]
    body_lines = [
        f"{greeting(contact)},",
        "",
        "Here is a compact sample of live public sector opportunities matched to your profile this week.",
        "",
        "Top live opportunities:",
        *(live_lines or ["- No live opportunities matched this run."]),
        "",
        "Recent market intelligence:",
        *(intel_lines or ["- No award signals available in this run."]),
        "",
        sample_payload["cta"] + ".",
    ]
    return {
        "channel": "email",
        "template_key": "weekly_shortlist_sample",
        "subject": f"Weekly tender shortlist sample for {contact.get('company_name') or 'your team'}",
        "body_text": "\n".join(body_lines),
    }


def render_whatsapp(contact: dict[str, Any], sample_payload: dict[str, Any]) -> dict[str, Any]:
    live_lines = [f"{index}. {format_item(item)}" for index, item in enumerate(strongest_live_items(sample_payload), start=1)]
    intel_lines = [f"- {format_item(item)}" for item in intelligence_items(sample_payload)]
    body_lines = [
        f"{greeting(contact)}, here is your weekly shortlist sample.",
        "Live opportunities:",
        *(live_lines or ["- No live opportunities matched this run."]),
        "Market intelligence:",
        *(intel_lines or ["- No award signals available in this run."]),
        sample_payload["cta"] + ".",
    ]
    return {
        "channel": "whatsapp",
        "template_key": "weekly_shortlist_sample",
        "subject": None,
        "body_text": "\n".join(body_lines),
    }


def render_discord(contact: dict[str, Any], sample_payload: dict[str, Any]) -> dict[str, Any]:
    live_lines = [f"- {format_item(item)}" for item in strongest_live_items(sample_payload)]
    intel_lines = [f"- {format_item(item)}" for item in intelligence_items(sample_payload)]
    content = "\n".join(
        [
            f"**{contact.get('company_name') or 'Weekly shortlist sample'}**",
            "",
            "Top live opportunities:",
            *(live_lines or ["- No live opportunities matched this run."]),
            "",
            "Recent market intelligence:",
            *(intel_lines or ["- No award signals available in this run."]),
            "",
            sample_payload["cta"] + ".",
        ]
    )
    return {
        "channel": "discord",
        "template_key": "weekly_shortlist_sample",
        "subject": None,
        "body_text": content,
        "payload": {"content": content},
    }


def render_message(channel: str, contact: dict[str, Any], sample_payload: dict[str, Any]) -> dict[str, Any]:
    normalized = channel.strip().lower()
    if normalized == "email":
        return render_email(contact, sample_payload)
    if normalized == "whatsapp":
        return render_whatsapp(contact, sample_payload)
    if normalized == "discord":
        return render_discord(contact, sample_payload)
    raise ValueError(f"Unsupported outreach channel: {channel}")
