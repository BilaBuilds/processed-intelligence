from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import duckdb


DEFAULT_DB = Path(r"C:\Users\bilal\tender_engine\data\warehouse\procurement.duckdb")
DEFAULT_OUTPUT = Path("data/intelligence_exports")
DEFAULT_HERMES_OUTPUT = Path("data/hermes_handoff")

IMPORTANT_TABLES = ("tenders", "awards", "buyer_memory", "run_log")
SECRET_PATTERN = re.compile(
    r"(api[_-]?key|password|passwd|secret|token|bearer\s+[a-z0-9._-]+|"
    r"[a-f0-9]{32,}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
    re.IGNORECASE,
)
PLACEHOLDER_NAME_PATTERN = re.compile(
    r"^(unknown|n/?a|none|null|not supplied|not provided|tbc|tbd|various|multiple|\[redacted\])$",
    re.IGNORECASE,
)
PUBLIC_BUYER_PATTERN = re.compile(
    r"\b(council|borough|nhs|department|ministry|university|college|school|"
    r"authority|government|police|fire|parish|trust|agency|transport for london|"
    r"network rail|environment agency|home office|foreign[, ]+commonwealth|"
    r"mayor and commonalty|met office|research (and|&) innovation|"
    r"national highways|shared business services)\b",
    re.IGNORECASE,
)


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    output_dir = Path(args.output)
    hermes_dir = Path(args.hermes_output)
    output_dir.mkdir(parents=True, exist_ok=True)
    hermes_dir.mkdir(parents=True, exist_ok=True)

    exporter = WarehouseExporter(db_path, output_dir, hermes_dir)
    exporter.run()
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export client-safe warehouse intelligence files.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to procurement.duckdb")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Intelligence export directory")
    parser.add_argument(
        "--hermes-output",
        default=str(DEFAULT_HERMES_OUTPUT),
        help="Hermes CSV handoff directory",
    )
    return parser.parse_args()


class WarehouseExporter:
    def __init__(self, db_path: Path, output_dir: Path, hermes_dir: Path) -> None:
        self.db_path = db_path
        self.output_dir = output_dir
        self.hermes_dir = hermes_dir
        self.generated_at = datetime.now(UTC).isoformat()
        self.warnings: list[str] = []
        self.tables: dict[str, dict[str, Any]] = {}

    def run(self) -> None:
        if not self.db_path.exists():
            raise FileNotFoundError(f"DuckDB file not found: {self.db_path}")

        with duckdb.connect(str(self.db_path), read_only=True) as con:
            self.tables = self._inspect_schema(con)
            self._print_counts()
            self._export_top_buyers(con)
            self._export_recent_high_score_tenders(con)
            self._export_buyer_memory(con)
            self._export_awards_top_winners(con)
            self._export_monthly_tender_trends(con)
            self._export_hermes_company_targets(con)
            self._export_hermes_buyer_targets(con)
            self._export_hermes_flat_targets()
            self._export_summary()
            self._export_hermes_readme()
            self._export_inventory()

    def _inspect_schema(self, con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, Any]]:
        rows = con.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
            ORDER BY table_schema, table_name
            """
        ).fetchall()
        tables: dict[str, dict[str, Any]] = {}
        for schema, table in rows:
            key = str(table)
            count = con.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"').fetchone()[0]
            columns = con.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                ORDER BY ordinal_position
                """,
                [schema, table],
            ).fetchall()
            tables[key] = {
                "schema": schema,
                "row_count": int(count),
                "columns": {str(name): str(data_type) for name, data_type in columns},
            }
        return tables

    def _print_counts(self) -> None:
        print("Warehouse tables:")
        for table, meta in self.tables.items():
            print(f"- {table}: {meta['row_count']}")

    def _export_top_buyers(self, con: duckdb.DuckDBPyConnection) -> None:
        headers = ["buyer", "tender_count", "first_seen", "last_seen", "avg_score", "sources", "deadline_count"]
        if not self._has_table("tenders") or not self._first_col("tenders", ["buyer_name", "buyer"]):
            self._warning("top_buyers.csv created empty: tenders buyer column missing.")
            self._write_csv(self.output_dir / "top_buyers.csv", headers, [])
            return

        buyer_col = self._first_col("tenders", ["buyer_name", "buyer"])
        score_col = self._first_col("tenders", ["score", "opportunity_score"])
        date_col = self._date_col("tenders")
        deadline_col = self._first_col("tenders", ["deadline", "closing_date", "submission_deadline"])
        source_col = self._first_col("tenders", ["source", "source_name", "portal"])

        select_parts = [
            f"{self._q(buyer_col)} AS buyer",
            "COUNT(*) AS tender_count",
            f"MIN({self._q(date_col)}) AS first_seen" if date_col else "NULL AS first_seen",
            f"MAX({self._q(date_col)}) AS last_seen" if date_col else "NULL AS last_seen",
            f"AVG({self._q(score_col)}) AS avg_score" if score_col else "NULL AS avg_score",
            f"STRING_AGG(DISTINCT CAST({self._q(source_col)} AS VARCHAR), '; ') AS sources"
            if source_col
            else "'warehouse' AS sources",
            f"SUM(CASE WHEN {self._q(deadline_col)} IS NOT NULL THEN 1 ELSE 0 END) AS deadline_count"
            if deadline_col
            else "0 AS deadline_count",
        ]
        rows = con.execute(
            f"""
            SELECT {", ".join(select_parts)}
            FROM tenders
            WHERE {self._q(buyer_col)} IS NOT NULL AND TRIM(CAST({self._q(buyer_col)} AS VARCHAR)) <> ''
            GROUP BY {self._q(buyer_col)}
            ORDER BY tender_count DESC, last_seen DESC NULLS LAST
            LIMIT 250
            """
        ).fetchall()
        self._write_csv(self.output_dir / "top_buyers.csv", headers, self._rows(headers, rows))

    def _export_recent_high_score_tenders(self, con: duckdb.DuckDBPyConnection) -> None:
        headers = ["title", "buyer", "deadline", "source", "score", "published", "country_region", "url"]
        if not self._has_table("tenders"):
            self._warning("recent_high_score_tenders.csv created empty: tenders table missing.")
            self._write_csv(self.output_dir / "recent_high_score_tenders.csv", headers, [])
            return

        cols = self.tables["tenders"]["columns"]
        selected = [self._q(name) for name in cols.keys()]
        order_col = self._first_col("tenders", ["score", "published_at", "publication_date", "published", "created_at", "date"])
        order_expr = f"{self._q(order_col)} DESC NULLS LAST" if order_col else "1"
        rows = con.execute(f"SELECT {', '.join(selected)} FROM tenders ORDER BY {order_expr} LIMIT 250").fetchall()
        names = list(cols.keys())
        out_rows = []
        for row in rows:
            record = dict(zip(names, row))
            raw = self._safe_json(record.get("raw_json"))
            out_rows.append(
                {
                    "title": self._pick(record, raw, ["title", "notice_title", "name", "description"]),
                    "buyer": self._pick(record, raw, ["buyer_name", "buyer", "authority_name"]),
                    "deadline": self._pick(record, raw, ["deadline", "closing_date", "submission_deadline"]),
                    "source": self._pick(record, raw, ["source", "source_name", "portal"]) or "warehouse",
                    "score": self._pick(record, raw, ["score", "opportunity_score"]),
                    "published": self._pick(
                        record,
                        raw,
                        ["published_at", "publication_date", "published", "created_at", "date"],
                    ),
                    "country_region": self._pick(record, raw, ["country", "region", "location"]),
                    "url": self._domain_safe_url(self._pick(record, raw, ["url", "link", "notice_url"])),
                }
            )
        self._write_csv(self.output_dir / "recent_high_score_tenders.csv", headers, out_rows)

    def _export_buyer_memory(self, con: duckdb.DuckDBPyConnection) -> None:
        headers = ["buyer_id", "buyer", "category", "frequency", "last_seen", "confidence"]
        if not self._has_table("buyer_memory"):
            self._warning("buyer_memory_summary.csv created empty: buyer_memory table missing.")
            self._write_csv(self.output_dir / "buyer_memory_summary.csv", headers, [])
            return

        cols = self.tables["buyer_memory"]["columns"]
        buyer_col = self._first_col("buyer_memory", ["buyer_id", "buyer_name", "buyer"])
        category_col = self._first_col("buyer_memory", ["category", "dominant_cpv", "sector"])
        frequency_col = self._first_col("buyer_memory", ["frequency", "procurement_count", "tender_count"])
        last_seen_col = self._first_col("buyer_memory", ["last_seen", "updated_at"])
        confidence_col = self._first_col("buyer_memory", ["confidence"])
        selected = {
            "buyer_id": buyer_col,
            "buyer": buyer_col,
            "category": category_col,
            "frequency": frequency_col,
            "last_seen": last_seen_col,
            "confidence": confidence_col,
        }
        select_sql = [f"{self._q(col)} AS {alias}" if col else f"NULL AS {alias}" for alias, col in selected.items()]
        order_sql = self._q(frequency_col) + " DESC NULLS LAST" if frequency_col else "1"
        rows = con.execute(
            f"SELECT {', '.join(select_sql)} FROM buyer_memory ORDER BY {order_sql} LIMIT 250"
        ).fetchall()
        self._write_csv(self.output_dir / "buyer_memory_summary.csv", headers, self._rows(headers, rows))

    def _export_awards_top_winners(self, con: duckdb.DuckDBPyConnection) -> None:
        headers = ["winner", "award_count", "total_value", "avg_value", "latest_award_date"]
        if not self._has_table("awards"):
            self._warning("awards_top_winners.csv created empty: awards table missing.")
            self._write_csv(self.output_dir / "awards_top_winners.csv", headers, [])
            return

        winner_col = self._first_col("awards", ["supplier_name", "winner", "award_winner"])
        if not winner_col:
            self._warning("awards_top_winners.csv created empty: awards winner column missing.")
            self._write_csv(self.output_dir / "awards_top_winners.csv", headers, [])
            return
        value_col = self._first_col("awards", ["value_amount", "award_value", "contract_value", "value"])
        date_col = self._first_col("awards", ["award_date", "date", "created_at"])
        rows = con.execute(
            f"""
            SELECT
              {self._q(winner_col)} AS winner,
              COUNT(*) AS award_count,
              {f"SUM({self._q(value_col)})" if value_col else "NULL"} AS total_value,
              {f"AVG({self._q(value_col)})" if value_col else "NULL"} AS avg_value,
              {f"MAX({self._q(date_col)})" if date_col else "NULL"} AS latest_award_date
            FROM awards
            WHERE {self._q(winner_col)} IS NOT NULL AND TRIM(CAST({self._q(winner_col)} AS VARCHAR)) <> ''
            GROUP BY {self._q(winner_col)}
            ORDER BY award_count DESC, total_value DESC NULLS LAST
            LIMIT 250
            """
        ).fetchall()
        self._write_csv(self.output_dir / "awards_top_winners.csv", headers, self._rows(headers, rows))

    def _export_monthly_tender_trends(self, con: duckdb.DuckDBPyConnection) -> None:
        headers = ["month", "tender_count", "avg_score", "unique_buyers"]
        if not self._has_table("tenders"):
            self._warning("monthly_tender_trends.csv created empty: tenders table missing.")
            self._write_csv(self.output_dir / "monthly_tender_trends.csv", headers, [])
            return
        date_col = self._date_col("tenders")
        if not date_col:
            self._warning("monthly_tender_trends.csv created empty: no usable tender date column.")
            self._write_csv(self.output_dir / "monthly_tender_trends.csv", headers, [])
            return
        score_col = self._first_col("tenders", ["score", "opportunity_score"])
        buyer_col = self._first_col("tenders", ["buyer_name", "buyer"])
        rows = con.execute(
            f"""
            SELECT
              STRFTIME(CAST({self._q(date_col)} AS DATE), '%Y-%m') AS month,
              COUNT(*) AS tender_count,
              {f"AVG({self._q(score_col)})" if score_col else "NULL"} AS avg_score,
              {f"COUNT(DISTINCT {self._q(buyer_col)})" if buyer_col else "NULL"} AS unique_buyers
            FROM tenders
            WHERE {self._q(date_col)} IS NOT NULL
            GROUP BY 1
            ORDER BY 1 DESC
            LIMIT 120
            """
        ).fetchall()
        self._write_csv(self.output_dir / "monthly_tender_trends.csv", headers, self._rows(headers, rows))

    def _export_hermes_company_targets(self, con: duckdb.DuckDBPyConnection) -> None:
        headers = ["company_name", "domain", "target_type", "source", "evidence", "priority", "notes"]
        targets: list[dict[str, Any]] = []
        if self._has_table("awards") and self._first_col("awards", ["supplier_name", "winner", "award_winner"]):
            winner_col = self._first_col("awards", ["supplier_name", "winner", "award_winner"])
            value_col = self._first_col("awards", ["value_amount", "award_value", "value"])
            date_col = self._first_col("awards", ["award_date", "date", "created_at"])
            rows = con.execute(
                f"""
                SELECT
                  {self._q(winner_col)} AS company_name,
                  COUNT(*) AS award_count,
                  {f"SUM({self._q(value_col)})" if value_col else "NULL"} AS total_value,
                  {f"MAX({self._q(date_col)})" if date_col else "NULL"} AS latest_award_date
                FROM awards
                WHERE {self._q(winner_col)} IS NOT NULL AND TRIM(CAST({self._q(winner_col)} AS VARCHAR)) <> ''
                GROUP BY {self._q(winner_col)}
                ORDER BY award_count DESC, total_value DESC NULLS LAST
                LIMIT 300
                """
            ).fetchall()
            for name, award_count, total_value, latest in rows:
                clean_name = self._clean_text(name)
                if not self._is_valid_target_name(clean_name) or self._is_public_buyer(clean_name):
                    continue
                targets.append(
                    {
                        "company_name": clean_name,
                        "domain": "",
                        "target_type": "supplier_award_winner",
                        "source": "awards",
                        "evidence": f"{award_count} historical award(s); latest={self._value(latest)}",
                        "priority": self._priority(award_count, total_value),
                        "notes": "domain required",
                    }
                )
        if not targets:
            self._warning("hermes_company_targets.csv has no supplier targets; check awards table coverage.")
        self._write_csv(self.hermes_dir / "hermes_company_targets.csv", headers, targets)

    def _export_hermes_buyer_targets(self, con: duckdb.DuckDBPyConnection) -> None:
        headers = ["company_name", "domain", "buyer_name", "target_type", "tender_count", "evidence", "priority", "notes"]
        targets: list[dict[str, Any]] = []
        if self._has_table("tenders") and self._first_col("tenders", ["buyer_name", "buyer"]):
            buyer_col = self._first_col("tenders", ["buyer_name", "buyer"])
            rows = con.execute(
                f"""
                SELECT {self._q(buyer_col)} AS buyer_name, COUNT(*) AS tender_count
                FROM tenders
                WHERE {self._q(buyer_col)} IS NOT NULL AND TRIM(CAST({self._q(buyer_col)} AS VARCHAR)) <> ''
                GROUP BY {self._q(buyer_col)}
                ORDER BY tender_count DESC
                LIMIT 250
                """
            ).fetchall()
            for buyer, count in rows:
                clean_buyer = self._clean_text(buyer)
                if not self._is_valid_target_name(clean_buyer):
                    continue
                targets.append(
                    {
                        "company_name": clean_buyer,
                        "domain": "",
                        "buyer_name": clean_buyer,
                        "target_type": "public_sector_buyer" if self._is_public_buyer(clean_buyer) else "buyer",
                        "tender_count": count,
                        "evidence": f"{count} tender record(s) in local warehouse",
                        "priority": self._priority(count, None),
                        "notes": "buyer intelligence target; not a supplier outreach target",
                    }
                )
        if not targets:
            self._warning("hermes_buyer_targets.csv has no buyer targets; check tenders table coverage.")
        self._write_csv(self.hermes_dir / "hermes_buyer_targets.csv", headers, targets)

    def _export_hermes_flat_targets(self) -> None:
        company_path = self.hermes_dir / "hermes_company_targets.csv"
        buyer_path = self.hermes_dir / "hermes_buyer_targets.csv"
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        company_rows_added = self._append_flat_targets(rows, seen, company_path, include_public_buyers=False)
        if company_rows_added == 0:
            self._warning(
                "warehouse_targets_FOR_HERMES.csv contains headers only because no usable supplier/company targets were available."
            )
        self._write_csv(self.hermes_dir / "warehouse_targets_FOR_HERMES.csv", ["company_name", "domain"], rows[:500])

    def _append_flat_targets(
        self,
        rows: list[dict[str, str]],
        seen: set[str],
        path: Path,
        include_public_buyers: bool,
    ) -> int:
        added = 0
        if not path.exists():
            return added
        with path.open("r", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                target_type = str(row.get("target_type") or "")
                if not include_public_buyers and target_type == "public_sector_buyer":
                    continue
                name = self._clean_text(row.get("company_name"))
                if (
                    not self._is_valid_target_name(name)
                    or name.lower() in seen
                    or (not include_public_buyers and self._is_public_buyer(name))
                ):
                    continue
                seen.add(name.lower())
                rows.append({"company_name": name, "domain": self._domain(row.get("domain"))})
                added += 1
        return added

    def _export_summary(self) -> None:
        table_lines = [f"- {table}: {meta['row_count']} rows" for table, meta in self.tables.items()]
        warnings = "\n".join(f"- {warning}" for warning in self.warnings) or "- No structural warnings."
        top_buyers = self._preview_names(self.output_dir / "top_buyers.csv", "buyer")
        winners = self._preview_names(self.output_dir / "awards_top_winners.csv", "winner")
        summary = f"""# Commercial Signal Summary

Generated: {self.generated_at}

## Warehouse Contents
{chr(10).join(table_lines) if table_lines else "- No tables found."}

## Top Buyer Patterns
{top_buyers}

## Top Opportunity Patterns
- Use `recent_high_score_tenders.csv` to identify high-score, recent opportunities.
- Use `monthly_tender_trends.csv` to show buyer and market activity over time.
- Use `buyer_memory_summary.csv` to turn historical repeat activity into account-level intelligence.

## Top Award Winners
{winners}

## Caveats
{warnings}
- These exports are derived summaries. They are not a complete warehouse dump.
- Blank domains in Hermes handoff files require manual or enrichment-stage domain resolution.
- Do not claim inferred buyer intent, incumbent status, or win probability unless backed by evidence in the exported rows.

## Demo Use
- Dashboard: use top buyers, recent tenders, and monthly trends as proof of historical signal.
- Buyer reports: use buyer memory and top buyers to show repeat-procurement patterns.
- Outreach: use Hermes CSV targets only, never raw DuckDB files.
- Ask ProcessEd/RAG: use these clean files as curated seed context before adding governed retrieval.

## What Not To Claim Publicly
- Do not claim exclusive access to public procurement data.
- Do not claim named suppliers are guaranteed incumbents unless confirmed by award evidence.
- Do not expose row-level raw JSON, raw database files, credentials, logs, or local file paths in client materials.
"""
        (self.output_dir / "commercial_signal_summary.md").write_text(summary, encoding="utf-8")

    def _export_hermes_readme(self) -> None:
        readme = r"""# Hermes Warehouse Handoff

This folder contains client-safe CSV exports for Hermes. Hermes should receive CSV targets only, never raw DuckDB, SQLite, backup, log, or warehouse files.

## Files

- `hermes_company_targets.csv`: supplier and award-winner targets derived from awards where available.
- `hermes_buyer_targets.csv`: buyer intelligence targets. Public-sector buyers are marked as buyers, not supplier outreach targets.
- `warehouse_targets_FOR_HERMES.csv`: simplified `company_name,domain` file compatible with the Hermes runner.

Blank domains are expected when the warehouse does not contain a direct domain, URL, or email signal. Enrichment may be limited until domains are added manually or by a safe enrichment pass.

## Copy Into Hermes Project

```powershell
Copy-Item "C:\Users\bilal\tender_engine_pilot\data\hermes_handoff\warehouse_targets_FOR_HERMES.csv" "C:\Users\bilal\OneDrive\Documents\Playground 3\data\leads\warehouse_targets_FOR_HERMES.csv" -Force
```

## Run Hermes

```powershell
cd "C:\Users\bilal\OneDrive\Documents\Playground 3"
python scripts\run_hermes.py --input data\leads\warehouse_targets_FOR_HERMES.csv
```

Suggested next target list: UK construction contractors, award winners, suppliers with repeated public-sector wins, framework-heavy firms, and high-fit companies with clear domains.
"""
        (self.hermes_dir / "README.md").write_text(readme, encoding="utf-8")

    def _export_inventory(self) -> None:
        inventory = {
            "db_path": str(self.db_path),
            "generated_at": self.generated_at,
            "tables_found": sorted(self.tables.keys()),
            "row_counts": {table: meta["row_count"] for table, meta in self.tables.items()},
            "available_columns": {
                table: sorted(meta["columns"].keys())
                for table, meta in self.tables.items()
                if table in IMPORTANT_TABLES
            },
            "warnings": self.warnings,
        }
        self._write_json(self.output_dir / "warehouse_inventory.json", inventory)

    def _has_table(self, table: str) -> bool:
        return table in self.tables

    def _first_col(self, table: str, candidates: list[str]) -> str | None:
        if not self._has_table(table):
            return None
        lower_map = {name.lower(): name for name in self.tables[table]["columns"].keys()}
        for candidate in candidates:
            if candidate.lower() in lower_map:
                return lower_map[candidate.lower()]
        return None

    def _date_col(self, table: str) -> str | None:
        return self._first_col(table, ["publication_date", "published", "published_at", "created_at", "date", "deadline"])

    def _q(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _rows(self, headers: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
        return [dict(zip(headers, row)) for row in rows]

    def _write_csv(self, path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({header: self._safe_cell(row.get(header)) for header in headers})

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._sanitize(payload), indent=2, default=str), encoding="utf-8")

    def _warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def _safe_json(self, raw: Any) -> dict[str, Any]:
        if raw is None:
            return {}
        try:
            parsed = json.loads(str(raw))
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _pick(self, record: dict[str, Any], raw: dict[str, Any], keys: list[str]) -> Any:
        lower_record = {str(key).lower(): value for key, value in record.items()}
        lower_raw = {str(key).lower(): value for key, value in raw.items()}
        for key in keys:
            for source in (lower_record, lower_raw):
                value = source.get(key.lower())
                if value not in (None, ""):
                    return value
        return ""

    def _safe_cell(self, value: Any) -> str:
        text = self._value(value)
        if SECRET_PATTERN.search(text):
            return "[REDACTED]"
        return text

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {self._safe_cell(key): self._sanitize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, str):
            return self._safe_cell(value)
        return value

    def _value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    def _clean_text(self, value: Any) -> str:
        text = self._safe_cell(value).strip()
        return re.sub(r"\s+", " ", text)

    def _domain_safe_url(self, value: Any) -> str:
        text = self._safe_cell(value).strip()
        if not text or text == "[REDACTED]":
            return ""
        try:
            parsed = urlparse(text if "://" in text else "https://" + text)
        except ValueError:
            return ""
        if not parsed.netloc:
            return ""
        return text

    def _domain(self, value: Any) -> str:
        text = self._safe_cell(value).strip().lower()
        if not text or text == "[redacted]":
            return ""
        try:
            parsed = urlparse(text if "://" in text else "https://" + text)
        except ValueError:
            return ""
        host = parsed.netloc or parsed.path.split("/")[0]
        host = host.removeprefix("www.")
        if "." not in host or SECRET_PATTERN.search(host):
            return ""
        return host

    def _is_public_buyer(self, name: str) -> bool:
        return bool(PUBLIC_BUYER_PATTERN.search(name))

    def _is_valid_target_name(self, name: str) -> bool:
        return bool(name) and not PLACEHOLDER_NAME_PATTERN.match(name.strip())

    def _priority(self, count: Any, value: Any) -> str:
        try:
            numeric_count = float(count or 0)
            numeric_value = float(value or 0)
        except (TypeError, ValueError):
            numeric_count = 0
            numeric_value = 0
        if numeric_count >= 10 or numeric_value >= 5_000_000:
            return "high"
        if numeric_count >= 3 or numeric_value >= 500_000:
            return "medium"
        return "low"

    def _preview_names(self, path: Path, column: str) -> str:
        if not path.exists():
            return "- Not available."
        names: list[str] = []
        with path.open("r", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                value = self._clean_text(row.get(column))
                if value:
                    names.append(value)
                if len(names) >= 10:
                    break
        if not names:
            return "- No rows available."
        counts = Counter(names)
        return "\n".join(f"- {name}" for name in counts.keys())


if __name__ == "__main__":
    raise SystemExit(main())
