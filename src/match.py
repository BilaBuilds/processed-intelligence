"""
src/match.py
============
Step 3 - Match + Score

Reads normalized_tenders.jsonl and scores each tender
against configurable keyword and value weights.

Scoring is deterministic: same input + same config = same scores.

Weights are loaded from the active sector pack
(see src/sector_pack.py and config/sectors/<sector>/scoring.yaml).
Set TENDER_SECTOR env var to switch sectors; default is "construction".

Output: scored_tenders.jsonl with two extra fields:
    score           - integer 0-100
    score_breakdown - dict showing contribution of each factor
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("match")

MAX_SCORE = 100
SCORING_VERSION = os.getenv("TENDER_SCORING_VERSION", "v1")
REQUIRED_DISQUALIFY_KEYWORDS = {
    "design only",
    "consultancy",
    "software",
    "graphic",
    "training",
    "it",
    "legal",
}
CONSTRUCTION_CPV_PREFIXES = ("45", "50")


# ---------------------------------------------------------------------------
# Load scoring config from sector pack (lazy, module-level cache)
# ---------------------------------------------------------------------------

def _load_scoring():
    """Load scoring constants from the active sector pack."""
    try:
        from src.sector_pack import get_pack
        pack = get_pack()
        disqualify_keywords = set(pack.scoring.disqualify_keywords) | REQUIRED_DISQUALIFY_KEYWORDS
        return (
            pack.scoring.keyword_weights,
            disqualify_keywords,
            pack.scoring.region_weights,
            pack.scoring.value_bands,
        )
    except Exception as exc:
        log.warning("Could not load sector pack scoring — using built-in defaults: %s", exc)
        return _default_scoring()


def _default_scoring():
    """Fallback scoring if sector pack is unavailable."""
    kw: dict[str, int] = {
        "construction": 15, "refurbishment": 15, "fit out": 15,
        "building works": 15, "civil engineering": 15,
        "maintenance": 10, "facilities": 10, "infrastructure": 10, "renovation": 10,
        "cleaning": 5, "grounds": 5, "landscaping": 5, "repair": 5,
    }
    disq: set[str] = {
        "chairs", "desks", "furniture", "stationery", "uniforms", "clothing",
        "catering", "food", "beverages", "vending", "meals",
        "software", "saas", "licensing", "cyber", "it support", "helpdesk",
        "website", "digital", "cloud", "data analytics", "crm", "erp",
        "consultancy", "advisory", "legal services", "accounting", "audit services",
        "recruitment", "staffing", "hr services", "payroll",
        "nursing", "domiciliary", "counselling", "therapy", "pharmacy",
        "personal protective equipment", "ppe supply",
        "fitness", "fitness classes", "gym", "leisure operator", "swimming",
        "training", "courier", "taxi", "bus service", "vehicle hire",
        "printing", "translation", "marketing", "advertising",
    }
    reg: dict[str, int] = {
        "london": 10, "south east": 10, "east of england": 8, "west midlands": 8,
        "north west": 6, "yorkshire": 6, "east midlands": 6, "south west": 5,
        "north east": 5, "wales": 4, "scotland": 4, "northern ireland": 4,
    }
    vb: list[tuple[float, float, int]] = [
        (50_000, 250_000, 20), (250_001, 750_000, 25),
        (750_001, 2_000_000, 20), (2_000_001, 5_000_000, 10),
    ]
    return kw, disq | REQUIRED_DISQUALIFY_KEYWORDS, reg, vb


# Load at import time (module-level, respects TENDER_SECTOR at startup)
_KEYWORD_WEIGHTS, _DISQUALIFY_KEYWORDS, _REGION_WEIGHTS, _VALUE_BANDS = _load_scoring()


# --- Scoring logic -----------------------------------------------------------


def is_disqualified(text: str) -> str | None:
    """Return the disqualifying keyword if found, else None."""
    text_lower = text.lower()
    for kw in _DISQUALIFY_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
            return kw
    return None


def score_keywords(text: str) -> tuple[int, dict]:
    text_lower = text.lower()
    breakdown  = {}
    total      = 0
    for keyword, weight in _KEYWORD_WEIGHTS.items():
        if re.search(r"\b" + re.escape(keyword) + r"\b", text_lower):
            breakdown[keyword] = weight
            total += weight
    return min(total, 50), breakdown   # cap keyword contribution at 50


def score_region(region: str | None) -> tuple[int, str]:
    if not region:
        return 0, "unknown"
    region_lower = region.lower()
    for name, weight in _REGION_WEIGHTS.items():
        if name in region_lower:
            return weight, name
    return 0, region_lower


def score_value(value: float | None) -> tuple[int, str]:
    if value is None:
        return 5, "unknown"     # small bonus for not disqualifying unknowns
    for lo, hi, pts in _VALUE_BANDS:
        if lo <= value <= hi:
            return pts, f"{lo:,.0f}-{hi:,.0f}"
    if value < 50_000:
        return 2, "too_small"
    return 5, "above_bands"     # very large — possible but less targeted


def parse_deadline(value: str | None) -> datetime | None:
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


def score_deadline_window(rec: dict, now_utc: datetime) -> tuple[int, str]:
    deadline = parse_deadline(rec.get("deadline_at") or rec.get("deadline"))
    if deadline is None:
        return 0, "unknown"
    days_until = int((deadline - now_utc).total_seconds() // 86400)
    if 5 <= days_until <= 30:
        return 5, "preferred_5_30_days"
    if 31 <= days_until <= 45:
        return 2, "acceptable_31_45_days"
    if days_until < 0:
        return 0, "past_due"
    return 0, f"{days_until}_days"


def cpv_matches(rec: dict) -> bool:
    if str(rec.get("procurement_category") or "").strip().lower() == "works":
        return True
    for code in rec.get("cpv_codes") or []:
        clean = str(code).strip()
        if clean.startswith(CONSTRUCTION_CPV_PREFIXES):
            return True
    return False


def cpv_missing(rec: dict) -> bool:
    cpv_codes = rec.get("cpv_codes") or []
    procurement_category = str(rec.get("procurement_category") or "").strip()
    return not cpv_codes and not procurement_category


def score_tender(rec: dict, now_utc: datetime) -> dict:
    searchable = " ".join(filter(None, [
        rec.get("title", ""),
        rec.get("description", ""),
    ]))

    # Disqualification check — off-niche contracts score zero.
    disqualifier = is_disqualified(searchable)
    if disqualifier:
        rec["score"] = 0
        rec["score_breakdown"] = {
            "keywords": 0,
            "keyword_matches": {},
            "region":   0,
            "region_matched": "disqualified",
            "value":    0,
            "value_band": "disqualified",
            "disqualified_by": disqualifier,
        }
        rec["scoring_version"] = SCORING_VERSION
        return rec

    kw_score, kw_breakdown = score_keywords(searchable)
    is_cpv_missing = cpv_missing(rec)
    has_cpv_match = cpv_matches(rec)
    if kw_score == 0 and not has_cpv_match:
        rec["score"] = 0
        rec["score_breakdown"] = {
            "keywords": 0,
            "keyword_matches": {},
            "cpv_match": False,
            "cpv_missing": is_cpv_missing,
            "region": 0,
            "region_matched": "no_core_signal",
            "value": 0,
            "value_band": "no_core_signal",
            "disqualified_by": "missing_keyword_and_cpv_signal",
        }
        rec["scoring_version"] = SCORING_VERSION
        return rec

    reg_score, reg_label   = score_region(rec.get("region"))
    value_amount = rec.get("value_amount")
    if value_amount is None:
        value_amount = rec.get("value")
    val_score, val_label = score_value(value_amount)
    deadline_score, deadline_label = score_deadline_window(rec, now_utc)

    soft_value_penalty = int(rec.get("soft_value_penalty") or 0)
    total = min(kw_score + reg_score + val_score + deadline_score, MAX_SCORE)
    if soft_value_penalty:
        total = max(0, total - soft_value_penalty)

    rec["score"] = total
    rec["score_breakdown"] = {
        "keywords": kw_score,
        "keyword_matches": kw_breakdown,
        "cpv_match": has_cpv_match,
        "cpv_missing": is_cpv_missing,
        "region":   reg_score,
        "region_matched": reg_label,
        "value":    val_score,
        "value_band": val_label,
        "deadline": deadline_score,
        "deadline_window": deadline_label,
        "soft_value_penalty": soft_value_penalty,
        "value_filter_mode": rec.get("value_filter_mode"),
    }
    rec["scoring_version"] = SCORING_VERSION
    return rec


# --- Runner ------------------------------------------------------------------


def run(context: dict) -> dict:
    norm_file: Path = context["norm_file"]
    run_dir: Path   = context["run_dir"]
    scored_file     = run_dir / "scored_tenders.jsonl"
    now_utc = datetime.now(timezone.utc)

    scored = []
    disqualified_count = 0
    cpv_missing_count = 0
    with open(norm_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("Skipping malformed JSON line in %s: %s", norm_file.name, exc)
                continue
            scored_rec = score_tender(rec, now_utc)
            if (scored_rec.get("score_breakdown") or {}).get("cpv_missing"):
                cpv_missing_count += 1
            if "disqualified_by" in (scored_rec.get("score_breakdown") or {}):
                disqualified_count += 1
            scored.append(scored_rec)

    # Sort highest score first
    scored.sort(key=lambda r: r["score"], reverse=True)

    with open(scored_file, "w", encoding="utf-8") as f:
        for rec in scored:
            f.write(json.dumps(rec, default=str) + "\n")

    top_score = scored[0]["score"] if scored else 0
    log.info(
        "Match complete: %d scored, top score: %d -> %s",
        len(scored), top_score, scored_file.name,
    )
    log.info(
        "Match filters:\n  disqualifiers: %d\n  cpv_missing: %d",
        disqualified_count,
        cpv_missing_count,
    )

    return {
        "scored_count": len(scored),
        "scored_file":  scored_file,
        "match_disqualified_count": disqualified_count,
        "match_cpv_missing_count": cpv_missing_count,
    }
