"""
src/tender_forecast.py
======================
Compatibility forecast artifact built from the canonical buyer timing engine.

This module intentionally does not own a second cadence model. It adapts the
deterministic timing signals from src.buyer_timing into the legacy
tender_forecast.json shape so older dashboard and reporting paths continue to
work without divergent logic.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.buyer_timing import compute_buyer_timing, compute_fit_by_buyer, load_inputs

log = logging.getLogger("tender_forecast")


def _forecast_status(signal: dict[str, Any]) -> str:
    status = str(signal.get("timing_status") or "insufficient_data")
    if status == "slipped":
        return "overdue"
    if status == "insufficient_data":
        return "sparse"
    return status


def _forecast_confidence(signal: dict[str, Any]) -> str:
    confidence = str(signal.get("timing_confidence") or "None").lower()
    if confidence == "none":
        return "low"
    return confidence


def _forecast_from_signal(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "buyer_key": signal.get("buyer_key"),
        "buyer_name": signal.get("buyer_name"),
        "record_count": signal.get("total_notices"),
        "last_seen_date": signal.get("last_seen_date", ""),
        "median_interval_days": signal.get("median_gap_days"),
        "predicted_next_date": signal.get("predicted_next_central", ""),
        "forecast_window_start": signal.get("predicted_next_start", ""),
        "forecast_window_end": signal.get("predicted_next_end", ""),
        "days_until_next": signal.get("days_until_central"),
        "status": _forecast_status(signal),
        "confidence": _forecast_confidence(signal),
    }


def compute_forecasts(
    history_by_buyer: dict[str, list[dict[str, Any]]],
    buyer_profiles: dict[str, dict[str, Any]],
    fit_by_buyer: dict[str, int] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    signals = compute_buyer_timing(
        history_by_buyer,
        buyer_profiles,
        fit_by_buyer=fit_by_buyer or {},
        now=now,
    )
    forecasts = [_forecast_from_signal(signal) for signal in signals]
    forecasts.sort(
        key=lambda forecast: (
            1 if forecast.get("days_until_next") is None else 0,
            forecast.get("days_until_next") if forecast.get("days_until_next") is not None else 9999,
            forecast.get("buyer_name") or "",
        )
    )
    return forecasts


def write_forecast(forecasts: list[dict[str, Any]], path: Path, now: datetime) -> None:
    statuses = Counter(forecast.get("status") for forecast in forecasts)
    artifact = {
        "generated_at": now.isoformat(),
        "buyer_count": len(forecasts),
        "due_soon_count": statuses.get("due_soon", 0),
        "due_count": statuses.get("due", 0),
        "overdue_count": statuses.get("overdue", 0),
        "forecasts": forecasts,
    }
    path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")


def run(context: dict) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    state_dir: Path = context.get("state_dir", Path("state"))
    run_dir: Path = context.get("run_dir", state_dir)
    forecast_file = run_dir / "tender_forecast.json"

    buyer_profiles, history_by_buyer, job_history = load_inputs(state_dir)
    if not history_by_buyer:
        log.info("Tender forecast: no buyer history found — skipping")
        return {
            "forecast_count": 0,
            "forecast_due_soon": 0,
            "forecast_due": 0,
            "forecast_overdue": 0,
            "forecast_file": None,
            "forecast_status": "no_history",
        }

    fit_by_buyer = compute_fit_by_buyer(buyer_profiles, history_by_buyer, job_history, now=now)
    forecasts = compute_forecasts(history_by_buyer, buyer_profiles, fit_by_buyer=fit_by_buyer, now=now)
    write_forecast(forecasts, forecast_file, now)

    statuses = Counter(forecast.get("status") for forecast in forecasts)
    log.info(
        "Tender forecast: %d buyers analysed — %d due soon, %d due, %d overdue -> %s",
        len(forecasts),
        statuses.get("due_soon", 0),
        statuses.get("due", 0),
        statuses.get("overdue", 0),
        forecast_file.name,
    )

    return {
        "forecast_count": len(forecasts),
        "forecast_due_soon": statuses.get("due_soon", 0),
        "forecast_due": statuses.get("due", 0),
        "forecast_overdue": statuses.get("overdue", 0),
        "forecast_file": str(forecast_file),
        "forecast_status": "ok",
    }
