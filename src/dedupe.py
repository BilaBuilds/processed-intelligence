"""
src/dedupe.py
=============
Step 6 - Dedupe Gate

Checks the shortlist against the persistent sent_log (SQLite).
Only passes through tenders we have never notified about before.

Stable key priority:
    id -> raw_id -> url -> title (last resort)

The sent_log lives in /state/sent_log.sqlite and persists across runs.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("dedupe")

STATE_DIR = Path(__file__).parent.parent / "state"
SENT_LOG_DB = STATE_DIR / "sent_log.sqlite"


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_log (
            key        TEXT PRIMARY KEY,
            title      TEXT,
            source     TEXT,
            run_id     TEXT,
            posted_at  TEXT
        )
        """
    )
    conn.commit()


def opp_key(rec: dict) -> str:
    """Return the most stable unique key for a tender record."""
    return (
        str(rec.get("id") or "").strip()
        or str(rec.get("raw_id") or "").strip()
        or str(rec.get("url") or "").strip()
        or str(rec.get("title") or "").strip()
    )


def load_sent_keys(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT key FROM sent_log").fetchall()
    return {row[0] for row in rows}


def mark_as_sent(conn: sqlite3.Connection, records: list[dict], run_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT OR IGNORE INTO sent_log (key, title, source, run_id, posted_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (opp_key(r), r.get("title"), r.get("source"), run_id, now)
            for r in records
        ],
    )
    conn.commit()


def run(context: dict) -> dict:
    shortlist_file: Path = context["shortlist_file"]
    run_dir: Path = context["run_dir"]
    run_id: str = run_dir.name

    STATE_DIR.mkdir(exist_ok=True)

    with open(shortlist_file, encoding="utf-8") as f:
        data = json.load(f)

    shortlist: list[dict] = data.get("opportunities", [])

    with sqlite3.connect(SENT_LOG_DB) as conn:
        init_db(conn)
        sent_keys = load_sent_keys(conn)

        new_records: list[dict] = []
        seen_in_batch: set[str] = set()
        already_seen_previous = 0
        duplicate_in_batch = 0
        missing_key = 0
        for rec in shortlist:
            key = opp_key(rec)
            if not key:
                missing_key += 1
                continue
            if key in sent_keys:
                already_seen_previous += 1
                continue
            if key in seen_in_batch:
                duplicate_in_batch += 1
                continue
            seen_in_batch.add(key)
            new_records.append(rec)

        already_seen_in_shortlist = already_seen_previous + duplicate_in_batch

        if not new_records:
            log.info(
                "Dedupe: all %d shortlisted tenders already sent - nothing new.",
                len(shortlist),
            )
        else:
            log.info(
                "Dedupe: %d new (of %d shortlisted, %d already seen, %d duplicates in batch)",
                len(new_records),
                len(shortlist),
                already_seen_in_shortlist,
                duplicate_in_batch,
            )
            mark_as_sent(conn, new_records, run_id)

    deduped_file = run_dir / "new_tenders.json"
    with open(deduped_file, "w", encoding="utf-8") as f:
        json.dump({"opportunities": new_records}, f, indent=2, default=str)

    return {
        "new_count": len(new_records),
        "deduped_file": deduped_file,
        "dedupe_input_count": len(shortlist),
        "dedupe_new_count": len(new_records),
        "dedupe_already_seen_count": already_seen_in_shortlist,
        "dedupe_previously_seen_count": already_seen_previous,
        "dedupe_batch_duplicate_count": duplicate_in_batch,
        "dedupe_missing_key_count": missing_key,
    }
