"""
Outreach Generator

Generates outreach drafts from structured buyer context packages.
Works WITHOUT calling an LLM — produces deterministic template-filled drafts
that the operator can review and edit before sending.

Usage:
    python scripts/generate_outreach.py --buyer "Wandsworth" --mode email
    python scripts/generate_outreach.py --buyer "Wandsworth" --mode whatsapp
    python scripts/generate_outreach.py --buyer "Wandsworth" --mode bd_note
    python scripts/generate_outreach.py --buyer "Wandsworth" --mode email --save
    python scripts/generate_outreach.py --actionable --mode email

The generator:
- Never fabricates contact details
- Only generates if fit >= 40% and at least one tender reference exists
- Writes drafts to the buyer dossier's ## Outreach Drafts section when --save is set
- Logs a 'mark_drafted' action to buyer_actions when --save is set
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

# Import context packager (same scripts/ dir)
sys.path.insert(0, str(BASE_DIR / "scripts"))
from openclaw_context import (
    package_buyer_context,
    _slug,
    _now_utc,
    _find_dossier,
    _load_text,
    _get_actionable_buyers,
    BUYERS_DIR,
    STATE_DIR,
    EXPORTS_DIR,
    WORKSPACE,
)

OUTREACH_DIR = WORKSPACE / "outreach"
DRAFTS_SECTION_TAG = "## Outreach Drafts"

# ---------------------------------------------------------------------------
# Safety guardrails
# ---------------------------------------------------------------------------

_MIN_FIT = 40  # minimum fit_to_client % to generate outreach

ALLOWED_TIMING_LABELS = {"Actionable", "Watch"}

# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def _format_tender_ref(tender: dict[str, Any]) -> str:
    """One-line tender reference for inclusion in outreach."""
    title = tender.get("title") or "(procurement notice)"
    published = tender.get("published") or ""
    month_year = published[:7] if published else ""
    if month_year:
        return f"{title} ({month_year})"
    return title


def _format_value_range(identity: dict[str, str]) -> str:
    v = identity.get("typical_value") or ""
    if not v or v in ("not available", "None", ""):
        return ""
    return f" (typically {v})"


def _company_intro() -> str:
    """One-sentence company introduction from operator context."""
    # Read from operator_context.md business section
    ctx_path = BASE_DIR / "openclaw_workspace" / "memory" / "operator_context.md"
    if ctx_path.exists():
        text = ctx_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("_") and len(line) > 20:
                # Use the first substantive line of the Business section
                if "ProcessEd" not in line:
                    return line
    return "We are a UK construction contractor specialising in public sector works."


def _check_guardrails(pkg: dict[str, Any]) -> tuple[bool, str]:
    """
    Returns (ok, reason).
    ok=True means it is safe to generate outreach.
    """
    timing = pkg.get("timing") or {}
    label = timing.get("label") or "unknown"
    fit = timing.get("fit_to_client")
    tenders = pkg.get("recent_tenders") or []
    action_state = pkg.get("action_state") or {}
    db_status = action_state.get("db_status") or "not_started"

    if label not in ALLOWED_TIMING_LABELS:
        return False, (
            f"Timing label is '{label}' — outreach generation requires "
            f"Actionable or Watch. Check back when their procurement window is closer."
        )

    if fit is not None and int(fit) < _MIN_FIT:
        return False, (
            f"Fit score is {fit}% — below the {_MIN_FIT}% minimum for outreach generation. "
            f"This buyer may not be a strong enough match for cold contact."
        )

    if not tenders:
        return False, (
            "No recent tender history found. Cannot generate evidence-based outreach "
            "without at least one tender reference. Run sync_to_openclaw.py to populate dossiers."
        )

    if db_status == "sent":
        return False, (
            f"Outreach status is already 'sent' for this buyer. "
            f"If you want to send a follow-up, use --mode follow_up."
        )

    return True, ""


# ---------------------------------------------------------------------------
# Draft generators
# ---------------------------------------------------------------------------

def generate_email(pkg: dict[str, Any]) -> str:
    name = pkg.get("buyer_name", "the buyer")
    identity = pkg.get("identity") or {}
    timing = pkg.get("timing") or {}
    tenders = pkg.get("recent_tenders") or []

    # Pick best tender reference (most recent)
    primary_tender = tenders[-1] if tenders else {}
    tender_ref = _format_tender_ref(primary_tender)
    value_range = _format_value_range(identity)
    window_start = timing.get("predicted_window_start") or ""
    window_end = timing.get("predicted_window_end") or ""
    contact_pattern = identity.get("contact_pattern", "")

    # Salutation
    if contact_pattern and "procurement" in contact_pattern.lower():
        salutation = "Dear Procurement Team"
    else:
        salutation = "Dear Procurement Team"

    # Window text
    if window_start and window_end:
        window_text = f"We note that your next procurement window appears to open around {window_start}, "
    elif window_start:
        window_text = f"We note a procurement window may be opening around {window_start}, "
    else:
        window_text = "We are currently reviewing upcoming procurement opportunities in your area, "

    company_intro = _company_intro()

    lines = [
        f"Subject: Construction Works Interest — {name}",
        "",
        f"{salutation},",
        "",
        f"We recently noted your publication of {tender_ref}{value_range} and wanted to make contact.",
        "",
        company_intro,
        "",
        f"{window_text}and we would welcome the opportunity to be considered for relevant works.",
        "",
        "Would you have 15 minutes for a brief call, or could you advise on any upcoming "
        "framework or tender opportunities we could express interest in?",
        "",
        "Many thanks for your time.",
        "",
        "[Your name]",
        "[Company]",
        "[Phone / Email]",
        "",
        "---",
        f"_Draft generated: {_now_utc()}  |  Fit: {timing.get('fit_to_client', 'n/a')}%  "
        f"|  Status: {(pkg.get('action_state') or {}).get('outreach_status', 'not_started')}_",
        "_Review carefully before sending. Never send without reading this draft first._",
    ]
    return "\n".join(lines)


def generate_whatsapp(pkg: dict[str, Any]) -> str:
    name = pkg.get("buyer_name", "the buyer")
    identity = pkg.get("identity") or {}
    timing = pkg.get("timing") or {}
    tenders = pkg.get("recent_tenders") or []

    primary_tender = tenders[-1] if tenders else {}
    tender_ref = _format_tender_ref(primary_tender)
    window_start = timing.get("predicted_window_start") or ""

    window_text = f"ahead of your window opening around {window_start}" if window_start else "for upcoming works"

    lines = [
        f"Hi, we're [Company] — a UK construction contractor.",
        f"We recently came across your {tender_ref} and wanted to reach out {window_text}.",
        "Happy to share our capability statement — would this be a good time to connect?",
        "",
        "---",
        f"_Draft generated: {_now_utc()}  |  Fit: {timing.get('fit_to_client', 'n/a')}%_",
        "_Review before sending._",
    ]
    return "\n".join(lines)


def generate_bd_note(pkg: dict[str, Any]) -> str:
    name = pkg.get("buyer_name", "the buyer")
    identity = pkg.get("identity") or {}
    timing = pkg.get("timing") or {}
    tenders = pkg.get("recent_tenders") or []
    action_state = pkg.get("action_state") or {}

    fit = timing.get("fit_to_client")
    label = timing.get("label") or "unknown"
    confidence = timing.get("confidence") or "unknown"
    window_start = timing.get("predicted_window_start") or "unknown"
    window_end = timing.get("predicted_window_end") or "unknown"
    action_note = timing.get("action_note") or "No specific note."
    typical_value = identity.get("typical_value") or "unknown"
    freq = identity.get("procurement_frequency") or identity.get("style") or "unknown"
    contact_pattern = identity.get("contact_pattern") or "unknown"
    operator_notes = pkg.get("operator_notes") or "_None._"
    db_status = action_state.get("db_status") or "not_started"
    dossier_status = action_state.get("outreach_status") or "not_started"

    tender_lines = "\n".join(
        f"  - {_format_tender_ref(t)}" for t in tenders
    ) or "  _No tender history._"

    lines = [
        f"# BD Note — {name}",
        f"_Generated: {_now_utc()}_",
        "",
        "## Why This Buyer Matters",
        f"- **Fit to client:** {fit}%",
        f"- **Typical contract value:** {typical_value}",
        f"- **Procurement style:** {freq}",
        f"- **Contact pattern:** {contact_pattern}",
        "",
        "## Timing Position",
        f"- **Signal:** {label} ({confidence} confidence)",
        f"- **Predicted window:** {window_start} → {window_end}",
        f"- **Action note:** {action_note}",
        "",
        "## Relevant Tender History",
        tender_lines,
        "",
        "## Current Outreach State",
        f"- **Dossier status:** {dossier_status}",
        f"- **DB status:** {db_status}",
        "",
        "## Recommended Approach",
    ]

    # Recommendation logic
    if label == "Actionable" and fit and int(fit) >= 60:
        lines.append(
            f"Strong candidate for immediate outreach. Procurement window opens {window_start}. "
            "Lead with a specific tender reference and request to be considered for works."
        )
    elif label == "Actionable":
        lines.append(
            f"Decent fit — pursue before window opens ({window_start}). "
            "Use tender history as conversation opener."
        )
    elif label == "Watch":
        lines.append(
            "Not yet actionable — monitor and make contact 4–6 weeks before window opens. "
            "Priority: verify contact and note in dossier."
        )
    else:
        lines.append(
            f"Timing label is {label} — hold off on outreach until signal improves. "
            "Keep dossier updated."
        )

    lines += [
        "",
        "## Operator Notes",
        operator_notes,
        "",
        "---",
        f"_For internal use only. Not for external distribution._",
    ]
    return "\n".join(lines)


def generate_follow_up(pkg: dict[str, Any]) -> str:
    name = pkg.get("buyer_name", "the buyer")
    identity = pkg.get("identity") or {}
    timing = pkg.get("timing") or {}
    tenders = pkg.get("recent_tenders") or []
    action_state = pkg.get("action_state") or {}

    latest_action = action_state.get("latest_action") or {}
    last_date = (latest_action.get("updated_at") or "")[:10]
    window_start = timing.get("predicted_window_start") or ""

    primary_tender = tenders[-1] if tenders else {}
    tender_ref = _format_tender_ref(primary_tender)

    window_text = (
        f"As your procurement window is now approaching (from {window_start}), "
        if window_start else "As your upcoming procurement period approaches, "
    )

    lines = [
        f"Subject: Following up — Construction Works Interest — {name}",
        "",
        "Dear Procurement Team,",
        "",
        f"I wanted to follow up on my earlier message{f' from {last_date}' if last_date else ''}.",
        "",
        f"{window_text}I wanted to reiterate our interest in being considered for relevant "
        f"construction works — particularly in areas such as {tender_ref}.",
        "",
        "Please let me know if there is a framework or approved list we should register on, "
        "or if a brief conversation would be helpful.",
        "",
        "Thank you for your time.",
        "",
        "[Your name]",
        "[Company]",
        "[Phone / Email]",
        "",
        "---",
        f"_Follow-up draft generated: {_now_utc()}  |  Last action: {last_date}_",
        "_Review carefully before sending._",
    ]
    return "\n".join(lines)


_GENERATORS = {
    "email": generate_email,
    "whatsapp": generate_whatsapp,
    "bd_note": generate_bd_note,
    "follow_up": generate_follow_up,
}


# ---------------------------------------------------------------------------
# Save to dossier
# ---------------------------------------------------------------------------

def _save_draft_to_dossier(buyer_name: str, mode: str, draft_text: str) -> Path | None:
    """
    Append draft to the ## Outreach Drafts section of the buyer dossier.
    Creates the section if it does not exist (before ## Memory Notes).
    Returns the dossier path if saved, else None.
    """
    dossier_path = _find_dossier(buyer_name)
    if dossier_path is None:
        return None

    content = dossier_path.read_text(encoding="utf-8")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    draft_block = (
        f"\n### {mode.replace('_', ' ').title()} draft — {timestamp}\n\n"
        f"```\n{draft_text}\n```\n"
    )

    if DRAFTS_SECTION_TAG in content:
        # Insert before ## Memory Notes (or at end if no Memory Notes)
        memory_tag = "## Memory Notes"
        if memory_tag in content:
            content = content.replace(
                memory_tag,
                draft_block + memory_tag,
                1,
            )
        else:
            # Append after the existing Drafts section tag
            idx = content.rfind(DRAFTS_SECTION_TAG)
            # Find end of section
            content = content + draft_block
    else:
        # Add the section before ## Memory Notes or at end
        memory_tag = "## Memory Notes"
        section_header = f"\n{DRAFTS_SECTION_TAG}\n"
        if memory_tag in content:
            content = content.replace(
                memory_tag,
                section_header + draft_block + memory_tag,
                1,
            )
        else:
            content = content + section_header + draft_block

    dossier_path.write_text(content, encoding="utf-8")
    return dossier_path


def _log_drafted_action(buyer_key: str, buyer_name: str) -> bool:
    """Log a mark_drafted action to buyer_actions DB.

    Returns True if the action was logged, False if skipped or failed.
    """
    override = os.getenv("OUTREACH_DB_PATH")
    db_path = Path(override).expanduser().resolve() if override else STATE_DIR / "outreach.sqlite"
    if not db_path.exists():
        print(f"Warning: DB not found at {db_path} — drafted action not logged", file=sys.stderr)
        return False
    try:
        sys.path.insert(0, str(BASE_DIR))
        from outreach.db import connect, init_db
        from outreach.repositories import create_action, has_open_action_of_type
        conn = connect(db_path)
        init_db(conn)
        if not has_open_action_of_type(conn, buyer_key, "mark_drafted"):
            create_action(
                conn,
                buyer_key=buyer_key,
                buyer_name=buyer_name,
                action_type="mark_drafted",
                action_status="drafted",
                notes="Outreach draft generated by generate_outreach.py",
                source="generate_outreach",
            )
        conn.close()
        return True
    except Exception as exc:
        print(f"Warning: could not log drafted action -- {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate deterministic outreach drafts from buyer context.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--buyer", help="Generate outreach for a specific buyer")
    group.add_argument("--actionable", action="store_true",
                       help="Generate outreach for all actionable buyers")

    p.add_argument("--mode", choices=list(_GENERATORS), default="email",
                   help=f"Draft type. Choices: {', '.join(_GENERATORS)} (default: email)")
    p.add_argument("--save", action="store_true",
                   help="Save draft to dossier and log drafted action")
    p.add_argument("--force", action="store_true",
                   help="Bypass guardrails and generate even if fit/timing conditions not met")
    return p


def _run_for_buyer(buyer_name: str, mode: str, save: bool, force: bool) -> int:
    pkg = package_buyer_context(buyer_name, mode="outreach")

    ok, reason = _check_guardrails(pkg)
    if not ok and not force:
        print(f"[SKIP] {pkg['buyer_name']}: {reason}")
        return 0

    if not ok and force:
        print(f"[WARN] Guardrail override: {reason}", file=sys.stderr)

    generator = _GENERATORS[mode]
    draft = generator(pkg)

    print(f"\n{'='*60}")
    print(f"Buyer: {pkg['buyer_name']}  |  Mode: {mode}")
    print(f"{'='*60}\n")
    print(draft)

    if save:
        buyer_key = _slug(buyer_name)
        dossier_path = _save_draft_to_dossier(buyer_name, mode, draft)
        if dossier_path:
            print(f"\n[Saved] Draft appended to {dossier_path}", file=sys.stderr)
        logged = _log_drafted_action(buyer_key, pkg["buyer_name"])
        if logged:
            print("[Logged] Drafted action recorded in DB", file=sys.stderr)
        else:
            print("# DB not updated -- run: python -m outreach.cli init-db  (then re-run with --save)", file=sys.stderr)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.buyer:
        return _run_for_buyer(args.buyer, args.mode, args.save, args.force)

    # --actionable: iterate all actionable buyers
    keys = _get_actionable_buyers()
    if not keys:
        print("No actionable buyers found in the latest run.")
        return 0

    generated = 0
    for key in keys:
        # Resolve name from dossier
        dossier_path = BUYERS_DIR / f"{key}.md"
        if dossier_path.exists():
            text = _load_text(dossier_path)
            for line in text.splitlines():
                if line.startswith("# Buyer Dossier —"):
                    name = line.replace("# Buyer Dossier —", "").strip()
                    break
            else:
                name = key.replace("_", " ").title()
        else:
            name = key.replace("_", " ").title()
        ret = _run_for_buyer(name, args.mode, args.save, args.force)
        if ret == 0:
            generated += 1

    print(f"\n[Done] {generated} buyer(s) processed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
