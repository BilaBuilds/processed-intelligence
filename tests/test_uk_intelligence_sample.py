import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_SAMPLE = ROOT / "data" / "samples" / "uk_intelligence_layer_raw.json"
CLEAN_SAMPLE = ROOT / "data" / "samples" / "uk_intelligence_sample_clean.json"
REPORT = ROOT / "docs" / "UK_INTELLIGENCE_SAMPLE_REPORT.md"
LIVE_DASHBOARD = ROOT / "data" / "export" / "hostinger_upload_bundle" / "dashboard_data.json"


def load_clean_sample():
    return json.loads(CLEAN_SAMPLE.read_text(encoding="utf-8"))


def test_uk_intelligence_sample_assets_exist():
    assert RAW_SAMPLE.exists()
    assert CLEAN_SAMPLE.exists()
    assert REPORT.exists()


def test_recommended_opportunities_are_deduplicated_and_rushmoor_is_not_repeated():
    clean = load_clean_sample()
    seen = set()
    rushmoor_count = 0

    for opportunity in clean["recommended_opportunities"]:
        key = (
            opportunity.get("url", "").strip().lower(),
            opportunity.get("buyer", "").strip().lower(),
            opportunity.get("title", "").strip().lower(),
            opportunity.get("deadline", "").strip().lower(),
        )
        assert key not in seen
        seen.add(key)

        if "rushmoor" in opportunity.get("buyer", "").lower():
            rushmoor_count += 1

    assert rushmoor_count <= 1


def test_expired_opportunities_are_separated_and_not_act_now():
    clean = load_clean_sample()

    assert all(not opportunity["is_expired"] for opportunity in clean["recommended_opportunities"])
    assert all(opportunity["is_expired"] for opportunity in clean["expired_opportunities"])

    for opportunity in clean["expired_opportunities"]:
        assert opportunity["demo_safe_status"] == "expired_in_current_review"
        assert opportunity["next_action"] == (
            "Historical signal only: use for buyer-pattern review, not live action."
        )
        assert "Act now" not in opportunity["next_action"]


def test_sample_wording_is_demo_safe():
    clean_text = CLEAN_SAMPLE.read_text(encoding="utf-8")
    report_text = REPORT.read_text(encoding="utf-8")

    assert "Historical sample" in report_text
    assert "not a live feed" in report_text
    assert "is a live feed" not in report_text
    assert "Act now" not in clean_text
    assert "Act now" not in report_text
    assert "outreach" not in clean_text
    assert "Treat as account-level target" not in clean_text


def test_live_hostinger_dashboard_data_is_not_modified():
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "data/export/hostinger_upload_bundle/dashboard_data.json"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0
