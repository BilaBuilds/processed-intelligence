from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_SUPPRESSION_DB = Path("data/hermes/memory/suppression.sqlite3")


class SuppressionList:
    def __init__(self, db_path: str | Path = DEFAULT_SUPPRESSION_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def is_suppressed(self, email: str | None) -> bool:
        normalized = self._normalize_email(email)
        if not normalized:
            return False
        with closing(self._connect()) as connection:
            with connection:
                row = connection.execute(
                    "SELECT 1 FROM suppression_list WHERE email = ? LIMIT 1",
                    (normalized,),
                ).fetchone()
        return row is not None

    def add(self, email: str, reason: str, source: str) -> None:
        normalized = self._normalize_email(email)
        if not normalized:
            raise ValueError("email is required for suppression")
        timestamp = datetime.now(UTC).isoformat()
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO suppression_list(email, reason, added_at, source)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(email) DO UPDATE SET
                        reason = excluded.reason,
                        added_at = excluded.added_at,
                        source = excluded.source
                    """,
                    (normalized, reason, timestamp, source),
                )

    def bulk_import(self, csv_path: str | Path) -> int:
        imported = 0
        with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                email = row.get("email") or row.get("Email") or row.get("EMAIL")
                if not self._normalize_email(email):
                    continue
                self.add(
                    str(email),
                    row.get("reason") or row.get("Reason") or "manual_import",
                    row.get("source") or row.get("Source") or "bulk_import",
                )
                imported += 1
        return imported

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS suppression_list (
                        email TEXT PRIMARY KEY,
                        reason TEXT,
                        added_at TIMESTAMP,
                        source TEXT
                    )
                    """
                )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _normalize_email(self, email: str | None) -> str:
        if not email:
            return ""
        normalized = str(email).strip().casefold()
        return normalized if "@" in normalized else ""


def ingest_bounce_or_unsubscribe(
    email: str,
    event_type: str,
    source: str = "mailbox_event",
    suppression_list: SuppressionList | None = None,
) -> None:
    if event_type not in {"bounce", "unsubscribe", "opt_out", "complaint"}:
        raise ValueError("event_type must be bounce, unsubscribe, opt_out, or complaint")
    store = suppression_list or SuppressionList()
    store.add(email, reason=event_type, source=source)
