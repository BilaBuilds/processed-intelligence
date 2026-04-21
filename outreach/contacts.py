"""
Contact targeting helpers for outreach.
"""

from __future__ import annotations

from typing import Any


def split_terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def has_usable_destination(contact: dict[str, Any]) -> bool:
    return bool(
        str(contact.get("email") or "").strip()
        or str(contact.get("whatsapp_number") or "").strip()
        or str(contact.get("discord_webhook_url") or "").strip()
    )


def channel_destination(contact: dict[str, Any], channel: str) -> str | None:
    mapping = {
        "email": contact.get("email"),
        "whatsapp": contact.get("whatsapp_number"),
        "discord": contact.get("discord_webhook_url"),
    }
    destination = mapping.get(channel)
    if destination is None:
        return None
    text = str(destination).strip()
    return text or None


def contact_matches(contact: dict[str, Any], *, sector: str | None = None, region: str | None = None, preferred_channel: str | None = None) -> bool:
    if not contact.get("is_active"):
        return False
    if preferred_channel and str(contact.get("preferred_channel") or "").strip().lower() != preferred_channel.strip().lower():
        return False
    if region:
        contact_region = str(contact.get("region") or "").strip().lower()
        target_region = region.strip().lower()
        if contact_region and target_region not in contact_region and contact_region not in target_region:
            return False
    if sector:
        contact_sectors = split_terms(contact.get("sectors"))
        target_sector = sector.strip().lower()
        if contact_sectors and all(target_sector not in item for item in contact_sectors):
            return False
    return has_usable_destination(contact)


def filter_contacts(
    contacts: list[dict[str, Any]],
    *,
    active_only: bool = True,
    sector: str | None = None,
    region: str | None = None,
    preferred_channel: str | None = None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for contact in contacts:
        if active_only and not contact.get("is_active"):
            continue
        if not contact_matches(contact, sector=sector, region=region, preferred_channel=preferred_channel):
            continue
        filtered.append(contact)
    return filtered
