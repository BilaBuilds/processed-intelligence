"""
src/buyer_watchlist.py
======================
Buyer Watchlist — deterministic computation layer.

Produces one structured record per tracked buyer containing all
fields needed for the dashboard watchlist surface and outreach prioritisation.

All scoring is deterministic: same inputs always produce the same outputs.
Gemini (AI) is NOT used here — it is optional only in buyer_intel.py for
the free-text brief. This module owns the numbers.

Fields produced per buyer:
    buyer_name          str   canonical display name
    activity_30d        int   tender count seen in last 30 days
    activity_90d        int   tender count seen in last 90 days
    total_notices       int   all-time count in buyer_history.jsonl
    typical_value       int   median value of history records (£)
    typical_value_label str   human label e.g. "£250k – £500k"
    top_categories      list  up to 4 distinct CPV / trade labels
    top_regions         list  up to 3 most frequent regions
    recent_match_count  int   how many of the last 10 notices scored >= MIN_SCORE
    fit_to_client       int   0-100 deterministic fit score
    outreach_priority   str   hot | warm | watch | low
    action_note         str   one-line action suggestion
    latest_notice_date  str   ISO date of most recent seen_at
    latest_notice_title str   title of most recent notice

Fit scoring breakdown (max 100):
    +35  frequency: bi-weekly/weekly
    +30  frequency: monthly
    +15  frequency: quarterly
    +35  value band: £100k–£1M  (SME sweet spot)
    +20  value band: £1M–£2.5M  (stretchy but reachable)
    +10  value band: other / unknown
    +15  activity_90d >= 3
    +10  activity_90d >= 1
    +5   recent_match_count >= 2

Priority rules (evaluated in order):
    hot   fit >= 65 AND activity_90d >= 2
    warm  fit >= 50  OR activity_90d >= 2
    watch fit >= 30
    low   everything else
"""

from __future__ import annotations

import csv
import json
import logging
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("buyer_watchlist")

MIN_SCORE_FOR_MATCH = 30   # tender score threshold for recent_match_count
PRIORITY_ORDER = {"hot": 0, "warm": 1, "watch": 2, "low": 3}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _normalise_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def _median_int(values: list[float]) -> int:
    if not values:
        return 0
    return int(statistics.median(values))


def _value_label(v: int) -> str:
    if v <= 0:
        return "Unknown"
    if v < 100_000:
        return f"< £100k"
    if v < 250_000:
        return "£100k – £250k"
    if v < 500_000:
        return "£250k – £500k"
    if v < 1_000_000:
        return "£500k – £1M"
    if v < 2_500_000:
        return "£1M – £2.5M"
    return "> £2.5M"


def _action_note(priority: str, activity_90d: int, fit: int, buyer_name: str) -> str:
    if priority == "hot":
        return f"Active in niche — contact {buyer_name} procurement team now."
    if priority == "warm":
        if activity_90d >= 2:
            return "Recently active — add to outreach shortlist this week."
        return "Good fit — schedule intro outreach within 2 weeks."
    if priority == "watch":
        return "Monitor — worth tracking as pipeline develops."
    return "Low overlap with current delivery profile — revisit if sector expands."


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_watchlist(
    buyer_profiles: dict[str, dict],
    history_by_buyer: dict[str, list[dict]],
    job_history: list[dict] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Compute a watchlist record for every buyer in buyer_profiles.

    Args:
        buyer_profiles:   dict keyed by normalised buyer name
        history_by_buyer: dict keyed by normalised buyer name -> list of history records
        job_history:      optional list of your own past jobs (for fit signal boost)
        now:              injectable for testing; defaults to utc now

    Returns:
        List of watchlist dicts, sorted by priority then fit score descending.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    cutoff_30 = now - timedelta(days=30)
    cutoff_90 = now - timedelta(days=90)

    # Build a set of buyer names mentioned in your own job history (for fit boost)
    job_history_buyers: set[str] = set()
    if job_history:
        for job in job_history:
            key = _normalise_key(job.get("buyer") or job.get("client") or job.get("buyer_name"))
            if key:
                job_history_buyers.add(key)

    records: list[dict[str, Any]] = []

    for buyer_key, profile in buyer_profiles.items():
        history = history_by_buyer.get(buyer_key, [])

        # Sort history by seen_at descending for recency
        def _sort_key(r: dict) -> str:
            return r.get("seen_at", "")
        history_sorted = sorted(history, key=_sort_key, reverse=True)

        # Activity counts
        activity_30d = 0
        activity_90d = 0
        for rec in history:
            dt = _parse_dt(rec.get("seen_at"))
            if dt is None:
                continue
            if dt >= cutoff_90:
                activity_90d += 1
            if dt >= cutoff_30:
                activity_30d += 1

        total_notices = len(history)

        # Typical value — median of non-zero values
        values = [
            float(r["value_amount"])
            for r in history
            if r.get("value_amount") and str(r["value_amount"]).replace(".", "").isdigit()
        ]
        typical_value = _median_int(values)

        # Fall back to profile avg_value if no history
        if typical_value == 0 and profile.get("avg_value"):
            try:
                typical_value = int(float(profile["avg_value"]))
            except (ValueError, TypeError):
                pass

        typical_value_label = _value_label(typical_value)

        # Top categories — from CPV codes, then title keywords
        cat_counts: dict[str, int] = {}
        for rec in history:
            for cpv in (rec.get("cpv_codes") or []):
                label = str(cpv).strip()
                if label:
                    cat_counts[label] = cat_counts.get(label, 0) + 1
        top_categories = [k for k, _ in sorted(cat_counts.items(), key=lambda x: -x[1])][:4]

        # Fall back: derive from profile style field
        if not top_categories and profile.get("style"):
            top_categories = [profile["style"].split(",")[0].strip()]

        # Top regions
        region_counts: dict[str, int] = {}
        for rec in history:
            reg = (rec.get("region") or "").strip().lower()
            if reg:
                region_counts[reg] = region_counts.get(reg, 0) + 1
        top_regions = [k.title() for k, _ in sorted(region_counts.items(), key=lambda x: -x[1])][:3]

        # Recent match count — last 10 notices with score >= threshold
        recent_ten = history_sorted[:10]
        recent_match_count = sum(
            1 for r in recent_ten
            if (r.get("score") or 0) >= MIN_SCORE_FOR_MATCH
        )

        # Latest notice
        latest = history_sorted[0] if history_sorted else {}
        latest_dt = _parse_dt(latest.get("seen_at"))
        latest_notice_date = latest_dt.strftime("%Y-%m-%d") if latest_dt else ""
        latest_notice_title = (latest.get("title") or "")[:120]

        # ── Fit score ──
        fit = 0
        freq = (profile.get("frequency") or "").lower()
        if "bi-weekly" in freq or "weekly" in freq:
            fit += 35
        elif "monthly" in freq:
            fit += 30
        elif "quarterly" in freq:
            fit += 15

        if 100_000 <= typical_value <= 1_000_000:
            fit += 35
        elif 1_000_001 <= typical_value <= 2_500_000:
            fit += 20
        elif typical_value > 0:
            fit += 10

        if activity_90d >= 3:
            fit += 15
        elif activity_90d >= 1:
            fit += 10

        if recent_match_count >= 2:
            fit += 5

        # Bonus: buyer appears in your own job history
        if buyer_key in job_history_buyers:
            fit += 10

        fit = min(fit, 99)

        # ── Priority ──
        if fit >= 65 and activity_90d >= 2:
            priority = "hot"
        elif fit >= 50 or activity_90d >= 2:
            priority = "warm"
        elif fit >= 30:
            priority = "watch"
        else:
            priority = "low"

        buyer_name = profile.get("full_name") or buyer_key.title()

        records.append({
            "buyer_name": buyer_name,
            "activity_30d": activity_30d,
            "activity_90d": activity_90d,
            "total_notices": total_notices,
            "typical_value": typical_value,
            "typical_value_label": typical_value_label,
            "top_categories": top_categories,
            "top_regions": top_regions,
            "recent_match_count": recent_match_count,
            "fit_to_client": fit,
            "outreach_priority": priority,
            "action_note": _action_note(priority, activity_90d, fit, buyer_name),
            "latest_notice_date": latest_notice_date,
            "latest_notice_title": latest_notice_title,
            # carry profile fields for dashboard display
            "frequency": profile.get("frequency", ""),
            "contact_pattern": profile.get("contact_pattern", ""),
            "style": profile.get("style", ""),
        })

    # Sort: priority order, then fit descending, then name
    records.sort(key=lambda r: (
        PRIORITY_ORDER.get(r["outreach_priority"], 9),
        -r["fit_to_client"],
        r["buyer_name"],
    ))
    return records


# ---------------------------------------------------------------------------
# Load helpers (used by pipeline step and bundle builder)
# ---------------------------------------------------------------------------

def load_buyer_history(history_file: Path) -> dict[str, list[dict]]:
    """Load buyer_history.jsonl grouped by normalised buyer key."""
    grouped: dict[str, list[dict]] = {}
    if not history_file.exists():
        return grouped
    for line in history_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            key = _normalise_key(rec.get("buyer_name"))
            if key:
                grouped.setdefault(key, []).append(rec)
        except Exception:
            continue
    return grouped


# ---------------------------------------------------------------------------
# Write artifacts
# ---------------------------------------------------------------------------

def write_json(records: list[dict], path: Path) -> None:
    path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")


def write_csv(records: list[dict], path: Path) -> None:
    if not records:
        path.write_text("", encoding="utf-8")
        return
    # Flatten list fields for CSV
    flat = []
    for r in records:
        row = dict(r)
        row["top_categories"] = "; ".join(r.get("top_categories") or [])
        row["top_regions"] = "; ".join(r.get("top_regions") or [])
        flat.append(row)
    fieldnames = [
        "buyer_name", "outreach_priority", "fit_to_client",
        "activity_30d", "activity_90d", "total_notices",
        "typical_value", "typical_value_label",
        "top_categories", "top_regions",
        "recent_match_count", "action_note",
        "latest_notice_date", "latest_notice_title",
        "frequency", "contact_pattern",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat)


# ---------------------------------------------------------------------------
# Pipeline entry point (called from buyer_intel.py)
# ---------------------------------------------------------------------------

def build_and_write(
    run_dir: Path,
    state_dir: Path,
) -> dict[str, Any]:
    """
    Build watchlist from state files and write run artifacts.

    Returns dict with artifact paths and summary stats.
    """
    buyer_profiles_file = state_dir / "buyer_profiles.json"
    history_file = state_dir / "buyer_history.jsonl"
    job_history_file = state_dir / "job_history.json"

    try:
        buyer_profiles: dict = json.loads(buyer_profiles_file.read_text(encoding="utf-8")) if buyer_profiles_file.exists() else {}
    except Exception as exc:
        log.warning("Could not load buyer_profiles.json: %s", exc)
        buyer_profiles = {}

    if not buyer_profiles:
        log.info("Buyer watchlist: no buyer profiles found — writing empty artifact")
        json_path = run_dir / "buyer_watchlist.json"
        csv_path = run_dir / "buyer_watchlist.csv"
        json_path.write_text("[]", encoding="utf-8")
        write_csv([], csv_path)
        return {
            "buyer_watchlist_count": 0,
            "buyer_watchlist_file": str(json_path),
            "buyer_watchlist_csv": str(csv_path),
            "buyer_watchlist_status": "no_profiles",
        }

    history_by_buyer = load_buyer_history(history_file)

    job_history: list[dict] = []
    if job_history_file.exists():
        try:
            job_history = json.loads(job_history_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    records = compute_watchlist(buyer_profiles, history_by_buyer, job_history)

    json_path = run_dir / "buyer_watchlist.json"
    csv_path = run_dir / "buyer_watchlist.csv"

    write_json(records, json_path)
    write_csv(records, csv_path)

    hot = sum(1 for r in records if r["outreach_priority"] == "hot")
    warm = sum(1 for r in records if r["outreach_priority"] == "warm")

    log.info(
        "Buyer watchlist: %d buyers — %d hot, %d warm -> %s",
        len(records), hot, warm, json_path.name,
    )

    return {
        "buyer_watchlist_count": len(records),
        "buyer_watchlist_hot": hot,
        "buyer_watchlist_warm": warm,
        "buyer_watchlist_file": str(json_path),
        "buyer_watchlist_csv": str(csv_path),
        "buyer_watchlist_status": "ok",
    }
