from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_FILES = [
    ROOT / "docs" / "WAREHOUSE_BUYER_INTELLIGENCE_REPORT.md",
    ROOT / "docs" / "SALES_PROOF_POINTS_FROM_WAREHOUSE.md",
    ROOT / "data" / "pilot" / "buyer_intelligence_sample.csv",
    ROOT / "data" / "pilot" / "top_50_buyer_targets.csv",
]


def test_warehouse_report_pack_files_exist() -> None:
    for path in REPORT_FILES:
        assert path.exists(), path
        assert path.stat().st_size > 0, path


def test_warehouse_report_pack_uses_verified_counts() -> None:
    combined = _combined_text()
    for count in ("15,786", "10,325", "2,274", "201"):
        assert count in combined


def test_warehouse_report_pack_keeps_claims_compliant() -> None:
    combined = _combined_text().lower()
    assert "historical local warehouse analysis" in combined
    assert "guaranteed tender wins" in combined
    assert "does not claim guaranteed tender wins" in combined
    assert "paying clients" in combined
    assert "does not claim paying clients" in combined
    assert "full production automation" in combined
    assert "does not claim full production automation" in combined
    assert "force hermes outreach from unsafe supplier data" in combined
    assert "does not force hermes outreach from unsafe supplier data" in combined


def test_warehouse_report_pack_contains_no_prohibited_positive_claims() -> None:
    combined = _combined_text().lower()
    prohibited_positive_claims = [
        "guarantees tender wins",
        "guaranteed wins",
        "we have paying clients",
        "our paying clients",
        "fully automated production coverage",
        "full production automation is live",
    ]
    for phrase in prohibited_positive_claims:
        assert phrase not in combined


def test_warehouse_report_pack_does_not_copy_raw_db_files() -> None:
    output_roots = [ROOT / "docs", ROOT / "data" / "pilot"]
    raw_files: list[Path] = []
    for output_root in output_roots:
        raw_files.extend(output_root.rglob("*.duckdb"))
        raw_files.extend(output_root.rglob("*.db"))
        raw_files.extend(output_root.rglob("*.wal"))
    assert raw_files == []


def test_warehouse_report_pack_contains_no_secrets() -> None:
    combined = _combined_text().lower()
    secret_markers = ["api_key", "password", "token", "4d1b19a8", "f3b8af"]
    for marker in secret_markers:
        assert marker not in combined


def _combined_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in REPORT_FILES)
