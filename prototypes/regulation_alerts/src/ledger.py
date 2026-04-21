import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Set

logger = logging.getLogger(__name__)


def _ledger_path(client_id: str, seen_dir: Path) -> Path:
    return seen_dir / f"{client_id}.jsonl"


def load_seen_ids(client_id: str, seen_dir: Path) -> Set[str]:
    """Return set of record IDs already seen by this client. Empty set if ledger missing."""
    path = _ledger_path(client_id, seen_dir)
    if not path.exists():
        return set()
    seen: Set[str] = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    seen.add(entry["id"])
    except Exception as e:
        logger.warning(f"[ledger] failed to load ledger for {client_id}: {e} — treating all as new")
        return set()
    return seen


def append_seen_ids(client_id: str, new_entries: List[dict], seen_dir: Path) -> None:
    """Atomically append new entries to the client's seen ledger.
    Writes existing + new content to .tmp then renames to final path.
    Non-fatal: logs and continues on any error.
    """
    if not new_entries:
        return
    try:
        seen_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"[ledger] failed to create seen_dir: {e} — skipping ledger write")
        return

    path = _ledger_path(client_id, seen_dir)
    tmp_path = path.with_suffix(".tmp")

    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        new_lines = "\n".join(
            json.dumps(e, ensure_ascii=True) for e in new_entries
        ) + "\n"

        with open(tmp_path, "w", encoding="utf-8") as f:
            if existing:
                f.write(existing)
                if not existing.endswith("\n"):
                    f.write("\n")
            f.write(new_lines)

        os.rename(tmp_path, path)
        logger.info(f"[ledger] appended {len(new_entries)} new id(s) for client {client_id}")
    except Exception as e:
        logger.warning(f"[ledger] failed to write ledger for {client_id}: {e} — continuing")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def make_ledger_entry(record_id: str, run_id: str) -> dict:
    return {
        "id": record_id,
        "first_seen_run": run_id,
        "first_seen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
