"""
src/decision.py
===============
Step 5 - Decision Engine

Reads shortlist.json and assigns:
    - decision_verdict: BID / REVIEW / NO_BID
    - decision_confidence: 0-100
    - decision_reasons: list[str]
    - risk_flags: list[str]

By default, only BID/REVIEW records are passed to downstream dedupe/notify.

Output:
    - decision_all.json         (all records with verdicts)
    - decision_shortlist.json   (filtered records for downstream steps)
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("decision")


def parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            dt = datetime.strptime(text, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def days_to_deadline(rec: dict[str, Any], now_utc: datetime) -> int | None:
    deadline = parse_deadline(rec.get("deadline"))
    if deadline is None:
        return None
    delta = deadline - now_utc
    return int(delta.total_seconds() // 86400)


def build_decision(rec: dict[str, Any], now_utc: datetime) -> dict[str, Any]:
    bid_min_score = int(os.getenv("TENDER_DECISION_BID_MIN_SCORE", "40"))
    review_min_score = int(os.getenv("TENDER_DECISION_REVIEW_MIN_SCORE", "28"))
    tight_deadline_days = int(os.getenv("TENDER_DECISION_TIGHT_DEADLINE_DAYS", "10"))

    score = int(rec.get("score") or 0)
    dtd = days_to_deadline(rec, now_utc)

    reasons: list[str] = []
    risks: list[str] = []

    if score >= bid_min_score:
        reasons.append("high_match_score")
    elif score >= review_min_score:
        reasons.append("moderate_match_score")
    else:
        reasons.append("low_match_score")

    value_score = int((rec.get("score_breakdown") or {}).get("value") or 0)
    if value_score >= 20:
        reasons.append("value_band_strong")
    elif value_score <= 2:
        risks.append("value_fit_weak")

    region_score = int((rec.get("score_breakdown") or {}).get("region") or 0)
    if region_score >= 8:
        reasons.append("region_fit_strong")
    elif region_score == 0:
        risks.append("region_unknown_or_weak")

    if dtd is not None:
        if dtd < 0:
            risks.append("deadline_passed")
        elif dtd <= tight_deadline_days:
            risks.append("tight_deadline")
        else:
            reasons.append("deadline_window_ok")
    else:
        risks.append("deadline_unknown")

    if not rec.get("buyer"):
        risks.append("buyer_unknown")
    if rec.get("value") in (None, ""):
        risks.append("value_unknown")

    if "deadline_passed" in risks:
        verdict = "NO_BID"
    elif score >= bid_min_score and "tight_deadline" not in risks:
        verdict = "BID"
    elif score >= review_min_score:
        verdict = "REVIEW"
    else:
        verdict = "NO_BID"

    confidence = 50 + min(score, 40)  # max base 90
    confidence -= min(len(risks) * 8, 35)
    if verdict == "NO_BID":
        confidence = max(35, min(confidence, 70))
    elif verdict == "REVIEW":
        confidence = max(45, min(confidence, 82))
    else:
        confidence = max(60, min(confidence, 95))

    out = dict(rec)
    out["deadline_days"] = dtd
    out["decision_verdict"] = verdict
    out["decision_confidence"] = int(confidence)
    out["decision_reasons"] = reasons
    out["risk_flags"] = risks
    return out


def run(context: dict) -> dict:
    shortlist_file: Path = context["shortlist_file"]
    run_dir: Path = context["run_dir"]

    include_raw = os.getenv("TENDER_DECISION_INCLUDE", "BID,REVIEW")
    include_set = {part.strip().upper() for part in include_raw.split(",") if part.strip()}
    if not include_set:
        include_set = {"BID", "REVIEW"}

    with open(shortlist_file, encoding="utf-8") as f:
        data = json.load(f)

    opportunities: list[dict[str, Any]] = data.get("opportunities", [])
    now_utc = datetime.now(timezone.utc)

    decided = [build_decision(rec, now_utc) for rec in opportunities]
    passed = [rec for rec in decided if rec.get("decision_verdict") in include_set]

    decision_all_file = run_dir / "decision_all.json"
    decision_shortlist_file = run_dir / "decision_shortlist.json"

    with open(decision_all_file, "w", encoding="utf-8") as f:
        json.dump({"opportunities": decided}, f, indent=2, default=str)
    with open(decision_shortlist_file, "w", encoding="utf-8") as f:
        json.dump({"opportunities": passed}, f, indent=2, default=str)

    verdict_counts: dict[str, int] = {}
    for rec in decided:
        verdict = str(rec.get("decision_verdict", "UNKNOWN"))
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    log.info(
        "Decision complete: %d input, %d passed (%s) -> %s",
        len(decided),
        len(passed),
        ",".join(sorted(include_set)),
        decision_shortlist_file.name,
    )
    log.info("Decision verdicts: %s", verdict_counts)

    # Override downstream shortlist to the decision-filtered list.
    return {
        "decision_file": decision_all_file,
        "shortlist_file": decision_shortlist_file,
        "decision_total_count": len(decided),
        "decision_pass_count": len(passed),
        "decision_verdict_counts": verdict_counts,
        "shortlist_count": len(passed),
    }

