"""
scripts/query_openclaw.py
=========================
Operator query helper for the OpenClaw memory workspace.

Reads deterministic pipeline artifacts (not markdown files) for accuracy,
then formats answers as readable plain text for operator or Claude consumption.
All output is deterministic.  No LLM calls.  No side effects.

Usage:
    python scripts/query_openclaw.py --due-soon
    python scripts/query_openclaw.py --contact-list
    python scripts/query_openclaw.py --changed-since 2026-04-17_120000
    python scripts/query_openclaw.py --signals
    python scripts/query_openclaw.py --sector construction
    python scripts/query_openclaw.py --sector social_housing
    python scripts/query_openclaw.py --strongest
    python scripts/query_openclaw.py --buyer "Croydon Council"
    python scripts/query_openclaw.py --summary
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
RUNS_DIR = BASE_DIR / "data" / "runs"
STATE_DIR = BASE_DIR / "state"

# -------------------------------------------------------------------
# Shared loaders
# -------------------------------------------------------------------

def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _slug(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


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
    return p if (p / "run_manifest.json").exists() else None


def _all_runs_sorted() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted(
        [d for d in RUNS_DIR.iterdir() if d.is_dir() and (d / "run_manifest.json").exists()],
        key=lambda d: d.name,
    )


def _load_timing_signals(run_dir: Path) -> list[dict]:
    timing_data = _read_json(run_dir / "buyer_timing_signals.json")
    if not timing_data:
        return []
    return timing_data if isinstance(timing_data, list) else timing_data.get("signals", [])


def _days_ago(value: str | None) -> int | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - d.astimezone(timezone.utc)).days
    except (ValueError, TypeError):
        try:
            return (date.today() - date.fromisoformat(value[:10])).days
        except (ValueError, TypeError):
            return None


def _currency(v) -> str:
    if v is None:
        return "n/a"
    try:
        f = float(v)
        if f >= 1_000_000:
            return f"£{f/1_000_000:.1f}m"
        if f >= 1_000:
            return f"£{int(f/1000)}k"
        return f"£{int(f)}"
    except (TypeError, ValueError):
        return str(v)


def _label_icon(label: str | None) -> str:
    return {"Actionable": "🟢", "Watch": "🟡", "Tracking": "⬜"}.get(label or "", "⬜")


def _hr() -> str:
    return "─" * 60


# -------------------------------------------------------------------
# Query implementations
# -------------------------------------------------------------------

def query_due_soon(run_dir: Path) -> str:
    """Buyers with timing windows open now or within 30 days."""
    signals = _load_timing_signals(run_dir)
    run_id = run_dir.name

    due = [
        s for s in signals
        if s.get("timing_status") in ("due_soon", "due", "overdue")
        and s.get("timing_confidence") in ("High", "Medium", "Weak")
    ]
    due.sort(key=lambda s: (
        {"High": 0, "Medium": 1, "Weak": 2}.get(s.get("timing_confidence"), 3),
        s.get("buyer_due_rank") or 9999,
    ))

    lines = [
        _hr(),
        f"DUE-SOON BUYERS  |  run: {run_id}",
        _hr(),
    ]
    if not due:
        lines.append("No buyers with open or imminent timing windows this run.")
        lines.append("(Check --signals for background tracking list.)")
        return "\n".join(lines)

    for s in due:
        name = s.get("buyer_name", "Unknown")
        conf = s.get("timing_confidence", "?")
        status = s.get("timing_status", "?")
        label = s.get("timing_label", "Tracking")
        central = s.get("predicted_next_central") or s.get("predicted_next_start") or "?"
        window = f"{s.get('predicted_next_start','?')} → {s.get('predicted_next_end','?')}"
        fit = s.get("fit_to_client")
        fit_str = f"{fit}%" if fit is not None else "not scored"
        action = s.get("action_note") or ""
        lines += [
            f"",
            f"  {_label_icon(label)} {name}",
            f"     Confidence: {conf}  |  Status: {status}  |  Label: {label}",
            f"     Window: {window}  (central: {central})",
            f"     Fit to client: {fit_str}",
        ]
        if action:
            lines.append(f"     Action: {action}")

    lines += ["", f"Total: {len(due)} buyer(s) in open/imminent window"]
    return "\n".join(lines)


def query_contact_list(run_dir: Path) -> str:
    """Ranked contact list for this week — Actionable first, then Watch with fit."""
    signals = _load_timing_signals(run_dir)
    run_id = run_dir.name

    profiles = {}
    raw_profiles = _read_json(STATE_DIR / "buyer_profiles.json") or {}
    for k, v in raw_profiles.items():
        profiles[_slug(k)] = v

    actionable = sorted(
        [s for s in signals if s.get("timing_label") == "Actionable"],
        key=lambda s: (
            {"High": 0, "Medium": 1, "Weak": 2}.get(s.get("timing_confidence"), 3),
            -(s.get("fit_to_client") or 0),
        ),
    )
    watch_fit = sorted(
        [s for s in signals if s.get("timing_label") == "Watch"
         and (s.get("fit_to_client") or 0) >= 30],
        key=lambda s: -(s.get("fit_to_client") or 0),
    )

    lines = [
        _hr(),
        f"CONTACT LIST THIS WEEK  |  run: {run_id}",
        _hr(),
    ]

    if not actionable and not watch_fit:
        lines.append("No Actionable buyers and no Watch buyers with fit ≥ 30% this run.")
        lines.append("Consider reviewing --signals for timing-visible accounts.")
        return "\n".join(lines)

    if actionable:
        lines += ["", "── ACTIONABLE — contact now ──────────────────────────", ""]
        for i, s in enumerate(actionable, 1):
            key = s.get("buyer_key") or _slug(s.get("buyer_name", ""))
            profile = profiles.get(key, {})
            contact = profile.get("contact_pattern") or "see buyer dossier"
            lines += [
                f"  {i}. {s.get('buyer_name')}",
                f"     Confidence: {s.get('timing_confidence')}  |  Fit: {s.get('fit_to_client','n/a')}%",
                f"     Window: {s.get('predicted_next_start','?')} → {s.get('predicted_next_end','?')}",
                f"     Contact via: {contact}",
                f"     {s.get('action_note','')}",
                "",
            ]

    if watch_fit:
        lines += ["── WATCH (fit ≥ 30%) — prepare, monitor ──────────────", ""]
        for i, s in enumerate(watch_fit, 1):
            key = s.get("buyer_key") or _slug(s.get("buyer_name", ""))
            profile = profiles.get(key, {})
            contact = profile.get("contact_pattern") or "see buyer dossier"
            lines += [
                f"  {i}. {s.get('buyer_name')}",
                f"     Confidence: {s.get('timing_confidence')}  |  Fit: {s.get('fit_to_client','n/a')}%",
                f"     Window: {s.get('predicted_next_start','?')} → {s.get('predicted_next_end','?')}",
                f"     Contact via: {contact}",
                "",
            ]

    lines.append(f"Total: {len(actionable)} actionable, {len(watch_fit)} watch-with-fit")
    return "\n".join(lines)


def query_changed_since(since_run_id: str, current_run_dir: Path) -> str:
    """What changed in timing signals between a prior run and the latest run."""
    prior_dir = _find_run(since_run_id)
    if not prior_dir:
        return f"ERROR: Run '{since_run_id}' not found in {RUNS_DIR}"

    current_sigs = {s["buyer_key"]: s for s in _load_timing_signals(current_run_dir)
                    if s.get("buyer_key")}
    prior_sigs = {s["buyer_key"]: s for s in _load_timing_signals(prior_dir)
                  if s.get("buyer_key")}

    # New buyers not in prior run
    new_keys = set(current_sigs) - set(prior_sigs)
    # Buyers whose label or confidence changed
    changed = []
    for key in set(current_sigs) & set(prior_sigs):
        c = current_sigs[key]
        p = prior_sigs[key]
        label_changed = c.get("timing_label") != p.get("timing_label")
        conf_changed = c.get("timing_confidence") != p.get("timing_confidence")
        status_changed = c.get("timing_status") != p.get("timing_status")
        if label_changed or conf_changed or status_changed:
            changed.append((key, p, c))
    # Buyers that dropped out
    dropped_keys = set(prior_sigs) - set(current_sigs)

    lines = [
        _hr(),
        f"CHANGES SINCE {since_run_id}  →  {current_run_dir.name}",
        _hr(),
    ]

    if new_keys:
        lines += ["", f"NEW BUYERS ({len(new_keys)}):"]
        for key in sorted(new_keys):
            s = current_sigs[key]
            lines.append(f"  + {s.get('buyer_name', key)}  [{s.get('timing_label','?')} / {s.get('timing_confidence','?')}]")

    if changed:
        lines += ["", f"LABEL / CONFIDENCE / STATUS CHANGES ({len(changed)}):"]
        for key, p, c in sorted(changed, key=lambda x: x[0]):
            name = c.get("buyer_name", key)
            p_label = p.get("timing_label", "?")
            c_label = c.get("timing_label", "?")
            p_conf = p.get("timing_confidence", "?")
            c_conf = c.get("timing_confidence", "?")
            p_status = p.get("timing_status", "?")
            c_status = c.get("timing_status", "?")
            parts = []
            if p_label != c_label:
                parts.append(f"label {p_label}→{c_label}")
            if p_conf != c_conf:
                parts.append(f"conf {p_conf}→{c_conf}")
            if p_status != c_status:
                parts.append(f"status {p_status}→{c_status}")
            lines.append(f"  ~ {name}:  {', '.join(parts)}")

    if dropped_keys:
        lines += ["", f"DROPPED OUT ({len(dropped_keys)}):"]
        for key in sorted(dropped_keys):
            name = prior_sigs[key].get("buyer_name", key)
            lines.append(f"  - {name}")

    if not new_keys and not changed and not dropped_keys:
        lines.append("No changes in buyer labels, confidence, or status between these two runs.")

    lines += [
        "",
        f"Summary: {len(new_keys)} new, {len(changed)} changed, {len(dropped_keys)} dropped",
    ]
    return "\n".join(lines)


def query_signals(run_dir: Path) -> str:
    """Full signal quality breakdown — High/Medium/Weak/None."""
    signals = _load_timing_signals(run_dir)
    run_id = run_dir.name

    by_conf: dict[str, list] = {"High": [], "Medium": [], "Weak": [], "None": [], "other": []}
    for s in signals:
        conf = s.get("timing_confidence") or "None"
        by_conf.setdefault(conf, by_conf["other"]).append(s)

    lines = [
        _hr(),
        f"SIGNAL QUALITY BREAKDOWN  |  run: {run_id}  |  {len(signals)} buyers",
        _hr(),
    ]
    for conf in ("High", "Medium", "Weak", "None"):
        group = by_conf.get(conf, [])
        label_counts = {}
        for s in group:
            label_counts[s.get("timing_label", "?")] = label_counts.get(s.get("timing_label", "?"), 0) + 1
        label_str = "  ".join(f"{l}:{n}" for l, n in sorted(label_counts.items()))
        lines.append(f"  {conf:8s}  {len(group):3d} buyers   {label_str}")
        if conf in ("High", "Medium") and group:
            for s in sorted(group, key=lambda s: -(s.get("fit_to_client") or 0))[:5]:
                name = s.get("buyer_name", "?")
                label = s.get("timing_label", "?")
                fit = s.get("fit_to_client")
                fit_str = f"fit={fit}%" if fit is not None else "fit=n/a"
                status = s.get("timing_status", "?")
                lines.append(f"           → {name}  [{label} / {status} / {fit_str}]")

    lines += [
        "",
        "Visibility breakdown:",
        f"  Full (High/Med conf):    {sum(1 for s in signals if s.get('timing_visibility')=='full')}",
        f"  Limited (Weak conf):     {sum(1 for s in signals if s.get('timing_visibility')=='limited')}",
        f"  Hidden (no pattern):     {sum(1 for s in signals if s.get('timing_visibility')=='hidden')}",
    ]
    return "\n".join(lines)


def query_sector(run_dir: Path, sector: str) -> str:
    """Buyers whose top_categories match a sector keyword."""
    signals = _load_timing_signals(run_dir)
    run_id = run_dir.name

    # Sector → CPV prefix mapping (coarse but deterministic)
    SECTOR_CPVS = {
        "construction": ("45", "77310", "77300"),
        "social_housing": ("45210", "45211", "45260", "45320", "45330", "45421"),
        "highways": ("45233", "45221"),
        "facilities": ("79993", "50700", "70330"),
    }
    sector_key = sector.lower().replace(" ", "_").replace("-", "_")
    cpv_prefixes = SECTOR_CPVS.get(sector_key)

    matched = []
    for s in signals:
        cats = s.get("top_categories") or []
        if isinstance(cats, str):
            cats = [cats]
        if cpv_prefixes:
            if any(str(c).startswith(pfx) for c in cats for pfx in cpv_prefixes):
                matched.append(s)
        else:
            # Fallback: text match on buyer name or action note
            text = (s.get("buyer_name") or "").lower()
            if sector_key.replace("_", "") in text.replace(" ", ""):
                matched.append(s)

    matched.sort(key=lambda s: (
        {"High": 0, "Medium": 1, "Weak": 2, "None": 3}.get(s.get("timing_confidence"), 3),
        {"Actionable": 0, "Watch": 1, "Tracking": 2}.get(s.get("timing_label"), 2),
        -(s.get("fit_to_client") or 0),
    ))

    lines = [
        _hr(),
        f"SECTOR: {sector.upper()}  |  run: {run_id}",
        _hr(),
    ]
    if not matched:
        lines.append(f"No buyers with CPV codes matching sector '{sector}' this run.")
        known = ", ".join(SECTOR_CPVS.keys())
        lines.append(f"Known sectors: {known}")
        return "\n".join(lines)

    for s in matched:
        name = s.get("buyer_name", "?")
        label = s.get("timing_label", "?")
        conf = s.get("timing_confidence", "?")
        fit = s.get("fit_to_client")
        fit_str = f"{fit}%" if fit is not None else "n/a"
        cats = s.get("top_categories") or []
        lines.append(f"  {_label_icon(label)} {name}  [{label} / {conf} / fit={fit_str}]")
        if cats:
            lines.append(f"     Categories: {', '.join(str(c) for c in cats[:4])}")

    lines.append(f"\nTotal: {len(matched)} buyers in sector '{sector}'")
    return "\n".join(lines)


def query_strongest(run_dir: Path) -> str:
    """Top accounts ranked by (label, confidence, fit) — no arbitrary maths."""
    signals = _load_timing_signals(run_dir)
    run_id = run_dir.name

    # Ordinal rankings — lower number = higher priority
    LABEL_RANK  = {"Actionable": 0, "Watch": 1, "Tracking": 2}
    CONF_RANK   = {"High": 0, "Medium": 1, "Weak": 2, "None": 3}

    def sort_key(s: dict) -> tuple:
        label_r = LABEL_RANK.get(s.get("timing_label") or "Tracking", 2)
        conf_r  = CONF_RANK.get(s.get("timing_confidence") or "None", 3)
        fit_r   = -(s.get("fit_to_client") or 0)   # negate: higher fit first
        return (label_r, conf_r, fit_r)

    ranked = sorted(signals, key=sort_key)
    top = ranked[:15]

    lines = [
        _hr(),
        f"STRONGEST ACCOUNTS  |  run: {run_id}  |  top {min(15,len(ranked))} of {len(ranked)}",
        _hr(),
        "",
        "Ranked by: Label (Actionable→Watch→Tracking) then Confidence (High→None) then Fit ↓",
        "",
    ]
    for rank, s in enumerate(top, 1):
        name   = s.get("buyer_name", "?")
        label  = s.get("timing_label") or "Tracking"
        conf   = s.get("timing_confidence") or "None"
        fit    = s.get("fit_to_client")
        fit_str = f"{fit}%" if fit is not None else "n/a"
        status  = s.get("timing_status", "?")
        window  = f"{s.get('predicted_next_start','?')} → {s.get('predicted_next_end','?')}"
        lines += [
            f"  {rank:2d}. {_label_icon(label)} {name}",
            f"      {label} / {conf} / fit={fit_str} / status={status}",
            f"      Window: {window}",
            "",
        ]
    return "\n".join(lines)


def query_buyer(run_dir: Path, buyer_name: str) -> str:
    """Look up a specific buyer across timing, forecast, and profile data."""
    signals = _load_timing_signals(run_dir)
    run_id = run_dir.name

    search = buyer_name.lower().strip()
    matches = [s for s in signals if search in s.get("buyer_name", "").lower()]

    profiles = {}
    raw_profiles = _read_json(STATE_DIR / "buyer_profiles.json") or {}
    for k, v in raw_profiles.items():
        profiles[_slug(k)] = v

    briefs = {}
    raw_briefs = _read_json(STATE_DIR / "buyer_briefs.json") or {}
    for k, v in raw_briefs.items():
        briefs[_slug(k)] = v

    lines = [
        _hr(),
        f"BUYER LOOKUP: '{buyer_name}'  |  run: {run_id}",
        _hr(),
    ]
    if not matches:
        lines.append(f"No buyer matching '{buyer_name}' found in timing signals.")
        lines.append("Try --signals for the full list of tracked buyers.")
        return "\n".join(lines)

    for s in matches:
        key = s.get("buyer_key") or _slug(s.get("buyer_name", ""))
        profile = profiles.get(key, {})
        brief = briefs.get(key, {})
        lines += [
            f"",
            f"Buyer:           {s.get('buyer_name')}",
            f"Key:             {key}",
            f"",
            f"Timing label:    {_label_icon(s.get('timing_label'))} {s.get('timing_label','?')}",
            f"Confidence:      {s.get('timing_confidence','?')}",
            f"Status:          {s.get('timing_status','?')}",
            f"Visibility:      {s.get('timing_visibility','?')}",
            f"Window:          {s.get('predicted_next_start','?')} → {s.get('predicted_next_end','?')}",
            f"Central:         {s.get('predicted_next_central','?')}",
            f"Total notices:   {s.get('total_notices','?')}",
            f"Last seen:       {s.get('last_seen_date','?')}",
            f"Fit to client:   {s.get('fit_to_client','n/a')}%",
            f"Avg value:       {_currency(s.get('buyer_avg_value'))}",
            f"Top categories:  {', '.join(s.get('top_categories') or []) or 'n/a'}",
            f"Action note:     {s.get('action_note','n/a')}",
            f"",
        ]
        if profile:
            lines += [
                f"── Operator profile ──────────────────────────────────",
                f"Frequency:       {profile.get('frequency','n/a')}",
                f"Avg value:       {_currency(profile.get('avg_value'))}",
                f"Style:           {profile.get('style','n/a')}",
                f"Contact:         {profile.get('contact_pattern','n/a')}",
                "",
            ]
        if brief:
            b = brief.get("brief") or brief.get("buyer_intel_summary") or ""
            if b:
                lines += [
                    f"── Intelligence brief ────────────────────────────────",
                    f"{b}",
                    "",
                ]

    return "\n".join(lines)


def query_summary(run_dir: Path) -> str:
    """One-page operational summary of the latest run."""
    manifest = _read_json(run_dir / "run_manifest.json") or {}
    signals = _load_timing_signals(run_dir)
    run_id = run_dir.name

    status = manifest.get("status", "unknown")
    new_count = manifest.get("new_count", 0)
    shortlist_count = manifest.get("shortlist_count", 0)
    timing_count = manifest.get("buyer_timing_count", len(signals))
    timing_actionable = manifest.get("timing_actionable_count", 0)
    timing_visible = manifest.get("timing_visible_count", 0)
    timing_due_soon = manifest.get("buyer_timing_due_soon", 0)
    timing_overdue = manifest.get("buyer_timing_overdue", 0)
    ingest_total = manifest.get("ingest_total_count", 0)
    started = (manifest.get("started_at") or "")[:19].replace("T", " ")
    duration = manifest.get("total_duration_s", "?")

    steps = manifest.get("steps", {})
    errors = [k for k, v in steps.items() if v.get("status") in ("error", "failed")]

    label_counts: dict[str, int] = {}
    for s in signals:
        l = s.get("timing_label") or "Tracking"
        label_counts[l] = label_counts.get(l, 0) + 1

    lines = [
        _hr(),
        f"OPERATIONAL SUMMARY  |  {run_id}",
        _hr(),
        "",
        f"  Status:          {status}",
        f"  Started:         {started}",
        f"  Duration:        {duration}s",
        f"  Ingested:        {ingest_total} records",
        f"  New tenders:     {new_count}",
        f"  Shortlisted:     {shortlist_count}",
        f"  Step errors:     {', '.join(errors) if errors else 'none'}",
        "",
        "── Buyer intelligence ────────────────────────────────",
        "",
        f"  Buyers tracked:  {timing_count}",
        f"  Timing visible:  {timing_visible}",
        f"  Actionable:      {timing_actionable}",
        f"  Due soon:        {timing_due_soon}",
        f"  Overdue:         {timing_overdue}",
        "",
        "  Label breakdown:",
    ]
    for label in ("Actionable", "Watch", "Tracking"):
        count = label_counts.get(label, 0)
        lines.append(f"    {_label_icon(label)} {label:12s} {count}")

    lines += [
        "",
        f"── Quick actions ─────────────────────────────────────",
        "",
        f"  python scripts/query_openclaw.py --due-soon",
        f"  python scripts/query_openclaw.py --contact-list",
        f"  python scripts/query_openclaw.py --signals",
        f"  python scripts/query_openclaw.py --strongest",
        "",
    ]
    return "\n".join(lines)


VALID_OUTREACH_STATUSES = ("not_started", "drafted", "sent", "ignored")

BUYERS_DIR = BASE_DIR / "openclaw_workspace" / "buyers"


def query_actionable(run_dir: Path) -> str:
    """Ranked outreach-ready list: all Actionable + Watch buyers with outreach status."""
    signals = _load_timing_signals(run_dir)
    run_id = run_dir.name

    LABEL_RANK = {"Actionable": 0, "Watch": 1, "Tracking": 2}
    CONF_RANK  = {"High": 0, "Medium": 1, "Weak": 2, "None": 3}

    candidates = [
        s for s in signals
        if s.get("timing_label") in ("Actionable", "Watch")
    ]
    candidates.sort(key=lambda s: (
        LABEL_RANK.get(s.get("timing_label") or "Tracking", 2),
        CONF_RANK.get(s.get("timing_confidence") or "None", 3),
        -(s.get("fit_to_client") or 0),
    ))

    lines = [
        _hr(),
        f"ACTIONABLE ACCOUNTS  |  run: {run_id}",
        _hr(),
    ]
    if not candidates:
        lines.append("No Actionable or Watch buyers this run.")
        return "\n".join(lines)

    for i, s in enumerate(candidates, 1):
        name  = s.get("buyer_name", "?")
        label = s.get("timing_label") or "?"
        conf  = s.get("timing_confidence") or "None"
        fit   = s.get("fit_to_client")
        fit_str = f"{fit}%" if fit is not None else "n/a"
        status = s.get("timing_status", "?")
        window = f"{s.get('predicted_next_start','?')} → {s.get('predicted_next_end','?')}"
        action = s.get("action_note", "")

        # Read outreach status from dossier
        safe_key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        dossier = BUYERS_DIR / f"{safe_key}.md"
        outreach_status = _get_outreach_status_for(name)

        status_icon = {"not_started": "⬜", "drafted": "✏️", "sent": "✅", "ignored": "🚫"}.get(outreach_status, "⬜")

        lines += [
            f"",
            f"  {i}. {_label_icon(label)} {name}  {status_icon} outreach: {outreach_status}",
            f"     {label} / {conf} / fit={fit_str} / status={status}",
            f"     Window: {window}",
        ]
        if action:
            lines.append(f"     {action}")

    not_started = sum(
        1 for s in candidates
        if _get_outreach_status_for(s.get("buyer_name", "")) == "not_started"
    )
    lines += [
        "",
        f"Total: {len(candidates)} candidate(s)  |  {not_started} not yet started",
        "",
        f"To mark outreach: python scripts/query_openclaw.py --set-outreach \"Buyer Name\" drafted|sent|ignored",
    ]
    return "\n".join(lines)


def _get_outreach_status_for(buyer_name: str) -> str:
    safe_key = re.sub(r"[^a-z0-9]+", "_", buyer_name.lower()).strip("_")
    dossier = BUYERS_DIR / f"{safe_key}.md"
    if not dossier.exists():
        return "not_started"
    for line in dossier.read_text(encoding="utf-8").splitlines():
        if "**Outreach status:**" in line:
            raw = line.split("**Outreach status:**", 1)
            return raw[1].strip().strip("*").strip() if len(raw) == 2 else "not_started"
    return "not_started"


def cmd_set_outreach(buyer_name: str, new_status: str) -> str:
    """Write outreach_status into an existing buyer dossier."""
    if new_status not in VALID_OUTREACH_STATUSES:
        return f"ERROR: '{new_status}' is not a valid status. Use: {', '.join(VALID_OUTREACH_STATUSES)}"

    safe_key = re.sub(r"[^a-z0-9]+", "_", buyer_name.lower()).strip("_")
    dossier = BUYERS_DIR / f"{safe_key}.md"

    if not dossier.exists():
        # Try fuzzy match
        matches = [f for f in BUYERS_DIR.glob("*.md") if buyer_name.lower() in f.stem.replace("_", " ")]
        if len(matches) == 1:
            dossier = matches[0]
        elif len(matches) > 1:
            names = ", ".join(f.stem.replace("_", " ").title() for f in matches)
            return f"ERROR: Multiple matches for '{buyer_name}': {names}\nBe more specific."
        else:
            return f"ERROR: No dossier found for '{buyer_name}' (looked for {dossier.name})\nRun sync first or check --buyer to confirm the name."

    text = dossier.read_text(encoding="utf-8")
    if "- **Outreach status:**" in text:
        updated = re.sub(
            r"- \*\*Outreach status:\*\*.*",
            f"- **Outreach status:** {new_status}",
            text,
        )
    else:
        # Insert after outreach_priority line
        updated = re.sub(
            r"(- \*\*Outreach priority:\*\*.*\n)",
            f"\\1- **Outreach status:** {new_status}\n",
            text,
        )

    dossier.write_text(updated, encoding="utf-8")
    buyer_display = dossier.stem.replace("_", " ").title()
    return f"✅ {buyer_display} → outreach status set to '{new_status}'\n   Dossier: {dossier.relative_to(BASE_DIR)}"


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query ProcessEd OpenClaw memory workspace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--run", help="Run ID to query (default: latest)")
    parser.add_argument("--due-soon", action="store_true", help="Buyers with open/imminent timing windows")
    parser.add_argument("--contact-list", action="store_true", help="Ranked contact list for this week")
    parser.add_argument("--changed-since", metavar="RUN_ID", help="What changed since a prior run")
    parser.add_argument("--signals", action="store_true", help="Full signal quality breakdown")
    parser.add_argument("--sector", metavar="SECTOR", help="Filter by sector (construction, social_housing, highways, facilities)")
    parser.add_argument("--strongest", action="store_true", help="Top accounts ranked by label → confidence → fit")
    parser.add_argument("--actionable", action="store_true", help="Ranked outreach-ready list with outreach status")
    parser.add_argument("--buyer", metavar="NAME", help="Look up a specific buyer")
    parser.add_argument("--summary", action="store_true", help="One-page operational summary")
    parser.add_argument(
        "--set-outreach", nargs=2, metavar=("BUYER", "STATUS"),
        help=f"Set outreach status for a buyer. STATUS: {', '.join(VALID_OUTREACH_STATUSES)}",
    )

    args = parser.parse_args()

    # --set-outreach does not need a run_dir
    if args.set_outreach:
        buyer_name, new_status = args.set_outreach
        print(cmd_set_outreach(buyer_name, new_status))
        return

    if args.run:
        run_dir = _find_run(args.run)
        if not run_dir:
            print(f"ERROR: Run '{args.run}' not found in {RUNS_DIR}", file=sys.stderr)
            sys.exit(1)
    else:
        run_dir = _find_latest_run()
        if not run_dir:
            print(f"ERROR: No runs found in {RUNS_DIR}", file=sys.stderr)
            sys.exit(1)

    # Route to the right query
    if args.due_soon:
        print(query_due_soon(run_dir))
    elif args.contact_list:
        print(query_contact_list(run_dir))
    elif args.changed_since:
        print(query_changed_since(args.changed_since, run_dir))
    elif args.signals:
        print(query_signals(run_dir))
    elif args.sector:
        print(query_sector(run_dir, args.sector))
    elif args.strongest:
        print(query_strongest(run_dir))
    elif args.actionable:
        print(query_actionable(run_dir))
    elif args.buyer:
        print(query_buyer(run_dir, args.buyer))
    elif args.summary:
        print(query_summary(run_dir))
    else:
        # Default: summary
        print(query_summary(run_dir))
        print()
        print("Run with --help to see all query options.")


if __name__ == "__main__":
    main()
