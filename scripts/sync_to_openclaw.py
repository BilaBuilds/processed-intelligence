"""
scripts/sync_to_openclaw.py
===========================
Deterministic artifact-to-memory sync for the OpenClaw sidecar.

Reads ProcessEd pipeline outputs and writes markdown memory files into
openclaw_workspace/.  Never calls an LLM.  Never modifies pipeline state.
Always includes source artifact and run_id.  Weak or missing data is stated
explicitly — nothing is silently dropped or fabricated.

Usage:
    python scripts/sync_to_openclaw.py                  # latest run
    python scripts/sync_to_openclaw.py --run 2026-04-18_120002
    python scripts/sync_to_openclaw.py --all            # sync all runs
    python scripts/sync_to_openclaw.py --buyers-only    # skip run summary
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("sync_to_openclaw")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
RUNS_DIR = BASE_DIR / "data" / "runs"
STATE_DIR = BASE_DIR / "state"
WORKSPACE = BASE_DIR / "openclaw_workspace"

BUYERS_DIR = WORKSPACE / "buyers"
RUNS_OUT_DIR = WORKSPACE / "runs"
DASHBOARDS_DIR = WORKSPACE / "dashboards"
MEMORY_DIR = WORKSPACE / "memory"
MEMORY_INDEX = WORKSPACE / "MEMORY.md"

# Operator-editable section tag — sync never rewrites content below this marker
OPERATOR_SECTION_TAG = "## Memory Notes"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _slug(name: str) -> str:
    """Convert buyer name to a safe filename slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not read %s: %s", path, exc)
        return None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    except Exception as exc:
        log.warning("Could not read %s: %s", path, exc)
    return records


RECENT_CHANGES_TAG = "## Recent Changes"

def _preserve_operator_notes(existing_path: Path) -> str:
    """Return the operator-editable tail of an existing dossier, or empty string.
    Captures from ## Memory Notes to end-of-file."""
    if not existing_path.exists():
        return ""
    text = existing_path.read_text(encoding="utf-8")
    idx = text.find(OPERATOR_SECTION_TAG)
    if idx == -1:
        return ""
    return "\n" + text[idx:]


def _read_outreach_status(existing_path: Path) -> str:
    """Read the current outreach_status line from an existing dossier.
    Returns the status string, defaulting to 'not_started'."""
    if not existing_path.exists():
        return "not_started"
    for line in existing_path.read_text(encoding="utf-8").splitlines():
        if "**Outreach status:**" in line:
            # "- **Outreach status:** drafted"
            raw = line.split("**Outreach status:**", 1)
            if len(raw) == 2:
                return raw[1].strip().strip("*").strip()
    return "not_started"


def _read_recent_changes(existing_path: Path) -> list[str]:
    """Return existing ## Recent Changes lines (excluding the header) from a dossier.
    Strips any malformed entries that contain raw markdown bold markers."""
    if not existing_path.exists():
        return []
    text = existing_path.read_text(encoding="utf-8")
    start = text.find(RECENT_CHANGES_TAG)
    if start == -1:
        return []
    # Find the next ## section after Recent Changes
    section_body = text[start + len(RECENT_CHANGES_TAG):]
    end = section_body.find("\n##")
    if end != -1:
        section_body = section_body[:end]
    lines = [
        l for l in section_body.splitlines()
        if l.strip()
        and not l.strip().startswith("_No changes")
        and "**" not in l        # drop any lines with raw bold markers (parse artefacts)
    ]
    return lines


def _val(v, unit: str = "", missing: str = "not available") -> str:
    if v is None or v == "" or v == [] or v == {}:
        return missing
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return f"{v}{unit}"


def _currency(v) -> str:
    if v is None:
        return "not available"
    try:
        f = float(v)
        if f >= 1_000_000:
            return f"£{f/1_000_000:.1f}m"
        if f >= 1_000:
            return f"£{int(f/1000)}k"
        return f"£{int(f)}"
    except (TypeError, ValueError):
        return str(v)


def _confidence_note(confidence: str | None) -> str:
    mapping = {
        "High": "Strong — 3+ evenly-spaced repeat notices, low variance.",
        "Medium": "Moderate — some pattern visible, some uncertainty.",
        "Weak": "Low — sparse data, timing estimates are indicative only.",
        "None": "No usable pattern — buyer appears infrequently or irregularly.",
        None: "Unknown — timing data not available.",
    }
    return mapping.get(confidence, f"Unknown value: {confidence}")


def _label_badge(label: str | None) -> str:
    if label == "Actionable":
        return "🟢 Actionable"
    if label == "Watch":
        return "🟡 Watch"
    if label == "Tracking":
        return "⬜ Tracking"
    return "⬜ No label"


def _find_latest_run() -> Path | None:
    if not RUNS_DIR.exists():
        return None
    runs = sorted(
        [d for d in RUNS_DIR.iterdir() if d.is_dir() and (d / "run_manifest.json").exists()],
        key=lambda d: d.name,
    )
    return runs[-1] if runs else None


def _find_run(run_id: str) -> Path | None:
    p = RUNS_DIR / run_id
    return p if p.exists() else None


def _all_runs() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted(
        [d for d in RUNS_DIR.iterdir() if d.is_dir() and (d / "run_manifest.json").exists()],
        key=lambda d: d.name,
    )


# ---------------------------------------------------------------------------
# Phase B — Run summary note
# ---------------------------------------------------------------------------

def write_run_summary(run_dir: Path) -> Path:
    """Write openclaw_workspace/runs/{run_id}.md from the run manifest."""
    run_id = run_dir.name
    manifest = _read_json(run_dir / "run_manifest.json")
    if manifest is None:
        log.warning("No manifest found in %s — skipping run summary", run_dir)
        return None

    status = manifest.get("status", "unknown")
    run_mode = manifest.get("run_mode", "unknown")
    started = manifest.get("started_at", "unknown")
    duration = manifest.get("total_duration_s", "?")
    shortlist_count = manifest.get("shortlist_count", 0)
    new_count = manifest.get("new_count", 0)
    ingest_total = manifest.get("ingest_total_count", 0)
    norm_kept = manifest.get("normalized_kept_count", 0)
    forecast_count = manifest.get("forecast_count", 0)
    timing_count = manifest.get("buyer_timing_count", 0)
    timing_due_soon = manifest.get("buyer_timing_due_soon", 0)
    timing_overdue = manifest.get("buyer_timing_overdue", 0)
    timing_slipped = manifest.get("buyer_timing_slipped", 0)
    timing_actionable = manifest.get("timing_actionable_count", 0)
    timing_visible = manifest.get("timing_visible_count", 0)
    buyer_intel_count = manifest.get("buyer_intel_unique_buyers", 0)
    cf_tags = manifest.get("cf_release_tag_counts", {})
    rejection_reasons = manifest.get("rejection_reason_counts", {})

    # Step health summary
    steps = manifest.get("steps", {})
    failed_steps = [k for k, v in steps.items() if v.get("status") in ("error", "failed")]
    step_health = "All steps OK" if not failed_steps else f"Non-fatal errors: {', '.join(failed_steps)}"

    # Verdict
    if status == "success_empty":
        verdict = "✅ Success — no new tenders this run (all previously seen or below threshold)"
    elif status == "success":
        verdict = f"✅ Success — {new_count} new tender(s) notified, {shortlist_count} shortlisted"
    elif status == "success_with_warnings":
        verdict = f"⚠️ Success with warnings — {new_count} new tender(s), some steps had errors"
    elif status == "cooldown_skip":
        verdict = "⏸ Cooldown skip — FTS fetch window not yet elapsed"
    elif status == "failed":
        verdict = "❌ Pipeline failed"
    else:
        verdict = f"Unknown status: {status}"

    lines = [
        f"# Run Summary — {run_id}",
        "",
        f"**Status:** {verdict}",
        f"**Run mode:** {run_mode}",
        f"**Started:** {started}",
        f"**Duration:** {duration}s",
        f"**Step health:** {step_health}",
        "",
        "## Ingest",
        "",
        f"- Total ingested: {ingest_total} records",
        f"- Kept after normalisation: {norm_kept}",
    ]
    if cf_tags:
        lines.append(f"- CF release tags: " + ", ".join(f"{k}={v}" for k, v in sorted(cf_tags.items(), key=lambda x: -x[1])))

    lines += [
        "",
        "## Selection",
        "",
        f"- Shortlisted: {shortlist_count}",
        f"- New (post-dedupe): {new_count}",
    ]
    if rejection_reasons:
        lines.append("- Rejection reasons: " + ", ".join(f"{k}={v}" for k, v in sorted(rejection_reasons.items(), key=lambda x: -x[1])))

    # Load timing signals for recommendation
    timing_signals = _read_json(run_dir / "buyer_timing_signals.json") or {}
    if isinstance(timing_signals, list):
        all_signals = timing_signals
    else:
        all_signals = timing_signals.get("signals", [])

    conf_counts = {"High": 0, "Medium": 0, "Weak": 0, "None": 0}
    for s in all_signals:
        c = s.get("timing_confidence") or "None"
        conf_counts[c] = conf_counts.get(c, 0) + 1

    fts_count = manifest.get("ingest_counts_by_source", {}).get("find_a_tender", 0)
    cf_count = manifest.get("ingest_counts_by_source", {}).get("contracts_finder", 0)

    # Top 3 recommendation: Actionable first, then Watch with highest fit, then tracking with fit
    LABEL_RANK  = {"Actionable": 0, "Watch": 1, "Tracking": 2}
    CONF_RANK   = {"High": 0, "Medium": 1, "Weak": 2, "None": 3}
    def _rec_key(s: dict) -> tuple:
        return (
            LABEL_RANK.get(s.get("timing_label") or "Tracking", 2),
            CONF_RANK.get(s.get("timing_confidence") or "None", 3),
            -(s.get("fit_to_client") or 0),
        )
    top3 = sorted(all_signals, key=_rec_key)[:3]

    lines += [
        "",
        "## Buyer intelligence",
        "",
        f"- Unique buyers tracked: {buyer_intel_count}",
        f"- Forecasted buyers: {forecast_count}",
        f"- Timing signals computed: {timing_count}",
        f"  - Timing visible (full/limited): {timing_visible}",
        f"  - Actionable label: {timing_actionable}",
        f"  - Due soon: {timing_due_soon}",
        f"  - Overdue: {timing_overdue}",
        f"  - Slipped: {timing_slipped}",
        "",
        "## Signal quality",
        "",
        f"- 🟢 High confidence:   {conf_counts.get('High', 0)} buyer(s)",
        f"- 🟡 Medium confidence: {conf_counts.get('Medium', 0)} buyer(s)",
        f"- 🔶 Weak confidence:   {conf_counts.get('Weak', 0)} buyer(s)",
        f"- ⬜ No pattern:        {conf_counts.get('None', 0)} buyer(s)",
        f"- FTS contribution: {fts_count} records  |  CF contribution: {cf_count} records",
        "",
        "## Recommendation",
        "",
    ]

    if top3:
        lines.append("Focus outreach on:")
        for s in top3:
            name   = s.get("buyer_name", "?")
            label  = s.get("timing_label") or "Tracking"
            conf   = s.get("timing_confidence") or "None"
            fit    = s.get("fit_to_client")
            fit_str = f", fit={fit}%" if fit is not None else ""
            status  = s.get("timing_status", "?")
            lines.append(f"- **{name}** — {label} / {conf}{fit_str} / {status}")
    else:
        lines.append("_No buyers with usable timing signals this run._")

    if timing_actionable == 0 and conf_counts.get("High", 0) == 0:
        lines += [
            "",
            "_No Actionable or High-confidence buyers this run. Pipeline is healthy but signal quality is low._",
            "_Consider: more historical data will sharpen buyer timing confidence over time._",
        ]

    lines += [
        "",
        f"_Source: `{run_dir / 'run_manifest.json'}`_",
        f"_Synced: {_now_iso()}_",
    ]

    out = RUNS_OUT_DIR / f"{run_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("  Run summary → %s", out.relative_to(BASE_DIR))
    return out


# ---------------------------------------------------------------------------
# Phase B — Timing watchlist summary
# ---------------------------------------------------------------------------

def write_timing_watchlist(run_dir: Path) -> Path | None:
    """Write openclaw_workspace/dashboards/timing_watchlist.md from timing signals."""
    run_id = run_dir.name
    timing_file = run_dir / "buyer_timing_signals.json"
    timing_data = _read_json(timing_file)
    if timing_data is None:
        log.info("  No timing signals file — skipping timing watchlist")
        return None

    signals = timing_data if isinstance(timing_data, list) else timing_data.get("signals", [])
    if not signals:
        log.info("  Timing signals empty — skipping timing watchlist")
        return None

    # Sort: Actionable first, then Watch, then by due rank
    label_order = {"Actionable": 0, "Watch": 1, "Tracking": 2, None: 3}
    sorted_sigs = sorted(
        signals,
        key=lambda s: (
            label_order.get(s.get("timing_label"), 3),
            s.get("buyer_due_rank") or 9999,
        ),
    )

    lines = [
        f"# Timing Watchlist",
        f"",
        f"_From run `{run_id}` — {len(signals)} buyers tracked_",
        f"_Synced: {_now_iso()}_",
        "",
        "## Actionable now",
        "",
    ]

    actionable = [s for s in sorted_sigs if s.get("timing_label") == "Actionable"]
    if actionable:
        for s in actionable:
            lines += _timing_row(s)
    else:
        lines.append("_No buyers with Actionable label this run._")

    lines += ["", "## Watch — monitor closely", ""]
    watch = [s for s in sorted_sigs if s.get("timing_label") == "Watch"]
    if watch:
        for s in watch[:20]:
            lines += _timing_row(s)
        if len(watch) > 20:
            lines.append(f"_…and {len(watch) - 20} more Watch buyers — see full timing signals file_")
    else:
        lines.append("_No Watch-label buyers this run._")

    lines += ["", "## Tracking — background monitoring", ""]
    tracking = [s for s in sorted_sigs if s.get("timing_label") not in ("Actionable", "Watch")]
    lines.append(f"_{len(tracking)} buyers in background tracking — not listed here to keep this readable_")

    out = DASHBOARDS_DIR / "timing_watchlist.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("  Timing watchlist → %s", out.relative_to(BASE_DIR))
    return out


def _timing_row(s: dict) -> list[str]:
    name = s.get("buyer_name", "Unknown")
    label = _label_badge(s.get("timing_label"))
    conf = s.get("timing_confidence", "None")
    status = s.get("timing_status", "unknown")
    predicted = s.get("predicted_next_central") or s.get("predicted_next_start") or "unknown"
    window_start = s.get("predicted_next_start", "?")
    window_end = s.get("predicted_next_end", "?")
    fit = s.get("fit_to_client")
    fit_str = f"{fit}%" if fit is not None else "not scored"
    action = s.get("action_note") or s.get("timing_reason") or ""
    mktg = s.get("timing_marketing_text", "")

    return [
        f"### {name}",
        f"- **Label:** {label}  **Confidence:** {conf}  **Status:** {status}",
        f"- **Predicted window:** {window_start} → {window_end}  (central: {predicted})",
        f"- **Fit to client:** {fit_str}",
        f"- **Note:** {action}" if action else "",
        f"- _Signal:_ {mktg}" if mktg else "",
        "",
    ]


# ---------------------------------------------------------------------------
# Phase C — Buyer dossiers
# ---------------------------------------------------------------------------

def write_buyer_dossiers(run_dir: Path) -> int:
    """Write/update one markdown dossier per buyer from timing signals + state files."""
    run_id = run_dir.name

    # Load all source artifacts
    timing_file = run_dir / "buyer_timing_signals.json"
    timing_data = _read_json(timing_file)
    signals_by_key: dict[str, dict] = {}
    if timing_data:
        signals = timing_data if isinstance(timing_data, list) else timing_data.get("signals", [])
        for s in signals:
            key = s.get("buyer_key") or _slug(s.get("buyer_name", ""))
            if key:
                signals_by_key[key] = s

    profiles: dict[str, dict] = {}
    raw_profiles = _read_json(STATE_DIR / "buyer_profiles.json") or {}
    for k, v in raw_profiles.items():
        profiles[_slug(k)] = v

    briefs: dict[str, dict] = {}
    raw_briefs = _read_json(STATE_DIR / "buyer_briefs.json") or {}
    for k, v in raw_briefs.items():
        briefs[_slug(k)] = v

    # Load shortlist for latest notice per buyer
    shortlist_notices: dict[str, list[dict]] = {}
    shortlist_data = _read_json(run_dir / "decision_shortlist.json") or {}
    for opp in shortlist_data.get("opportunities", []):
        key = _slug(opp.get("buyer_name", ""))
        shortlist_notices.setdefault(key, []).append(opp)

    # Load buyer history for activity counts
    history_by_buyer: dict[str, list[dict]] = {}
    for record in _read_jsonl(STATE_DIR / "buyer_history.jsonl"):
        key = _slug(record.get("buyer_name", ""))
        if key:
            history_by_buyer.setdefault(key, []).append(record)

    # All known buyer keys across all sources
    all_keys = set(signals_by_key) | set(profiles) | set(briefs)
    if not all_keys:
        log.warning("  No buyer data found — no dossiers written")
        return 0

    written = 0
    BUYERS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove any legacy files whose names contain spaces or special chars
    # (produced before the slug-on-write fix).  Safe to do because slugged
    # versions are always written in the same pass.
    for stale in BUYERS_DIR.iterdir():
        if stale.suffix == ".md" and stale.name != _slug(stale.stem) + ".md":
            try:
                stale.unlink()
            except OSError:
                pass  # Windows: file will be overwritten next write cycle

    for key in sorted(all_keys):
        sig = signals_by_key.get(key, {})
        profile = profiles.get(key, {})
        brief = briefs.get(key, {})
        history = history_by_buyer.get(key, [])
        notices = shortlist_notices.get(key, [])

        # Resolve buyer name — prefer timing signal (most recently computed)
        buyer_name = (
            sig.get("buyer_name")
            or profile.get("full_name")
            or brief.get("buyer_name")
            or key.replace("_", " ").title()
        )

        safe_key = _slug(key)
        dossier_path = BUYERS_DIR / f"{safe_key}.md"
        operator_notes = _preserve_operator_notes(dossier_path)
        outreach_status = _read_outreach_status(dossier_path)
        existing_changes = _read_recent_changes(dossier_path)

        # Latest notice from shortlist; fall back to sig last_seen
        latest_title = "not available"
        latest_date = "not available"
        if notices:
            n = notices[0]
            latest_title = n.get("title", "not available")
            latest_date = n.get("deadline_at") or n.get("seen_at") or "not available"
        elif sig.get("last_seen_date"):
            latest_date = sig["last_seen_date"]
            latest_title = "(not in this run's shortlist)"

        # Activity counts from history
        today = date.today()
        activity_30d = sum(
            1 for r in history
            if _days_ago(r.get("seen_at") or r.get("deadline_at")) is not None
            and _days_ago(r.get("seen_at") or r.get("deadline_at")) <= 30
        )
        activity_90d = sum(
            1 for r in history
            if _days_ago(r.get("seen_at") or r.get("deadline_at")) is not None
            and _days_ago(r.get("seen_at") or r.get("deadline_at")) <= 90
        )
        total_notices = sig.get("total_notices") or len(history) or 0

        # Value
        avg_value_pipeline = sig.get("buyer_avg_value")
        avg_value_profile = profile.get("avg_value")
        avg_value = avg_value_pipeline or avg_value_profile

        # Categories
        top_categories = sig.get("top_categories") or brief.get("top_categories") or []
        if isinstance(top_categories, str):
            top_categories = [top_categories]

        # Fit
        fit_to_client = sig.get("fit_to_client")

        # Timing
        timing_status = sig.get("timing_status") or "unknown"
        timing_confidence = sig.get("timing_confidence") or "None"
        timing_label = sig.get("timing_label") or "Tracking"
        timing_visibility = sig.get("timing_visibility") or "hidden"
        predicted_next_start = sig.get("predicted_next_start") or "not available"
        predicted_next_end = sig.get("predicted_next_end") or "not available"
        predicted_central = sig.get("predicted_next_central") or "not available"
        action_note = sig.get("action_note") or "No specific action note."
        timing_reason = sig.get("timing_reason") or ""
        mktg_text = sig.get("timing_marketing_text") or ""

        # Outreach priority: Actionable > Watch > Tracking
        if timing_label == "Actionable" and timing_confidence in ("High", "Medium"):
            outreach_priority = "HIGH — contact this week"
        elif timing_label == "Watch":
            outreach_priority = "MEDIUM — monitor, prepare contact list"
        else:
            outreach_priority = "LOW — background tracking"

        # Brief summary
        brief_text = brief.get("brief") or brief.get("buyer_intel_summary") or "not available"
        buyer_pattern = brief.get("buyer_pattern") or "not available"
        category_bias = brief.get("buyer_category_bias") or "not available"

        # Profile notes
        freq = profile.get("frequency") or "not available"
        style = profile.get("style") or "not available"
        contact_pattern = profile.get("contact_pattern") or "not available"

        # --- Recent Changes: detect transitions vs previous dossier ---
        today_str = date.today().isoformat()
        new_change_lines = []
        for line in existing_changes:
            # Carry forward existing change lines
            new_change_lines.append(line)

        # Read the previous values directly from the existing dossier (before overwrite)
        prev_label = prev_conf = prev_status = None
        if dossier_path.exists():
            for line in dossier_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("- **Timing label:**"):
                    # e.g. "- **Timing label:** 🟢 Actionable"
                    # The badge includes an emoji; scan for the word
                    raw_lbl = line.split("**Timing label:**", 1)[1].strip() if "**Timing label:**" in line else ""
                    for lbl in ("Actionable", "Watch", "Tracking"):
                        if lbl in raw_lbl:
                            prev_label = lbl
                            break
                elif line.startswith("- **Confidence:**"):
                    for conf in ("High", "Medium", "Weak", "None"):
                        if conf in line:
                            prev_conf = conf
                            break
                elif "**Status:**" in line and not line.startswith("- **Outreach"):
                    # "- **Status:** overdue"  →  "overdue"
                    raw = line.split("**Status:**", 1)
                    prev_status = raw[1].strip().strip("*").strip() if len(raw) == 2 else None

        transition_parts = []
        if prev_label and prev_label != timing_label:
            transition_parts.append(f"label {prev_label}→{timing_label}")
        if prev_conf and prev_conf != timing_confidence:
            transition_parts.append(f"confidence {prev_conf}→{timing_confidence}")
        if prev_status and prev_status != timing_status and prev_status != "unknown":
            transition_parts.append(f"status {prev_status}→{timing_status}")

        if transition_parts:
            change_entry = f"- {today_str} ({run_id}): " + ", ".join(transition_parts)
            # Avoid duplicate entries for the same run
            if not any(run_id in line for line in new_change_lines):
                new_change_lines.append(change_entry)

        lines = [
            f"# Buyer Dossier — {buyer_name}",
            f"",
            f"_Source run: `{run_id}`  |  Synced: {_now_iso()}_",
            f"",
            "## Identity",
            f"",
            f"- **Buyer name:** {buyer_name}",
            f"- **Buyer key:** `{key}`",
            f"- **Region:** {_val(sig.get('top_regions', [None])[0] if sig.get('top_regions') else None)}",
            f"",
            "## Latest activity",
            f"",
            f"- **Latest notice title:** {latest_title}",
            f"- **Latest notice date:** {latest_date}",
            f"- **Activity (30d):** {activity_30d} notice(s)",
            f"- **Activity (90d):** {activity_90d} notice(s)",
            f"- **Total notices seen:** {total_notices}",
            f"- **Typical value:** {_currency(avg_value)}",
            f"- **Top categories:** {', '.join(top_categories) if top_categories else 'not available'}",
            f"",
            "## Timing intelligence",
            f"",
            f"- **Timing label:** {_label_badge(timing_label)}",
            f"- **Confidence:** {timing_confidence} — {_confidence_note(timing_confidence)}",
            f"- **Status:** {timing_status}",
            f"- **Visibility:** {timing_visibility}",
            f"- **Predicted window:** {predicted_next_start} → {predicted_next_end}",
            f"- **Predicted central:** {predicted_central}",
            f"- **Fit to client:** {_val(fit_to_client, '%')}",
            f"- **Action note:** {action_note}",
        ]
        if timing_reason:
            lines.append(f"- **Timing reason:** {timing_reason}")
        if mktg_text:
            lines.append(f"- **Signal text:** {mktg_text}")

        lines += [
            f"",
            "## Commercial intelligence",
            f"",
            f"- **Outreach priority:** {outreach_priority}",
            f"- **Outreach status:** {outreach_status}",
            f"- **Buyer brief:** {brief_text}",
            f"- **Buyer pattern:** {buyer_pattern}",
            f"- **Category bias:** {category_bias}",
            f"",
            "## Operator profile",
            f"",
            f"- **Procurement frequency:** {freq}",
            f"- **Style:** {style}",
            f"- **Contact pattern:** {contact_pattern}",
            f"",
            f"_Artifact: `{timing_file}`_",
            f"",
            RECENT_CHANGES_TAG,
            f"",
        ]
        if new_change_lines:
            lines += new_change_lines
        else:
            lines.append("_No changes recorded yet — transitions between runs will appear here._")

        # Append preserved operator notes (or fresh section)
        if operator_notes:
            lines.append(operator_notes)
        else:
            lines += [
                f"",
                OPERATOR_SECTION_TAG,
                f"",
                f"_Add free-text notes here. This section is never overwritten by the sync script._",
            ]

        dossier_path.write_text("\n".join(lines), encoding="utf-8")
        written += 1

    log.info("  Buyer dossiers → %s (%d files)", BUYERS_DIR.relative_to(BASE_DIR), written)
    return written


def _days_ago(value: str | None) -> int | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - d.astimezone(timezone.utc)
        return delta.days
    except (ValueError, TypeError):
        try:
            d2 = date.fromisoformat(value[:10])
            return (date.today() - d2).days
        except (ValueError, TypeError):
            return None


# ---------------------------------------------------------------------------
# MEMORY.md index update
# ---------------------------------------------------------------------------

def update_memory_index(run_id: str, buyer_count: int) -> None:
    """Refresh the last-sync line in MEMORY.md."""
    if not MEMORY_INDEX.exists():
        return
    text = MEMORY_INDEX.read_text(encoding="utf-8")
    updated = re.sub(
        r"_Last sync:.*_",
        f"_Last sync: `{run_id}` — {buyer_count} buyer dossiers — {_now_iso()}_",
        text,
    )
    MEMORY_INDEX.write_text(updated, encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def sync_run(run_dir: Path, buyers_only: bool = False) -> dict:
    run_id = run_dir.name
    log.info("Syncing run %s", run_id)
    result = {"run_id": run_id, "buyers": 0, "run_summary": None, "timing_watchlist": None}

    if not buyers_only:
        result["run_summary"] = str(write_run_summary(run_dir) or "")
        result["timing_watchlist"] = str(write_timing_watchlist(run_dir) or "")

    result["buyers"] = write_buyer_dossiers(run_dir)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync ProcessEd artifacts to OpenClaw workspace")
    parser.add_argument("--run", help="Specific run ID to sync (default: latest)")
    parser.add_argument("--all", action="store_true", help="Sync all runs")
    parser.add_argument("--buyers-only", action="store_true", help="Skip run summary and timing watchlist")
    args = parser.parse_args()

    for d in [BUYERS_DIR, RUNS_OUT_DIR, DASHBOARDS_DIR, MEMORY_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    if args.all:
        runs = _all_runs()
        if not runs:
            log.error("No runs found in %s", RUNS_DIR)
            sys.exit(1)
        log.info("Syncing %d run(s)", len(runs))
        total_buyers = 0
        for run_dir in runs:
            r = sync_run(run_dir, buyers_only=args.buyers_only)
            total_buyers = r["buyers"]  # last run wins for buyer dossiers
        update_memory_index(runs[-1].name, total_buyers)
        log.info("Done — %d buyer dossiers written", total_buyers)
    else:
        if args.run:
            run_dir = _find_run(args.run)
            if run_dir is None:
                log.error("Run %s not found in %s", args.run, RUNS_DIR)
                sys.exit(1)
        else:
            run_dir = _find_latest_run()
            if run_dir is None:
                log.error("No runs found in %s", RUNS_DIR)
                sys.exit(1)

        r = sync_run(run_dir, buyers_only=args.buyers_only)
        update_memory_index(r["run_id"], r["buyers"])
        log.info(
            "Done — run %s synced. Buyers: %d, run summary: %s, timing watchlist: %s",
            r["run_id"],
            r["buyers"],
            "written" if r["run_summary"] else "skipped",
            "written" if r["timing_watchlist"] else "skipped",
        )


if __name__ == "__main__":
    main()
