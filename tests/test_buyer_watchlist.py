"""
Tests for src/buyer_watchlist.py

Covers:
- All 14 fields are present in output
- Activity counts are correct (30d / 90d / total)
- Typical value uses median of history, falls back to profile
- fit_to_client is deterministic and bounded 0-99
- outreach_priority bucketing matches documented rules
- action_note is non-empty for all priority levels
- Sorting: hot first, then fit descending
- write_csv produces parseable output
- Empty inputs don't raise
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.buyer_watchlist import (
    compute_watchlist,
    load_buyer_history,
    write_csv,
    write_json,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────

NOW = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)


def _dt(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


PROFILES = {
    "wandsworth council": {
        "full_name": "London Borough of Wandsworth",
        "frequency": "monthly",
        "avg_value": 500000,
        "style": "collaborative, often pre-qualify",
        "contact_pattern": "procurement + contract manager",
    },
    "environment agency": {
        "full_name": "Environment Agency",
        "frequency": "quarterly",
        "avg_value": 900000,
        "style": "environmental focus, regulatory heavy",
        "contact_pattern": "project manager",
    },
    "unknown buyer co": {
        "full_name": "Unknown Buyer Co",
        "frequency": "unknown",
        "avg_value": 0,
        "style": "",
        "contact_pattern": "",
    },
}

HISTORY = {
    "wandsworth council": [
        {"buyer_name": "Wandsworth Council", "title": "Drainage works A", "value_amount": 450000, "region": "london", "score": 72, "cpv_codes": ["drainage"], "seen_at": _dt(5)},
        {"buyer_name": "Wandsworth Council", "title": "Civils package B", "value_amount": 380000, "region": "london", "score": 65, "cpv_codes": ["civils"], "seen_at": _dt(20)},
        {"buyer_name": "Wandsworth Council", "title": "Old groundworks", "value_amount": 600000, "region": "london", "score": 40, "cpv_codes": ["groundworks"], "seen_at": _dt(100)},
    ],
    "environment agency": [
        {"buyer_name": "Environment Agency", "title": "Flood alleviation", "value_amount": 950000, "region": "south east", "score": 58, "cpv_codes": ["drainage", "earthworks"], "seen_at": _dt(60)},
    ],
}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestComputeWatchlist:

    def test_all_required_fields_present(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        required = [
            "buyer_name", "activity_30d", "activity_90d", "total_notices",
            "typical_value", "typical_value_label", "top_categories", "top_regions",
            "recent_match_count", "fit_to_client", "outreach_priority",
            "action_note", "latest_notice_date", "latest_notice_title",
        ]
        for rec in records:
            for field in required:
                assert field in rec, f"Missing field '{field}' in record for {rec.get('buyer_name')}"

    def test_activity_counts_correct(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        w = next(r for r in records if "Wandsworth" in r["buyer_name"])
        # 2 records within 30d (days 5 and 20), 2 within 90d, 1 older (day 100)
        assert w["activity_30d"] == 2
        assert w["activity_90d"] == 2
        assert w["total_notices"] == 3

    def test_typical_value_is_median(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        w = next(r for r in records if "Wandsworth" in r["buyer_name"])
        # median of [450000, 380000, 600000] = 450000
        assert w["typical_value"] == 450000

    def test_typical_value_falls_back_to_profile(self):
        records = compute_watchlist(PROFILES, {}, now=NOW)
        w = next(r for r in records if "Wandsworth" in r["buyer_name"])
        assert w["typical_value"] == 500000

    def test_fit_score_bounded(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        for rec in records:
            assert 0 <= rec["fit_to_client"] <= 99, f"fit_to_client out of range for {rec['buyer_name']}"

    def test_fit_score_deterministic(self):
        r1 = compute_watchlist(PROFILES, HISTORY, now=NOW)
        r2 = compute_watchlist(PROFILES, HISTORY, now=NOW)
        for a, b in zip(r1, r2):
            assert a["fit_to_client"] == b["fit_to_client"]
            assert a["outreach_priority"] == b["outreach_priority"]

    def test_priority_hot_requires_fit_and_activity(self):
        # Build a buyer with high fit and high activity
        profiles = {"active buyer ltd": {"full_name": "Active Buyer Ltd", "frequency": "bi-weekly", "avg_value": 400000, "style": "", "contact_pattern": ""}}
        history = {"active buyer ltd": [
            {"buyer_name": "Active Buyer Ltd", "value_amount": 400000, "region": "london", "score": 50, "cpv_codes": [], "seen_at": _dt(5)},
            {"buyer_name": "Active Buyer Ltd", "value_amount": 400000, "region": "london", "score": 50, "cpv_codes": [], "seen_at": _dt(10)},
            {"buyer_name": "Active Buyer Ltd", "value_amount": 400000, "region": "london", "score": 50, "cpv_codes": [], "seen_at": _dt(15)},
        ]}
        records = compute_watchlist(profiles, history, now=NOW)
        assert records[0]["outreach_priority"] == "hot"

    def test_priority_low_when_no_activity_and_low_fit(self):
        records = compute_watchlist(PROFILES, {}, now=NOW)
        unknown = next(r for r in records if "Unknown" in r["buyer_name"])
        assert unknown["outreach_priority"] == "low"

    def test_sorted_hot_first_then_fit_descending(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        priority_order = {"hot": 0, "warm": 1, "watch": 2, "low": 3}
        for i in range(len(records) - 1):
            a, b = records[i], records[i + 1]
            pa, pb = priority_order[a["outreach_priority"]], priority_order[b["outreach_priority"]]
            assert pa <= pb, f"Priority order wrong: {a['outreach_priority']} before {b['outreach_priority']}"
            if pa == pb:
                assert a["fit_to_client"] >= b["fit_to_client"]

    def test_action_note_non_empty_for_all_priorities(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        for rec in records:
            assert rec["action_note"], f"Empty action_note for {rec['buyer_name']} ({rec['outreach_priority']})"

    def test_empty_profiles_returns_empty_list(self):
        records = compute_watchlist({}, {}, now=NOW)
        assert records == []

    def test_empty_history_still_returns_records(self):
        records = compute_watchlist(PROFILES, {}, now=NOW)
        assert len(records) == len(PROFILES)

    def test_job_history_boosts_fit(self):
        job_history = [{"buyer": "wandsworth council", "type": "groundworks", "value": 500000, "region": "london"}]
        records_with = compute_watchlist(PROFILES, HISTORY, job_history=job_history, now=NOW)
        records_without = compute_watchlist(PROFILES, HISTORY, job_history=None, now=NOW)
        w_with = next(r for r in records_with if "Wandsworth" in r["buyer_name"])
        w_without = next(r for r in records_without if "Wandsworth" in r["buyer_name"])
        assert w_with["fit_to_client"] > w_without["fit_to_client"]

    def test_top_categories_populated_from_cpv(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        w = next(r for r in records if "Wandsworth" in r["buyer_name"])
        assert len(w["top_categories"]) > 0
        assert "drainage" in w["top_categories"]

    def test_top_regions_populated(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        w = next(r for r in records if "Wandsworth" in r["buyer_name"])
        assert "London" in w["top_regions"]


class TestWriteArtifacts:

    def test_write_json_and_reload(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = Path(f.name)
        write_json(records, path)
        reloaded = json.loads(path.read_text())
        assert len(reloaded) == len(records)
        assert reloaded[0]["buyer_name"] == records[0]["buyer_name"]
        path.unlink(missing_ok=True)

    def test_write_csv_parseable(self):
        records = compute_watchlist(PROFILES, HISTORY, now=NOW)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = Path(f.name)
        write_csv(records, path)
        rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        assert len(rows) == len(records)
        assert "buyer_name" in rows[0]
        assert "outreach_priority" in rows[0]
        assert "fit_to_client" in rows[0]
        path.unlink(missing_ok=True)

    def test_write_csv_empty_input(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = Path(f.name)
        write_csv([], path)
        assert path.read_text() == ""
        path.unlink(missing_ok=True)


class TestLoadBuyerHistory:

    def test_load_groups_by_normalised_key(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w", encoding="utf-8") as f:
            f.write(json.dumps({"buyer_name": "Transport For London", "seen_at": _dt(1), "value_amount": 800000, "region": "london", "score": 60, "cpv_codes": []}) + "\n")
            f.write(json.dumps({"buyer_name": "transport for london", "seen_at": _dt(2), "value_amount": 750000, "region": "london", "score": 55, "cpv_codes": []}) + "\n")
            path = Path(f.name)
        result = load_buyer_history(path)
        assert "transport for london" in result
        assert len(result["transport for london"]) == 2
        path.unlink(missing_ok=True)

    def test_load_missing_file_returns_empty(self):
        result = load_buyer_history(Path("/tmp/does_not_exist_xyz.jsonl"))
        assert result == {}
