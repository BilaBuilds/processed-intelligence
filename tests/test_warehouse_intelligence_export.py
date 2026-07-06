from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import duckdb


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "warehouse_intelligence_export.py"


def test_warehouse_intelligence_export_creates_safe_outputs(tmp_path: Path) -> None:
    db_path = tmp_path / "procurement.duckdb"
    output_dir = tmp_path / "intelligence_exports"
    hermes_dir = tmp_path / "hermes_handoff"
    _create_full_db(db_path)

    before_tables = _tables(db_path)
    before_tender_count = _count(db_path, "tenders")

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db_path),
            "--output",
            str(output_dir),
            "--hermes-output",
            str(hermes_dir),
        ],
        check=True,
        cwd=SCRIPT.parents[1],
    )

    expected_files = [
        output_dir / "warehouse_inventory.json",
        output_dir / "top_buyers.csv",
        output_dir / "recent_high_score_tenders.csv",
        output_dir / "buyer_memory_summary.csv",
        output_dir / "awards_top_winners.csv",
        output_dir / "monthly_tender_trends.csv",
        output_dir / "commercial_signal_summary.md",
        hermes_dir / "hermes_company_targets.csv",
        hermes_dir / "hermes_buyer_targets.csv",
        hermes_dir / "README.md",
        hermes_dir / "warehouse_targets_FOR_HERMES.csv",
    ]
    for path in expected_files:
        assert path.exists(), path

    inventory = json.loads((output_dir / "warehouse_inventory.json").read_text(encoding="utf-8"))
    assert inventory["row_counts"]["tenders"] == 2
    assert inventory["row_counts"]["awards"] == 2
    assert "buyer_name" in inventory["available_columns"]["tenders"]

    with (hermes_dir / "warehouse_targets_FOR_HERMES.csv").open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert set(rows[0]) == {"company_name", "domain"}

    assert _tables(db_path) == before_tables
    assert _count(db_path, "tenders") == before_tender_count
    assert not list(output_dir.rglob("*.duckdb"))
    assert not list(output_dir.rglob("*.db"))
    assert not list(hermes_dir.rglob("*.duckdb"))
    assert not list(hermes_dir.rglob("*.db"))

    combined_output = "\n".join(path.read_text(encoding="utf-8") for path in expected_files)
    assert "API_KEY" not in combined_output
    assert "PASSWORD" not in combined_output
    assert "TOKEN" not in combined_output


def test_warehouse_intelligence_export_handles_missing_optional_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "minimal.duckdb"
    output_dir = tmp_path / "intelligence_exports"
    hermes_dir = tmp_path / "hermes_handoff"
    with duckdb.connect(str(db_path)) as con:
        con.execute(
            """
            CREATE TABLE tenders (
                buyer_name VARCHAR,
                score FLOAT,
                published_at DATE,
                raw_json VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO tenders VALUES
            ('Example Council', 91.0, '2026-07-01', '{"title":"Drainage works"}')
            """
        )

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db_path),
            "--output",
            str(output_dir),
            "--hermes-output",
            str(hermes_dir),
        ],
        check=True,
        cwd=SCRIPT.parents[1],
    )

    buyer_memory_rows = list(csv.DictReader((output_dir / "buyer_memory_summary.csv").open()))
    awards_rows = list(csv.DictReader((output_dir / "awards_top_winners.csv").open()))
    inventory = json.loads((output_dir / "warehouse_inventory.json").read_text(encoding="utf-8"))

    assert buyer_memory_rows == []
    assert awards_rows == []
    assert any("buyer_memory table missing" in warning for warning in inventory["warnings"])
    assert any("awards table missing" in warning for warning in inventory["warnings"])
    assert (hermes_dir / "warehouse_targets_FOR_HERMES.csv").exists()


def _create_full_db(db_path: Path) -> None:
    with duckdb.connect(str(db_path)) as con:
        con.execute(
            """
            CREATE TABLE tenders (
                notice_id VARCHAR,
                buyer_name VARCHAR,
                region VARCHAR,
                cpv_code VARCHAR,
                value_amount FLOAT,
                published_at DATE,
                status VARCHAR,
                selection_bucket VARCHAR,
                score FLOAT,
                rejection_reasons VARCHAR,
                run_date DATE,
                created_at TIMESTAMP,
                raw_json VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO tenders VALUES
            (
                'n1',
                'Example Council',
                'London',
                '45000000',
                1250000,
                '2026-07-01',
                'open',
                'shortlist',
                92.5,
                '',
                '2026-07-01',
                '2026-07-01 10:00:00',
                '{"title":"Highways maintenance", "url":"https://example.gov.uk/tender"}'
            ),
            (
                'n2',
                'Example Council',
                'South East',
                '45200000',
                750000,
                '2026-06-01',
                'open',
                'watch',
                80.0,
                '',
                '2026-06-01',
                '2026-06-01 10:00:00',
                '{"title":"TOKEN should not leak", "url":"https://example.gov.uk/other"}'
            )
            """
        )
        con.execute(
            """
            CREATE TABLE awards (
                notice_id VARCHAR,
                buyer_name VARCHAR,
                supplier_name VARCHAR,
                value_amount FLOAT,
                award_date DATE,
                cpv_code VARCHAR,
                region VARCHAR,
                created_at TIMESTAMP,
                raw_json VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO awards VALUES
            ('a1', 'Example Council', 'BuildCo Ltd', 2500000, '2026-05-01', '45000000', 'London', '2026-05-01 10:00:00', '{}'),
            ('a2', 'Example Council', 'BuildCo Ltd', 3000000, '2026-06-01', '45000000', 'London', '2026-06-01 10:00:00', '{}')
            """
        )
        con.execute(
            """
            CREATE TABLE buyer_memory (
                buyer_name VARCHAR,
                procurement_count INTEGER,
                total_value FLOAT,
                dominant_cpv VARCHAR,
                last_seen DATE,
                updated_at TIMESTAMP
            )
            """
        )
        con.execute(
            """
            INSERT INTO buyer_memory VALUES
            ('Example Council', 2, 2000000, '45000000', '2026-07-01', '2026-07-01 10:00:00')
            """
        )
        con.execute(
            """
            CREATE TABLE run_log (
                run_id VARCHAR,
                run_date DATE,
                status VARCHAR
            )
            """
        )
        con.execute("INSERT INTO run_log VALUES ('r1', '2026-07-01', 'ok')")


def _tables(db_path: Path) -> list[str]:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return [
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE' ORDER BY table_name"
            ).fetchall()
        ]


def _count(db_path: Path, table: str) -> int:
    with duckdb.connect(str(db_path), read_only=True) as con:
        return int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
