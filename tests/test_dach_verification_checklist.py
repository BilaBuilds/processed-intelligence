import csv
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "DACH_LIVE_SOURCE_VERIFICATION.md"
CSV_PATH = ROOT / "data" / "dach" / "source_verification_TEMPLATE.csv"

REQUIRED_COLUMNS = [
    "country",
    "source_name",
    "url",
    "owner",
    "api_available",
    "rss_available",
    "download_available",
    "auth_required",
    "robots_or_terms_checked",
    "rate_limit_known",
    "fields_available",
    "verified_by",
    "verified_at",
    "status",
    "next_action",
    "notes",
]

PROTECTED_PATHS = [
    "run_pipeline.py",
    "ProcessEd_Dashboard.html",
    "dashboard_data.js",
    "dashboard_data.json",
    "hostinger_upload",
    "data/export/hostinger_upload_bundle",
    "data/export/dach_demo_bundle",
]


def read_rows():
    with CSV_PATH.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def test_verification_doc_and_csv_exist():
    assert DOC_PATH.exists()
    assert CSV_PATH.exists()


def test_csv_has_required_columns_and_dach_countries():
    rows = read_rows()

    assert rows
    assert list(rows[0].keys()) == REQUIRED_COLUMNS
    assert {"Germany", "Austria", "Switzerland"}.issubset(
        {row["country"] for row in rows}
    )


def test_csv_rows_are_unverified_by_default():
    rows = read_rows()

    assert all(row["status"] == "unverified" for row in rows)
    assert all(
        row["next_action"] == "verify source terms and available access method"
        for row in rows
    )


def test_doc_contains_required_guardrail_language():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "Only then build adapter" in text
    assert "No live scraping has been performed" in text
    assert "Current TenderNed Hostinger demo remains untouched" in text
    assert "DACH static demo remains fixture-only" in text
    assert "run_pipeline.py must not be modified for source verification" in text


def test_run_pipeline_and_dashboard_bundles_untouched():
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", *PROTECTED_PATHS],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, "Protected pipeline/dashboard paths changed"


def test_verification_rows_by_country():
    counts = Counter(row["country"] for row in read_rows())

    assert counts["Germany"] == 5
    assert counts["Austria"] == 3
    assert counts["Switzerland"] == 3
