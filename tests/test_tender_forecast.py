from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.tender_forecast import compute_forecasts, write_forecast

NOW = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)


def _dt(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def test_forecast_wrapper_uses_canonical_timing_engine_shape() -> None:
    history = {
        "wandsworth council": [
            {"buyer_name": "Wandsworth Council", "seen_at": _dt(120), "cpv_codes": ["drainage"]},
            {"buyer_name": "Wandsworth Council", "seen_at": _dt(90), "cpv_codes": ["drainage"]},
            {"buyer_name": "Wandsworth Council", "seen_at": _dt(60), "cpv_codes": ["drainage"]},
            {"buyer_name": "Wandsworth Council", "seen_at": _dt(30), "cpv_codes": ["drainage"]},
        ]
    }
    forecasts = compute_forecasts(history, {"wandsworth council": {"full_name": "London Borough of Wandsworth"}}, now=NOW)
    record = forecasts[0]

    assert record["buyer_name"] == "London Borough of Wandsworth"
    assert "predicted_next_date" in record
    assert record["status"] in {"due_soon", "due", "upcoming", "distant", "overdue", "sparse"}


def test_write_forecast_creates_parseable_artifact(tmp_path: Path) -> None:
    forecasts = [
        {
            "buyer_key": "environment agency",
            "buyer_name": "Environment Agency",
            "record_count": 4,
            "last_seen_date": "2026-04-01",
            "median_interval_days": 30,
            "predicted_next_date": "2026-05-01",
            "forecast_window_start": "2026-04-25",
            "forecast_window_end": "2026-05-07",
            "days_until_next": 13,
            "status": "due_soon",
            "confidence": "high",
        }
    ]
    path = tmp_path / "tender_forecast.json"
    write_forecast(forecasts, path, NOW)

    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert artifact["buyer_count"] == 1
    assert artifact["due_soon_count"] == 1
    assert artifact["forecasts"][0]["buyer_key"] == "environment agency"
