from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from enrichment.models import ContactRecord


class EnrichmentCache:
    NOT_FOUND_SOURCE = "not_found"

    def __init__(
        self,
        path: str | Path = "enrichment_cache.sqlite3",
        ttl: timedelta = timedelta(days=30),
        not_found_ttl: timedelta = timedelta(days=7),
    ) -> None:
        self.path = Path(path)
        self.ttl = ttl
        self.not_found_ttl = not_found_ttl
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get(self, company_name: str, domain: str | None = None) -> ContactRecord | None:
        record = self.get_cached_record(company_name, domain)
        if record is None or record.source == self.NOT_FOUND_SOURCE:
            return None
        return record

    def get_cached_record(
        self,
        company_name: str,
        domain: str | None = None,
    ) -> ContactRecord | None:
        cache_key = self._cache_key(company_name)
        domain_key = self._domain_key(domain)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT record_json, source, cached_at
                FROM enrichment_cache
                WHERE company_name = ? AND domain = ?
                """,
                (cache_key, domain_key),
            ).fetchone()

        if row is None:
            return None

        record_json, source, cached_at = row
        if self._is_expired(cached_at, source):
            return None

        return ContactRecord(**json.loads(record_json))

    def set(
        self,
        company_name: str,
        record: ContactRecord,
        domain: str | None = None,
    ) -> None:
        cache_key = self._cache_key(company_name)
        domain_key = self._domain_key(domain)
        cached_at = datetime.now(UTC).isoformat()
        record_json = json.dumps(asdict(record), sort_keys=True)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO enrichment_cache (
                    company_name,
                    domain,
                    record_json,
                    source,
                    cached_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(company_name, domain) DO UPDATE SET
                    record_json = excluded.record_json,
                    source = excluded.source,
                    cached_at = excluded.cached_at
                """,
                (cache_key, domain_key, record_json, record.source, cached_at),
            )

    def set_not_found(self, company_name: str, domain: str | None = None) -> None:
        self.set(
            company_name,
            ContactRecord(
                company=company_name,
                source=self.NOT_FOUND_SOURCE,
                confidence=0.0,
                raw={"status": self.NOT_FOUND_SOURCE, "domain": self._domain_key(domain)},
            ),
            domain,
        )

    def invalidate(self, company_name: str, domain: str | None = None) -> None:
        cache_key = self._cache_key(company_name)
        domain_key = self._domain_key(domain)
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM enrichment_cache
                WHERE company_name = ? AND domain = ?
                """,
                (cache_key, domain_key),
            )

    def _init_db(self) -> None:
        with self._connect() as connection:
            if self._needs_schema_rebuild(connection):
                self._rebuild_legacy_schema(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS enrichment_cache (
                    company_name TEXT NOT NULL,
                    domain TEXT NOT NULL DEFAULT 'unknown',
                    record_json TEXT NOT NULL,
                    source TEXT,
                    cached_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (company_name, domain)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_enrichment_cache_domain
                ON enrichment_cache(domain)
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _is_expired(self, cached_at: str, source: str | None = None) -> bool:
        cached_datetime = datetime.fromisoformat(cached_at)
        if cached_datetime.tzinfo is None:
            cached_datetime = cached_datetime.replace(tzinfo=UTC)
        ttl = self.not_found_ttl if source == self.NOT_FOUND_SOURCE else self.ttl
        return datetime.now(UTC) - cached_datetime > ttl

    def _cache_key(self, company_name: str) -> str:
        return " ".join(company_name.casefold().split())

    def _domain_key(self, domain: str | None) -> str:
        if not domain:
            return "unknown"
        value = str(domain).strip().casefold()
        if not value:
            return "unknown"
        if "://" not in value:
            value = f"//{value}"
        parsed = urlparse(value)
        host = parsed.netloc or parsed.path
        host = host.split("/", maxsplit=1)[0].split(":", maxsplit=1)[0]
        host = host.removeprefix("www.").strip(".")
        return host or "unknown"

    def _needs_schema_rebuild(self, connection: sqlite3.Connection) -> bool:
        table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'enrichment_cache'
            """
        ).fetchone()
        if table is None:
            return False
        columns = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(enrichment_cache)").fetchall()
        }
        if "domain" not in columns:
            return True
        primary_key_columns = [
            row[1]
            for row in sorted(
                connection.execute("PRAGMA table_info(enrichment_cache)").fetchall(),
                key=lambda item: item[5],
            )
            if row[5]
        ]
        return primary_key_columns != ["company_name", "domain"]

    def _rebuild_legacy_schema(self, connection: sqlite3.Connection) -> None:
        legacy_name = "enrichment_cache_legacy"
        connection.execute(f"DROP TABLE IF EXISTS {legacy_name}")
        connection.execute(f"ALTER TABLE enrichment_cache RENAME TO {legacy_name}")
        connection.execute(
            """
            CREATE TABLE enrichment_cache (
                company_name TEXT NOT NULL,
                domain TEXT NOT NULL DEFAULT 'unknown',
                record_json TEXT NOT NULL,
                source TEXT,
                cached_at TIMESTAMP NOT NULL,
                PRIMARY KEY (company_name, domain)
            )
            """
        )
        rows = connection.execute(
            f"SELECT company_name, record_json, source, cached_at FROM {legacy_name}"
        ).fetchall()
        for company_name, record_json, source, cached_at in rows:
            domain = self._domain_from_record_json(record_json)
            connection.execute(
                """
                INSERT OR REPLACE INTO enrichment_cache (
                    company_name, domain, record_json, source, cached_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (company_name, domain, record_json, source, cached_at),
            )
        connection.execute(f"DROP TABLE IF EXISTS {legacy_name}")

    def _domain_from_record_json(self, record_json: str) -> str:
        try:
            payload = json.loads(record_json)
        except json.JSONDecodeError:
            return "unknown"
        raw = payload.get("raw") if isinstance(payload, dict) else None
        if isinstance(raw, dict):
            for key in ("domain", "website", "url", "best_url", "source_url"):
                if raw.get(key):
                    return self._domain_key(str(raw[key]))
            company_profile = raw.get("company_profile")
            if isinstance(company_profile, dict) and company_profile.get("domain"):
                return self._domain_key(str(company_profile["domain"]))
        email = payload.get("email") if isinstance(payload, dict) else None
        if isinstance(email, str) and "@" in email:
            return self._domain_key(email.rsplit("@", maxsplit=1)[1])
        return "unknown"
