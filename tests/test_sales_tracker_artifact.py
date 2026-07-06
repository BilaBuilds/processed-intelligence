import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SALES_DIR = ROOT / "data" / "sales"
HTML = SALES_DIR / "process_ed_sales_tracker.html"
JSON_DATA = SALES_DIR / "process_ed_sales_tracker_data.json"
JS_DATA = SALES_DIR / "process_ed_sales_tracker_data.js"
CSV_DATA = SALES_DIR / "outreach_tracker_2026_07_06.csv"
DOCS = ROOT / "docs" / "SALES_TRACKER_ARTIFACT.md"
RUN_PIPELINE = ROOT / "run_pipeline.py"


EXPECTED_COMPANIES = {
    "Kier",
    "Morgan Sindall",
    "Balfour Beatty",
    "Tilbury Douglas",
    "Wates",
    "Galliford Try",
    "Octavius Infrastructure",
    "VolkerFitzpatrick",
    "Colas",
    "Bachy Soletanche",
}

PIPELINE_STATUSES = [
    "Target identified",
    "Contact found",
    "Message drafted",
    "Sent",
    "Replied",
    "Call booked",
    "Pilot candidate",
    "Closed / not now",
]


def test_sales_tracker_files_exist():
    assert HTML.exists()
    assert JSON_DATA.exists()
    assert JS_DATA.exists()
    assert CSV_DATA.exists()
    assert DOCS.exists()


def test_html_references_data_js_and_exposes_working_ui():
    html = HTML.read_text(encoding="utf-8")
    assert "process_ed_sales_tracker_data.js" in html
    assert "Today's outreach goals" in html
    assert "opt_out" in html
    assert "suppression_note" in html
    assert "Export current CSV" in html
    assert "Copy outreach message" in html
    assert "Copy follow-up message" in html
    for status in PIPELINE_STATUSES:
        assert status in html


def test_js_exposes_expected_global():
    js = JS_DATA.read_text(encoding="utf-8")
    assert "window.PROCESSED_SALES_TRACKER_DATA" in js


def test_json_contains_all_companies_and_default_statuses():
    data = json.loads(JSON_DATA.read_text(encoding="utf-8"))
    companies = data["companies"]
    assert {row["company"] for row in companies} == EXPECTED_COMPANIES
    assert all(row["status"] == "Target identified" for row in companies)
    assert all("opt_out" in row for row in companies)
    assert all("suppression_note" in row for row in companies)


def test_csv_mirrors_tracker_fields_and_companies():
    with CSV_DATA.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["company"] for row in rows} == EXPECTED_COMPANIES
    assert {"opt_out", "suppression_note", "response_sentiment"}.issubset(rows[0].keys())
    assert all(row["status"] == "Target identified" for row in rows)


def test_no_run_pipeline_modification_required():
    assert RUN_PIPELINE.exists()
    html = HTML.read_text(encoding="utf-8")
    docs = DOCS.read_text(encoding="utf-8")
    assert "run_pipeline.py" not in html
    assert "No backend, API key, credential, React, Next.js, or Flask service is required." in docs
