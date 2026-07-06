import csv
import json
import subprocess
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_PATH = ROOT / "docs" / "DACH_GTM_PLAYBOOK.md"
MESSAGES_PATH = ROOT / "docs" / "DACH_OUTREACH_MESSAGES.md"
CSV_PATH = ROOT / "data" / "outreach" / "dach_target_segments.csv"
JSON_PATH = ROOT / "data" / "outreach" / "dach_linkedin_templates.json"

PROTECTED_PATHS = [
    "run_pipeline.py",
    "ProcessEd_Dashboard.html",
    "dashboard_data.js",
    "dashboard_data.json",
    "hostinger_upload",
    "data/export/hostinger_upload_bundle",
    "data/export/dach_demo_bundle",
]

FORBIDDEN_PHRASES = [
    "guaranteed win",
    "live dach coverage",
    "bid advice",
    "paid client",
    "paying client",
    "paying customer",
]

REQUIRED_TEMPLATE_KEYS = {
    "english_connection_note",
    "german_connection_note",
    "english_followup",
    "german_followup",
    "swiss_variant",
    "demo_invite",
    "followup_1",
    "followup_2",
}

REQUIRED_PLACEHOLDERS = {"{name}", "{company}", "{country}", "{demo_link}"}


def read_all_pack_text() -> str:
    return "\n".join(
        [
            PLAYBOOK_PATH.read_text(encoding="utf-8"),
            MESSAGES_PATH.read_text(encoding="utf-8"),
            CSV_PATH.read_text(encoding="utf-8"),
            JSON_PATH.read_text(encoding="utf-8"),
        ]
    )


def test_gtm_pack_files_exist():
    assert PLAYBOOK_PATH.exists()
    assert MESSAGES_PATH.exists()
    assert CSV_PATH.exists()
    assert JSON_PATH.exists()


def test_csv_has_dach_countries_and_required_segments():
    with CSV_PATH.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))

    countries = {row["country"] for row in rows}
    counts = Counter(row["country"] for row in rows)

    assert {"Germany", "Austria", "Switzerland"}.issubset(countries)
    assert counts["Germany"] >= 3
    assert counts["Switzerland"] >= 2
    assert counts["Austria"] >= 2


def test_json_has_english_german_templates_and_placeholders():
    templates = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    assert REQUIRED_TEMPLATE_KEYS.issubset(templates)
    assert "english_connection_note" in templates
    assert "german_connection_note" in templates

    for name, template in templates.items():
        missing = REQUIRED_PLACEHOLDERS - set(
            placeholder for placeholder in REQUIRED_PLACEHOLDERS if placeholder in template
        )
        assert not missing, f"{name} missing placeholders: {sorted(missing)}"


def test_language_stays_honest_and_pilot_stage():
    text = read_all_pack_text().lower()

    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text

    assert "fixture" in text or "sample" in text
    assert "pilot" in text
    assert "discovery stage" in text or "pilot/discovery stage" in text


def test_run_pipeline_and_dashboard_bundles_untouched():
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", *PROTECTED_PATHS],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, "Protected pipeline/dashboard paths changed"
