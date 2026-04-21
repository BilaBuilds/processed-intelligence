"""
src/normalize.py
================
Step 2 - Normalize

Reads raw_tenders.jsonl and maps every record into a clean
standard schema regardless of source format.

Output schema (every field always present):
    id          - stable unique ID (source:ocid or source:url-hash)
    title       - tender title
    buyer       - buying organisation name
    region      - geographic region
    deadline    - ISO date string or None
    value       - estimated value as float or None
    currency    - e.g. GBP
    url         - direct link to tender
    description - summary text
    source      - which feed it came from
    raw_id      - original ID from source
    fetched_at  - ISO datetime when ingested
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.entities import ProcurementOpportunity, SupplierEntity, utc_now_iso

log = logging.getLogger("normalize")

STATUS_EXCLUDE_TERMS = {
    "award",
    "awarded",
    "closed",
    "completed",
    "cancelled",
    "withdrawn",
}

MIN_ACTIONABLE_DEADLINE_DAYS = 3
MIN_JOB_HISTORY_FOR_HARD_VALUE_FILTER = 8
SOFT_VALUE_PENALTY = 10


# --- ONS NUTS/ITL region code decoder ----------------------------------------
# Maps raw NUTS1/ITL1 codes (as returned by FTS/CF APIs) to readable English names.
# Covers all UK regions. Unknown codes are passed through as-is.

ONS_REGION_CODES: dict[str, str] = {
    # England — NUTS1 / ITL1
    "UKC": "North East England",
    "UKD": "North West England",
    "UKE": "Yorkshire and The Humber",
    "UKF": "East Midlands",
    "UKG": "West Midlands",
    "UKH": "East of England",
    "UKI": "London",
    "UKJ": "South East England",
    "UKK": "South West England",
    # Devolved nations
    "UKL": "Wales",
    "UKM": "Scotland",
    "UKN": "Northern Ireland",
    # Sub-region codes (NUTS2/ITL2 — first 5 chars)
    "UKC1": "Tees Valley and Durham",
    "UKC2": "Northumberland and Tyne and Wear",
    "UKD1": "Cumbria",
    "UKD3": "Greater Manchester",
    "UKD4": "Lancashire",
    "UKD6": "Cheshire",
    "UKD7": "Merseyside",
    "UKE1": "East Yorkshire and Northern Lincolnshire",
    "UKE2": "North Yorkshire",
    "UKE3": "South Yorkshire",
    "UKE4": "West Yorkshire",
    "UKF1": "Derbyshire and Nottinghamshire",
    "UKF2": "Leicestershire, Rutland and Northamptonshire",
    "UKF3": "Lincolnshire",
    "UKG1": "Herefordshire, Worcestershire and Warwickshire",
    "UKG2": "Shropshire and Staffordshire",
    "UKG3": "West Midlands (Met County)",
    "UKH1": "East Anglia",
    "UKH2": "Bedfordshire and Hertfordshire",
    "UKH3": "Essex",
    "UKI3": "Inner London — West",
    "UKI4": "Inner London — East",
    "UKI5": "Outer London — East and North East",
    "UKI6": "Outer London — South",
    "UKI7": "Outer London — West and North West",
    "UKJ1": "Berkshire, Buckinghamshire and Oxfordshire",
    "UKJ2": "Surrey, East and West Sussex",
    "UKJ3": "Hampshire and Isle of Wight",
    "UKJ4": "Kent",
    "UKK1": "Gloucestershire, Wiltshire and Bristol/Bath area",
    "UKK2": "Dorset and Somerset",
    "UKK3": "Cornwall and Isles of Scilly",
    "UKK4": "Devon",
    "UKL1": "West Wales and The Valleys",
    "UKL2": "East Wales",
    "UKM5": "North Eastern Scotland",
    "UKM6": "Highlands and Islands",
    "UKM7": "Eastern Scotland",
    "UKM8": "West Central Scotland",
    "UKM9": "Southern Scotland",
    # ITL2 equivalents (same codes, included for completeness)
}


def decode_region(raw_region: str | None) -> str | None:
    """Convert ONS NUTS/ITL codes to readable region names. Pass-through if already readable."""
    if not raw_region:
        return raw_region
    stripped = raw_region.strip()
    # Check 5-char code first (NUTS2/ITL2), then 4-char, then 3-char (NUTS1/ITL1)
    for length in (5, 4, 3):
        candidate = stripped[:length].upper()
        if candidate in ONS_REGION_CODES:
            return ONS_REGION_CODES[candidate]
    # Already readable or unknown code — return as-is
    return stripped


# --- Schema ------------------------------------------------------------------


def empty_record() -> dict:
    return {
        "id":          None,
        "title":       None,
        "buyer":       None,
        "region":      None,
        "deadline":    None,
        "value":       None,
        "currency":    "GBP",
        "url":         None,
        "description": None,
        "status":      None,
        "release_tags": [],
        "source":      None,
        "raw_id":      None,
        "fetched_at":  None,
    }


def url_hash(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def load_job_history_value_bounds(state_dir: Path) -> dict[str, float]:
    job_history_file = state_dir / "job_history.json"
    if not job_history_file.exists():
        return {}
    try:
        rows = json.loads(job_history_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(rows, list):
        return {}

    values: list[float] = []
    for row in rows:
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError, AttributeError):
            continue
        if value > 0:
            values.append(value)
    if not values:
        return {}

    avg_value = sum(values) / len(values)
    return {
        "job_history_count": len(values),
        "avg_value": avg_value,
        "min_value": min(values),
        "max_value": max(values),
    }


def extract_cpv_codes(tender: dict) -> list[str]:
    codes: list[str] = []

    def _append_classification(classification: dict | None) -> None:
        if not isinstance(classification, dict):
            return
        if str(classification.get("scheme") or "").strip().upper() != "CPV":
            return
        code = str(classification.get("id") or "").strip()
        if code and code not in codes:
            codes.append(code)

    _append_classification(tender.get("classification"))
    for classification in tender.get("additionalClassifications", []) or []:
        _append_classification(classification)
    for item in tender.get("items", []) or []:
        _append_classification((item or {}).get("classification"))
        for classification in (item or {}).get("additionalClassifications", []) or []:
            _append_classification(classification)
    return codes


def exclusion_reason_for_record(
    rec: dict,
    now_utc: datetime,
    value_bounds: dict[str, float],
) -> str | None:
    status_text = " ".join(
        [
            str(rec.get("status") or "").strip().lower(),
            " ".join(str(tag).strip().lower() for tag in (rec.get("release_tags") or [])),
        ]
    ).strip()
    if any(term in status_text for term in STATUS_EXCLUDE_TERMS):
        return "status_filter"

    deadline = parse_datetime(rec.get("deadline_at") or rec.get("deadline"))
    if deadline is not None and deadline < (now_utc + timedelta(days=MIN_ACTIONABLE_DEADLINE_DAYS)):
        return "deadline_filter"

    avg_value = float(value_bounds.get("avg_value") or 0)
    job_history_count = int(value_bounds.get("job_history_count") or 0)
    if avg_value > 0 and job_history_count >= MIN_JOB_HISTORY_FOR_HARD_VALUE_FILTER:
        raw_value = rec.get("value_amount")
        if raw_value is None:
            raw_value = rec.get("value")
        try:
            value_amount = float(raw_value)
        except (TypeError, ValueError):
            value_amount = None
        if value_amount is not None:
            if value_amount < (avg_value * 0.25) or value_amount > (avg_value * 3.0):
                return "value_filter"

    return None


def value_filter_penalty(rec: dict, value_bounds: dict[str, float]) -> int:
    avg_value = float(value_bounds.get("avg_value") or 0)
    job_history_count = int(value_bounds.get("job_history_count") or 0)
    if avg_value <= 0 or job_history_count >= MIN_JOB_HISTORY_FOR_HARD_VALUE_FILTER:
        return 0

    raw_value = rec.get("value_amount")
    if raw_value is None:
        raw_value = rec.get("value")
    try:
        value_amount = float(raw_value)
    except (TypeError, ValueError):
        return 0

    if value_amount < (avg_value * 0.25) or value_amount > (avg_value * 3.0):
        return SOFT_VALUE_PENALTY
    return 0


# --- Per-source mappers ------------------------------------------------------


def map_ocds_release(raw: dict, source_prefix: str, base_url: str) -> dict:
    """Generic mapper for OCDS-format releases (works for both CF and FaT)."""
    rec = empty_record()
    rec["source"] = source_prefix

    ocid    = raw.get("ocid", "")
    source_notice_id = str(raw.get("id") or ocid or "").strip()
    tender  = raw.get("tender", {})
    parties = raw.get("parties", [])
    buyer   = next((p for p in parties if "buyer" in p.get("roles", [])), {})

    rec["raw_id"]      = source_notice_id or ocid
    rec["id"]          = f"{source_prefix}:{source_notice_id}" if source_notice_id else None
    rec["title"]       = tender.get("title")
    rec["buyer"]       = buyer.get("name")
    rec["description"] = tender.get("description")
    rec["fetched_at"]  = raw.get("date")
    rec["status"]      = tender.get("status")
    raw_tags = raw.get("tag", []) or []
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    if isinstance(raw_tags, list):
        rec["release_tags"] = [str(tag).strip() for tag in raw_tags if str(tag).strip()]

    value_obj            = tender.get("value", {}) or {}
    raw_amount           = value_obj.get("amount")
    try:
        rec["value"]     = float(raw_amount) if raw_amount is not None else None
    except (TypeError, ValueError):
        rec["value"]     = None
    rec["value_amount"]  = rec["value"]
    rec["value_currency"] = value_obj.get("currency", "GBP") or "GBP"
    rec["currency"]      = rec["value_currency"]

    period = tender.get("tenderPeriod") or {}
    rec["deadline"]      = period.get("endDate")
    rec["deadline_at"]   = rec["deadline"]

    docs = tender.get("documents") or []
    for doc in docs:
        url = str(doc.get("url") or "").strip()
        if url:
            rec["url"] = url
            break

    address = buyer.get("address") or {}
    raw_region = address.get("region") or address.get("countryName")
    rec["region"]        = decode_region(raw_region) if raw_region else None

    rec["opportunity_id"]    = source_notice_id or ocid
    rec["source_notice_id"]  = source_notice_id
    rec["buyer_name"]        = buyer.get("name")
    rec["source_url"]        = f"{base_url}{source_notice_id}" if source_notice_id and base_url else None
    rec["published_at"]      = raw.get("date")
    rec["updated_at"]        = raw.get("date")
    rec["ingested_at"]       = utc_now_iso()
    rec["cpv_codes"]         = extract_cpv_codes(tender)
    rec["procurement_category"] = tender.get("mainProcurementCategory")

    return rec


def map_contracts_finder(raw: dict) -> dict:
    return map_ocds_release(raw, "cf", "https://www.contractsfinder.service.gov.uk/Notice/")


def map_find_a_tender(raw: dict) -> dict:
    return map_ocds_release(raw, "fat", "https://www.find-tender.service.gov.uk/Notice/")


SOURCE_MAPPERS: dict = {
    "contracts_finder": map_contracts_finder,
    "find_a_tender":    map_find_a_tender,
}


def normalize_record(raw: dict) -> dict | None:
    source = raw.get("_source")
    mapper = SOURCE_MAPPERS.get(source)
    if not mapper:
        log.warning("No mapper for source '%s' - skipping", source)
        return None
    try:
        return mapper(raw)
    except Exception as exc:
        log.warning("Failed to normalize record: %s - %s", raw.get("ocid"), exc)
        return None


def run(context: dict) -> dict:
    raw_file:  Path = context["raw_file"]
    run_dir:   Path = context["run_dir"]
    state_dir: Path | None = context.get("state_dir")

    norm_file              = run_dir / "normalized_tenders.jsonl"
    supplier_entities_file = run_dir / "supplier_entities.json"

    value_bounds = load_job_history_value_bounds(state_dir) if state_dir else {}
    job_history_count = int(value_bounds.get("job_history_count") or 0)
    value_filter_mode = "hard" if job_history_count >= MIN_JOB_HISTORY_FOR_HARD_VALUE_FILTER else "soft"

    now_utc = datetime.now(timezone.utc)

    records: list[dict] = []
    skipped = 0
    status_filtered  = 0
    deadline_filtered = 0
    value_filtered   = 0
    supplier_entities: dict = {}

    with open(raw_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("Skipping malformed JSON line in %s: %s", raw_file.name, exc)
                skipped += 1
                continue
            rec = normalize_record(raw)
            if rec is None:
                skipped += 1
                continue

            exclusion = exclusion_reason_for_record(rec, now_utc, value_bounds)
            if exclusion == "status_filter":
                status_filtered += 1
                skipped += 1
                continue
            if exclusion == "deadline_filter":
                deadline_filtered += 1
                skipped += 1
                continue
            if exclusion == "value_filter":
                value_filtered += 1
                skipped += 1
                continue

            # Apply soft value penalty (score deduction, not exclusion)
            rec["soft_value_penalty"] = value_filter_penalty(rec, value_bounds)

            records.append(rec)

            supplier_name = str(raw.get("supplier_name") or raw.get("supplier") or "").strip()
            if supplier_name:
                supplier_id = f"supplier:{url_hash(supplier_name.lower())}"
                entity = SupplierEntity(
                    supplier_id=supplier_id,
                    legal_name=supplier_name,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
                supplier_entities[supplier_id] = entity.to_dict()

    with open(norm_file, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, default=str) + "\n")

    with open(supplier_entities_file, "w", encoding="utf-8") as f:
        json.dump({"entities": list(supplier_entities.values())}, f, indent=2)

    log.info(
        "Normalize complete: %d normalized, %d skipped (status=%d, deadline=%d, value=%d) -> %s",
        len(records), skipped, status_filtered, deadline_filtered, value_filtered, norm_file.name,
    )

    return {
        "norm_count":                  len(records),
        "norm_file":                   norm_file,
        "norm_dropped_count":          skipped,
        "norm_status_filtered_count":  status_filtered,
        "norm_deadline_filtered_count": deadline_filtered,
        "norm_value_filtered_count":   value_filtered,
        "value_filter_mode":           value_filter_mode,
        "supplier_entities_file":      supplier_entities_file,
        "supplier_entity_count":       len(supplier_entities),
    }
