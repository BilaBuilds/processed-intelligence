from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from enrichment.mailbox import ImapDraftClient, MailboxDraftConfig
from enrichment.agents.memory import HermesMemoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create mailbox drafts from Hermes outreach artifacts.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print drafts that would be created without connecting to IMAP.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Create drafts even if this artifact was already synced.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    artifacts = sorted((args.run_dir / "outreach").glob("*.json"))
    if not artifacts:
        print("No Hermes outreach artifacts found.")
        return 1

    client = None
    if not args.dry_run:
        client = ImapDraftClient(MailboxDraftConfig.from_env(REPO_ROOT / ".env"))

    sync_log = args.run_dir / "draft_sync_log.json"
    global_sync_log = REPO_ROOT / "data" / "hermes" / "memory" / "draft_sync_keys.json"
    synced = _load_sync_log(sync_log)
    global_synced = _load_sync_log(global_sync_log)
    global_synced.update(_load_historical_sync_logs(REPO_ROOT / "data" / "hermes" / "runs"))
    created = 0
    skipped = 0
    for artifact_path in artifacts:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        review = artifact.get("operator_review") or {}
        qa = artifact.get("truth_qa") or {}
        profile = artifact.get("research_profile") or {}
        policy = profile.get("policy_decision") or {}
        draft = artifact.get("draft") or {}

        if review.get("status") != "approval_ready" or not qa.get("passed"):
            skipped += 1
            continue
        if policy and not (policy.get("allowed") or policy.get("policy_allowed")):
            skipped += 1
            continue

        to = profile.get("email")
        subject = draft.get("subject")
        body = draft.get("body")
        if not to or not subject or not body:
            skipped += 1
            continue

        draft_key = _draft_key(to, subject, body)
        if (draft_key in synced or draft_key in global_synced) and not args.force:
            skipped += 1
            continue

        if args.dry_run:
            print(f"DRY RUN draft: to={to} subject={subject}")
        else:
            client.create_draft(to=to, subject=subject, body=body)
            synced[draft_key] = {
                "artifact": artifact_path.as_posix(),
                "to": to,
                "subject": subject,
            }
            _write_sync_log(sync_log, synced)
            global_synced[draft_key] = {
                "artifact": artifact_path.as_posix(),
                "run_dir": args.run_dir.as_posix(),
                "to": to,
                "subject": subject,
            }
            _write_sync_log(global_sync_log, global_synced)
        created += 1

    if not args.dry_run:
        HermesMemoryStore(REPO_ROOT / "data" / "hermes" / "memory").record_draft_sync(
            args.run_dir,
            created,
            skipped,
        )
    print(f"Drafts created: {created}; skipped: {skipped}")
    return 0


def _draft_key(to: str, subject: str, body: str) -> str:
    digest = hashlib.sha256(f"{to}\n{subject}\n{body}".encode("utf-8")).hexdigest()
    return digest[:24]


def _load_sync_log(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_sync_log(path: Path, data: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_historical_sync_logs(runs_root: Path) -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    if not runs_root.exists():
        return merged
    for path in runs_root.glob("*/draft_sync_log.json"):
        merged.update(_load_sync_log(path))
    return merged


if __name__ == "__main__":
    raise SystemExit(main())
