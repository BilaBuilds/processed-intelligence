import json
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.manifest import build_manifest, write_manifest, ALLOWED_STATUSES


def _minimal_manifest(**overrides):
    defaults = dict(
        run_id="2026-04-19_120000",
        started_at="2026-04-19T12:00:00Z",
        completed_at="2026-04-19T12:00:10Z",
        ingest_status="ok",
        raw_count=5,
        normalize_status="ok",
        normalized_count=4,
        match_status="ok",
        scored_count=4,
        products_status="ok",
        products_generated=2,
        clients_status="ok",
        clients_notified=1,
        notify_status="ok",
        source_health={
            "govuk_guidance": {"status": "ok", "fetched": 5, "error": None}
        },
        product_summaries={},
        client_summaries={},
    )
    defaults.update(overrides)
    return build_manifest(**defaults)


def test_manifest_written_to_correct_path():
    manifest = _minimal_manifest()
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "2026-04-19_120000"
        path = write_manifest(manifest, run_dir)
        assert path == run_dir / "run_manifest.json"
        assert path.exists()


def test_step_statuses_only_allowed_values():
    manifest = _minimal_manifest()
    for step_name, step_data in manifest["steps"].items():
        status = step_data["status"]
        assert status in ALLOWED_STATUSES, f"step '{step_name}' has invalid status '{status}'"


def test_source_health_written_correctly():
    health = {
        "govuk_guidance": {"status": "ok", "fetched": 12, "error": None},
        "ea_publications": {"status": "error", "fetched": 0, "error": "timeout"},
    }
    manifest = _minimal_manifest(source_health=health)
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test_run"
        path = write_manifest(manifest, run_dir)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["source_health"]["govuk_guidance"]["status"] == "ok"
        assert loaded["source_health"]["ea_publications"]["error"] == "timeout"


def test_empty_run_produces_valid_manifest():
    manifest = _minimal_manifest(
        raw_count=0,
        normalized_count=0,
        scored_count=0,
        products_generated=0,
        clients_notified=0,
        products_status="no_products",
        clients_status="no_clients",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "empty_run"
        path = write_manifest(manifest, run_dir)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["steps"]["ingest"]["status"] == "ok"
        assert loaded["steps"]["products"]["status"] == "no_products"
        assert loaded["steps"]["clients"]["status"] == "no_clients"
        assert loaded["run_id"] == "2026-04-19_120000"
