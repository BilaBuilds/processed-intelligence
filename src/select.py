"""
src/select.py
=============
Step 4 - Select

Reads scored_tenders.jsonl and deterministically buckets tenders into:
    - shortlist
    - review candidates
    - market intelligence
    - rejected

For downstream compatibility, shortlist.json remains the source-of-truth
JSON artifact consumed by decision/dedupe, while JSONL bucket outputs are
also written for analysis and review workflows.
"""

import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("select")
MIN_ACTIONABLE_DEADLINE_DAYS = 3


def parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    try:
        # Date-only format
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


def status_is_active(rec: dict) -> bool:
    status = str(rec.get("status") or "").strip().lower()
    if not status:
        return True
    return status in {"active", "open"}


def has_release_tag(rec: dict, target: str) -> bool:
    tags = rec.get("release_tags", []) or []
    return any(str(tag).strip().lower() == target.lower() for tag in tags)


def is_live_deadline(rec: dict, now_utc: datetime) -> bool:
    parsed = parse_deadline(rec.get("deadline_at") or rec.get("deadline"))
    if parsed is None:
        return True
    return parsed >= (now_utc + timedelta(days=MIN_ACTIONABLE_DEADLINE_DAYS))


def rejection_reasons_for_record(rec: dict, now_utc: datetime) -> list[str]:
    reasons: list[str] = []
    if not status_is_active(rec):
        reasons.append("inactive_status")
    if has_release_tag(rec, "award"):
        reasons.append("award")
    if has_release_tag(rec, "awardUpdate"):
        reasons.append("awardUpdate")
    if not is_live_deadline(rec, now_utc):
        reasons.append("stale_deadline")
    return reasons


# --- Runner ------------------------------------------------------------------


def run(context: dict) -> dict:
    min_score = int(os.getenv("TENDER_MIN_SCORE", "20"))
    review_min_score = int(os.getenv("TENDER_REVIEW_MIN_SCORE", "15"))
    top_n = int(os.getenv("TENDER_SHORTLIST_N", os.getenv("TENDER_TOP_N", "10")))

    # Use context_file if available (post-context layer), else scored_file (legacy)
    context_file: Path = context.get("context_file")
    scored_file: Path = context["scored_file"]
    input_file = context_file if context_file and context_file.exists() else scored_file
    run_dir: Path     = context["run_dir"]
    shortlist_file    = run_dir / "shortlist.json"
    shortlist_jsonl   = run_dir / "shortlist.jsonl"
    review_file       = run_dir / "review_candidates.jsonl"
    market_file       = run_dir / "market_intelligence.jsonl"
    rejected_file     = run_dir / "rejected_tenders.jsonl"

    shortlisted = []
    review_candidates = []
    market_intelligence = []
    now_utc = datetime.now(timezone.utc)
    filtered_deadline = 0
    filtered_status = 0
    rejected = []
    rejection_reason_counts: Counter[str] = Counter()
    fallback_promoted = 0

    with open(input_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("Skipping malformed JSON line in %s: %s", input_file.name, exc)
                continue
            score = int(rec.get("score", 0) or 0)
            rejection_reasons = rejection_reasons_for_record(rec, now_utc)
            if rejection_reasons:
                if "stale_deadline" in rejection_reasons:
                    filtered_deadline += 1
                if any(reason in {"inactive_status", "award", "awardUpdate"} for reason in rejection_reasons):
                    filtered_status += 1
                rejection_reason_counts.update(rejection_reasons)
                if "award" in rejection_reasons or "awardUpdate" in rejection_reasons:
                    market_rec = dict(rec)
                    market_rec["selection_bucket"] = "market_intelligence"
                    market_rec["rejection_reasons"] = rejection_reasons
                    market_intelligence.append(market_rec)
                else:
                    rejected_rec = dict(rec)
                    rejected_rec["selection_bucket"] = "rejected"
                    rejected_rec["rejection_reasons"] = rejection_reasons
                    rejected.append(rejected_rec)
                continue
            if score >= min_score:
                shortlisted_rec = dict(rec)
                shortlisted_rec["selection_bucket"] = "shortlist"
                shortlisted.append(shortlisted_rec)
                continue
            if score >= review_min_score:
                review_rec = dict(rec)
                review_rec["selection_bucket"] = "review"
                review_candidates.append(review_rec)
                continue
            rejected_rec = dict(rec)
            rejected_rec["selection_bucket"] = "rejected"
            rejected_rec["rejection_reasons"] = ["below_threshold"]
            rejected.append(rejected_rec)
            rejection_reason_counts.update(["below_threshold"])

    # Already sorted by score from match step, just cap the shortlist.
    shortlisted.sort(key=lambda rec: int(rec.get("score", 0) or 0), reverse=True)
    review_candidates.sort(key=lambda rec: int(rec.get("score", 0) or 0), reverse=True)
    shortlist = shortlisted[:top_n]
    if not shortlist and review_candidates:
        fallback_count = min(2, len(review_candidates))
        promoted = []
        for rec in review_candidates[:fallback_count]:
            promoted_rec = dict(rec)
            promoted_rec["selection_bucket"] = "shortlist"
            promoted_rec["selection_fallback"] = "review_promotion"
            promoted.append(promoted_rec)
        shortlist = promoted
        review_candidates = review_candidates[fallback_count:]
        fallback_promoted = len(promoted)

    with open(shortlist_file, "w", encoding="utf-8") as f:
        json.dump({"opportunities": shortlist}, f, indent=2, default=str)
    for path, rows in (
        (shortlist_jsonl, shortlist),
        (review_file, review_candidates),
        (market_file, market_intelligence),
        (rejected_file, rejected),
    ):
        with open(path, "w", encoding="utf-8") as f:
            for rec in rows:
                f.write(json.dumps(rec, default=str) + "\n")

    log.info(
        "Select complete: %d shortlisted, %d review, %d market intelligence, %d rejected",
        len(shortlist),
        len(review_candidates),
        len(market_intelligence),
        len(rejected),
    )
    if fallback_promoted:
        log.info(
            "Select fallback: promoted %d review tender(s) into shortlist because no direct shortlist candidates existed",
            fallback_promoted,
        )
    log.info(
        "Select filters:\n  stale_deadline: %d\n  inactive_status: %d\n  award: %d\n  awardUpdate: %d\n  below_threshold: %d",
        rejection_reason_counts.get("stale_deadline", 0),
        rejection_reason_counts.get("inactive_status", 0),
        rejection_reason_counts.get("award", 0),
        rejection_reason_counts.get("awardUpdate", 0),
        rejection_reason_counts.get("below_threshold", 0),
    )

    return {
        "shortlist_count": len(shortlist),
        "shortlist_file":  shortlist_file,
        "shortlist_jsonl_file": shortlist_jsonl,
        "review_count": len(review_candidates),
        "review_candidates_file": review_file,
        "market_intelligence_count": len(market_intelligence),
        "market_intelligence_file": market_file,
        "rejected_tenders_file": rejected_file,
        "rejected_tenders_count": len(rejected),
        "rejected_count": len(rejected),
        "select_rejection_reason_counts": dict(sorted(rejection_reason_counts.items())),
        "rejection_reason_counts": dict(sorted(rejection_reason_counts.items())),
        "select_eligible_count": len(shortlist) + len(review_candidates),
        "select_stale_filtered_count": filtered_deadline,
        "select_excluded_filtered_count": filtered_status,
        "select_fallback_promoted_count": fallback_promoted,
    }
