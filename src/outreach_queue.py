"""
src/outreach_queue.py
=====================
Outreach Queue — deterministic commercial action layer.

Ranks tracked buyers by outreach urgency using existing signals:
    buyer_watchlist   (fit, priority, activity, notice history)
    buyer_timing      (timing_label, confidence, visibility, predicted window)
    buyer_intel       (free-text brief if available)
    outreach.sqlite   (buyer_actions — last contact state)

Produces per-run artifacts:
    outreach_queue.json
    outreach_queue.csv

Score components (max 100):
    watchlist priority : hot=40  warm=25  watch=10  low=0
    timing label       : Actionable=25  Watch=12  Tracking=5  else=0
    timing confidence  : High=15  Medium=10  Weak=5  None=0
    timing visibility  : full=8  limited=4  hidden=0
    fit_to_client      : fit // 5  (max 19)
    activity_90d bonus : min(activity_90d, 3) * 3  (max 9)
    recent_match       : +4 if recent_match_count >= 2

Priority buckets (outreach_priority — separate from watchlist priority):
    Hot     score >= 65
    Warm    score >= 40
    Monitor score >= 20
    Low     < 20

Channel rules (evaluated top-down, first match wins):
    email         Hot OR (Warm AND timing_label=Actionable)
    email         Warm AND fit >= 55
    linkedin      Warm
    linkedin      Monitor AND timing_visibility != hidden
    monitor_only  everything else
"""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("outreach_queue")

# ---------------------------------------------------------------------------
# Score / priority
# ---------------------------------------------------------------------------

_WL_PRIORITY_SCORE = {"hot": 40, "warm": 25, "watch": 10, "low": 0}
_TIMING_LABEL_SCORE = {"Actionable": 25, "Watch": 12, "Tracking": 5}
_TIMING_CONF_SCORE  = {"High": 15, "Medium": 10, "Weak": 5, "None": 0}
_TIMING_VIS_SCORE   = {"full": 8, "limited": 4, "hidden": 0}


def compute_outreach_score(wl: dict, ts: dict) -> int:
    score = _WL_PRIORITY_SCORE.get(wl.get("outreach_priority", "low"), 0)
    score += _TIMING_LABEL_SCORE.get(ts.get("timing_label", ""), 0)
    score += _TIMING_CONF_SCORE.get(ts.get("timing_confidence", "None"), 0)
    score += _TIMING_VIS_SCORE.get(ts.get("timing_visibility", "hidden"), 0)
    score += (wl.get("fit_to_client") or 0) // 5
    score += min((wl.get("activity_90d") or 0), 3) * 3
    if (wl.get("recent_match_count") or 0) >= 2:
        score += 4
    return min(score, 100)


def score_to_priority(score: int) -> str:
    if score >= 65:
        return "Hot"
    if score >= 40:
        return "Warm"
    if score >= 20:
        return "Monitor"
    return "Low"


# ---------------------------------------------------------------------------
# Channel recommendation
# ---------------------------------------------------------------------------

def recommend_channel(priority: str, wl: dict, ts: dict) -> str:
    timing_label = ts.get("timing_label", "")
    fit = wl.get("fit_to_client") or 0
    vis = ts.get("timing_visibility", "hidden")

    if priority == "Hot":
        return "email"
    if priority == "Warm" and timing_label == "Actionable":
        return "email"
    if priority == "Warm" and fit >= 55:
        return "email"
    if priority == "Warm":
        return "linkedin"
    if priority == "Monitor" and vis != "hidden":
        return "linkedin"
    return "monitor_only"


# ---------------------------------------------------------------------------
# Reason + action note generation
# ---------------------------------------------------------------------------

def _readable_category(wl: dict) -> str:
    """
    Return a human-readable category label.
    Prefers 'style' (free-text, e.g. "Waste, construction") over top_categories
    which may contain raw CPV codes like "34100000".
    Falls back to 'procurement' if nothing useful is available.
    """
    style = (wl.get("style") or "").strip()
    if style:
        # Use first segment (before comma) to keep it concise
        return style.split(",")[0].strip().lower() or "procurement"
    cats = wl.get("top_categories") or []
    if cats:
        candidate = str(cats[0]).strip()
        # Skip pure numeric CPV codes — not human-readable
        if not candidate.isdigit():
            return candidate.lower()
    return "procurement"


def build_outreach_reason(priority: str, wl: dict, ts: dict) -> str:
    buyer = wl.get("buyer_name", "this buyer")
    cat_str = _readable_category(wl)
    timing_label = ts.get("timing_label", "")
    timing_conf = ts.get("timing_confidence", "None")
    fit = wl.get("fit_to_client") or 0
    activity = wl.get("activity_90d") or 0

    if priority == "Hot":
        if timing_label == "Actionable":
            return (
                f"Active buyer with {timing_conf.lower()}-confidence actionable timing window. "
                f"High fit ({fit}) and {activity} notices in 90 days — contact now."
            )
        return (
            f"High-fit buyer ({fit}) with strong recent activity ({activity} notices in 90 days). "
            f"Priority contact for {cat_str}."
        )
    if priority == "Warm":
        if timing_label in ("Actionable", "Watch"):
            return (
                f"Repeat {cat_str} buyer with {timing_conf.lower()}-confidence timing signal. "
                f"Good fit ({fit}) — add to outreach shortlist."
            )
        return (
            f"Active {cat_str} buyer with recurring procurement pattern. "
            f"Fit score {fit} — schedule intro outreach within 2 weeks."
        )
    if priority == "Monitor":
        if activity > 0:
            return (
                f"Recent buyer activity detected ({activity} notices in 90 days) but timing signal is "
                f"{timing_conf.lower() if timing_conf != 'None' else 'weak'}. Monitor and prepare."
            )
        return f"Known {cat_str} buyer; low recent activity. Keep in pipeline, revisit next quarter."
    return f"Low overlap with current delivery profile. Monitor as sector signal develops."


def build_action_note(priority: str, channel: str, ts: dict) -> str:
    timing_label = ts.get("timing_label", "")
    if priority == "Hot":
        if timing_label == "Actionable":
            return "Window open — send intro email this week."
        return "High priority — draft and send intro email."
    if priority == "Warm":
        if channel == "email":
            return "Add to outreach queue — draft intro email within 2 weeks."
        return "Connect via LinkedIn; move to email if they engage."
    if priority == "Monitor":
        return "Monitor portal activity — trigger outreach if new notice appears."
    return "Low priority — revisit if sector or fit improves."


# ---------------------------------------------------------------------------
# Draft text templates
# ---------------------------------------------------------------------------

def build_draft(wl: dict, ts: dict) -> tuple[str, str]:
    """Return (draft_subject, draft_message) — plain text, no AI."""
    buyer = wl.get("buyer_name", "your organisation")
    cat_str = _readable_category(wl)
    regions = wl.get("top_regions") or []
    region_str = f" in {regions[0]}" if regions else ""
    latest_title = wl.get("latest_notice_title") or ""
    ref_notice = f" including your recent notice '{latest_title[:80]}'" if latest_title else ""

    subject = (
        f"Introduction — procurement support for upcoming {cat_str} packages"
    )
    message = (
        f"Dear {buyer} Procurement Team,\n\n"
        f"We have been tracking your recent {cat_str} procurement activity{region_str}{ref_notice} "
        f"and would welcome the opportunity to discuss upcoming packages where we could add value.\n\n"
        f"We specialise in supporting public sector buyers with {cat_str} procurement and have "
        f"experience delivering similar programmes across the UK.\n\n"
        f"Would you be open to a brief introductory conversation at your convenience?\n\n"
        f"Kind regards"
    )
    return subject, message


# ---------------------------------------------------------------------------
# Contact state from outreach.sqlite
# ---------------------------------------------------------------------------

_ACTION_TYPE_TO_STATUS = {
    "mark_sent":      "contacted",
    "mark_drafted":   "drafted",
    "mark_follow_up": "follow_up_due",
    "mark_paused":    "paused",
    "mark_ignored":   "paused",
}


def load_contact_states(outreach_db: Path) -> dict[str, dict]:
    """
    Returns dict keyed by normalised buyer_key → {contact_status, last_contacted_at, notes}.
    Reads latest buyer_action per buyer from outreach.sqlite.
    """
    states: dict[str, dict] = {}
    if not outreach_db.exists():
        return states
    try:
        conn = sqlite3.connect(str(outreach_db))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Latest action per buyer_key
        cur.execute("""
            SELECT buyer_key, buyer_name, action_type, action_status, notes, created_at
            FROM buyer_actions
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        conn.close()
        # First occurrence per buyer_key is the most recent
        for row in rows:
            key = (row["buyer_key"] or "").strip()
            if not key or key in states:
                continue
            status = _ACTION_TYPE_TO_STATUS.get(row["action_type"], "not_contacted")
            if row["action_status"] in ("sent",):
                status = "contacted"
            elif row["action_status"] in ("drafted",):
                status = "drafted"
            states[key] = {
                "contact_status": status,
                "last_contacted_at": row["created_at"] or "",
                "notes": row["notes"] or "",
            }
    except Exception as exc:
        log.warning("Could not load outreach state from DB: %s", exc)
    return states


def _normalise_key(name: str) -> str:
    import re
    return re.sub(r"\s+", "_", (name or "").strip().lower())


def _default_contact_state() -> dict:
    return {"contact_status": "not_contacted", "last_contacted_at": "", "notes": ""}


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not load %s: %s", path.name, exc)
        return default if default is not None else {}


def _load_buyer_briefs(state_dir: Path) -> dict[str, str]:
    raw = _load_json(state_dir / "buyer_briefs.json", {})
    # buyer_briefs.json is keyed by normalised buyer key → dict with 'brief' field
    out: dict[str, str] = {}
    for key, val in raw.items():
        if isinstance(val, dict):
            out[key] = val.get("brief") or val.get("summary") or ""
        elif isinstance(val, str):
            out[key] = val
    return out


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_outreach_queue(
    watchlist: list[dict],
    timing_signals: list[dict],
    buyer_briefs: dict[str, str],
    contact_states: dict[str, dict],
) -> list[dict]:
    """
    Merge watchlist + timing + intel + contact state into a ranked outreach queue.
    """
    # Build timing lookup by buyer_key
    timing_by_key: dict[str, dict] = {}
    for sig in timing_signals:
        k = sig.get("buyer_key") or _normalise_key(sig.get("buyer_name", ""))
        if k:
            timing_by_key[k] = sig

    records: list[dict] = []
    for wl in watchlist:
        buyer_name = wl.get("buyer_name", "")
        buyer_key = _normalise_key(buyer_name)

        ts = timing_by_key.get(buyer_key, {})
        brief = buyer_briefs.get(buyer_key, "")
        state = contact_states.get(buyer_key, _default_contact_state())

        score = compute_outreach_score(wl, ts)
        priority = score_to_priority(score)
        channel = recommend_channel(priority, wl, ts)
        reason = build_outreach_reason(priority, wl, ts)
        action_note = build_action_note(priority, channel, ts)
        draft_subject, draft_message = build_draft(wl, ts)

        records.append({
            # Identity
            "buyer_name":            buyer_name,
            "buyer_key":             buyer_key,
            # Scoring
            "outreach_score":        score,
            "outreach_priority":     priority,
            # Timing
            "timing_label":          ts.get("timing_label", "Tracking"),
            "timing_confidence":     ts.get("timing_confidence", "None"),
            "timing_visibility":     ts.get("timing_visibility", "hidden"),
            "timing_status":         ts.get("timing_status", ""),
            "predicted_next_start":  ts.get("predicted_next_start", ""),
            "predicted_next_end":    ts.get("predicted_next_end", ""),
            "predicted_next_central": ts.get("predicted_next_central", ""),
            # Fit & activity
            "fit_to_client":         wl.get("fit_to_client", 0),
            "activity_90d":          wl.get("activity_90d", 0),
            "activity_30d":          wl.get("activity_30d", 0),
            "typical_value":         wl.get("typical_value", 0),
            "typical_value_label":   wl.get("typical_value_label", "Unknown"),
            "top_categories":        wl.get("top_categories", []),
            "top_regions":           wl.get("top_regions", []),
            "recent_match_count":    wl.get("recent_match_count", 0),
            # Latest notice
            "latest_notice_date":    wl.get("latest_notice_date", ""),
            "latest_notice_title":   wl.get("latest_notice_title", ""),
            # Intel
            "buyer_intel_summary":   brief,
            # Reason + channel
            "outreach_reason":       reason,
            "action_note":           action_note,
            "recommended_channel":   channel,
            # Draft
            "draft_subject":         draft_subject,
            "draft_message":         draft_message,
            # Contact state
            "contact_status":        state["contact_status"],
            "last_contacted_at":     state["last_contacted_at"],
            "notes":                 state["notes"],
        })

    # Sort: priority order, then score descending, then name
    _priority_order = {"Hot": 0, "Warm": 1, "Monitor": 2, "Low": 3}
    records.sort(key=lambda r: (
        _priority_order.get(r["outreach_priority"], 9),
        -r["outreach_score"],
        r["buyer_name"],
    ))
    return records


# ---------------------------------------------------------------------------
# Artifact writers
# ---------------------------------------------------------------------------

_CSV_FIELDS = [
    "buyer_name", "outreach_priority", "outreach_score",
    "timing_label", "timing_confidence", "timing_visibility",
    "fit_to_client", "activity_90d", "typical_value_label",
    "top_categories", "top_regions",
    "latest_notice_date", "latest_notice_title",
    "predicted_next_start", "predicted_next_end",
    "outreach_reason", "action_note", "recommended_channel",
    "draft_subject",
    "contact_status", "last_contacted_at", "notes",
]


def write_artifacts(records: list[dict], run_dir: Path) -> tuple[Path, Path]:
    json_path = run_dir / "outreach_queue.json"
    csv_path  = run_dir / "outreach_queue.csv"

    json_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    flat = []
    for r in records:
        row = dict(r)
        row["top_categories"] = "; ".join(r.get("top_categories") or [])
        row["top_regions"]    = "; ".join(r.get("top_regions") or [])
        flat.append(row)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat)

    return json_path, csv_path


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def build_and_write(run_dir: Path, state_dir: Path) -> dict[str, Any]:
    """
    Load signals from latest run artifacts, build queue, write outputs.
    Returns summary dict for manifest.
    """
    watchlist      = _load_json(run_dir / "buyer_watchlist.json", [])
    timing_raw     = _load_json(run_dir / "buyer_timing_signals.json", [])
    timing_signals = timing_raw if isinstance(timing_raw, list) else timing_raw.get("signals", [])
    buyer_briefs   = _load_buyer_briefs(state_dir)
    contact_states = load_contact_states(state_dir / "outreach.sqlite")

    records = build_outreach_queue(watchlist, timing_signals, buyer_briefs, contact_states)

    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=True)

    json_path, csv_path = write_artifacts(records, run_dir)

    hot_count          = sum(1 for r in records if r["outreach_priority"] == "Hot")
    warm_count         = sum(1 for r in records if r["outreach_priority"] == "Warm")
    follow_up_count    = sum(1 for r in records if r["contact_status"] == "follow_up_due")

    log.info(
        "Outreach queue: %d buyers — %d Hot, %d Warm, %d follow-up due → %s",
        len(records), hot_count, warm_count, follow_up_count, json_path.name,
    )

    return {
        "outreach_queue_count":         len(records),
        "outreach_hot_count":           hot_count,
        "outreach_warm_count":          warm_count,
        "outreach_follow_up_due_count": follow_up_count,
        "outreach_status":              "ok" if records else "ok_empty",
        "outreach_queue_file":          str(json_path),
        "outreach_queue_csv":           str(csv_path),
    }
