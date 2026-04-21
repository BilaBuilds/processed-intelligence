"""
src/decision.py
===============
Step 5 - Decision Engine

Reads shortlist.json and assigns:
    - decision_verdict: BID / REVIEW / NO_BID
    - decision_confidence: 0-100
    - decision_reasons: list[str]
    - risk_flags: list[str]

Persists source-of-truth runtime artifacts:
    - decision_all.json
    - decision_shortlist.json
    - decision_events.json
    - risk_signals.json
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.entities import DecisionEvent, RiskSignal

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
    deadline = parse_deadline(rec.get("deadline_at") or rec.get("deadline"))
    if deadline is None:
        return None
    delta = deadline - now_utc
    return int(delta.total_seconds() // 86400)


def build_decision(rec: dict[str, Any], now_utc: datetime) -> dict[str, Any]:
    bid_min_score = int(os.getenv("TENDER_DECISION_BID_MIN_SCORE", "40"))
    review_min_score = int(os.getenv("TENDER_DECISION_REVIEW_MIN_SCORE", "28"))
    tight_deadline_days = int(os.getenv("TENDER_DECISION_TIGHT_DEADLINE_DAYS", "10"))
    sme_value_ceiling = float(
        os.getenv("TENDER_DECISION_SME_VALUE_MAX", os.getenv("TENDER_SME_VALUE_CEILING", "5000000"))
    )

    score = int(rec.get("score") or 0)
    dtd = days_to_deadline(rec, now_utc)

    # Preserve context layer if present (from context.py)
    context = rec.get("context", {})

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

    buyer_name = rec.get("buyer_name") or rec.get("buyer")
    if not buyer_name:
        risks.append("buyer_unknown")

    value_amount = rec.get("value_amount")
    if value_amount is None:
        value_amount = rec.get("value")
    if value_amount in (None, ""):
        risks.append("value_unknown")
    else:
        try:
            if float(value_amount) > sme_value_ceiling:
                risks.append("value_too_large_for_sme")
                reasons.append("value_ceiling_exceeded")
        except (TypeError, ValueError):
            pass

    if "deadline_passed" in risks:
        verdict = "NO_BID"
    elif (
        score >= bid_min_score
        and "tight_deadline" not in risks
        and "value_too_large_for_sme" not in risks
    ):
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
    out["decision_reasons"] = reasons or ["unclassified"]
    out["risk_flags"] = risks
    out["decision_reason_codes"] = out["decision_reasons"]
    return out


def build_provenance_refs(rec: dict[str, Any]) -> list[str]:
    refs = []
    for field in ("source_url", "url", "source_notice_id", "ocid", "opportunity_id", "id"):
        value = rec.get(field)
        if value:
            refs.append(str(value))
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(refs))


def risk_signal_severity(flag: str) -> str:
    if flag in {"deadline_passed", "value_fit_weak"}:
        return "high"
    if flag in {"tight_deadline", "buyer_unknown", "value_too_large_for_sme"}:
        return "medium"
    return "low"


def run(context: dict) -> dict:
    shortlist_file: Path = context["shortlist_file"]
    run_dir: Path = context["run_dir"]
    run_id = run_dir.name

    include_raw = os.getenv("TENDER_DECISION_INCLUDE", "BID,REVIEW")
    include_set = {part.strip().upper() for part in include_raw.split(",") if part.strip()}
    if not include_set:
        include_set = {"BID", "REVIEW"}

    with open(shortlist_file, encoding="utf-8") as f:
        data = json.load(f)

    opportunities: list[dict[str, Any]] = data.get("opportunities", [])
    now_utc = datetime.now(timezone.utc)
    decided_at_iso = now_utc.isoformat()
    scoring_version = os.getenv("TENDER_SCORING_VERSION", "v1")
    model_version = os.getenv("TENDER_MODEL_VERSION") or None

    decided = [build_decision(rec, now_utc) for rec in opportunities]
    passed = [rec for rec in decided if rec.get("decision_verdict") in include_set]

    decision_events: list[dict[str, Any]] = []
    risk_signals: list[dict[str, Any]] = []

    for index, rec in enumerate(decided, start=1):
        opportunity_id = (
            str(rec.get("opportunity_id") or "").strip()
            or str(rec.get("id") or "").strip()
            or f"{run_id}:unknown:{index}"
        )
        decision_id = f"{run_id}:decision:{index:05d}"
        provenance_refs = build_provenance_refs(rec)

        event = DecisionEvent(
            decision_id=decision_id,
            opportunity_id=opportunity_id,
            verdict=str(rec.get("decision_verdict", "NO_BID")),
            confidence=int(rec.get("decision_confidence") or 0),
            reason_codes=list(rec.get("decision_reason_codes") or ["unclassified"]),
            risk_flags=list(rec.get("risk_flags") or []),
            score_total=int(rec.get("score") or 0),
            scoring_version=str(rec.get("scoring_version") or scoring_version),
            model_version=model_version,
            provenance_refs=provenance_refs or [opportunity_id],
            decided_at=decided_at_iso,
        )
        decision_events.append(event.to_dict())
        rec["decision_id"] = decision_id
        rec["provenance_refs"] = event.provenance_refs

        for risk_index, risk_flag in enumerate(event.risk_flags, start=1):
            signal = RiskSignal(
                risk_signal_id=f"{decision_id}:risk:{risk_index:02d}",
                subject_type="opportunity",
                subject_id=opportunity_id,
                signal_type=risk_flag,
                severity=risk_signal_severity(risk_flag),
                confidence=max(40, event.confidence - 10),
                evidence_source=(event.provenance_refs[0] if event.provenance_refs else opportunity_id),
                created_at=decided_at_iso,
            )
            risk_signals.append(signal.to_dict())

    decision_all_file = run_dir / "decision_all.json"
    decision_shortlist_file = run_dir / "decision_shortlist.json"
    decision_events_file = run_dir / "decision_events.json"
    risk_signals_file = run_dir / "risk_signals.json"

    with open(decision_all_file, "w", encoding="utf-8") as f:
        json.dump({"opportunities": decided}, f, indent=2, default=str)
    with open(decision_shortlist_file, "w", encoding="utf-8") as f:
        json.dump({"opportunities": passed}, f, indent=2, default=str)
    with open(decision_events_file, "w", encoding="utf-8") as f:
        json.dump({"decision_events": decision_events}, f, indent=2, default=str)
    with open(risk_signals_file, "w", encoding="utf-8") as f:
        json.dump({"risk_signals": risk_signals}, f, indent=2, default=str)

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
        "decision_events_file": decision_events_file,
        "risk_signals_file": risk_signals_file,
        "shortlist_file": decision_shortlist_file,
        "decision_total_count": len(decided),
        "decision_pass_count": len(passed),
        "decision_verdict_counts": verdict_counts,
        "decision_event_count": len(decision_events),
        "risk_signal_count": len(risk_signals),
        "shortlist_count": len(passed),
    }
