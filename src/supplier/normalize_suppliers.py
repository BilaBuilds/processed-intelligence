"""
src/supplier/normalize_suppliers.py
=====================================
Stage 2 of the supplier intelligence layer: validate and normalise
raw supplier dicts (from ingest_suppliers) into SupplierRecord models.

Normalisation steps:
    1. Pydantic validation — rejects structurally invalid records
    2. Region decoding    — ONS NUTS codes → readable names (shared util)
    3. Capability tagging — lowercase, stripped, deduplicated
    4. Value coercion     — string "£100,000" → float 100000.0
    5. Hash generation    — SHA-256 of the normalised record for audit tracing

Design rules:
    - Bad records are logged and counted, never silently dropped
    - Returns only valid SupplierRecord objects
    - NormalizeResult carries full skip audit for manifest
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from src.schemas.supplier import SupplierRecord
from src.utils.region import decode_region

log = logging.getLogger("supplier.normalize")

_CURRENCY_RE = re.compile(r"[£$€,\s]")


@dataclass
class NormalizeResult:
    records_in: int = 0
    records_out: int = 0
    records_skipped: int = 0
    skip_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.records_out > 0


def normalize_suppliers(
    raw_records: list[dict],
) -> tuple[list[SupplierRecord], NormalizeResult]:
    """
    Validate and normalise a list of raw supplier dicts.

    Args:
        raw_records: output of ingest_suppliers()

    Returns:
        (records, result) — validated SupplierRecord list and summary
    """
    result = NormalizeResult(records_in=len(raw_records))
    records: list[SupplierRecord] = []

    for raw in raw_records:
        row_ref = f"row {raw.get('source_row', '?')} ({raw.get('source_file', '?')})"
        try:
            record = _normalize_one(raw)
            records.append(record)
            result.records_out += 1
        except ValidationError as exc:
            result.records_skipped += 1
            reason = f"{row_ref}: validation error — {_fmt_validation_error(exc)}"
            result.skip_reasons.append(reason)
            log.warning("Supplier skipped: %s", reason)
        except Exception as exc:  # noqa: BLE001
            result.records_skipped += 1
            reason = f"{row_ref}: unexpected error — {exc}"
            result.skip_reasons.append(reason)
            log.warning("Supplier skipped: %s", reason)

    log.info(
        "Supplier normalize: in=%d out=%d skipped=%d",
        result.records_in,
        result.records_out,
        result.records_skipped,
    )
    return records, result


def _normalize_one(raw: dict) -> SupplierRecord:
    """Normalise a single raw supplier dict into a SupplierRecord."""
    normalised = dict(raw)  # copy — never mutate the input

    # 1. Region: decode ONS codes to readable names
    raw_region = normalised.get("region") or None
    normalised["region"] = decode_region(raw_region)
    normalised["region_normalised"] = decode_region(raw_region)

    # 2. Value coercion: "£100,000" or "100000" → float
    for vfield in ("value_min", "value_max"):
        raw_val = normalised.get(vfield)
        normalised[vfield] = _coerce_value(raw_val)

    # 3. Capability / sector / accreditation / flag normalisation
    #    SupplierRecord validators handle CSV-string splitting and lowercasing.
    #    We ensure None/empty strings become empty so the validator doesn't trip.
    for list_field in ("capabilities", "sectors", "accreditations", "flags"):
        if not normalised.get(list_field):
            normalised[list_field] = []

    # 4. Build and validate via Pydantic
    record = SupplierRecord(**normalised)

    # 5. Attach a content hash for audit tracing
    #    Hash is based on the normalised, validated fields — not the raw input.
    record = record.model_copy(
        update={"__supplier_hash__": _record_hash(record)}
    )

    return record


def supplier_hash(record: SupplierRecord) -> str:
    """
    Return the SHA-256 audit hash for a normalised SupplierRecord.
    Stable for the same logical record regardless of input ordering.
    """
    return _record_hash(record)


def _record_hash(record: SupplierRecord) -> str:
    """SHA-256 of the canonicalised record dict — for audit tracing."""
    canonical = {
        "supplier_id": record.supplier_id,
        "name": record.name,
        "region_normalised": record.region_normalised,
        "capabilities": sorted(record.capabilities),
        "sectors": sorted(record.sectors),
        "value_min": record.value_min,
        "value_max": record.value_max,
        "flags": sorted(record.flags),
    }
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _coerce_value(raw) -> float | None:
    """Coerce a raw value field to float. Returns None if unparseable."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = _CURRENCY_RE.sub("", str(raw)).strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fmt_validation_error(exc: ValidationError) -> str:
    errors = exc.errors()
    return "; ".join(
        f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
        for e in errors[:3]
    )
