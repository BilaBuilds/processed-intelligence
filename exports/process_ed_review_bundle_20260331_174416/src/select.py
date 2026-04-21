"""
src/select.py
=============
Step 4 - Select

Reads scored_tenders.jsonl and keeps only the top N tenders
above a minimum score threshold.

Output: shortlist.json
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("select")


EXCLUDED_STATUS_TERMS = {
    "award",
    "awarded",
    "cancelled",
    "canceled",
    "closed",
    "complete",
    "completed",
    "contract",
    "implementation",
    "terminated",
    "unsuccessful",
    "withdrawn",
}


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


def is_live_deadline(rec: dict, now_utc: datetime) -> bool:
    parsed = parse_deadline(rec.get("deadline"))
    if parsed is None:
        # Keep unknown deadlines; status filter still applies.
        return True
    return parsed >= now_utc


def is_excluded_by_status(rec: dict) -> bool:
    status = str(rec.get("status") or "").strip().lower()
    tags = rec.get("release_tags", []) or []
    tag_text = " ".join(str(tag).strip().lower() for tag in tags)
    combined = f"{status} {tag_text}".strip()
    if not combined:
        return False
    return any(term in combined for term in EXCLUDED_STATUS_TERMS)


# --- Runner ------------------------------------------------------------------


def run(context: dict) -> dict:
    min_score = int(os.getenv("TENDER_MIN_SCORE", "20"))
    top_n = int(os.getenv("TENDER_SHORTLIST_N", os.getenv("TENDER_TOP_N", "10")))

    scored_file: Path = context["scored_file"]
    run_dir: Path     = context["run_dir"]
    shortlist_file    = run_dir / "shortlist.json"

    candidates = []
    now_utc = datetime.now(timezone.utc)
    filtered_deadline = 0
    filtered_status = 0

    with open(scored_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("score", 0) < min_score:
                continue
            if not is_live_deadline(rec, now_utc):
                filtered_deadline += 1
                continue
            if is_excluded_by_status(rec):
                filtered_status += 1
                continue
            candidates.append(rec)

    # Already sorted by score from match step, just take top N
    shortlist = candidates[:top_n]

    with open(shortlist_file, "w", encoding="utf-8") as f:
        json.dump({"opportunities": shortlist}, f, indent=2, default=str)

    log.info(
        "Select complete: %d eligible (min=%d), %d shortlisted -> %s",
        len(candidates), min_score, len(shortlist), shortlist_file.name,
    )
    log.info(
        "Select filters: %d stale deadline, %d excluded status/tag",
        filtered_deadline,
        filtered_status,
    )

    return {
        "shortlist_count": len(shortlist),
        "shortlist_file":  shortlist_file,
    }
