import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.dach.score_dach_tenders import (
    DISCLAIMER,
    SCORING_VERSION,
    score_tender,
)


ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCRIPT = ROOT / "scripts" / "dach" / "export_dach_demo.py"
SCORING_SCRIPT = ROOT / "scripts" / "dach" / "score_dach_tenders.py"
SCORED_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_scored.json"
SUMMARY_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_score_summary.json"
DOC_PATH = ROOT / "docs" / "DACH_SCORING_MODEL.md"
HOSTINGER_BUNDLE_PATH = ROOT / "data" / "export" / "hostinger_upload_bundle"

VALID_PRIORITIES = {"HIGH", "MEDIUM", "LOW", "MONITOR"}


def bundle_snapshot():
    if not HOSTINGER_BUNDLE_PATH.exists():
        return None

    paths = sorted(path for path in HOSTINGER_BUNDLE_PATH.rglob("*") if path.is_file())
    return [
        (
            path.relative_to(HOSTINGER_BUNDLE_PATH).as_posix(),
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in paths
    ]


def run_demo_export_and_scoring():
    subprocess.run(["python", str(EXPORT_SCRIPT)], cwd=ROOT, check=True, timeout=30)
    return subprocess.run(
        ["python", str(SCORING_SCRIPT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_scoring_script_runs_and_outputs_files():
    before_bundle = bundle_snapshot()
    result = run_demo_export_and_scoring()

    assert "Scored 9 DACH demo tenders" in result.stdout
    assert SCORED_PATH.exists()
    assert SUMMARY_PATH.exists()
    assert bundle_snapshot() == before_bundle


def test_every_scored_tender_has_required_scoring_fields():
    run_demo_export_and_scoring()
    scored = json.loads(SCORED_PATH.read_text(encoding="utf-8"))

    assert len(scored) == 9
    for tender in scored:
        assert isinstance(tender["fit_score"], int)
        assert 0 <= tender["fit_score"] <= 100
        assert tender["priority"] in VALID_PRIORITIES
        assert isinstance(tender["reasons"], list)
        assert tender["reasons"]
        assert "Fixture-only demo record" in tender["reasons"]
        assert tender["next_action"]
        assert tender["scoring_version"] == "dach_fixture_scoring_v0_2"
        assert "Act now" not in tender["next_action"]


def test_scoring_distribution_is_demo_ready():
    run_demo_export_and_scoring()
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    count_by_priority = summary["count_by_priority"]

    assert summary["scoring_version"] == "dach_fixture_scoring_v0_2"
    assert count_by_priority["HIGH"] >= 2
    assert count_by_priority["MEDIUM"] >= 3
    assert count_by_priority["LOW"] + count_by_priority["MONITOR"] >= 1
    assert 50 <= summary["average_fit_score"] <= 75


def test_construction_civils_examples_score_above_non_core_examples():
    now = datetime.now(timezone.utc)
    construction = score_tender(
        {
            "title": "Bridge repair and civil engineering works",
            "description": "Concrete infrastructure maintenance framework",
            "deadline": (now + timedelta(days=30)).date().isoformat(),
            "value": 1_500_000,
            "country": "Germany",
        },
        now=now,
    )
    non_core = score_tender(
        {
            "title": "Software only office supplies",
            "description": "Pure IT consulting only",
            "deadline": (now + timedelta(days=30)).date().isoformat(),
            "value": 1_500_000,
            "country": "Germany",
        },
        now=now,
    )

    assert construction["fit_score"] > non_core["fit_score"]


def test_expired_stale_notices_are_monitor_only():
    expired = score_tender(
        {
            "title": "Road maintenance works",
            "description": "Construction repair",
            "deadline": "2000-01-01",
            "value": 1_500_000,
            "country": "Austria",
        }
    )

    assert expired["priority"] != "HIGH"
    assert expired["priority"] == "MONITOR"
    assert expired["next_action"] == "Monitor only"
    assert "Act now" not in expired["next_action"]
    assert "Expired/stale notice" in expired["reasons"]


def test_expired_fixture_records_are_monitor_if_present():
    run_demo_export_and_scoring()
    scored = json.loads(SCORED_PATH.read_text(encoding="utf-8"))

    for tender in scored:
        if "Expired/stale notice" in tender["reasons"]:
            assert tender["priority"] == "MONITOR"
            assert tender["next_action"] == "Monitor only"


def test_summary_disclaimer_and_docs_language():
    run_demo_export_and_scoring()
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    docs = DOC_PATH.read_text(encoding="utf-8").lower()

    assert summary["disclaimer"] == DISCLAIMER
    assert "No live scraping performed" in summary["disclaimer"]
    assert "Not bid advice" in summary["disclaimer"]
    assert "not bid advice" in docs
    assert "no guaranteed win" in docs


def test_run_pipeline_is_not_modified():
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "run_pipeline.py"],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, "run_pipeline.py has local modifications"


def test_current_hostinger_bundle_and_dashboard_are_not_modified():
    result = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "--",
            "data/export/hostinger_upload_bundle",
            "ProcessEd_Dashboard.html",
            "dashboard_data.js",
            "hostinger_upload",
        ],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, "Protected Hostinger/TenderNed paths changed"
