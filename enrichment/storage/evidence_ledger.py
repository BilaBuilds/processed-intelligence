from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from enrichment.models.evidence import EvidenceItem


DEFAULT_EVIDENCE_LEDGER_DB = Path("data/evidence/evidence_ledger.sqlite3")


class EvidenceLedger:
    def __init__(self, path: str | Path = DEFAULT_EVIDENCE_LEDGER_DB) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def store(self, evidence: EvidenceItem) -> str:
        evidence_id = evidence.evidence_id or self._evidence_id(evidence)
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence_ledger (
                    id,
                    entity_type,
                    entity_key,
                    field_name,
                    field_value_json,
                    source_provider,
                    source_url,
                    source_ref,
                    evidence_type,
                    confidence,
                    collected_at,
                    expires_at,
                    raw_snippet,
                    reasoning_note,
                    client_safe,
                    run_id,
                    created_at,
                    conflict
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_key, field_name, source_provider, collected_at)
                DO UPDATE SET
                    field_value_json = excluded.field_value_json,
                    source_url = excluded.source_url,
                    source_ref = excluded.source_ref,
                    evidence_type = excluded.evidence_type,
                    confidence = excluded.confidence,
                    expires_at = excluded.expires_at,
                    raw_snippet = excluded.raw_snippet,
                    reasoning_note = excluded.reasoning_note,
                    client_safe = excluded.client_safe,
                    run_id = excluded.run_id,
                    conflict = excluded.conflict
                """,
                (
                    evidence_id,
                    evidence.entity_type,
                    evidence.entity_key,
                    evidence.field_name,
                    json.dumps(evidence.field_value, sort_keys=True),
                    evidence.source_provider,
                    evidence.source_url,
                    evidence.source_ref,
                    evidence.evidence_type,
                    evidence.confidence,
                    evidence.collected_at.isoformat(),
                    evidence.expires_at.isoformat() if evidence.expires_at else None,
                    evidence.raw_snippet,
                    evidence.reasoning_note,
                    int(evidence.client_safe),
                    evidence.run_id,
                    created_at,
                    int(evidence.conflict),
                ),
            )
        return evidence_id

    def get_by_entity_key(self, entity_key: str) -> list[EvidenceItem]:
        return self._query(
            "SELECT * FROM evidence_ledger WHERE entity_key = ? ORDER BY collected_at DESC",
            (entity_key,),
        )

    def get_by_field(self, entity_key: str, field_name: str) -> list[EvidenceItem]:
        return self._query(
            """
            SELECT * FROM evidence_ledger
            WHERE entity_key = ? AND field_name = ?
            ORDER BY confidence DESC, collected_at DESC
            """,
            (entity_key, field_name),
        )

    def get_client_safe(
        self,
        entity_key: str,
        min_confidence: float = 0.75,
    ) -> list[EvidenceItem]:
        now = datetime.now(UTC).isoformat()
        return self._query(
            """
            SELECT * FROM evidence_ledger
            WHERE entity_key = ?
              AND client_safe = 1
              AND confidence >= ?
              AND evidence_type = 'observed'
              AND conflict = 0
              AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY field_name, confidence DESC, collected_at DESC
            """,
            (entity_key, min_confidence, now),
        )

    def get_for_export(self, run_id: str) -> list[EvidenceItem]:
        return self._query(
            "SELECT * FROM evidence_ledger WHERE run_id = ? ORDER BY entity_key, field_name",
            (run_id,),
        )

    def mark_expired(self, before_date: datetime) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE evidence_ledger
                SET expires_at = ?
                WHERE collected_at < ? AND (expires_at IS NULL OR expires_at > ?)
                """,
                (now, before_date.isoformat(), now),
            )
            return int(cursor.rowcount)

    def mark_conflicts(self, entity_key: str, field_name: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE evidence_ledger
                SET conflict = 1
                WHERE entity_key = ? AND field_name = ?
                """,
                (entity_key, field_name),
            )
            return int(cursor.rowcount)

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_ledger (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    field_value_json TEXT NOT NULL,
                    source_provider TEXT NOT NULL,
                    source_url TEXT,
                    source_ref TEXT,
                    evidence_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    collected_at TEXT NOT NULL,
                    expires_at TEXT,
                    raw_snippet TEXT,
                    reasoning_note TEXT,
                    client_safe INTEGER NOT NULL,
                    run_id TEXT,
                    created_at TEXT NOT NULL,
                    conflict INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(entity_key, field_name, source_provider, collected_at)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity_key ON evidence_ledger(entity_key)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_field_name ON evidence_ledger(field_name)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_source_provider ON evidence_ledger(source_provider)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_confidence ON evidence_ledger(confidence DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_safe ON evidence_ledger(client_safe)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_expires_at ON evidence_ledger(expires_at)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _query(self, sql: str, params: tuple[Any, ...]) -> list[EvidenceItem]:
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_evidence(row) for row in rows]

    def _row_to_evidence(self, row: sqlite3.Row) -> EvidenceItem:
        return EvidenceItem(
            entity_type=row["entity_type"],
            entity_key=row["entity_key"],
            field_name=row["field_name"],
            field_value=json.loads(row["field_value_json"]),
            source_provider=row["source_provider"],
            source_url=row["source_url"],
            source_ref=row["source_ref"],
            evidence_type=row["evidence_type"],
            confidence=float(row["confidence"]),
            collected_at=datetime.fromisoformat(row["collected_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            raw_snippet=row["raw_snippet"],
            reasoning_note=row["reasoning_note"],
            client_safe=bool(row["client_safe"]),
            run_id=row["run_id"],
            conflict=bool(row["conflict"]),
            evidence_id=row["id"],
        )

    def _evidence_id(self, evidence: EvidenceItem) -> str:
        payload = {
            "entity_key": evidence.entity_key,
            "field_name": evidence.field_name,
            "field_value": evidence.field_value,
            "source_provider": evidence.source_provider,
            "collected_at": evidence.collected_at.isoformat(),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
