"""
OpenClaw Context Packager

Assembles a structured context package for LLM-assisted outreach work.
Output is plain text optimised for direct paste into an AI agent prompt,
or JSON for programmatic use.

Usage:
    python scripts/openclaw_context.py --buyer "London Borough of Wandsworth"
    python scripts/openclaw_context.py --actionable
    python scripts/openclaw_context.py --run 2026-04-18_120002
    python scripts/openclaw_context.py --actionable --json
    python scripts/openclaw_context.py --buyer "Wandsworth" --mode outreach
    python scripts/openclaw_context.py --agent-prompt
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(os.getenv("TENDER_BASE_DIR", str(Path(__file__).resolve().parent.parent))).expanduser().resolve()
WORKSPACE = BASE_DIR / "openclaw_workspace"
BUYERS_DIR = WORKSPACE / "buyers"
RUNS_DIR = BASE_DIR / "data" / "runs"
STATE_DIR = BASE_DIR / "state"
MEMORY_DIR = WORKSPACE / "memory"
SECTORS_DIR = WORKSPACE / "sectors"
EXPORTS_DIR = WORKSPACE / "exports"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _load_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return default


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            rows.append(json.loads(text))
        except Exception:
            pass
    return rows


def _latest_run_dir() -> Path | None:
    if not RUNS_DIR.exists():
        return None
    candidates = sorted(
        (p for p in RUNS_DIR.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    for c in candidates:
        m = _load_json(c / "run_manifest.json", {})
        if str(m.get("status") or "").startswith("success"):
            return c
    return None


def _read_dossier_field(text: str, field: str) -> str:
    """Extract a bolded field value from dossier markdown."""
    marker = f"**{field}:**"
    for line in text.splitlines():
        if marker in line:
            parts = line.split(marker, 1)
            if len(parts) == 2:
                return parts[1].strip().strip("*").strip()
    return ""


def _get_outreach_status_from_dossier(text: str) -> str:
    marker = "**Outreach status:**"
    if marker in text:
        parts = text.split(marker, 1)
        if len(parts) == 2:
            return parts[1].strip().split("\n")[0].strip().strip("*").strip()
    return "not_started"


def _extract_memory_notes(text: str) -> str:
    """Return everything under '## Memory Notes' section."""
    tag = "## Memory Notes"
    if tag in text:
        parts = text.split(tag, 1)
        return parts[1].strip() if len(parts) == 2 else ""
    return ""


def _extract_recent_changes(text: str) -> str:
    """Return the Recent Changes section (between its tag and Memory Notes)."""
    tag = "## Recent Changes"
    end_tag = "## Memory Notes"
    if tag not in text:
        return ""
    parts = text.split(tag, 1)
    body = parts[1]
    if end_tag in body:
        body = body.split(end_tag, 1)[0]
    return body.strip()


def _load_action_state_for(buyer_key: str) -> dict[str, Any]:
    """Read action state from outreach DB for a single buyer. Graceful fallback."""
    override = os.getenv("OUTREACH_DB_PATH")
    db_path = Path(override).expanduser().resolve() if override else STATE_DIR / "outreach.sqlite"
    if not db_path.exists():
        return {"overall_status": "not_started", "action_count": 0, "latest_action": None}
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, action_type, action_status, run_id, notes, actor, source, created_at, updated_at "
            "FROM buyer_actions WHERE buyer_key = ? ORDER BY updated_at DESC",
            (buyer_key,),
        ).fetchall()
        conn.close()
    except Exception:
        return {"overall_status": "not_started", "action_count": 0, "latest_action": None}

    actions = [dict(r) for r in rows]
    STATUS_PRIORITY = {
        "sent": 0, "drafted": 1, "follow_up": 2,
        "ignored": 3, "completed": 4, "pending": 5, "failed": 6,
    }
    overall = "not_started"
    latest: dict[str, Any] | None = None
    for a in actions:
        s = a.get("action_status", "")
        if STATUS_PRIORITY.get(s, 99) < STATUS_PRIORITY.get(overall, 99):
            overall = s
            latest = a
    return {"overall_status": overall, "action_count": len(actions), "latest_action": latest}


def _find_dossier(buyer_name: str) -> Path | None:
    slug = _slug(buyer_name)
    for path in BUYERS_DIR.glob("*.md"):
        if path.stem == slug:
            return path
    # Fallback: partial match
    for path in BUYERS_DIR.glob("*.md"):
        if slug in path.stem or path.stem in slug:
            return path
    return None


def _load_timing_signal(buyer_key: str, run_dir: Path | None) -> dict[str, Any] | None:
    if run_dir is None:
        return None
    timing_file = run_dir / "buyer_timing_signals.json"
    data = _load_json(timing_file, {})
    for sig in data.get("signals") or []:
        if sig.get("buyer_key") == buyer_key:
            return sig
    return None


def _load_watchlist_fit(buyer_key: str) -> int | None:
    """Read fit_to_client for a buyer from the latest run's buyer_watchlist.json."""
    try:
        from src.run_utils import latest_run_dir as _latest  # type: ignore
        run_dir = _latest()
    except Exception:
        runs = sorted(RUNS_DIR.glob("*/buyer_watchlist.json")) if RUNS_DIR.exists() else []
        if not runs:
            return None
        run_dir = runs[-1].parent

    wl_file = run_dir / "buyer_watchlist.json"
    if not wl_file.exists():
        return None
    try:
        wl = json.loads(wl_file.read_text(encoding="utf-8"))
        for entry in wl:
            if _slug(entry.get("buyer_name", "")) == buyer_key:
                v = entry.get("fit_to_client")
                return int(v) if v is not None else None
    except Exception:
        pass
    return None


def _load_recent_tenders(buyer_key: str, limit: int = 5) -> list[dict[str, Any]]:
    """Load recent tender records for a buyer from buyer_history.jsonl.

    Each line in buyer_history.jsonl IS one tender record keyed by buyer_name.
    """
    history_file = STATE_DIR / "buyer_history.jsonl"
    matches: list[dict[str, Any]] = []
    for row in _load_jsonl(history_file):
        if _slug(row.get("buyer_name", "")) == buyer_key:
            matches.append(row)
    # Sort by seen_at descending, return most recent
    matches.sort(key=lambda r: r.get("seen_at", ""), reverse=True)
    return matches[:limit]


def _operator_context() -> str:
    return _load_text(MEMORY_DIR / "operator_context.md", "_No operator context available._")


def _clean_timing_label(value: str | None) -> str | None:
    """Strip leading emoji/symbol characters from a timing label."""
    if value is None:
        return None
    import re as _re
    # Strip any leading non-word characters (emoji, symbols, whitespace)
    cleaned = _re.sub(r"^[^\w]+", "", str(value), flags=_re.UNICODE).strip()
    return cleaned or None


# ---------------------------------------------------------------------------
# Buyer context package
# ---------------------------------------------------------------------------

def package_buyer_context(buyer_name: str, mode: str = "full") -> dict[str, Any]:
    """
    Build a structured context package for a single buyer.

    mode:
        full      — all sections
        outreach  — dossier + timing + action state + recent tenders (drop sector noise)
        brief     — identity + timing summary only
    """
    buyer_key = _slug(buyer_name)
    run_dir = _latest_run_dir()

    dossier_path = _find_dossier(buyer_name)
    dossier_text = _load_text(dossier_path) if dossier_path else ""
    resolved_name = buyer_name

    # Try to get canonical name from dossier heading
    if dossier_text:
        for line in dossier_text.splitlines():
            if line.startswith("# Buyer Dossier —"):
                resolved_name = line.replace("# Buyer Dossier —", "").strip()
                break

    timing_signal = _load_timing_signal(buyer_key, run_dir)
    action_state = _load_action_state_for(buyer_key)
    recent_tenders = _load_recent_tenders(buyer_key)
    memory_notes = _extract_memory_notes(dossier_text) if dossier_text else ""
    recent_changes = _extract_recent_changes(dossier_text) if dossier_text else ""
    outreach_status = _get_outreach_status_from_dossier(dossier_text) if dossier_text else "not_started"

    # Pull key dossier fields
    fields: dict[str, str] = {}
    if dossier_text:
        for field in [
            "Timing label", "Status", "Confidence", "Fit to client", "Region", "Typical value",
            "Procurement frequency", "Contact pattern", "Style",
            "Predicted window", "Action note",
        ]:
            v = _read_dossier_field(dossier_text, field)
            if v:
                fields[field.lower().replace(" ", "_")] = v

    package: dict[str, Any] = {
        "buyer_key": buyer_key,
        "buyer_name": resolved_name,
        "packaged_at": _now_utc(),
        "mode": mode,
        "dossier_available": dossier_path is not None,
        "identity": fields,
        "timing": {
            "label": (timing_signal or {}).get("timing_label") or _clean_timing_label(fields.get("timing_label")),
            "confidence": (timing_signal or {}).get("timing_confidence") or fields.get("confidence"),
            "predicted_window_start": (timing_signal or {}).get("predicted_next_start") or fields.get("predicted_window", "").split("→")[0].strip(),
            "predicted_window_end": (timing_signal or {}).get("predicted_next_end") or fields.get("predicted_window", "").split("→")[-1].strip(),
            "action_note": (timing_signal or {}).get("action_note") or fields.get("action_note"),
            "fit_to_client": (timing_signal or {}).get("fit_to_client") or _load_watchlist_fit(buyer_key),
        },
        "action_state": {
            "outreach_status": outreach_status,
            "db_status": action_state["overall_status"],
            "action_count": action_state["action_count"],
            "latest_action": action_state["latest_action"],
        },
        "recent_tenders": [
            {
                "title": t.get("title") or t.get("notice_title") or "(no title)",
                "published": t.get("published") or t.get("published_at") or "",
                "value": t.get("value") or t.get("estimated_value"),
                "category": t.get("category") or t.get("notice_type"),
            }
            for t in recent_tenders
        ],
        "operator_notes": memory_notes,
        "recent_changes": recent_changes,
    }

    if mode == "full":
        package["operator_context"] = _operator_context()

    return package


def render_buyer_context_text(pkg: dict[str, Any]) -> str:
    """Render a buyer context package as plain text for LLM consumption."""
    lines: list[str] = []
    lines.append(f"# Context Package — {pkg['buyer_name']}")
    lines.append(f"_Packaged: {pkg['packaged_at']}  |  Mode: {pkg['mode']}_")
    lines.append("")

    # Identity
    lines.append("## Buyer Identity")
    identity = pkg.get("identity") or {}
    for k, v in identity.items():
        lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
    if not identity:
        lines.append("_No dossier available — run sync_to_openclaw.py first._")
    lines.append("")

    # Timing
    lines.append("## Timing Signal")
    t = pkg.get("timing") or {}
    lines.append(f"- **Label:** {t.get('label') or 'unknown'}")
    lines.append(f"- **Confidence:** {t.get('confidence') or 'unknown'}")
    w_start = t.get("predicted_window_start") or ""
    w_end = t.get("predicted_window_end") or ""
    if w_start:
        lines.append(f"- **Predicted window:** {w_start} → {w_end}")
    if t.get("action_note"):
        lines.append(f"- **Action note:** {t['action_note']}")
    if t.get("fit_to_client") is not None:
        lines.append(f"- **Fit to client:** {t['fit_to_client']}%")
    lines.append("")

    # Outreach action state
    lines.append("## Outreach State")
    a = pkg.get("action_state") or {}
    lines.append(f"- **Status (dossier):** {a.get('outreach_status', 'not_started')}")
    lines.append(f"- **Status (DB):** {a.get('db_status', 'not_started')}")
    lines.append(f"- **Actions logged:** {a.get('action_count', 0)}")
    if a.get("latest_action"):
        la = a["latest_action"]
        lines.append(f"- **Last action:** {la.get('action_type')} → {la.get('action_status')} ({la.get('updated_at', '')[:10]})")
    lines.append("")

    # Recent tenders
    lines.append("## Recent Tenders")
    tenders = pkg.get("recent_tenders") or []
    if tenders:
        for t_ in tenders:
            val = f"  £{t_['value']:,}" if t_.get("value") else ""
            cat = f"  [{t_['category']}]" if t_.get("category") else ""
            lines.append(f"- {t_['published'][:7] if t_.get('published') else '?'} — {t_['title']}{val}{cat}")
    else:
        lines.append("_No recent tender history available._")
    lines.append("")

    # Operator notes
    if pkg.get("operator_notes"):
        lines.append("## Operator Notes")
        lines.append(pkg["operator_notes"])
        lines.append("")

    # Recent changes
    if pkg.get("recent_changes"):
        lines.append("## Recent Changes")
        lines.append(pkg["recent_changes"])
        lines.append("")

    # Operator context (full mode only)
    if pkg.get("operator_context"):
        lines.append("## Business Context")
        lines.append(pkg["operator_context"])
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Actionable buyers context
# ---------------------------------------------------------------------------

def _get_actionable_buyers() -> list[str]:
    """Return buyer keys from timing signals with label=Actionable + High/Medium confidence."""
    run_dir = _latest_run_dir()
    if not run_dir:
        return []
    data = _load_json(run_dir / "buyer_timing_signals.json", {})
    result: list[str] = []
    for sig in data.get("signals") or []:
        if (
            sig.get("timing_label") == "Actionable"
            and sig.get("timing_confidence") in ("High", "Medium")
        ):
            result.append(sig.get("buyer_key") or sig.get("buyer_name") or "")
    return [k for k in result if k]


def package_actionable_context() -> dict[str, Any]:
    """Package context for all currently actionable buyers."""
    keys = _get_actionable_buyers()
    buyers: list[dict[str, Any]] = []
    for key in keys:
        # Try to resolve real name from dossier
        dossier_path = BUYERS_DIR / f"{key}.md"
        if dossier_path.exists():
            text = _load_text(dossier_path)
            for line in text.splitlines():
                if line.startswith("# Buyer Dossier —"):
                    name = line.replace("# Buyer Dossier —", "").strip()
                    buyers.append(package_buyer_context(name, mode="outreach"))
                    break
            else:
                buyers.append(package_buyer_context(key.replace("_", " ").title(), mode="outreach"))
        else:
            buyers.append(package_buyer_context(key.replace("_", " ").title(), mode="outreach"))

    return {
        "type": "actionable_buyers",
        "count": len(buyers),
        "packaged_at": _now_utc(),
        "operator_context": _operator_context(),
        "buyers": buyers,
    }


def render_actionable_context_text(pkg: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Actionable Buyers Context Package")
    lines.append(f"_{pkg['count']} buyers  |  Packaged: {pkg['packaged_at']}_")
    lines.append("")
    lines.append("## Business Context")
    lines.append(pkg.get("operator_context") or "_No operator context._")
    lines.append("")
    lines.append("---")
    for buyer_pkg in pkg.get("buyers") or []:
        lines.append("")
        lines.append(render_buyer_context_text(buyer_pkg))
        lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Run context
# ---------------------------------------------------------------------------

def package_run_context(run_id: str) -> dict[str, Any]:
    """Package context for a specific run."""
    run_dir = RUNS_DIR / run_id
    manifest = _load_json(run_dir / "run_manifest.json", {})
    summary_path = WORKSPACE / "runs" / f"{run_id}.md"
    summary_text = _load_text(summary_path)

    # Top shortlisted buyers from this run
    shortlist = _load_json(run_dir / "decision_shortlist.json", {}).get("opportunities") or []
    top_buyers: list[str] = []
    seen: set[str] = set()
    for opp in shortlist[:10]:
        k = _slug(opp.get("buyer_name") or opp.get("buyer") or "")
        if k and k not in seen:
            seen.add(k)
            top_buyers.append(k)

    return {
        "type": "run_context",
        "run_id": run_id,
        "packaged_at": _now_utc(),
        "manifest": {
            "status": manifest.get("status"),
            "shortlist_count": manifest.get("shortlist_count", 0),
            "review_count": manifest.get("review_count", 0),
            "finished_at": manifest.get("finished_at"),
        },
        "run_summary": summary_text,
        "top_buyers": top_buyers,
        "operator_context": _operator_context(),
    }


def render_run_context_text(pkg: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Run Context — {pkg['run_id']}")
    lines.append(f"_Packaged: {pkg['packaged_at']}_")
    lines.append("")
    m = pkg.get("manifest") or {}
    lines.append(f"**Status:** {m.get('status', 'unknown')}  |  "
                 f"**Shortlist:** {m.get('shortlist_count', 0)}  |  "
                 f"**Review:** {m.get('review_count', 0)}")
    lines.append("")
    if pkg.get("run_summary"):
        lines.append("## Run Summary")
        lines.append(pkg["run_summary"])
        lines.append("")
    if pkg.get("top_buyers"):
        lines.append("## Top Buyers This Run")
        for b in pkg["top_buyers"]:
            lines.append(f"- {b.replace('_', ' ').title()}")
        lines.append("")
    lines.append("## Business Context")
    lines.append(pkg.get("operator_context") or "_No operator context._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent system prompt
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = """\
You are the ProcessEd OpenClaw Agent — a business intelligence and outreach assistant
for a UK construction contractor using the ProcessEd tender intelligence platform.

## Your role

You help the operator (Bil) take action on procurement intelligence gathered by the
ProcessEd pipeline. You read structured context packages and produce:
1. Outreach drafts — cold emails, WhatsApp messages, BD introductions
2. Buyer analysis — interpreting timing signals, prioritising who to contact
3. Strategic advice — when to contact, how to position, what to lead with

## What you know

You receive structured context packages containing:
- Buyer dossier data (procurement history, timing signals, fit scores)
- Recent tenders from that buyer
- Current outreach state (not_started / drafted / sent / ignored)
- Operator business context (sectors, regions, value range, outreach posture)
- Operator notes (free-text intelligence added by the operator)

## What you must never do

- Fabricate contact names, emails, or phone numbers
- Claim a tender exists that is not in the provided data
- Invent procurement dates or deadlines not in the data
- Assume the operator has already been in contact unless outreach_status confirms it
- Generate marketing fluff that ignores the actual fit score or timing signal

## Output format

- Be direct and professional — this is B2B procurement outreach
- Use the buyer's real procurement history as evidence of fit
- Lead with the specific reason for contact (a tender they published, a timing window)
- Keep outreach drafts concise: email ≤ 200 words, WhatsApp ≤ 80 words
- Flag when outreach_status is already 'sent' and ask if a follow-up is intended

## Confidence in your output

Only generate outreach if:
- Timing label is Actionable or Watch
- Fit to client ≥ 40%
- There are ≥ 1 recent tenders to reference

If these conditions are not met, say so and explain what would need to change.
"""


# ---------------------------------------------------------------------------
# Task templates
# ---------------------------------------------------------------------------

TASK_TEMPLATES: dict[str, str] = {
    "cold_email": """\
Using the context below, draft a cold outreach email.

Requirements:
- Subject line referencing a specific recent tender or procurement category
- Opening line that names a specific tender they published (from the data)
- One sentence establishing who we are and relevant sector experience
- One sentence tying our capability to their upcoming procurement window
- Clear call to action (15-minute call or request to be included on frameworks)
- Tone: professional, direct, not salesy
- Length: ≤ 200 words body

Do NOT fabricate contact details. Address as "Dear Procurement Team" if no contact name is available.
""",
    "whatsapp": """\
Using the context below, draft a WhatsApp outreach message.

Requirements:
- Opens with who we are and why we're reaching out
- References one specific tender or category from their history
- Mentions the timing window if present
- Simple call to action
- Tone: professional but conversational
- Length: ≤ 80 words

Do NOT include links or attachments — this is a first-touch message only.
""",
    "bd_note": """\
Using the context below, write a business development note for internal use.

Include:
- Who this buyer is and why they matter to us
- Current timing position (when their window opens)
- Key tenders from their history that match our work
- Recommended approach and messaging angle
- Any red flags or considerations
- Suggested next action with timeline

Format: clear sections, operator-facing, factual. Not for external use.
""",
    "follow_up": """\
Using the context below, draft a follow-up message.

Context: the operator has already made initial contact (outreach_status = drafted or sent).

Requirements:
- Reference the initial outreach without being pushy
- Add new value — a recent tender, an upcoming window, or a sector insight
- Clear next step
- Keep it shorter than the first contact
- Tone: warm but professional
""",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Package OpenClaw context for LLM-assisted outreach.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--buyer", help="Package context for a specific buyer by name")
    p.add_argument("--actionable", action="store_true",
                   help="Package context for all currently actionable buyers")
    p.add_argument("--run", metavar="RUN_ID",
                   help="Package context for a specific pipeline run")
    p.add_argument("--mode", choices=["full", "outreach", "brief"], default="full",
                   help="Context detail level for --buyer (default: full)")
    p.add_argument("--json", action="store_true",
                   help="Output as JSON instead of plain text")
    p.add_argument("--agent-prompt", action="store_true",
                   help="Print the agent system prompt")
    p.add_argument("--task", choices=list(TASK_TEMPLATES), metavar="TASK",
                   help=f"Append a task template. Choices: {', '.join(TASK_TEMPLATES)}")
    p.add_argument("--save", action="store_true",
                   help="Save output to openclaw_workspace/exports/ as well as printing")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.agent_prompt:
        print(AGENT_SYSTEM_PROMPT)
        if args.task:
            print("\n---\n")
            print(TASK_TEMPLATES[args.task])
        return 0

    # Build package
    package: dict[str, Any] | None = None
    text_output: str = ""

    if args.buyer:
        package = package_buyer_context(args.buyer, mode=args.mode)
        text_output = render_buyer_context_text(package)
    elif args.actionable:
        package = package_actionable_context()
        text_output = render_actionable_context_text(package)
    elif args.run:
        package = package_run_context(args.run)
        text_output = render_run_context_text(package)
    else:
        parser.print_help()
        return 1

    # Append task template if requested
    if args.task:
        text_output += "\n\n---\n\n## Task\n\n" + TASK_TEMPLATES[args.task]

    # Output
    if args.json:
        print(json.dumps(package, ensure_ascii=False, indent=2, default=str))
    else:
        print(text_output)

    # Save
    if args.save and package is not None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        if args.buyer:
            slug = _slug(args.buyer)
            out_path = EXPORTS_DIR / f"{slug}_context_{args.mode}.md"
        elif args.actionable:
            out_path = EXPORTS_DIR / "actionable_context.md"
        elif args.run:
            out_p