from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from enrichment.models.evidence import EvidenceItem
from enrichment.storage.evidence_ledger import EvidenceLedger


def get_client_safe_claims(
    entity_key: str,
    min_confidence: float = 0.75,
    ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    ledger = EvidenceLedger(ledger_path) if ledger_path else EvidenceLedger()
    candidates = ledger.get_by_entity_key(entity_key)
    grouped: dict[str, list[EvidenceItem]] = {}
    for item in candidates:
        grouped.setdefault(item.field_name, []).append(item)

    safe: dict[str, Any] = {}
    for field_name, items in grouped.items():
        if any(item.conflict for item in items):
            continue
        valid = [
            item
            for item in items
            if _is_client_safe_item(item, min_confidence)
        ]
        if not valid:
            continue
        selected = sorted(
            valid,
            key=lambda item: (item.confidence, item.collected_at),
            reverse=True,
        )[0]
        safe[field_name] = {
            "value": selected.field_value,
            "confidence": selected.confidence,
            "source": selected.source_provider,
            "timestamp": selected.collected_at.isoformat(),
            "evidence_id": selected.evidence_id,
        }
    return safe


def _is_client_safe_item(item: EvidenceItem, min_confidence: float) -> bool:
    if not item.client_safe:
        return False
    if item.confidence < min_confidence:
        return False
    if item.expires_at and item.expires_at <= datetime.now(UTC):
        return False
    if item.evidence_type != "observed":
        return False
    if item.source_provider == "pattern_guess" and "verified" not in (
        item.reasoning_note or ""
    ).casefold():
        return False
    if item.source_provider == "companies_house" and "needs_review=true" in (
        item.reasoning_note or ""
    ).casefold():
        return False
    return True
