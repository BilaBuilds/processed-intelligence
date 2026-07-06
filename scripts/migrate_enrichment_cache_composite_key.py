from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


REPORT_FIELDS = (
    "company_name",
    "domain",
    "status",
    "domain_source",
    "source",
    "cached_at",
    "reason",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate enrichment cache from company-only keys to company+domain keys."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("enrichment_cache.sqlite3"),
        help="Path to enrichment cache SQLite database.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("migration_report.csv"),
        help="CSV report path for manual review rows.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    migrate_cache(args.db, args.report)
    return 0


def migrate_cache(db_path: Path, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        with connection:
            if not _table_exists(connection):
                _create_new_schema(connection)
                _write_report(report_path, [])
                return

            if _has_composite_schema(connection):
                _write_report(report_path, _review_existing_unknown_rows(connection))
                return

            legacy_rows = connection.execute(
                "SELECT company_name, record_json, source, cached_at FROM enrichment_cache"
            ).fetchall()
            connection.execute("ALTER TABLE enrichment_cache RENAME TO enrichment_cache_legacy")
            _create_new_schema(connection)

            report_rows: list[dict[str, str]] = []
            for company_name, record_json, source, cached_at in legacy_rows:
                domain, domain_source = _infer_domain(record_json)
                status = "migrated" if domain != "unknown" else "manual_review"
                reason = (
                    "domain inferred from cached record"
                    if domain != "unknown"
                    else "could not infer domain confidently; preserved with domain=unknown"
                )
                connection.execute(
                    """
                    INSERT OR REPLACE INTO enrichment_cache (
                        company_name, domain, record_json, source, cached_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (company_name, domain, record_json, source, cached_at),
                )
                report_rows.append(
                    {
                        "company_name": company_name,
                        "domain": domain,
                        "status": status,
                        "domain_source": domain_source,
                        "source": source or "",
                        "cached_at": cached_at,
                        "reason": reason,
                    }
                )

            connection.execute("DROP TABLE enrichment_cache_legacy")
            _write_report(report_path, report_rows)


def _table_exists(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'enrichment_cache'
            """
        ).fetchone()
        is not None
    )


def _has_composite_schema(connection: sqlite3.Connection) -> bool:
    columns = connection.execute("PRAGMA table_info(enrichment_cache)").fetchall()
    primary_key_columns = [row[1] for row in sorted(columns, key=lambda item: item[5]) if row[5]]
    return primary_key_columns == ["company_name", "domain"]


def _create_new_schema(connection: sqlite3.Connection) -> None:
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


def _review_existing_unknown_rows(connection: sqlite3.Connection) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT company_name, domain, source, cached_at
        FROM enrichment_cache
        WHERE domain = 'unknown'
        """
    ).fetchall()
    return [
        {
            "company_name": company_name,
            "domain": domain,
            "status": "manual_review",
            "domain_source": "unknown",
            "source": source or "",
            "cached_at": cached_at,
            "reason": "existing composite row uses domain=unknown",
        }
        for company_name, domain, source, cached_at in rows
    ]


def _infer_domain(record_json: str) -> tuple[str, str]:
    try:
        payload = json.loads(record_json)
    except json.JSONDecodeError:
        return "unknown", "invalid_record_json"
    if not isinstance(payload, dict):
        return "unknown", "invalid_record_json"

    raw = payload.get("raw")
    if isinstance(raw, dict):
        for key in ("domain", "website", "url", "best_url", "source_url"):
            domain = _normalize_domain(raw.get(key))
            if domain != "unknown":
                return domain, f"raw.{key}"
        company_profile = raw.get("company_profile")
        if isinstance(company_profile, dict):
            domain = _normalize_domain(company_profile.get("domain"))
            if domain != "unknown":
                return domain, "raw.company_profile.domain"

    email = payload.get("email")
    if isinstance(email, str) and "@" in email:
        domain = _normalize_domain(email.rsplit("@", maxsplit=1)[1])
        if domain != "unknown":
            return domain, "email_domain"

    return "unknown", "unknown"


def _normalize_domain(domain: object) -> str:
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


def _write_report(report_path: Path, rows: list[dict[str, str]]) -> None:
    with report_path.open("w", encoding="utf-8", newline="") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
