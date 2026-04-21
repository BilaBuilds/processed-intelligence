import json
import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .schema import RegulationRecord, make_record_id, record_to_dict

logger = logging.getLogger(__name__)

# Region normalization map: substring (lowercase) -> canonical region
REGION_MAP = [
    ("greater london", "London"),
    ("london borough", "London"),
    (" london", "London"),
    ("london ", "London"),
    ("birmingham", "West Midlands"),
    ("west midlands", "West Midlands"),
    ("wolverhampton", "West Midlands"),
    ("coventry", "West Midlands"),
    ("sandwell", "West Midlands"),
    ("oxford", "Oxfordshire"),
    ("oxfordshire", "Oxfordshire"),
    ("national", "National"),
    ("england", "National"),
    ("uk", "National"),
    ("united kingdom", "National"),
]

TRADE_KEYWORDS = {
    "civils": [
        "highway", "public realm", "excavation", "carriageway", "footway",
        "groundwork", "earthworks", "civil engineering", "road", "pavement",
    ],
    "drainage": [
        "sewer", "drainage", "suds", "surface water", "foul water",
        "stormwater", "culvert", "combined sewer", "flood risk",
    ],
    "building_services": [
        "boiler", "heat pump", "hvac", "m&e", "gas", "ventilation",
        "electrical", "fire safety", "part l", "epc",
    ],
}

IMPACT_KEYWORDS = {
    "code_change": ["regulation change", "approved document", "new requirement"],
    "permit": ["permit", "licence", "authorisation", "notification required"],
    "environment": ["environmental permit", "ea guidance", "water quality"],
    "safety": ["health and safety", "cdm", "riddor", "safe working"],
    "planning": ["planning permission", "permitted development", "article 4"],
    "consultation": ["consultation", "call for evidence", "have your say"],
}

DATE_FORMATS = [
    "%d %B %Y",
    "%B %d, %Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d %b %Y",
]


def _ascii_safe(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", errors="ignore").decode("ascii")


def _normalize_region(region_hint: str, text: str) -> str:
    # Search text first for specific region signals
    lower_text = text.lower()
    for substr, canonical in REGION_MAP:
        if substr == "national" or substr in ("uk", "england", "united kingdom"):
            continue  # skip generic matches; these are checked from source hint only
        if substr in lower_text:
            return canonical
    # If no specific region in text, check if source hint is a specific known region
    lower_hint = region_hint.lower()
    for substr, canonical in REGION_MAP:
        if substr != "national" and substr in lower_hint:
            return canonical
    # National source + no text signal = Unknown (region not determinable from content)
    if region_hint == "National":
        return "Unknown"
    return "Unknown"


def _parse_date(date_str: str) -> str:
    if not date_str:
        return ""
    date_str = date_str.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Try ISO-like extraction
    iso_match = re.search(r"\d{4}-\d{2}-\d{2}", date_str)
    if iso_match:
        return iso_match.group(0)
    return ""


def _infer_trade_tags(text: str) -> List[str]:
    lower = text.lower()
    tags = []
    for tag, keywords in TRADE_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                tags.append(tag)
                break
    return tags


def _classify_impact_type(text: str) -> str:
    lower = text.lower()
    for impact_type, keywords in IMPACT_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return impact_type
    return "other"


def _trim_summary(text: str, max_chars: int = 500) -> str:
    text = _ascii_safe(text.strip())
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0]
    return text


def normalize_record(raw: dict) -> Optional[RegulationRecord]:
    try:
        title = _ascii_safe(raw.get("title", "").strip())
        url = raw.get("url", "").strip()
        authority = _ascii_safe(raw.get("authority", "Unknown").strip())
        source = raw.get("source", "")
        raw_text = raw.get("raw_text", "")
        date_hint = raw.get("date_hint", "")
        source_region = raw.get("region", "National")

        if not title or not url:
            return None

        published_at = _parse_date(date_hint)
        region = _normalize_region(source_region, raw_text)
        trade_tags = _infer_trade_tags(title + " " + raw_text)
        impact_type = _classify_impact_type(title + " " + raw_text)
        summary = _trim_summary(raw_text)
        truncated_raw = raw_text[:2000]

        record_id = make_record_id(url, title, published_at)

        return RegulationRecord(
            id=record_id,
            title=title,
            authority=authority,
            region=region,
            published_at=published_at,
            effective_at="",
            url=url,
            summary=summary,
            source=source,
            trade_tags=trade_tags,
            impact_type=impact_type,
            raw_text=_ascii_safe(truncated_raw),
            relevance_score=0,
            relevance_reasons=[],
        )
    except Exception as e:
        logger.warning(f"[normalize] failed to normalize record '{raw.get('title', '')[:60]}': {e}")
        return None


def run_normalize(
    raw_records: List[dict],
    run_dir: Path,
    dry_run: bool = False,
) -> List[RegulationRecord]:
    normalized = []
    for raw in raw_records:
        record = normalize_record(raw)
        if record:
            normalized.append(record)

    # Dedupe by id
    seen_ids = set()
    deduped = []
    for rec in normalized:
        if rec.id not in seen_ids:
            seen_ids.add(rec.id)
            deduped.append(rec)

    if not dry_run:
        out_path = run_dir / "normalized_regulations.jsonl"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in deduped:
                f.write(json.dumps(record_to_dict(rec), ensure_ascii=True) + "\n")
        logger.info(f"[normalize] wrote {len(deduped)} records to {out_path}")

    return deduped
