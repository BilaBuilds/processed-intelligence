import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dach" / "export_dach_dashboard_bundle.py"
BUNDLE_DIR = ROOT / "data" / "export" / "dach_demo_bundle"
INDEX_PATH = BUNDLE_DIR / "index.html"
JSON_PATH = BUNDLE_DIR / "dach_dashboard_data.json"
JS_PATH = BUNDLE_DIR / "dach_dashboard_data.js"
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


def run_bundle_script():
    return subprocess.run(
        ["python", str(SCRIPT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_script_runs_and_bundle_files_exist():
    before_bundle = bundle_snapshot()
    result = run_bundle_script()

    assert "Exported DACH static dashboard bundle" in result.stdout
    assert BUNDLE_DIR.exists()
    assert INDEX_PATH.exists()
    assert JSON_PATH.exists()
    assert JS_PATH.exists()
    assert bundle_snapshot() == before_bundle


def test_index_references_data_script_and_global_exists():
    run_bundle_script()
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    js_text = JS_PATH.read_text(encoding="utf-8")

    assert "dach_dashboard_data.js" in index_text
    assert "window.PROCESSED_DACH_DASHBOARD_DATA" in js_text


def test_payload_contains_required_data_and_disclaimer():
    run_bundle_script()
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    index_text = INDEX_PATH.read_text(encoding="utf-8")
    combined_text = (
        index_text
        + "\n"
        + JSON_PATH.read_text(encoding="utf-8")
        + "\n"
        + JS_PATH.read_text(encoding="utf-8")
    )

    assert payload["source"] == "dach_demo_fixture"
    assert payload["tenders"]
    for country in ["Germany", "Austria", "Switzerland"]:
        assert country in combined_text

    assert "Not a live feed" in payload["disclaimer"]
    assert "No live scraping performed" in payload["disclaimer"]
    assert "Not bid advice" in payload["disclaimer"]


def test_bundle_avoids_forbidden_claim_language():
    run_bundle_script()
    combined_text = (
        INDEX_PATH.read_text(encoding="utf-8")
        + "\n"
        + JSON_PATH.read_text(encoding="utf-8")
        + "\n"
        + JS_PATH.read_text(encoding="utf-8")
    ).lower()

    assert "guaranteed win" not in combined_text
    assert "real-time" not in combined_text
    assert "production" not in combined_text


def test_run_pipeline_is_not_modified():
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "run_pipeline.py"],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, "run_pipeline.py has local modifications"


def test_current_hostinger_bundle_is_untouched():
    before_bundle = bundle_snapshot()
    run_bundle_script()
    after_bundle = bundle_snapshot()

    assert after_bundle == before_bundle


def test_current_tenderned_hostinger_dashboard_is_untouched():
    result = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "--",
            "ProcessEd_Dashboard.html",
            "dashboard_data.js",
            "dashboard_data.json",
            "hostinger_upload",
            "data/export/hostinger_upload_bundle",
        ],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0, "TenderNed/Hostinger dashboard paths changed"
