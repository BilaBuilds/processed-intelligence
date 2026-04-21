"""
Build a local JavaScript bundle consumed by ProcessEd_Dashboard.html.

Usage:
    python scripts/build_dashboard_bundle.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = BASE_DIR / "data" / "runs"
STATE_DIR = BASE_DIR / "state"
CONFIG_DIR = BASE_DIR / "config"
OUTPUT_FILE = BASE_DIR / "dashboard_data.js"
OPENCLAW_BUYERS_DIR = BASE_DIR / "openclaw_workspace" / "buyers"

# Ensure project root is in sys.path so src.* imports work when script is run directly
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def load_action_states() -> dict[str, dict[str, Any]]:
    """
    Load the current outreach action state for every tracked buyer.

    Returns a dict keyed by normalised buyer_key → state dict with fields:
        overall_status   str   e.g. "sent", "drafted", "pending", "not_started"
        action_count     int
        latest_action    dict | None

    Gracefully returns {} if the DB is missing, locked, or corrupt.
    """
    override = os.getenv("OUTREACH_DB_PATH")
    db_path = Path(override).expanduser().resolve() if override else STATE_DIR / "outreach.sqlite"
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Pull all buyer_actions in one query and derive states in Python
        rows = conn.execute(
            "SELECT buyer_key, id, action_type, action_status, run_id, "
            "notes, actor, source, created_at, updated_at "
            "FROM buyer_actions ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()
    except Exception:
        return {}

    # Group by buyer_key
    by_buyer: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        d = dict(row)
        k = str(d.get("buyer_key") or "").strip().lower()
        if k:
            by_buyer.setdefault(k, []).append(d)

    STATUS_PRIORITY = {
        "sent": 0, "drafted": 1, "follow_up": 2,
        "ignored": 3, "completed": 4, "pending": 5, "failed": 6,
    }

    result: dict[str, dict[str, Any]] = {}
    for buyer_key, actions in by_buyer.items():
        overall = "not_started"
        latest_action: dict[str, Any] | None = None
        for action in actions:
            s = action.get("action_status", "")
            if STATUS_PRIORITY.get(s, 99) < STATUS_PRIORITY.get(overall, 99):
                overall = s
                latest_action = action
        result[buyer_key] = {
            "overall_status": overall,
            "action_count": len(actions),
            "latest_action": latest_action,
        }
    return result


def latest_run_dir() -> Path:
    candidates = sorted(
        (path for path in RUNS_DIR.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )
    for candidate in candidates:
        manifest = load_json(candidate / "run_manifest.json", {})
        if str(manifest.get("status") or "").startswith("success"):
            return candidate
    raise FileNotFoundError(f"No successful runs found in {RUNS_DIR}")


def normalise_buyer_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def slugify_buyer(value: str | None) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _quote_cli_arg(value: str) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def _normalise_action_state(raw: str | None) -> str:
    state = str(raw or "").strip().lower()
    if state in {"drafted"}:
        return "drafted"
    if state in {"sent", "follow_up", "completed"}:
        return "sent"
    if state in {"ignored"}:
        return "ignored"
    return "not_started"


def _action_state_badge(state: str) -> str:
    mapping = {
        "not_started": "Not started",
        "drafted": "Drafted",
        "sent": "Sent",
        "ignored": "Ignored",
    }
    return mapping.get(state, "Not started")


def _build_next_action(card: dict[str, Any]) -> str:
    timing_label = str(card.get("timing_label") or "Tracking")
    timing_visibility = str(card.get("timing_visibility") or "hidden")
    outreach_status = _normalise_action_state(card.get("outreach_status") or card.get("action_state"))
    fit = int(card.get("fit_to_client") or 0)

    if outreach_status == "sent":
        return "Wait / follow up later"
    if outreach_status == "ignored":
        return "No action"
    if timing_visibility == "limited":
        return "Monitor"
    if timing_label == "Actionable" and outreach_status == "not_started":
        return "Draft outreach"
    if timing_label == "Actionable" and outreach_status == "drafted":
        return "Send outreach"
    if timing_label == "Watch" and fit >= 60 and outreach_status == "not_started":
        return "Prepare outreach"
    return "Review dossier"


def _add_operator_fields(card: dict[str, Any]) -> dict[str, Any]:
    buyer_name = str(card.get("name") or card.get("buyer_name") or "").strip()
    slug = slugify_buyer(card.get("key") or buyer_name)
    dossier_path = OPENCLAW_BUYERS_DIR / f"{slug}.md"
    action_state = _normalise_action_state(card.get("outreach_status") or card.get("action_state"))

    card["buyer_slug"] = slug
    card["outreach_status"] = action_state
    card["action_state"] = action_state
    card["action_state_label"] = _action_state_badge(action_state)
    card["action_state_badge"] = action_state
    card["next_action"] = _build_next_action(card)
    card["dossier_path"] = str(dossier_path)
    card["dossier_uri"] = dossier_path.resolve().as_uri()
    card["dossier_exists"] = dossier_path.exists()
    card["cli_mark_drafted"] = f"python scripts/generate_outreach.py --buyer {_quote_cli_arg(buyer_name)} --mode email --save"
    card["cli_mark_sent"] = f"python -m outreach.cli create-action --buyer {_quote_cli_arg(buyer_name)} --type mark_sent --status sent"
    card["cli_mark_ignored"] = f"python -m outreach.cli create-action --buyer {_quote_cli_arg(buyer_name)} --type mark_ignored --status ignored"
    return card


def build_run_history(limit: int = 12) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    candidates = sorted(
        (path for path in RUNS_DIR.iterdir() if path.is_dir()),
        key=lambda path: path.name,
        reverse=True,
    )[:limit]
    for run_dir in candidates:
        manifest = load_json(run_dir / "run_manifest.json", {})
        if not manifest:
            continue
        history.append(
            {
                "run_id": manifest.get("run_id", run_dir.name),
                "status": manifest.get("status", "unknown"),
                "notify_status": (
                    (manifest.get("steps") or {}).get("notify") or {}
                ).get("status", "unknown"),
                "ingest_total_count": manifest.get("ingest_total_count", 0),
                "shortlist_count": manifest.get("shortlist_count", 0),
                "review_count": manifest.get("review_count", 0),
                "new_count": manifest.get("new_count", 0),
                "decision_verdict_counts": manifest.get("decision_verdict_counts", {}),
                "finished_at": manifest.get("finished_at"),
                "duration_s": manifest.get("total_duration_s", 0),
            }
        )
    return history


def build_buyer_watchlist_cards(latest_run: Path, state_dir: Path) -> list[dict[str, Any]]:
    """
    Load buyer watchlist from the run artifact if present.
    Falls back to computing from state files directly.
    Maps fields to the shape expected by the dashboard JS.
    """
    artifact = latest_run / "buyer_watchlist.json"
    if artifact.exists():
        try:
            records = json.loads(artifact.read_text(encoding="utf-8"))
            return [_watchlist_record_to_card(r) for r in records]
        except Exception:
            pass

    import sys
    sys.path.insert(0, str(BASE_DIR))
    from src.buyer_watchlist import compute_watchlist, load_buyer_history

    buyer_profiles: dict = load_json(state_dir / "buyer_profiles.json", {})
    if not buyer_profiles:
        return []
    history_by_buyer = load_buyer_history(state_dir / "buyer_history.jsonl")
    job_history: list = load_json(state_dir / "job_history.json", [])
    records = compute_watchlist(buyer_profiles, history_by_buyer, job_history)
    return [_watchlist_record_to_card(r) for r in records]


def _watchlist_record_to_card(r: dict) -> dict[str, Any]:
    """Map a watchlist record to the JS dashboard card shape."""
    return {
        # Core identity
        "key": normalise_buyer_key(r.get("buyer_name", "")),
        "name": r.get("buyer_name", ""),
        # Legacy fields
        "frequency": r.get("frequency", ""),
        "avg_value": r.get("typical_value") or None,
        "style": r.get("style", ""),
        "contact_pattern": r.get("contact_pattern", ""),
        # Watchlist fields
        "activity_30d": r.get("activity_30d", 0),
        "activity_90d": r.get("activity_90d", 0),
        "total_notices": r.get("total_notices", 0),
        "typical_value": r.get("typical_value", 0),
        "typical_value_label": r.get("typical_value_label", ""),
        "top_categories": r.get("top_categories") or [],
        "top_regions": r.get("top_regions") or [],
        "recent_match_count": r.get("recent_match_count", 0),
        "fit_score": r.get("fit_to_client", 0),
        "fit_to_client": r.get("fit_to_client", 0),
        "outreach_priority": r.get("outreach_priority", "low"),
        "action_note": r.get("action_note", ""),
        "latest_notice_date": r.get("latest_notice_date", ""),
        "latest_notice_title": r.get("latest_notice_title", ""),
        # categories alias for legacy dashboard code
        "categories": r.get("top_categories") or [],
        # Buyer intel enrichment fields (injected post-dedupe; may be absent)
        "buyer_intel_summary": r.get("buyer_intel_summary", ""),
        "buyer_pattern": r.get("buyer_pattern", ""),
        "buyer_avg_value": r.get("buyer_avg_value"),
        "buyer_activity_90d": r.get("buyer_activity_90d"),
        "buyer_category_bias": r.get("buyer_category_bias") or [],
        # Outreach action state (injected by merge_action_states; defaults present)
        "outreach_status": r.get("outreach_status", "not_started"),
        "action_state": r.get("action_state", "not_started"),
        "action_count": r.get("action_count", 0),
    }


def _merge_action_states(
    buyer_cards: list[dict[str, Any]],
    action_states: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge outreach action state into buyer cards, then apply operator fields
    (next_action, dossier path/URI, CLI commands) to each card.
    Cards that have no DB record keep outreach_status='not_started'.
    Mutates cards in-place; also returns the list.
    """
    for card in buyer_cards:
        key = card.get("key", "")
        state = action_states.get(key) or action_states.get(slugify_buyer(card.get("name") or key))
        if state:
            card["outreach_status"] = state.get("overall_status", "not_started")
            card["action_state"] = state.get("overall_status", "not_started")
            card["action_count"] = state.get("action_count", 0)
            card["latest_action"] = state.get("latest_action")
        # Apply operator fields (dossier, next_action, CLI commands) after timing
        # and action state are both present so next_action can be computed correctly.
        _add_operator_fields(card)
    return buyer_cards


def build_forecast_data(latest_run: Path) -> dict[str, Any]:
    artifact = latest_run / "tender_forecast.json"
    if artifact.exists():
        try:
            return load_json(artifact, {})
        except Exception:
            pass
    return {}


def build_timing_data(latest_run: Path) -> dict[str, Any]:
    artifact = latest_run / "buyer_timing_signals.json"
    if artifact.exists():
        try:
            return load_json(artifact, {})
        except Exception:
            pass
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from src.buyer_timing import build_and_write as _build_timing
        result = _build_timing(run_dir=latest_run, state_dir=STATE_DIR)
        if result.get("buyer_timing_file"):
            return load_json(Path(result["buyer_timing_file"]), {})
    except Exception:
        pass
    return {}


def build_timing_backtest_data(latest_run: Path) -> dict[str, Any]:
    artifact = latest_run / "buyer_timing_backtest.json"
    if artifact.exists():
        try:
            return load_json(artifact, {})
        except Exception:
            pass
    return {}


# ---------------------------------------------------------------------------
# Commercial Radar — deterministic computation from existing signals
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {"hot": 0, "warm": 1, "watch": 2, "low": 3}
_CONFIDENCE_ORDER = {"High": 0, "Medium": 1, "Weak": 2, "None": 3}
_ACTIONABLE_STATUSES = {"due_soon", "overdue"}
_SLIPPED_STATUSES = {"slipped", "overdue"}
_FIT_THRESHOLD_HIGH = 60
_FIT_THRESHOLD_WATCH = 40


def build_commercial_radar(
    buyer_cards: list[dict[str, Any]],
    timing_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Deterministically compute commercial radar sections from existing buyer
    cards (with timing already merged in) and raw timing signals.

    Returns a dict with:
        actionable_buyers    - timing_label=Actionable, High/Medium confidence
        high_fit_watchers    - Watch label, fit >= threshold
        slipped_buyers       - past their window, not None confidence
        emerging_buyers      - new activity in 30d
        sector_radar         - top categories + regions last 90d
        focus_summary        - compact "where to focus" list (max 5 buyers)
    """
    # Build timing lookup by buyer key
    timing_by_key: dict[str, dict] = {
        s["buyer_key"]: s for s in timing_signals if "buyer_key" in s
    }

    # Enrich cards with timing fields if not already merged
    enriched: list[dict[str, Any]] = []
    for card in buyer_cards:
        c = dict(card)
        key = c.get("key", "")
        if key in timing_by_key and not c.get("timing_status"):
            tsig = timing_by_key[key]
            c["timing_status"] = tsig.get("timing_status")
            c["timing_confidence"] = tsig.get("timing_confidence")
            c["timing_label"] = tsig.get("timing_label", "Tracking")
            c["timing_visibility"] = tsig.get("timing_visibility", "hidden")
            c["timing_marketing_text"] = tsig.get("timing_marketing_text", "")
            c["buyer_due_rank"] = tsig.get("buyer_due_rank")
            # Prefer watchlist fit (richer signal); fall back to timing signal fit
            card_fit = c.get("fit_to_client") or 0
            timing_fit = tsig.get("fit_to_client") or 0
            c["fit_to_client"] = card_fit if card_fit > 0 else timing_fit
            c["action_note"] = tsig.get("action_note", c.get("action_note", ""))
            c["predicted_next_start"] = tsig.get("predicted_next_start", "")
            c["predicted_next_end"] = tsig.get("predicted_next_end", "")
        # Ensure timing_label default
        if not c.get("timing_label"):
            c["timing_label"] = "Tracking"
        if not c.get("timing_confidence"):
            c["timing_confidence"] = "None"
        if not c.get("timing_visibility"):
            c["timing_visibility"] = "hidden"
        enriched.append(c)

    # 1. Actionable buyers — timing_label=Actionable + High/Medium confidence
    #    Sorted by buyer_due_rank asc (lower = more urgent), then fit desc
    actionable = [
        c for c in enriched
        if c.get("timing_label") == "Actionable"
        and c.get("timing_confidence") in ("High", "Medium")
    ]
    actionable.sort(
        key=lambda c: (
            c.get("buyer_due_rank") or 9999,
            -(c.get("fit_to_client") or 0),
        )
    )

    # 2. High-fit watchers — Watch label, fit >= threshold
    watchers = [
        c for c in enriched
        if c.get("timing_label") == "Watch"
        and (c.get("fit_to_client") or 0) >= _FIT_THRESHOLD_WATCH
    ]
    watchers.sort(key=lambda c: -(c.get("fit_to_client") or 0))

    # 3. Slipped buyers — past their window, confidence not None
    slipped = [
        c for c in enriched
        if c.get("timing_status") in _SLIPPED_STATUSES
        and c.get("timing_confidence") not in ("None", None, "")
    ]
    slipped.sort(key=lambda c: c.get("latest_notice_date") or "", reverse=True)

    # 4. Emerging buyers — any activity in last 30d
    emerging = [
        c for c in enriched
        if (c.get("activity_30d") or 0) > 0
        and c.get("timing_label") != "Actionable"  # already in actionable list
    ]
    emerging.sort(key=lambda c: (-(c.get("activity_30d") or 0), -(c.get("fit_to_client") or 0)))

    # 5. Sector radar — top categories and regions from all cards (90d activity)
    all_cats: list[str] = []
    all_regions: list[str] = []
    for c in enriched:
        if (c.get("activity_90d") or 0) > 0:
            all_cats.extend(c.get("top_categories") or [])
            all_regions.extend(c.get("top_regions") or [])
    top_categories = [cat for cat, _ in Counter(all_cats).most_common(6)]
    top_regions = [reg for reg, _ in Counter(all_regions).most_common(4)]

    # 6. Focus summary — top 5 buyers to chase this week
    #    Priority: Actionable first (by rank), then Watch+high-fit, then emerging
    focus_pool = actionable[:3] + watchers[:2] + emerging[:2]
    # Deduplicate by key preserving order
    seen_keys: set[str] = set()
    focus_summary: list[dict[str, Any]] = []
    for c in focus_pool:
        k = c.get("key", "")
        if k not in seen_keys:
            seen_keys.add(k)
            focus_summary.append({
                "name": c.get("name", ""),
                "key": k,
                "timing_label": c.get("timing_label", "Tracking"),
                "timing_confidence": c.get("timing_confidence", "None"),
                "timing_status": c.get("timing_status", ""),
                "fit_to_client": c.get("fit_to_client") or 0,
                "outreach_priority": c.get("outreach_priority", "low"),
                "action_note": c.get("action_note", ""),
                "predicted_next_start": c.get("predicted_next_start", ""),
                "predicted_next_end": c.get("predicted_next_end", ""),
                "buyer_due_rank": c.get("buyer_due_rank"),
                "outreach_status": c.get("outreach_status", "not_started"),
                "action_state": c.get("action_state", "not_started"),
                "action_state_label": c.get("action_state_label", "Not started"),
                "action_state_badge": c.get("action_state_badge", "not_started"),
                "next_action": c.get("next_action", "Review dossier"),
                "dossier_path": c.get("dossier_path", ""),
                "dossier_uri": c.get("dossier_uri", ""),
                "dossier_exists": c.get("dossier_exists", False),
                "cli_mark_drafted": c.get("cli_mark_drafted", ""),
                "cli_mark_sent": c.get("cli_mark_sent", ""),
                "cli_mark_ignored": c.get("cli_mark_ignored", ""),
            })
        if len(focus_summary) >= 5:
            break

    def _card_summary(c: dict) -> dict[str, Any]:
        return {
            "name": c.get("name", ""),
            "key": c.get("key", ""),
            "timing_label": c.get("timing_label", "Tracking"),
            "timing_confidence": c.get("timing_confidence", "None"),
            "timing_status": c.get("timing_status", ""),
            "timing_visibility": c.get("timing_visibility", "hidden"),
            "timing_marketing_text": c.get("timing_marketing_text", ""),
            "fit_to_client": c.get("fit_to_client") or 0,
            "outreach_priority": c.get("outreach_priority", "low"),
            "action_note": c.get("action_note", ""),
            "activity_30d": c.get("activity_30d", 0),
            "activity_90d": c.get("activity_90d", 0),
            "predicted_next_start": c.get("predicted_next_start", ""),
            "predicted_next_end": c.get("predicted_next_end", ""),
            "buyer_due_rank": c.get("buyer_due_rank"),
            "buyer_intel_summary": c.get("buyer_intel_summary", ""),
            "top_categories": c.get("top_categories") or [],
            # Outreach action state
            "outreach_status": c.get("outreach_status", "not_started"),
            "action_state": c.get("action_state", "not_started"),
            "action_state_label": c.get("action_state_label", "Not started"),
            "action_state_badge": c.get("action_state_badge", "not_started"),
            "next_action": c.get("next_action", "Review dossier"),
            "dossier_path": c.get("dossier_path", ""),
            "dossier_uri": c.get("dossier_uri", ""),
            "dossier_exists": c.get("dossier_exists", False),
            "cli_mark_drafted": c.get("cli_mark_drafted", ""),
            "cli_mark_sent": c.get("cli_mark_sent", ""),
            "cli_mark_ignored": c.get("cli_mark_ignored", ""),
        }

    return {
        "actionable_buyers": [_card_summary(c) for c in actionable[:8]],
        "high_fit_watchers": [_card_summary(c) for c in watchers[:6]],
        "slipped_buyers": [_card_summary(c) for c in slipped[:6]],
        "emerging_buyers": [_card_summary(c) for c in emerging[:6]],
        "sector_radar": {
            "top_categories": top_categories,
            "top_regions": top_regions,
        },
        "focus_summary": focus_summary,
        "counts": {
            "actionable": len(actionable),
            "watchers": len(watchers),
            "slipped": len(slipped),
            "emerging": len(emerging),
            "total_tracked": len(enriched),
        },
    }


def _merge_timing_into_cards(
    buyer_cards: list[dict[str, Any]],
    timing_data: dict[str, Any],
    forecast_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Merge forecast and timing signal fields into buyer cards in-place.
    Returns the updated list.
    """
    if forecast_data.get("forecasts"):
        forecast_by_key = {f["buyer_key"]: f for f in forecast_data["forecasts"]}
        for card in buyer_cards:
            fcast = forecast_by_key.get(card.get("key", ""))
            if fcast:
                card["days_until_next"] = fcast.get("days_until_next")
                card["forecast_status"] = fcast.get("status")
                card["predicted_next_date"] = fcast.get("predicted_next_date", "")
                card["forecast_window_start"] = fcast.get("forecast_window_start", "")
                card["forecast_window_end"] = fcast.get("forecast_window_end", "")
                card["median_interval_days"] = fcast.get("median_interval_days")
                card["forecast_confidence"] = fcast.get("confidence", "low")

    if timing_data.get("signals"):
        # Build lookup keyed by both the raw buyer_key and its slug form so the merge
        # succeeds regardless of whether signals use spaces or underscores.
        timing_by_key: dict[str, Any] = {}
        for s in timing_data["signals"]:
            raw = s.get("buyer_key", "")
            timing_by_key[raw] = s
            timing_by_key[slugify_buyer(raw)] = s
        for card in buyer_cards:
            card_key = card.get("key", "")
            tsig = timing_by_key.get(card_key) or timing_by_key.get(slugify_buyer(card_key))
            if tsig:
                card["timing_status"] = tsig.get("timing_status")
                card["timing_confidence"] = tsig.get("timing_confidence")
                card["timing_label"] = tsig.get("timing_label", "Tracking")
                card["timing_visibility"] = tsig.get("timing_visibility", "hidden")
                card["timing_marketing_text"] = tsig.get("timing_marketing_text", "")
                card["timing_reason"] = tsig.get("timing_reason", "")
                card["timing_action_note"] = tsig.get("action_note", "")
                card["days_until_window_open"] = tsig.get("days_until_window_open")
                card["days_until_central"] = tsig.get("days_until_central")
                card["predicted_next_start"] = tsig.get("predicted_next_start", "")
                card["predicted_next_central"] = tsig.get("predicted_next_central", "")
                card["predicted_next_end"] = tsig.get("predicted_next_end", "")
                card["median_gap_days"] = tsig.get("median_gap_days")
                card["gap_stddev"] = tsig.get("gap_stddev")
                card["category_repeat_strength"] = tsig.get("category_repeat_strength", 0)
                card["quarter_distribution"] = tsig.get("quarter_distribution", {})
                card["month_distribution"] = tsig.get("month_distribution", {})
                card["timing_score"] = tsig.get("timing_score", 0)
                # Prefer watchlist fit (richer signal); fall back to timing signal fit
                _card_fit = card.get("fit_to_client") or 0
                _timing_fit = tsig.get("fit_to_client") or 0
                card["fit_to_client"] = _card_fit if _card_fit > 0 else _timing_fit
                card["buyer_due_rank"] = tsig.get("buyer_due_rank")
                card["buyer_intel_summary"] = tsig.get("buyer_intel_summary") or card.get("buyer_intel_summary", "")
                card["buyer_pattern"] = tsig.get("buyer_pattern") or card.get("buyer_pattern", "")
                card["buyer_activity_90d"] = tsig.get("buyer_activity_90d") if tsig.get("buyer_activity_90d") is not None else card.get("buyer_activity_90d")
                card["buyer_avg_value"] = tsig.get("buyer_avg_value") if tsig.get("buyer_avg_value") is not None else card.get("buyer_avg_value")
                card["buyer_category_bias"] = tsig.get("buyer_category_bias") or card.get("buyer_category_bias") or []

    return buyer_cards


def build_outreach_queue_data(run_dir: Path, state_dir: Path) -> dict[str, Any]:
    """
    Load outreach_queue.json from the latest run.
    Falls back to building live from watchlist + timing if artifact missing.
    Never returns fake data — returns empty records list if nothing available.
    """
    artifact = run_dir / "outreach_queue.json"
    if artifact.exists():
        try:
            records = json.loads(artifact.read_text(encoding="utf-8"))
            if isinstance(records, list):
                hot  = sum(1 for r in records if r.get("outreach_priority") == "Hot")
                warm = sum(1 for r in records if r.get("outreach_priority") == "Warm")
                follow_up = sum(1 for r in records if r.get("contact_status") == "follow_up_due")
                actionable = sum(
                    1 for r in records
                    if r.get("timing_label") == "Actionable"
                    and r.get("timing_confidence") in ("High", "Medium")
                )
                return {
                    "records": records,
                    "counts": {
                        "total": len(records),
                        "hot": hot,
                        "warm": warm,
                        "actionable": actionable,
                        "follow_up_due": follow_up,
                    },
                    "source": "run_artifact",
                }
        except Exception as exc:
            print(f"  [outreach_queue] Could not load artifact: {exc}")

    # Fall back: build live
    try:
        from src.outreach_queue import (
            build_outreach_queue,
            load_contact_states,
        )
        watchlist = load_json(run_dir / "buyer_watchlist.json", [])
        timing_raw = load_json(run_dir / "buyer_timing_signals.json", [])
        timing_signals = timing_raw if isinstance(timing_raw, list) else timing_raw.get("signals", [])
        briefs_raw = load_json(state_dir / "buyer_briefs.json", {})
        buyer_briefs = {
            k: (v.get("brief") or v.get("summary") or "") if isinstance(v, dict) else str(v)
            for k, v in briefs_raw.items()
        }
        contact_states = load_contact_states(state_dir / "outreach.sqlite")
        records = build_outreach_queue(watchlist, timing_signals, buyer_briefs, contact_states)
        hot  = sum(1 for r in records if r.get("outreach_priority") == "Hot")
        warm = sum(1 for r in records if r.get("outreach_priority") == "Warm")
        follow_up = sum(1 for r in records if r.get("contact_status") == "follow_up_due")
        actionable = sum(
            1 for r in records
            if r.get("timing_label") == "Actionable"
            and r.get("timing_confidence") in ("High", "Medium")
        )
        return {
            "records": records,
            "counts": {
                "total": len(records),
                "hot": hot,
                "warm": warm,
                "actionable": actionable,
                "follow_up_due": follow_up,
            },
            "source": "live_build",
        }
    except Exception as exc:
        print(f"  [outreach_queue] Fallback build failed: {exc}")

    return {"records": [], "counts": {"total": 0, "hot": 0, "warm": 0, "actionable": 0, "follow_up_due": 0}, "source": "empty"}


def build_product_data(run_dir: Path) -> dict[str, Any]:
    """
    Load product metadata from product_summary.json files in the run directory.
    Returns a dict with a "products" key containing a list of product summaries.
    Gracefully handles missing product files by returning empty list.
    """
    products: list[dict[str, Any]] = []
    products_dir = run_dir / "products"
    manifest = load_json(run_dir / "run_manifest.json", {})
    manifest_outputs = ((manifest.get("products") or {}).get("outputs") or {})

    if not products_dir.exists():
        return {"products": []}

    try:
        for product_subdir in sorted(products_dir.iterdir()):
            if not product_subdir.is_dir():
                continue
            summary_file = product_subdir / "product_summary.json"
            if summary_file.exists():
                try:
                    summary = load_json(summary_file, {})
                    shortlist = load_json(product_subdir / "product_shortlist.json", [])
                    product_id = summary.get("product_id", product_subdir.name)
                    manifest_entry = manifest_outputs.get(product_id, {})
                    item_count = summary.get("item_count")
                    if not isinstance(item_count, int):
                        item_count = len(shortlist) if isinstance(shortlist, list) else 0
                    products.append({
                        "id": product_id,
                        "display_name": summary.get("display_name", product_subdir.name),
                        "status": (
                            summary.get("status")
                            or manifest_entry.get("status")
                            or ("ok" if item_count > 0 else "empty")
                        ),
                        "item_count": item_count,
                        "filter_stages": summary.get("filter_stages", {}),
                        "tenders": shortlist if isinstance(shortlist, list) else [],
                    })
                except Exception:
                    # Skip this product if summary is malformed
                    continue
    except Exception:
        # If products dir traversal fails, just return empty
        pass

    return {"products": products}


def build_client_data(run_dir: Path) -> dict[str, Any]:
    """
    Load client summary artifacts from the latest run.
    Returns {"clients": [...]} — empty list if no client outputs exist.
    Fails gracefully: never raises, never returns fake data.
    """
    clients_dir = run_dir / "clients"
    clients: list[dict[str, Any]] = []
    manifest = load_json(run_dir / "run_manifest.json", {})
    manifest_outputs = ((manifest.get("clients") or {}).get("outputs") or {})
    if not clients_dir.exists():
        return {"clients": clients}
    for client_dir in sorted(clients_dir.iterdir()):
        if not client_dir.is_dir():
            continue
        summary_path = client_dir / "client_summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            shortlist_payload = load_json(client_dir / "client_shortlist.json", {})
            if isinstance(shortlist_payload, list):
                tenders = shortlist_payload
                new_tenders = [t for t in tenders if t.get("is_new")]
            elif isinstance(shortlist_payload, dict):
                tenders = shortlist_payload.get("tenders", [])
                new_tenders = shortlist_payload.get("new_tenders", [])
            else:
                tenders = []
                new_tenders = []

            client_id = summary.get("client_id", client_dir.name)
            manifest_entry = manifest_outputs.get(client_id, {})
            item_count = summary.get("item_count")
            if not isinstance(item_count, int):
                item_count = len(tenders) if isinstance(tenders, list) else 0
            new_count = summary.get("new_count")
            if not isinstance(new_count, int):
                new_count = len(new_tenders) if isinstance(new_tenders, list) else 0
            clients.append({
                "id": client_id,
                "display_name": summary.get("display_name", client_dir.name),
                "status": (
                    summary.get("status")
                    or manifest_entry.get("status")
                    or ("ok" if item_count > 0 else "empty")
                ),
                "item_count": item_count,
                "new_count": new_count,
                "notified": bool(summary.get("notified", False)),
                "notify_status": summary.get("notify_status", "skipped"),
                "subscribed_products": summary.get("subscribed_products", []),
                "tenders": tenders if isinstance(tenders, list) else [],
                "new_tenders": new_tenders if isinstance(new_tenders, list) else [],
            })
        except Exception:
            continue
    return {"clients": clients}


def build_bundle() -> dict[str, Any]:
    """Build and return the full dashboard bundle dict from the latest run artifacts."""
    try:
        latest_run = latest_run_dir()
    except FileNotFoundError as exc:
        print(f"[dashboard] No successful run found: {exc}")
        latest_run = None

    # --- Core pipeline artifacts ---
    if latest_run:
        manifest = load_json(latest_run / "run_manifest.json", {})
        shortlist_raw = load_json(latest_run / "decision_shortlist.json", {"opportunities": []})
        opportunities = shortlist_raw.get("opportunities", []) if isinstance(shortlist_raw, dict) else []
        context_rows = load_jsonl(latest_run / "context_tenders.jsonl")
        context_by_id = {r.get("id") or r.get("notice_id"): r for r in context_rows if r.get("id") or r.get("notice_id")}

        # Attach context to opportunities
        for opp in opportunities:
            oid = opp.get("id") or opp.get("notice_id")
            ctx = context_by_id.get(oid, {})
            for field in ("rationale", "risk_flags", "context_tags", "buyer_intel"):
                if field not in opp and field in ctx:
                    opp[field] = ctx[field]

        run_id = manifest.get("run_id", "")
        run_status = manifest.get("status", "unknown")
        ingest_counts = manifest.get("ingest", {})
        run_history = build_run_history()
    else:
        manifest = {}
        opportunities = []
        run_id = ""
        run_status = "no_runs"
        ingest_counts = {}
        run_history = []

    # --- Buyer cards & timing ---
    forecast_data: dict[str, Any] = {}
    timing_data: dict[str, Any] = {}
    timing_backtest: dict[str, Any] = {}
    buyer_cards: list[dict[str, Any]] = []
    if latest_run:
        forecast_data = build_forecast_data(latest_run)
        timing_data = build_timing_data(latest_run)
        timing_backtest = build_timing_backtest_data(latest_run)
        buyer_cards = build_buyer_watchlist_cards(latest_run, STATE_DIR)
        buyer_cards = _merge_timing_into_cards(buyer_cards, timing_data, forecast_data)

    # Operator fields for each card
    action_states = load_action_states()
    buyer_cards = _merge_action_states(buyer_cards, action_states)

    # --- Commercial radar ---
    timing_signals_list = timing_data.get("signals", []) if latest_run else []
    commercial_radar = build_commercial_radar(
        buyer_cards=buyer_cards,
        timing_signals=timing_signals_list,
    ) if latest_run else {"focus": [], "radar_items": [], "radar_summary": {}}

    # --- Outreach queue ---
    outreach_queue = build_outreach_queue_data(latest_run, STATE_DIR) if latest_run else {
        "records": [], "counts": {"total": 0, "hot": 0, "warm": 0, "actionable": 0, "follow_up_due": 0}, "source": "empty"
    }

    # --- Products & clients ---
    product_data = build_product_data(latest_run) if latest_run else {"products": []}
    client_data = build_client_data(latest_run) if latest_run else {"clients": []}

    import datetime as _dt

    return {
        "generatedAt": _dt.datetime.utcnow().isoformat() + "Z",
        "latestRun": {
            "runId": run_id,
            "status": run_status,
            "ingest": ingest_counts,
            "manifest": manifest,
            "opportunities": opportunities,
            "buyerCards": buyer_cards,
            "buyerTiming": timing_data,
            "buyerTimingBacktest": timing_backtest,
            "products": product_data.get("products", []),
            "clients": client_data.get("clients", []),
        },
        "buyerCards": buyer_cards,
        "buyerCardCount": len(buyer_cards),
        "buyerTiming": timing_data,
        "buyerTimingBacktest": timing_backtest,
        "commercialRadar": commercial_radar,
        "outreachQueue": outreach_queue,
        "runHistory": run_history,
    }


def main() -> None:
    """Rebuild dashboard_data.js from the latest run artifacts."""
    bundle = build_bundle()

    js_content = f"window.DASHBOARD_DATA = {json.dumps(bundle, ensure_ascii=False, default=str)};\n"
    OUTPUT_FILE.write_text(js_content, encoding="utf-8")

    latest_run_data = bundle.get("latestRun", {})
    run_id = latest_run_data.get("runId", "")
    run_status = latest_run_data.get("status", "")
    opportunities = latest_run_data.get("opportunities", [])
    buyer_cards = bundle.get("buyerCards", [])
    timing_data = bundle.get("buyerTiming", {})

    print(f"[dashboard] Bundle written -> {OUTPUT_FILE}")
    print(f"  Run: {run_id} | Status: {run_status}")
    print(f"  Tenders: {len(opportunities)} | Buyer cards: {len(buyer_cards)}")
    print(f"  Products: {len(latest_run_data.get('products', []))} | Clients: {len(latest_run_data.get('clients', []))}")

    if buyer_cards:
        s = buyer_cards[0]
        print(
            f"  Sample card: {s.get('name', '?')!r} | "
            f"next_action={s.get('next_action', '?')!r} | "
            f"outreach={s.get('outreach_status', '?')!r} | "
            f"dossier_exists={s.get('dossier_exists', False)}"
        )

    timing_signals = timing_data.get("signals", [])
    actionable = sum(1 for s in timing_signals if s.get("timing_label") == "Actionable")
    radar_focus = bundle.get("commercialRadar", {}).get("focus", [])
    print(f"  Timing signals: {len(timing_signals)} | Actionable: {actionable}")
    print(f"  Radar focus items: {len(radar_focus)}")


if __name__ == "__main__":
    main()
