"""
Tests for the seen-records ledger and novelty tracking in select + notify.
All tests are deterministic, offline, and use temp directories.
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ledger import load_seen_ids, append_seen_ids, make_ledger_entry
from src.schema import RegulationRecord
from src.select import run_select


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(id: str, score: int = 30) -> RegulationRecord:
    return RegulationRecord(
        id=id,
        title=f"Drainage Works Guidance {id}",
        authority="Environment Agency",
        region="London",
        published_at="2026-01-15",
        effective_at="",
        url=f"https://gov.uk/guidance/{id}",
        summary="Surface water drainage regulation",
        source="ea_publications",
        trade_tags=["drainage"],
        impact_type="environment",
        raw_text="sewer drainage surface water guidance",
        relevance_score=score,
        relevance_reasons=["matched: drainage", "region: London"],
    )


def _base_product(id="drainage_regulations"):
    return {
        "id": id,
        "display_name": "Drainage Alerts",
        "enabled": True,
        "min_score": 20,
        "shortlist_size": 10,
        "include_keywords": [],
        "exclude_keywords": [],
        "regions": [],
        "trade_tags": [],
        "impact_types": [],
        "allow_null_effective_date": True,
        "notify": True,
    }


def _base_client(client_id="test_client", products=None):
    return {
        "client_id": client_id,
        "display_name": "Test Client",
        "active": True,
        "subscribed_products": products or ["drainage_regulations"],
        "filters": {"min_score": 0, "regions": [], "authority_whitelist": []},
        "notify": {"channel": "discord", "webhook_env_var": "TEST_WEBHOOK"},
    }


# ---------------------------------------------------------------------------
# Test 1: First run — all records new when ledger missing
# ---------------------------------------------------------------------------

def test_first_run_all_records_new():
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_dir = Path(tmpdir) / "seen"
        records = [_make_record("r1"), _make_record("r2")]

        seen_ids = load_seen_ids("test_client", seen_dir)
        assert seen_ids == set()

        new = [r for r in records if r.id not in seen_ids]
        assert len(new) == 2


# ---------------------------------------------------------------------------
# Test 2: Second run — same records already seen → new_count = 0
# ---------------------------------------------------------------------------

def test_second_run_same_records_not_new():
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_dir = Path(tmpdir) / "seen"
        records = [_make_record("r1"), _make_record("r2")]

        # Simulate first run: append both IDs
        entries = [make_ledger_entry(r.id, "run-001") for r in records]
        append_seen_ids("test_client", entries, seen_dir)

        # Second run: load and check
        seen_ids = load_seen_ids("test_client", seen_dir)
        new = [r for r in records if r.id not in seen_ids]
        assert len(new) == 0


# ---------------------------------------------------------------------------
# Test 3: Third run — mix of old + new → only new ones counted
# ---------------------------------------------------------------------------

def test_third_run_mix_of_old_and_new():
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_dir = Path(tmpdir) / "seen"

        # First run: saw r1 and r2
        entries = [make_ledger_entry("r1", "run-001"), make_ledger_entry("r2", "run-001")]
        append_seen_ids("test_client", entries, seen_dir)

        # Third run: r1, r2 still here plus new r3, r4
        all_records = [_make_record("r1"), _make_record("r2"),
                       _make_record("r3"), _make_record("r4")]
        seen_ids = load_seen_ids("test_client", seen_dir)
        new = [r for r in all_records if r.id not in seen_ids]

        assert len(new) == 2
        assert {r.id for r in new} == {"r3", "r4"}


# ---------------------------------------------------------------------------
# Test 4: Ledger file created at correct path
# ---------------------------------------------------------------------------

def test_ledger_created_at_correct_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_dir = Path(tmpdir) / "seen"
        entries = [make_ledger_entry("r1", "run-001")]
        append_seen_ids("my_client", entries, seen_dir)

        expected_path = seen_dir / "my_client.jsonl"
        assert expected_path.exists()


# ---------------------------------------------------------------------------
# Test 5: Ledger is append-only — old entries not removed on second write
# ---------------------------------------------------------------------------

def test_ledger_is_append_only():
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_dir = Path(tmpdir) / "seen"

        # First write: r1
        append_seen_ids("c1", [make_ledger_entry("r1", "run-001")], seen_dir)
        # Second write: r2
        append_seen_ids("c1", [make_ledger_entry("r2", "run-002")], seen_dir)

        # Both r1 and r2 must be in the file
        seen_ids = load_seen_ids("c1", seen_dir)
        assert "r1" in seen_ids
        assert "r2" in seen_ids
        assert len(seen_ids) == 2


# ---------------------------------------------------------------------------
# Test 6: Ledger write is atomic (no .tmp file left after success)
# ---------------------------------------------------------------------------

def test_ledger_write_is_atomic():
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_dir = Path(tmpdir) / "seen"
        entries = [make_ledger_entry("r1", "run-001")]
        append_seen_ids("c1", entries, seen_dir)

        ledger_path = seen_dir / "c1.jsonl"
        tmp_path = ledger_path.with_suffix(".tmp")

        assert ledger_path.exists()
        assert not tmp_path.exists()


# ---------------------------------------------------------------------------
# Test 7: Missing ledger handled gracefully — no crash
# ---------------------------------------------------------------------------

def test_missing_ledger_graceful():
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_dir = Path(tmpdir) / "no_such_dir" / "nested"
        # No error raised
        result = load_seen_ids("nonexistent_client", seen_dir)
        assert result == set()


# ---------------------------------------------------------------------------
# Test 8: notify_status = "skipped" when new_count = 0
# ---------------------------------------------------------------------------

def test_notify_status_skipped_when_no_new():
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_dir = Path(tmpdir) / "seen"
        run_dir = Path(tmpdir) / "run-001"
        records = [_make_record("r1", score=40), _make_record("r2", score=35)]

        # Pre-seed ledger so both records are already seen
        entries = [make_ledger_entry(r.id, "prev-run") for r in records]
        append_seen_ids("test_client", entries, seen_dir)

        _, client_results = run_select(
            scored=records,
            products=[_base_product()],
            clients=[_base_client()],
            run_dir=run_dir,
            dry_run=True,
            seen_dir=seen_dir,
        )

        summary = client_results["test_client"]["summary"]
        assert summary["new_count"] == 0
        assert summary["notify_status"] == "skipped"


# ---------------------------------------------------------------------------
# Test 9: notify_status = "sent" when new_count > 0 (mock webhook)
# ---------------------------------------------------------------------------

def test_notify_status_sent_when_new_records(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        seen_dir = Path(tmpdir) / "seen"
        run_dir = Path(tmpdir) / "run-001"
        records = [_make_record("r1", score=40)]

        # Ledger is empty — r1 is new
        _, client_results = run_select(
            scored=records,
            products=[_base_product()],
            clients=[_base_client()],
            run_dir=run_dir,
            dry_run=True,
            seen_dir=seen_dir,
        )

        summary = client_results["test_client"]["summary"]
        assert summary["new_count"] == 1

        # Now simulate notify with a mocked webhook
        from src import notify as notify_mod
        monkeypatch.setenv("TEST_WEBHOOK", "https://discord.com/api/webhooks/fake")
        mock_resp = MagicMock()
        mock_resp.raise_for_status = lambda: None

        with patch("src.notify.requests.post", return_value=mock_resp) as mock_post:
            result = notify_mod.run_notify(
                run_id="run-001",
                client_results=client_results,
                run_dir=run_dir,
                dry_run=False,
            )

        updated_summary = result["test_client"]["summary"]
        assert updated_summary["notify_status"] == "sent"
        assert updated_summary["notified"] is True
        assert mock_post.called
