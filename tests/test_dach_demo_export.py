import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCRIPT = ROOT / "scripts" / "dach" / "export_dach_demo.py"
JSON_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_tenders.json"
JSONL_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_tenders.jsonl"
SUMMARY_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_summary.json"
HOSTINGER_BUNDLE_PATH = ROOT / "data" / "export" / "hostinger_upload_bundle"


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


def run_export_script():
    return subprocess.run(
        ["python", str(EXPORT_SCRIPT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_export_script_runs_and_writes_demo_files():
    before_bundle = bundle_snapshot()
    result = run_export_script()

    assert "Exported 9 DACH demo tenders" in result.stdout
    assert JSON_PATH.exists()
    assert JSONL_PATH.exists()
    assert SUMMARY_PATH.exists()
    assert bundle_snapshot() == before_bundle


def test_demo_export_counts_and_disclaimer():
    run_export_script()

    tenders = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    jsonl_rows = [
        json.loads(line)
        for line in JSONL_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(tenders) == 9
    assert len(jsonl_rows) == 9
    assert summary["total_tenders"] == 9
    assert summary["count_by_country"] == {
        "Austria": 3,
        "Germany": 3,
        "Switzerland": 3,
    }
    assert summary["disclaimer"] == "DACH demo generated from fixture data. No live scraping performed."


def test_no_network_libraries_are_required_by_export_script():
    script_text = EXPORT_SCRIPT.read_text(encoding="utf-8")

    assert "requests" not in script_text
    assert "urllib" not in script_text
    assert "http.client" not in script_text


def test_run_pipeline_is_not_modified():
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "run_pipeline.py"],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, "run_pipeline.py has local modifications"


def test_current_hostinger_tenderned_dashboard_is_not_modified():
    result = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "--",
            "ProcessEd_Dashboard.html",
            "dashboard_data.js",
            "hostinger_upload",
        ],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, "Hostinger/TenderNed dashboard has local modifications"
