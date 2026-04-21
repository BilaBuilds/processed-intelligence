"""
src/patterns.py
===============
Optional deterministic pattern recognition enrichment.

Flow:
    match -> patterns -> select

Modes:
    disabled
    enabled_no_score_adjustment
    enabled_with_bounded_adjustment
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("patterns")

VALID_PATTERN_MODES = {
    "disabled",
    "enabled_no_score_adjustment",
    "enabled_with_bounded_adjustment",
}

KEYWORD_PATTERN_LIMIT = 4
STOPWORDS = {
    "and", "the", "for", "with", "from", "into", "works", "work", "services",
    "service", "supply", "contract", "framework", "project", "programme", "phase",
}


def pattern_mode() -> str:
    mode = os.getenv("TENDER_PATTERN_MODE", "disabled").strip().lower()
    if mode not in VALID_PATTERN_MODES:
        return "disabled"
    return mode


def value_band(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if amount < 50_000:
        return "micro"
    if amount <= 250_000:
        return "small"
    if amount <= 1_000_000:
        return "mid"
    if amount <= 5_000_000:
        return "large"
    return "enterprise"


def buyer_type(buyer: str | None) -> str:
    text = str(buyer or "").lower()
    if "council" in text or "borough" in text or "authority" in text:
        return "local_authority"
    if "nhs" in text or "health" in text:
        return "health"
    if "university" in text or "college" in text or "academy" in text:
        return "education"
    if "housing" in text or "homes" in text:
        return "housing"
    if "network rail" in text or "national grid" in text or "transport" in text:
        return "infrastructure"
    return "other"


def deadline_band(deadline_days: Any) -> str:
    try:
        days = int(deadline_days)
    except (TypeError, ValueError):
        return "unknown"
    if days < 0:
        return "passed"
    if days <= 7:
        return "urgent"
    if days <= 21:
        return "near_term"
    if days <= 45:
        return "standard"
    return "long_cycle"


def parse_deadline_days(record: dict[str, Any]) -> int | None:
    raw = record.get("deadline_days")
    if raw not in (None, ""):
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    deadline_value = record.get("deadline_at") or record.get("deadline")
    if not deadline_value:
        return None
    text = str(deadline_value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        deadline_dt = datetime.fromisoformat(text)
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        else:
            deadline_dt = deadline_dt.astimezone(timezone.utc)
        return int((deadline_dt - datetime.now(timezone.utc)).total_seconds() // 86400)
    except ValueError:
        return None


def title_keywords(record: dict[str, Any]) -> list[str]:
    text = f"{record.get('title', '')} {record.get('description', '')}".lower()
    candidates = re.findall(r"[a-z][a-z0-9\-]{3,}", text)
    ordered: list[str] = []
    for token in candidates:
        if token in STOPWORDS:
            continue
        if token not in ordered:
            ordered.append(token)
        if len(ordered) >= KEYWORD_PATTERN_LIMIT:
            break
    return ordered


def safe_json_load(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logging.warning("Skipping malformed JSON line in %s: %s", path.name, exc)
    return rows


def load_history(run_dir: Path, run_limit: int) -> dict[str, Counter]:
    runs_root = run_dir.parent
    candidate_runs = [
        path for path in sorted(runs_root.iterdir(), reverse=True)
        if path.is_dir() and path != run_dir
    ][:run_limit]

    relevant_buyers: Counter[str] = Counter()
    relevant_keywords: Counter[str] = Counter()
    win_zones: Counter[str] = Counter()
    deadline_rhythms: Counter[str] = Counter()
    no_bid_keywords: Counter[str] = Counter()
    no_bid_buyers: Counter[str] = Counter()

    for history_run in candidate_runs:
        decision_all = history_run / "decision_all.json"
        if decision_all.exists():
            opportunities = safe_json_load(decision_all).get("opportunities", [])
            if isinstance(opportunities, list):
                for rec in opportunities:
                    verdict = str(rec.get("decision_verdict") or "").upper()
                    if verdict in {"BID", "REVIEW"}:
                        buyer = str(rec.get("buyer") or rec.get("buyer_name") or "").strip()
                        if buyer:
                            relevant_buyers[buyer] += 1
                        for keyword in title_keywords(rec):
                            relevant_keywords[keyword] += 1
                        zone_key = "|".join(
                            [
                                str(rec.get("region") or "unknown"),
                                buyer_type(rec.get("buyer") or rec.get("buyer_name")),
                                value_band(rec.get("value_amount") or rec.get("value")),
                                title_keywords(rec)[0] if title_keywords(rec) else "none",
                            ]
                        )
                        win_zones[zone_key] += 1
                        deadline_rhythms[deadline_band(rec.get("deadline_days"))] += 1
                    elif verdict == "NO_BID":
                        buyer = str(rec.get("buyer") or rec.get("buyer_name") or "").strip()
                        if buyer:
                            no_bid_buyers[buyer] += 1
                        for keyword in title_keywords(rec):
                            no_bid_keywords[keyword] += 1

    return {
        "relevant_buyers": relevant_buyers,
        "relevant_keywords": relevant_keywords,
        "win_zones": win_zones,
        "deadline_rhythms": deadline_rhythms,
        "no_bid_keywords": no_bid_keywords,
        "no_bid_buyers": no_bid_buyers,
    }


def analyze_record(record: dict[str, Any], history: dict[str, Counter], max_adjustment: int) -> dict[str, Any]:
    matching_patterns: list[str] = []
    risk_patterns: list[str] = []

    buyer = str(record.get("buyer") or record.get("buyer_name") or "").strip()
    keywords = title_keywords(record)
    buyer_history_count = int(history["relevant_buyers"].get(buyer, 0)) if buyer else 0
    category_history_count = sum(int(history["relevant_keywords"].get(keyword, 0)) for keyword in keywords)

    if buyer_history_count >= 2:
        matching_patterns.append(f"buyer recurrence: {buyer_history_count} similar historical wins/reviews")

    if category_history_count >= 2:
        matching_patterns.append(f"category recurrence: {category_history_count} historical keyword hits")

    zone_key = "|".join(
        [
            str(record.get("region") or "unknown"),
            buyer_type(record.get("buyer") or record.get("buyer_name")),
            value_band(record.get("value_amount") or record.get("value")),
            keywords[0] if keywords else "none",
        ]
    )
    zone_count = int(history["win_zones"].get(zone_key, 0))
    if zone_count >= 2:
        matching_patterns.append(f"win-zone recurrence: {zone_count} matching historical combinations")

    current_deadline_band = deadline_band(parse_deadline_days(record))
    deadline_count = int(history["deadline_rhythms"].get(current_deadline_band, 0))
    if deadline_count >= 2 and current_deadline_band != "unknown":
        matching_patterns.append(f"deadline rhythm: {deadline_count} historical {current_deadline_band} matches")

    no_bid_keyword_hits = sum(int(history["no_bid_keywords"].get(keyword, 0)) for keyword in keywords)
    if no_bid_keyword_hits >= 2:
        risk_patterns.append(f"stale/no-bid pattern: {no_bid_keyword_hits} historical keyword misses")

    no_bid_buyer_hits = int(history["no_bid_buyers"].get(buyer, 0)) if buyer else 0
    if no_bid_buyer_hits >= 2:
        risk_patterns.append(f"buyer risk recurrence: {no_bid_buyer_hits} historical no-bids for buyer")

    raw_adjustment = 0
    raw_adjustment += min(3, buyer_history_count)
    raw_adjustment += min(2, category_history_count // 2)
    raw_adjustment += min(2, zone_count)
    raw_adjustment += 1 if deadline_count >= 2 else 0
    raw_adjustment -= min(3, no_bid_keyword_hits)
    raw_adjustment -= min(2, no_bid_buyer_hits)

    bounded_adjustment = max(-max_adjustment, min(max_adjustment, raw_adjustment))
    confidence = 0
    if matching_patterns or risk_patterns:
        confidence = max(35, min(90, 35 + (len(matching_patterns) * 12) + (len(risk_patterns) * 8)))

    return {
        "pattern_score_adjustment": bounded_adjustment,
        "pattern_confidence": confidence,
        "matching_patterns": matching_patterns,
        "risk_patterns": risk_patterns,
        "buyer_history_count": buyer_history_count,
        "category_history_count": category_history_count,
        "win_zone_history_count": zone_count,
        "deadline_history_count": deadline_count,
        "no_bid_keyword_hits": no_bid_keyword_hits,
        "no_bid_buyer_hits": no_bid_buyer_hits,
    }


def run(context: dict[str, Any]) -> dict[str, Any]:
    mode = pattern_mode()
    run_dir: Path = context["run_dir"]
    scored_file: Path = context["scored_file"]

    if mode == "disabled":
        log.info("Pattern module disabled.")
        return {
            "pattern_module_status": "disabled",
            "pattern_signal_count": 0,
            "pattern_adjusted_count": 0,
            "pattern_artifacts": {},
        }

    max_adjustment = int(os.getenv("TENDER_PATTERN_MAX_ADJUSTMENT", "5"))
    history_run_limit = int(os.getenv("TENDER_PATTERN_HISTORY_RUN_LIMIT", "50"))
    history = load_history(run_dir, history_run_limit)

    records = iter_jsonl(scored_file)
    enriched_records: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    adjusted_count = 0

    for record in records:
        signal = analyze_record(record, history, max_adjustment)
        enriched = dict(record)
        enriched.update(signal)
        enriched["pattern_mode"] = mode
        enriched["score_original"] = int(record.get("score") or 0)
        enriched["pattern_adjusted_score"] = max(0, min(100, enriched["score_original"] + signal["pattern_score_adjustment"]))
        if mode == "enabled_with_bounded_adjustment" and signal["pattern_score_adjustment"] != 0:
            enriched["score"] = enriched["pattern_adjusted_score"]
            adjusted_count += 1
        signals.append(
            {
                "id": enriched.get("id"),
                "title": enriched.get("title"),
                **signal,
            }
        )
        enriched_records.append(enriched)

    enriched_file = run_dir / "pattern_enriched_tenders.jsonl"
    with enriched_file.open("w", encoding="utf-8") as handle:
        for record in enriched_records:
            handle.write(json.dumps(record, default=str) + "\n")

    pattern_signals_file = run_dir / "pattern_signals.json"
    pattern_summary_file = run_dir / "pattern_summary.json"
    pattern_signals_file.write_text(json.dumps({"signals": signals}, indent=2), encoding="utf-8")

    summary = {
        "mode": mode,
        "signal_count": len([signal for signal in signals if signal["matching_patterns"] or signal["risk_patterns"]]),
        "adjusted_count": adjusted_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "history_run_limit": history_run_limit,
    }
    pattern_summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    log.info(
        "Pattern module complete: %d records, %d signals, %d adjusted",
        len(enriched_records),
        summary["signal_count"],
        adjusted_count,
    )

    return {
        "scored_file": enriched_file,
        "pattern_module_status": "ok",
        "pattern_signal_count": summary["signal_count"],
        "pattern_adjusted_count": adjusted_count,
        "pattern_artifacts": {
            "pattern_signals_file": str(pattern_signals_file),
            "pattern_summary_file": str(pattern_summary_file),
            "pattern_enriched_file": str(enriched_file),
        },
    }
