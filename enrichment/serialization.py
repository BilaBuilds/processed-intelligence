from __future__ import annotations

from dataclasses import asdict
from typing import Any

from enrichment.models import ContactRecord


def record_to_dict(record: ContactRecord | None) -> dict[str, Any]:
    if record is None:
        return {}
    return asdict(record)


def public_record_payload(record: ContactRecord | None) -> dict[str, Any] | None:
    if record is None:
        return None
    return record_to_dict(record)
