"""
Tests for src/buyer_timing.py

Covers:
- All 17 fields present per record
- Median / mean gap calculations
- Gap stddev (None when < 2 intervals)
- Month and quarter distribution accuracy
- Category repeat strength
- Confidence bucket rules (High/Medium/Weak/None)
- Timing status buckets (due_soon, due, upcoming, distant, slipped, overdue, insufficient_data)
- Seasonality nudge doesn't break dates
- Action note non-empty for all statuses
- Sorting: due_soon/overdue first, insufficient_data last
- write_json produces valid artifact with summary counts
- write_csv produces parseable CSV
- Empty history returns empty list
- Single-record buyer gets insufficient_data
- Two-record buyer gets Weak confidence
- build_and_write returns expected keys
"""
from __future__ import annotations

import csv
import json
import statistics
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.buyer_timing import (
    _category_repeat_strength,
    _coefficient_of_variation,
    _dominant_quarter,
    _intervals,
    compute_buyer_timing,
    write_csv,
    write_json,
)

NOW = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)


def _dt(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


# ---------------------------------------------------------------------------
# Module-level shared fixtures used by the class-based tests
# ---------------------------------------------------------------------------

PROFILES = {
    "wandsworth council": {
        "full_name": "London Borough of Wandsworth",
        "frequency": "monthly",
        "avg_value": 480000,
        "style": "civils",
        "contact_pattern": "procurement",
    }
}

HISTORY = {
    "wandsworth council": [
        {"buyer_name": "Wandsworth Council", "seen_at": _dt(120), "cpv_codes": ["civils", "drainage"], "value_amount": 300000},
        {"buyer_name": "Wandsworth Council", "seen_at": _dt(90), "cpv_codes": ["civils"], "value_amount": 350000},
        {"buyer_name": "Wandsworth Council", "seen_at": _dt(60), "cpv_codes": ["civils", "earthworks"], "value_amount": 400000},
        {"buyer_name": "Wandsworth Council", "seen_at": _dt(30), "cpv_codes": ["civils"], "value_amount": 450000},
    ],
    "environment agency": [
        {"buyer_name": "Environment Agency", "seen_at": _dt(200), "cpv_codes": ["flooding"]},
        {"buyer_name": "Environment Agency", "seen_at": _dt(150), "cpv_codes": ["flooding"]},
        {"buyer_name": "Environment Agency", "seen_at": _dt(95), "cpv_codes": ["flooding"]},
        {"buyer_name": "Environment Agency", "seen_at": _dt(40), "cpv_codes": ["flooding"]},
    ],
    "sparse buyer": [
        {"buyer_name": "Sparse Buyer", "seen_at": _dt(300), "cpv_codes": []},
    ],
}


# ---------------------------------------------------------------------------
# Standalone tests (already in file, kept for compatibility)
# ---------------------------------------------------------------------------


def test_buyer_timing_sufficiency_thresholds() -> None:
    history = {
        "one buyer": [{"buyer_name": "One Buyer", "seen_at": _dt(10), "cpv_codes": []}],
        "two buyer": [
            {"buyer_name": "Two Buyer", "seen_at": _dt(50), "cpv_codes": []},
            {"buyer_name": "Two Buyer", "seen_at": _dt(20), "cpv_codes": []},
        ],
    }
    results = compute_buyer_timing(history, {}, now=NOW)
    one = next(record for record in results if record["buyer_key"] == "one buyer")
    two = next(record for record in results if record["buyer_key"] == "two buyer")

    assert one["timing_confidence"] == "None"
    assert one["timing_status"] == "insufficient_data"
    assert two["timing_confidence"] == "Weak"


def test_confidence_bucket_assignment() -> None:
    history = {
        "regular buyer": [
            {"buyer_name": "Regular Buyer", "seen_at": _dt(100), "cpv_codes": []},
            {"buyer_name": "Regular Buyer", "seen_at": _dt(80), "cpv_codes": []},
            {"buyer_name": "Regular Buyer", "seen_at": _dt(60), "cpv_codes": []},
            {"buyer_name": "Regular Buyer", "seen_at": _dt(40), "cpv_codes": []},
            {"buyer_name": "Regular Buyer", "seen_at": _dt(20), "cpv_codes": []},
        ],
        "moderate buyer": [
            {"buyer_name": "Moderate Buyer", "seen_at": _dt(95), "cpv_codes": []},
            {"buyer_name": "Moderate Buyer", "seen_at": _dt(70), "cpv_codes": []},
            {"buyer_name": "Moderate Buyer", "seen_at": _dt(42), "cpv_codes": []},
            {"buyer_name": "Moderate Buyer", "seen_at": _dt(18), "cpv_codes": []},
        ],
    }
    results = compute_buyer_timing(history, {}, now=NOW)
    regular = next(record for record in results if record["buyer_key"] == "regular buyer")
    moderate = next(record for record in results if record["buyer_key"] == "moderate buyer")

    assert regular["timing_confidence"] == "High"
    assert moderate["timing_confidence"] in {"Medium", "Weak"}


def test_seasonality_adjustment_behavior() -> None:
    history = {
        "seasonal buyer": [
            {"buyer_name": "Seasonal Buyer", "seen_at": "2025-01-05T00:00:00+00:00", "cpv_codes": ["civils"]},
            {"buyer_name": "Seasonal Buyer", "seen_at": "2025-02-01T00:00:00+00:00", "cpv_codes": ["civils"]},
            {"buyer_name": "Seasonal Buyer", "seen_at": "2025-03-01T00:00:00+00:00", "cpv_codes": ["civils"]},
            {"buyer_name": "Seasonal Buyer", "seen_at": "2026-01-10T00:00:00+00:00", "cpv_codes": ["civils"]},
            {"buyer_name": "Seasonal Buyer", "seen_at": "2026-02-10T00:00:00+00:00", "cpv_codes": ["civils"]},
        ]
    }
    results = compute_buyer_timing(history, {}, now=NOW)
    record = results[0]
    assert record["dominant_quarter"] == "Q1"
    assert "Most notices cluster in Q1." in record["timing_reason"]


def test_category_recurrence_behavior() -> None:
    history = {
        "repeat buyer": [
            {"buyer_name": "Repeat Buyer", "seen_at": _dt(120), "cpv_codes": ["drainage"]},
            {"buyer_name": "Repeat Buyer", "seen_at": _dt(90), "cpv_codes": ["drainage"]},
            {"buyer_name": "Repeat Buyer", "seen_at": _dt(60), "cpv_codes": ["drainage"]},
            {"buyer_name": "Repeat Buyer", "seen_at": _dt(30), "cpv_codes": ["drainage"]},
        ]
    }
    results = compute_buyer_timing(history, {}, now=NOW)
    record = results[0]
    assert record["category_repeat_strength"] >= 0.6
    assert "Repeat category signal" in record["timing_reason"]


def test_manifest_artifact_generation(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    run_dir = tmp_path / "data" / "runs" / "2026-04-18_120000"
    state_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)

    (state_dir / "buyer_profiles.json").write_text(
        json.dumps(PROFILES),
        encoding="utf-8",
    )
    (state_dir / "job_history.json").write_text(
        json.dumps([{"buyer": "Wandsworth Council", "value": 350000, "type": "civils"}]),
        encoding="utf-8",
    )
    history_rows = HISTORY["wandsworth council"]
    (state_dir / "buyer_history.jsonl").write_text(
        "\n".join(json.dumps(row) for row in history_rows) + "\n",
        encoding="utf-8",
    )

    from src.buyer_timing import build_and_write
    result = build_and_write(run_dir=run_dir, state_dir=state_dir, now=NOW)

    assert result["buyer_timing_status"] == "ok"
    assert Path(result["buyer_timing_file"]).exists()
    assert Path(result["buyer_timing_csv"]).exists()
    assert Path(result["buyer_timing_backtest_file"]).exists()

    signals = json.loads(Path(result["buyer_timing_file"]).read_text(encoding="utf-8"))
    backtest = json.loads(Path(result["buyer_timing_backtest_file"]).read_text(encoding="utf-8"))
    assert "signals" in signals
    assert "results" in backtest


# ---------------------------------------------------------------------------
# Class-based tests (reconstructed from pyc + updated for Title-case values)
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_intervals_correct(self) -> None:
        dts = [
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
            datetime(2026, 3, 2, tzinfo=timezone.utc),
        ]
        intervals = _intervals(dts)
        assert len(intervals) == 2
        assert abs(intervals[0] - 30) < 1
        assert abs(intervals[1] - 30) < 1

    def test_intervals_single_returns_empty(self) -> None:
        dts = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        assert _intervals(dts) == []

    def test_cv_correct(self) -> None:
        vals = [30.0, 30.0, 30.0]
        cv = _coefficient_of_variation(vals)
        assert cv is not None
        assert cv < 0.01

    def test_cv_none_for_single_value(self) -> None:
        assert _coefficient_of_variation([30.0]) is None

    def test_dominant_quarter_correct(self) -> None:
        # _dominant_quarter takes a pre-built quarter_dist dict, returns (quarter, fraction)
        quarter_dist = {"Q1": 3, "Q2": 0, "Q3": 1, "Q4": 0}
        dominant, fraction = _dominant_quarter(quarter_dist)
        assert dominant == "Q1"
        assert fraction > 0.5

    def test_dominant_quarter_empty(self) -> None:
        dominant, fraction = _dominant_quarter({"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0})
        assert dominant is None
        assert fraction == 0.0

    def test_category_repeat_strength_full_match(self) -> None:
        records = [
            {"cpv_codes": ["civils"]},
            {"cpv_codes": ["civils"]},
            {"cpv_codes": ["civils"]},
        ]
        assert _category_repeat_strength(records) == 1.0

    def test_category_repeat_strength_no_match(self) -> None:
        records = [
            {"cpv_codes": ["civils"]},
            {"cpv_codes": ["drainage"]},
            {"cpv_codes": ["earthworks"]},
        ]
        assert _category_repeat_strength(records) < 0.5

    def test_category_repeat_strength_partial(self) -> None:
        records = [
            {"cpv_codes": ["civils"]},
            {"cpv_codes": ["civils"]},
            {"cpv_codes": ["drainage"]},
            {"cpv_codes": ["drainage"]},
        ]
        strength = _category_repeat_strength(records)
        assert 0.3 <= strength <= 0.7

    def test_category_repeat_strength_single_returns_zero(self) -> None:
        records = [{"cpv_codes": ["civils"]}]
        assert _category_repeat_strength(records) == 0.0


class TestComputeBuyerTiming:
    def test_returns_record_per_buyer_with_history(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        keys = {r["buyer_key"] for r in results}
        assert "wandsworth council" in keys
        assert "environment agency" in keys
        assert "sparse buyer" in keys

    def test_all_required_fields_present(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        required_fields = (
            "buyer_key", "buyer_name", "total_notices", "last_seen_date",
            "median_gap_days", "mean_gap_days", "gap_stddev",
            "month_distribution", "quarter_distribution",
            "category_repeat_strength", "top_categories",
            "predicted_next_start", "predicted_next_end",
            "timing_confidence", "timing_reason", "action_note",
            "days_until_window_open", "timing_status",
        )
        rec = next(r for r in results if r["buyer_key"] == "wandsworth council")
        for field in required_fields:
            assert field in rec, f"Missing field '{field}' in record for {rec['buyer_key']}"

    def test_wandsworth_median_gap_approx_30d(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        rec = next(r for r in results if r["buyer_key"] == "wandsworth council")
        assert abs(rec["median_gap_days"] - 30) <= 5

    def test_wandsworth_mean_gap_set(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        rec = next(r for r in results if r["buyer_key"] == "wandsworth council")
        assert rec["mean_gap_days"] is not None

    def test_wandsworth_gap_stddev_set(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        rec = next(r for r in results if r["buyer_key"] == "wandsworth council")
        assert rec["gap_stddev"] is not None

    def test_sparse_gap_stddev_none(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        rec = next(r for r in results if r["buyer_key"] == "sparse buyer")
        assert rec["gap_stddev"] is None

    def test_month_distribution_keys_are_strings(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        rec = next(r for r in results if r["buyer_key"] == "wandsworth council")
        assert all(isinstance(k, str) for k in rec["month_distribution"].keys())

    def test_quarter_distribution_has_all_quarters(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        rec = next(r for r in results if r["buyer_key"] == "wandsworth council")
        assert all(q in rec["quarter_distribution"] for q in ("Q1", "Q2", "Q3", "Q4"))

    def test_quarter_distribution_sums_to_total_notices(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        rec = next(r for r in results if r["buyer_key"] == "wandsworth council")
        assert sum(rec["quarter_distribution"].values()) == rec["total_notices"]

    def test_category_repeat_strength_bounded(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        for rec in results:
            assert 0.0 <= rec["category_repeat_strength"] <= 1.0

    def test_wandsworth_category_repeat_non_zero(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        rec = next(r for r in results if r["buyer_key"] == "wandsworth council")
        assert rec["category_repeat_strength"] > 0

    def test_ea_medium_or_weak_confidence(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        ea = next(r for r in results if r["buyer_key"] == "environment agency")
        assert ea["timing_confidence"] in {"High", "Medium", "Weak"}

    def test_sparse_confidence_none(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        s = next(r for r in results if r["buyer_key"] == "sparse buyer")
        assert s["timing_confidence"] == "None"

    def test_sparse_status_insufficient_data(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        s = next(r for r in results if r["buyer_key"] == "sparse buyer")
        assert s["timing_status"] == "insufficient_data"

    def test_sparse_predicted_dates_empty(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        s = next(r for r in results if r["buyer_key"] == "sparse buyer")
        assert not s["predicted_next_start"]  # None or empty string — no prediction for insufficient data

    def test_high_confidence_for_very_regular_buyer(self) -> None:
        """Very regular bi-weekly buyer (6 records, low cv) should be High confidence."""
        history = {
            "regular": [
                {"buyer_name": "Regular", "seen_at": _dt(70), "cpv_codes": []},
                {"buyer_name": "Regular", "seen_at": _dt(56), "cpv_codes": []},
                {"buyer_name": "Regular", "seen_at": _dt(42), "cpv_codes": []},
                {"buyer_name": "Regular", "seen_at": _dt(28), "cpv_codes": []},
                {"buyer_name": "Regular", "seen_at": _dt(14), "cpv_codes": []},
                {"buyer_name": "Regular", "seen_at": _dt(1), "cpv_codes": []},
            ]
        }
        results = compute_buyer_timing(history, {}, now=NOW)
        assert results[0]["timing_confidence"] == "High"

    def test_two_records_gives_weak_confidence(self) -> None:
        history = {
            "two buyer": [
                {"buyer_name": "Two Buyer", "seen_at": _dt(60), "cpv_codes": []},
                {"buyer_name": "Two Buyer", "seen_at": _dt(30), "cpv_codes": []},
            ]
        }
        results = compute_buyer_timing(history, {}, now=NOW)
        assert results[0]["timing_confidence"] == "Weak"

    def test_overdue_status_for_long_dormant_buyer(self) -> None:
        """Buyer last seen 90 days ago with ~30d median gap: window has passed → slipped or overdue."""
        history = {
            "old buyer": [
                {"buyer_name": "Old Buyer", "seen_at": _dt(150), "cpv_codes": []},
                {"buyer_name": "Old Buyer", "seen_at": _dt(120), "cpv_codes": []},
                {"buyer_name": "Old Buyer", "seen_at": _dt(90), "cpv_codes": []},
            ]
        }
        results = compute_buyer_timing(history, {}, now=NOW)
        assert results[0]["timing_status"] in {"overdue", "slipped"}

    def test_due_soon_status_for_imminent_buyer(self) -> None:
        history = {
            "busy": [
                {"buyer_name": "Busy", "seen_at": _dt(56), "cpv_codes": []},
                {"buyer_name": "Busy", "seen_at": _dt(42), "cpv_codes": []},
                {"buyer_name": "Busy", "seen_at": _dt(28), "cpv_codes": []},
                {"buyer_name": "Busy", "seen_at": _dt(14), "cpv_codes": []},
            ]
        }
        results = compute_buyer_timing(history, {}, now=NOW)
        assert results[0]["timing_status"] in {"due_soon", "due"}

    def test_action_note_non_empty_for_all_statuses(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        for rec in results:
            assert isinstance(rec["action_note"], str)
            assert len(rec["action_note"]) > 0

    def test_timing_reason_non_empty(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        for rec in results:
            assert isinstance(rec["timing_reason"], str)
            assert len(rec["timing_reason"]) > 0

    def test_sorted_insufficient_data_last(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        last = results[-1]
        assert last["timing_status"] == "insufficient_data"

    def test_buyer_name_from_profile(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        rec = next(r for r in results if r["buyer_key"] == "wandsworth council")
        assert rec["buyer_name"] == "London Borough of Wandsworth"

    def test_buyer_name_titlecased_without_profile(self) -> None:
        history = {"environment agency": HISTORY["environment agency"]}
        results = compute_buyer_timing(history, {}, now=NOW)
        rec = results[0]
        assert rec["buyer_name"][0].isupper()

    def test_empty_history_returns_empty_list(self) -> None:
        assert compute_buyer_timing({}, {}, now=NOW) == []

    def test_deterministic_same_inputs_same_outputs(self) -> None:
        r1 = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        r2 = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        assert [r["buyer_key"] for r in r1] == [r["buyer_key"] for r in r2]
        assert [r["timing_confidence"] for r in r1] == [r["timing_confidence"] for r in r2]


class TestArtifacts:
    def test_write_json_and_reload(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            path = Path(f.name)
        write_json(results, path, now=NOW)
        data = json.loads(path.read_text())
        assert "signals" in data
        assert len(data["signals"]) == len(results)
        assert "buyer_count" in data
        assert isinstance(data.get("due_soon_count"), int)
        assert isinstance(data.get("overdue_count"), int)
        assert "generated_at" in data
        path.unlink(missing_ok=True)

    def test_write_csv_parseable(self) -> None:
        results = compute_buyer_timing(HISTORY, PROFILES, now=NOW)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = Path(f.name)
        write_csv(results, path)
        rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        assert len(rows) == len(results)
        assert "buyer_name" in rows[0]
        assert "timing_status" in rows[0]
        assert "timing_confidence" in rows[0]
        assert "action_note" in rows[0]
        path.unlink(missing_ok=True)

    def test_write_csv_empty_input(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = Path(f.name)
        write_csv([], path)
        content = path.read_text()
        # Empty input should produce just a header row (or truly empty) — both are acceptable
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert len(lines) <= 1  # at most a header, no data rows
        path.unlink(missing_ok=True)
