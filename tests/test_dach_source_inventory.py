import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "data" / "dach" / "source_inventory_TEMPLATE.json"
REPORT_PATH = ROOT / "data" / "dach" / "source_inventory_report.md"
REPORT_SCRIPT = ROOT / "scripts" / "dach_source_inventory_report.py"
HOSTINGER_BUNDLE_PATH = ROOT / "data" / "export" / "hostinger_upload_bundle"

REQUIRED_SOURCE_FIELDS = {
    "country",
    "source_name",
    "source_type",
    "base_url",
    "status",
    "auth_required",
    "fields_expected",
    "scraper_difficulty",
    "commercial_priority",
    "notes",
}

REQUIRED_EXPECTED_FIELDS = {
    "title",
    "buyer",
    "country",
    "region",
    "deadline",
    "value",
    "currency",
    "cpv",
    "url",
    "source",
    "notice_id",
    "published_at",
    "description",
}


def load_inventory():
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


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


def test_json_template_exists_and_is_valid():
    inventory = load_inventory()

    assert isinstance(inventory["sources"], list)
    assert inventory["sources"]


def test_dach_countries_exist():
    countries = {source["country"] for source in load_inventory()["sources"]}

    assert {"Germany", "Austria", "Switzerland"}.issubset(countries)


def test_every_source_has_required_fields_and_unverified_status():
    for source in load_inventory()["sources"]:
        assert REQUIRED_SOURCE_FIELDS.issubset(source)
        assert REQUIRED_EXPECTED_FIELDS.issubset(set(source["fields_expected"]))
        assert source["status"] == "unverified"


def test_report_script_runs_without_internet_and_generates_report():
    before_bundle = bundle_snapshot()

    result = subprocess.run(
        ["python", str(REPORT_SCRIPT)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert "Generated" in result.stdout
    assert REPORT_PATH.exists()

    report_text = REPORT_PATH.read_text(encoding="utf-8")
    for country in ["Germany", "Austria", "Switzerland"]:
        assert country in report_text

    assert bundle_snapshot() == before_bundle


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
