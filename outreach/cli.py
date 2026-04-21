"""
CLI entrypoint for manual outreach operations.

Original commands (contacts, samples):
    python -m outreach.cli init-db
    python -m outreach.cli list-contacts
    python -m outreach.cli preview-sample --contact-id <id>
    python -m outreach.cli send-sample    --contact-id <id>

Action layer commands (Phase 1):
    python -m outreach.cli list-actions   [--buyer "..."] [--type ...] [--status ...]
    python -m outreach.cli create-action  --buyer "..." --type <type> [--run-id ...] [--notes "..."] [--allow-duplicate]
    python -m outreach.cli set-action-status --action-id <id> --status <status> [--notes "..."]
    python -m outreach.cli buyer-state    --buyer "..."
    python -m outreach.cli export-contact-brief --buyer "..."
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from outreach.db import ACTION_STATUSES, ACTION_TYPES, connect, db_path, init_db
from outreach.repositories import (
    buyer_current_state,
    create_action,
    get_action,
    has_open_action_of_type,
    list_actions,
    list_contacts,
    update_action_status,
)
from outreach.service import preview_sample_for_contact, send_sample_to_contact

BASE_DIR = Path(os.getenv("TENDER_BASE_DIR", str(Path(__file__).resolve().parent.parent))).expanduser().resolve()
STATE_DIR = BASE_DIR / "state"
RUNS_DIR = BASE_DIR / "data" / "runs"
WORKSPACE = BASE_DIR / "openclaw_workspace"
BUYERS_DIR = WORKSPACE / "buyers"
EXPORTS_DIR = WORKSPACE / "exports"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    s = name.lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _hr() -> str:
    return "─" * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_dossier(buyer_name: str) -> Path | None:
    """Locate buyer dossier by exact slug or fuzzy stem match."""
    safe = _slug(buyer_name)
    exact = BUYERS_DIR / f"{safe}.md"
    if exact.exists():
        return exact
    # fuzzy: any dossier whose stem contains every word in buyer_name
    words = buyer_name.lower().split()
    for f in sorted(BUYERS_DIR.glob("*.md")):
        stem = f.stem.replace("_", " ")
        if all(w in stem for w in words):
            return f
    return None


def _read_dossier_field(path: Path, marker: str) -> str | None:
    """Extract a single field value from a dossier markdown line."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if marker in line:
            raw = line.split(marker, 1)
            return raw[1].strip().strip("*").strip() if len(raw) == 2 else None
    return None


def _load_timing_signal(buyer_key: str) -> dict:
    """Load the latest timing signal for a buyer from the most-recent run."""
    if not RUNS_DIR.exists():
        return {}
    runs = sorted(
        [d for d in RUNS_DIR.iterdir() if d.is_dir() and (d / "buyer_timing_signals.json").exists()],
        key=lambda d: d.name,
    )
    if not runs:
        return {}
    import json as _json
    try:
        data = _json.loads((runs[-1] / "buyer_timing_signals.json").read_text(encoding="utf-8"))
        signals = data if isinstance(data, list) else data.get("signals", [])
        for s in signals:
            if s.get("buyer_key") == buyer_key or _slug(s.get("buyer_name", "")) == buyer_key:
                return s
    except Exception:
        pass
    return {}


def _load_recent_tenders(buyer_key: str, limit: int = 5) -> list[dict]:
    """Load the most recent buyer_history records for a buyer."""
    history_file = STATE_DIR / "buyer_history.jsonl"
    if not history_file.exists():
        return []
    import json as _json
    records = []
    try:
        for line in history_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = _json.loads(line)
                if _slug(r.get("buyer_name", "")) == buyer_key:
                    records.append(r)
            except Exception:
                pass
    except Exception:
        pass
    # Sort newest first
    records.sort(key=lambda r: r.get("seen_at") or r.get("deadline_at") or "", reverse=True)
    return records[:limit]


# ---------------------------------------------------------------------------
# Contact brief export
# ---------------------------------------------------------------------------

def export_contact_brief(buyer_name: str, *, source: str = "cli") -> dict:
    """Generate and save a compact contact brief for a buyer.

    Returns a dict with keys: status, path, content (str brief).
    """
    buyer_key = _slug(buyer_name)
    dossier_path = _find_dossier(buyer_name)
    if dossier_path is None:
        return {
            "status": "error",
            "error": f"No dossier found for '{buyer_name}'. Run sync_to_openclaw.py first.",
        }

    dossier_text = dossier_path.read_text(encoding="utf-8")
    sig = _load_timing_signal(buyer_key)
    tenders = _load_recent_tenders(buyer_key)

    # Extract fields from dossier
    def _field(marker: str) -> str:
        return _read_dossier_field(dossier_path, marker) or "not available"

    buyer_display = _field("**Buyer name:**")
    region = _field("**Region:**")
    activity_30d = _field("**Activity (30d):**")
    activity_90d = _field("**Activity (90d):**")
    total_notices = _field("**Total notices seen:**")
    typical_value = _field("**Typical value:**")
    top_cats = _field("**Top categories:**")
    timing_label = sig.get("timing_label") or _field("**Timing label:**").replace("🟢", "").replace("🟡", "").replace("⬜", "").strip()
    timing_conf = sig.get("timing_confidence") or _field("**Confidence:**").split("—")[0].strip()
    timing_status = sig.get("timing_status") or _field("**Status:**")
    window_start = sig.get("predicted_next_start") or "unknown"
    window_end = sig.get("predicted_next_end") or "unknown"
    action_note = sig.get("action_note") or _field("**Action note:**")
    fit = sig.get("fit_to_client")
    fit_str = f"{fit}%" if fit is not None else "not scored"
    outreach_priority = _field("**Outreach priority:**")
    outreach_status = _field("**Outreach status:**")
    brief_text = _field("**Buyer brief:**")
    contact_pattern = _field("**Contact pattern:**")
    freq = _field("**Procurement frequency:**")
    style = _field("**Style:**")

    # Operator notes (extract Memory Notes section)
    op_notes = ""
    mem_idx = dossier_text.find("## Memory Notes")
    if mem_idx != -1:
        raw_notes = dossier_text[mem_idx + len("## Memory Notes"):].strip()
        if raw_notes and not raw_notes.startswith("_Add free-text"):
            op_notes = raw_notes

    # Recent tenders block
    tender_lines = []
    for t in tenders:
        title = t.get("title") or "(no title)"
        date = (t.get("seen_at") or t.get("deadline_at") or "")[:10]
        value = t.get("value_amount")
        val_str = f"  £{int(value/1000)}k" if value else ""
        tender_lines.append(f"  - {date}: {title}{val_str}")

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# Contact Brief — {buyer_display}",
        f"_Generated: {now_str}_",
        "",
        "## Summary",
        f"- **Region:** {region}",
        f"- **Typical value:** {typical_value}",
        f"- **Procurement frequency:** {freq}",
        f"- **Style:** {style}",
        f"- **Contact pattern:** {contact_pattern}",
        f"- **Fit to client:** {fit_str}",
        "",
        "## Timing",
        f"- **Label:** {timing_label}",
        f"- **Confidence:** {timing_conf}",
        f"- **Status:** {timing_status}",
        f"- **Predicted window:** {window_start} → {window_end}",
        f"- **Action note:** {action_note}",
        "",
        "## Intelligence",
        f"- **Activity (30d):** {activity_30d}",
        f"- **Activity (90d):** {activity_90d}",
        f"- **Total notices:** {total_notices}",
        f"- **Top categories:** {top_cats}",
        f"- **Brief:** {brief_text}",
        "",
        "## Outreach state",
        f"- **Priority:** {outreach_priority}",
        f"- **Status:** {outreach_status}",
        "",
    ]
    if tender_lines:
        lines += ["## Recent tenders", ""] + tender_lines + [""]
    if op_notes:
        lines += ["## Operator notes", "", op_notes, ""]

    content = "\n".join(lines)

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXPORTS_DIR / f"{buyer_key}_contact_brief.md"
    out_path.write_text(content, encoding="utf-8")

    return {"status": "ok", "path": str(out_path), "content": content}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m outreach.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- original commands ---
    init_db_parser = subparsers.add_parser("init-db")
    init_db_parser.add_argument("--db-path", default=None)

    list_p = subparsers.add_parser("list-contacts")
    list_p.add_argument("--db-path", default=None)

    preview_p = subparsers.add_parser("preview-sample")
    preview_p.add_argument("--contact-id", type=int, required=True)
    preview_p.add_argument("--run-id", default=None)
    preview_p.add_argument("--db-path", default=None)
    preview_p.add_argument("--runs-dir", default=None)

    send_p = subparsers.add_parser("send-sample")
    send_p.add_argument("--contact-id", type=int, required=True)
    send_p.add_argument("--run-id", default=None)
    send_p.add_argument("--force", action="store_true")
    send_p.add_argument("--db-path", default=None)
    send_p.add_argument("--runs-dir", default=None)

    # --- Phase 1 action commands ---
    la_p = subparsers.add_parser("list-actions", help="List buyer actions")
    la_p.add_argument("--buyer", default=None, help="Filter by buyer name (converted to slug)")
    la_p.add_argument("--type", dest="action_type", default=None, choices=sorted(ACTION_TYPES))
    la_p.add_argument("--status", dest="action_status", default=None, choices=sorted(ACTION_STATUSES))
    la_p.add_argument("--limit", type=int, default=50)
    la_p.add_argument("--db-path", default=None)
    la_p.add_argument("--json", dest="as_json", action="store_true")

    ca_p = subparsers.add_parser("create-action", help="Create a new buyer action")
    ca_p.add_argument("--buyer", required=True, help="Buyer name (will be slugged)")
    ca_p.add_argument("--type", dest="action_type", required=True, choices=sorted(ACTION_TYPES))
    ca_p.add_argument("--status", dest="action_status", default=None, choices=sorted(ACTION_STATUSES))
    ca_p.add_argument("--run-id", default=None)
    ca_p.add_argument("--notes", default=None)
    ca_p.add_argument("--source", default="cli")
    ca_p.add_argument("--allow-duplicate", action="store_true",
                      help="Create even if an open action of the same type already exists")
    ca_p.add_argument("--db-path", default=None)

    ss_p = subparsers.add_parser("set-action-status", help="Update status of an existing action")
    ss_p.add_argument("--action-id", type=int, required=True)
    ss_p.add_argument("--status", dest="action_status", required=True, choices=sorted(ACTION_STATUSES))
    ss_p.add_argument("--notes", default=None)
    ss_p.add_argument("--db-path", default=None)

    bs_p = subparsers.add_parser("buyer-state", help="Show derived outreach state for a buyer")
    bs_p.add_argument("--buyer", required=True)
    bs_p.add_argument("--db-path", default=None)
    bs_p.add_argument("--json", dest="as_json", action="store_true")

    ecb_p = subparsers.add_parser("export-contact-brief", help="Generate and save a contact brief")
    ecb_p.add_argument("--buyer", required=True)
    ecb_p.add_argument("--print", dest="print_content", action="store_true",
                       help="Also print the brief to stdout")
    ecb_p.add_argument("--db-path", default=None)

    return parser


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db = Path(args.db_path).resolve() if getattr(args, "db_path", None) else None
    connection = connect(db)
    try:
        init_db(connection)
        runs_dir = Path(args.runs_dir).resolve() if getattr(args, "runs_dir", None) else None

        # --- original commands ---
        if args.command == "init-db":
            print(f"Initialized outreach DB at {db or db_path()}")
            return 0

        if args.command == "list-contacts":
            for contact in list_contacts(connection):
                print(
                    f"{contact['id']}: {contact['company_name']} | "
                    f"{contact.get('contact_name') or '-'} | "
                    f"{contact['preferred_channel']} | active={bool(contact['is_active'])}"
                )
            return 0

        if args.command == "preview-sample":
            result = preview_sample_for_contact(
                contact_id=args.contact_id, run_id=args.run_id,
                conn=connection, runs_dir=runs_dir,
            )
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            return 0 if result.get("status") == "preview" else 1

        if args.command == "send-sample":
            result = send_sample_to_contact(
                args.contact_id, run_id=args.run_id, force=args.force,
                conn=connection, runs_dir=runs_dir,
            )
            print(json.dumps(result, indent=2, sort_keys=True, default=str))
            return 0 if result.get("status") in {"sent", "duplicate_skipped"} else 1

        # --- Phase 1: action commands ---
        if args.command == "list-actions":
            buyer_key = _slug(args.buyer) if args.buyer else None
            actions = list_actions(
                connection,
                buyer_key=buyer_key,
                action_type=args.action_type,
                action_status=args.action_status,
                limit=args.limit,
            )
            if args.as_json:
                print(json.dumps(actions, indent=2))
                return 0
            if not actions:
                print("No actions found.")
                return 0
            print(_hr())
            print(f"BUYER ACTIONS ({len(actions)})")
            print(_hr())
            for a in actions:
                print(
                    f"  [{a['id']:4d}] {a['buyer_name']:<40s} "
                    f"{a['action_type']:<22s} {a['action_status']:<12s} "
                    f"{a['created_at'][:10]}"
                )
            return 0

        if args.command == "create-action":
            buyer_key = _slug(args.buyer)
            if not args.allow_duplicate and has_open_action_of_type(connection, buyer_key, args.action_type):
                print(
                    f"SKIPPED: '{args.buyer}' already has an open '{args.action_type}' action. "
                    f"Use --allow-duplicate to create anyway.",
                    file=sys.stderr,
                )
                return 1
            action_id = create_action(
                connection,
                buyer_key=buyer_key,
                buyer_name=args.buyer,
                action_type=args.action_type,
                action_status=args.action_status or "pending",
                run_id=args.run_id,
                notes=args.notes,
                source=args.source,
            )
            print(f"Created action #{action_id}: {args.buyer} / {args.action_type} -> {args.action_status or 'pending'}")
            print("# Dashboard is stale -- run: python scripts/build_dashboard_bundle.py", file=sys.stderr)
            return 0

        if args.command == "set-action-status":
            updated = update_action_status(
                connection,
                action_id=args.action_id,
                action_status=args.action_status,
                notes=args.notes,
            )
            if not updated:
                print(f"ERROR: No action found with id={args.action_id}", file=sys.stderr)
                return 1
            print(f"Action #{args.action_id} -> {args.action_status}")
            print("# Dashboard is stale -- run: python scripts/build_dashboard_bundle.py", file=sys.stderr)
            return 0

        if args.command == "buyer-state":
            buyer_key = _slug(args.buyer)
            state = buyer_current_state(connection, buyer_key)
            if args.as_json:
                print(json.dumps(state, indent=2))
                return 0
            print(_hr())
            print(f"BUYER STATE: {args.buyer}")
            print(_hr())
            print(f"  Overall status:  {state['overall_status']}")
            print(f"  Total actions:   {state['action_count']}")
            if state["latest_action"]:
                la = state["latest_action"]
                print(f"  Latest:          #{la['id']} {la['action_type']} → {la['action_status']}  ({la['updated_at'][:10]})")
            if state["all_actions"]:
                print()
                print("  History:")
                for a in state["all_actions"]:
                    notes_hint = f"  [{a['notes'][:40]}]" if a.get("notes") else ""
                    print(f"    [{a['id']:4d}] {a['action_type']:<22s} {a['action_status']:<12s} {a['updated_at'][:10]}{notes_hint}")
            return 0

        if args.command == "export-contact-brief":
            result = export_contact_brief(args.buyer, source="cli")
            if result["status"] == "error":
                print(f"ERROR: {result['error']}", file=sys.stderr)
                return 1
            print(f"Contact brief saved → {result['path']}")
            if args.print_content:
                print()
                print(result["content"])
            return 0

        parser.print_help()
        return 1

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    finally:
        connection.close()


def main() -> None:
    sys.exit(run_cli() or 0)


if __name__ == "__main__":
    main()
