"""
src/buyer_timing.py
===================
Deterministic buyer procurement timing engine.

Owns the canonical timing model used by:
    - buyer_timing_signals.json / .csv
    - buyer_timing_backtest.json
    - tender_forecast compatibility artifact
    - dashboard timing intelligence surfaces

The model keeps timing confidence, fit_to_client, and commercial actionability
as separate fields so weak evidence cannot masquerade as a strong signal.
"""

from __future__ import annotations

import csv
import json
import logging
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.buyer_watchlist import compute_watchlist

log = logging.getLogger("buyer_timing")

MIN_NOTICES_FOR_PREDICTION = 2
MIN_NOTICES_FOR_MEDIUM = 3
MIN_NOTICES_FOR_HIGH = 5
HIGH_CV_THRESHOLD = 0.35
MEDIUM_CV_THRESHOLD = 0.75
SEASONAL_THRESHOLD = 0.60
CATEGORY_REPEAT_THRESHOLD = 0.60

DUE_SOON_DAYS = 14
DUE_DAYS = 30
UPCOMING_DAYS = 90

CONFIDENCE_ORDER = {"High": 0, "Medium": 1, "Weak": 2, "None": 3}
STATUS_PRIORITY = {
    "overdue": 0,
    "due_soon": 1,
    "due": 2,
    "upcoming": 3,
    "distant": 4,
    "slipped": 5,
    "insufficient_data": 6,
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _record_dt(record: dict[str, Any]) -> datetime | None:
    for field in ("notice_published_at", "published_at", "updated_at", "seen_at"):
        dt = _parse_dt(record.get(field))
        if dt is not None:
            return dt
    return None


def _normalise_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def _quarter(month: int) -> str:
    return f"Q{((month - 1) // 3) + 1}"


def _intervals(timestamps: list[datetime]) -> list[float]:
    values: list[float] = []
    for idx in range(1, len(timestamps)):
        delta = (timestamps[idx] - timestamps[idx - 1]).total_seconds() / 86400
        if delta > 0:
            values.append(delta)
    return values


def _collapse_to_unique_notice_dates(timed: list[tuple[datetime, dict[str, Any]]]) -> list[tuple[datetime, dict[str, Any]]]:
    """
    Collapse multiple same-day notices into one cadence event.

    Buyers often publish several notices on the same day; treating those as
    separate cadence intervals creates false 0-day gaps and exaggerated
    "due now" signals. We keep raw `total_notices`, but timing cadence is
    computed from unique notice dates.
    """
    by_day: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for dt, record in timed:
        key = dt.strftime("%Y-%m-%d")
        current = by_day.get(key)
        if current is None or dt < current[0]:
            by_day[key] = (dt, record)
    return [by_day[key] for key in sorted(by_day)]


def _coefficient_of_variation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    if mean <= 0:
        return None
    return statistics.stdev(values) / mean


def _dominant_quarter(quarter_dist: dict[str, int]) -> tuple[str | None, float]:
    total = sum(quarter_dist.values())
    if total <= 0:
        return None, 0.0
    dominant = max(quarter_dist, key=quarter_dist.get)
    return dominant, quarter_dist[dominant] / total


def _category_repeat_strength(records_sorted: list[dict]) -> float:
    if len(records_sorted) < 2:
        return 0.0
    overlaps = 0
    pairs = 0
    for idx in range(1, len(records_sorted)):
        previous = set(records_sorted[idx - 1].get("cpv_codes") or [])
        current = set(records_sorted[idx].get("cpv_codes") or [])
        if not previous and not current:
            continue
        pairs += 1
        if previous & current:
            overlaps += 1
    if pairs == 0:
        return 0.0
    return round(overlaps / pairs, 3)


def _top_categories(records: list[dict], n: int = 3) -> list[str]:
    counter: Counter[str] = Counter()
    for record in records:
        for cpv in record.get("cpv_codes") or []:
            text = str(cpv).strip()
            if text:
                counter[text] += 1
    return [label for label, _ in counter.most_common(n)]


def _weighted_gap(intervals: list[float]) -> float | None:
    if not intervals:
        return None
    weights = list(range(1, len(intervals) + 1))
    numerator = sum(gap * weight for gap, weight in zip(intervals, weights))
    denominator = sum(weights)
    if denominator <= 0:
        return None
    return numerator / denominator


def _month_distribution(timestamps: list[datetime]) -> dict[str, int]:
    dist: dict[str, int] = {str(month): 0 for month in range(1, 13)}
    for ts in timestamps:
        dist[str(ts.month)] += 1
    return dist


def _quarter_distribution(timestamps: list[datetime]) -> dict[str, int]:
    dist = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
    for ts in timestamps:
        dist[_quarter(ts.month)] += 1
    return dist


def _confidence(record_count: int, cv: float | None) -> str:
    if record_count < MIN_NOTICES_FOR_PREDICTION:
        return "None"
    if record_count >= MIN_NOTICES_FOR_HIGH and cv is not None and cv <= HIGH_CV_THRESHOLD:
        return "High"
    if record_count >= MIN_NOTICES_FOR_MEDIUM and cv is not None and cv <= MEDIUM_CV_THRESHOLD:
        return "Medium"
    return "Weak"


def _window_half_width(
    adjusted_gap: float,
    stddev: float | None,
    confidence: str,
    seasonal_fraction: float,
    category_strength: float,
) -> float:
    base = max(
        7.0,
        adjusted_gap * 0.18,
        (stddev or 0.0) * 0.9,
    )
    multiplier = 1.0
    if confidence == "High":
        multiplier *= 0.9
    elif confidence == "Weak":
        multiplier *= 1.2
    if seasonal_fraction >= SEASONAL_THRESHOLD:
        multiplier *= 0.92
    if category_strength >= CATEGORY_REPEAT_THRESHOLD:
        multiplier *= 0.92
    return round(min(max(base * multiplier, 7.0), 60.0), 1)


def _seasonality_adjustment(
    predicted_central: datetime,
    dominant_quarter: str | None,
    dominant_fraction: float,
    total_notices: int,
) -> tuple[datetime, str]:
    if (
        dominant_quarter is None
        or dominant_fraction < SEASONAL_THRESHOLD
        or total_notices < 4
    ):
        return predicted_central, ""

    quarter_month = {"Q1": 1, "Q2": 4, "Q3": 7, "Q4": 10}[dominant_quarter]
    target_year = predicted_central.year
    if predicted_central.month > quarter_month + 2:
        target_year += 1
    quarter_anchor = datetime(target_year, quarter_month, 1, tzinfo=timezone.utc)
    drift_days = (quarter_anchor - predicted_central).total_seconds() / 86400
    nudge_days = max(min(drift_days * 0.35, 21), -21)
    adjusted = predicted_central + timedelta(days=nudge_days)
    reason = f"Seasonality nudged toward {dominant_quarter} ({round(dominant_fraction * 100)}%)."
    return adjusted, reason


def _timing_status(
    now: datetime,
    predicted_start: datetime | None,
    predicted_end: datetime | None,
    predicted_central: datetime | None,
    confidence: str,
) -> tuple[str, int | None]:
    if confidence == "None" or predicted_start is None or predicted_end is None or predicted_central is None:
        return "insufficient_data", None

    if now > predicted_end:
        return "slipped", int((predicted_end - now).total_seconds() // 86400)
    if predicted_start <= now <= predicted_end:
        return "overdue", int((predicted_central - now).total_seconds() // 86400)

    days_until_central = int((predicted_central - now).total_seconds() // 86400)
    if days_until_central <= DUE_SOON_DAYS:
        return "due_soon", days_until_central
    if days_until_central <= DUE_DAYS:
        return "due", days_until_central
    if days_until_central <= UPCOMING_DAYS:
        return "upcoming", days_until_central
    return "distant", days_until_central


def _timing_score(
    status: str,
    confidence: str,
    cv: float | None,
    seasonal_fraction: float,
    category_strength: float,
) -> int:
    status_points = {
        "overdue": 34,
        "due_soon": 32,
        "due": 24,
        "upcoming": 14,
        "distant": 4,
        "slipped": 16,
        "insufficient_data": 0,
    }
    confidence_points = {"High": 28, "Medium": 18, "Weak": 8, "None": 0}
    regularity_bonus = 0
    if cv is not None:
        regularity_bonus = max(0, min(14, round((1.0 - min(cv, 1.0)) * 14)))
    seasonal_bonus = 5 if seasonal_fraction >= SEASONAL_THRESHOLD else 0
    recurrence_bonus = 5 if category_strength >= CATEGORY_REPEAT_THRESHOLD else 0
    score = status_points.get(status, 0) + confidence_points.get(confidence, 0) + regularity_bonus + seasonal_bonus + recurrence_bonus
    return max(0, min(int(score), 100))


def _timing_reason(
    confidence: str,
    total_notices: int,
    median_gap: float | None,
    mean_gap: float | None,
    cv: float | None,
    dominant_quarter: str | None,
    dominant_fraction: float,
    category_strength: float,
    top_categories: list[str],
    seasonality_note: str,
) -> str:
    if confidence == "None":
        return f"Only {total_notices} notice(s) on record — insufficient history for a safe timing prediction."

    parts: list[str] = []
    if median_gap is not None and mean_gap is not None:
        parts.append(f"Median gap {round(median_gap)}d, mean {round(mean_gap)}d.")
    if cv is not None:
        parts.append(f"Cadence variance {round(cv, 2)}.")
    if dominant_quarter and dominant_fraction >= SEASONAL_THRESHOLD:
        parts.append(f"Most notices cluster in {dominant_quarter}.")
    if category_strength >= CATEGORY_REPEAT_THRESHOLD and top_categories:
        parts.append(f"Repeat category signal in {top_categories[0]}.")
    if seasonality_note:
        parts.append(seasonality_note)
    return " ".join(parts) or "Historical cadence estimate only."


def _action_note(status: str, confidence: str, fit_to_client: int, top_categories: list[str]) -> str:
    fit_suffix = ""
    if fit_to_client >= 65:
        fit_suffix = " Good fit to client profile."
    elif fit_to_client <= 35:
        fit_suffix = " Timing may be usable, but commercial fit is weak."

    if status == "overdue":
        return f"Window is open now — monitor portals and contact procurement immediately.{fit_suffix}".strip()
    if status == "due_soon":
        return f"Likely due within 14 days — prepare outreach and bid pack now.{fit_suffix}".strip()
    if status == "due":
        return f"Likely due within 30 days — line up capability statement and references.{fit_suffix}".strip()
    if status == "upcoming":
        return f"Likely this quarter — keep warm and watch {'/'.join(top_categories[:1]) or 'buyer activity'}.{fit_suffix}".strip()
    if status == "distant":
        return f"Not near-term yet — monitor only.{fit_suffix}".strip()
    if status == "slipped":
        return f"Past expected window — treat as weaker timing signal and monitor opportunistically.{fit_suffix}".strip()
    return "Track this buyer until more history accumulates."


def _build_signal(
    buyer_key: str,
    records: list[dict[str, Any]],
    buyer_profiles: dict[str, dict[str, Any]],
    fit_by_buyer: dict[str, int],
    now: datetime,
) -> dict[str, Any]:
    profile = buyer_profiles.get(buyer_key, {})
    buyer_name = profile.get("full_name") or buyer_key.title()
    total_notices = len(records)

    timed: list[tuple[datetime, dict[str, Any]]] = []
    for record in records:
        dt = _record_dt(record)
        if dt is not None:
            timed.append((dt, record))
    timed.sort(key=lambda item: item[0])

    if not timed:
        return {
            "buyer_key": buyer_key,
            "buyer_name": buyer_name,
            "total_notices": total_notices,
            "last_seen_date": "",
            "median_gap_days": None,
            "mean_gap_days": None,
            "gap_stddev": None,
            "month_distribution": {str(month): 0 for month in range(1, 13)},
            "quarter_distribution": {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0},
            "category_repeat_strength": 0.0,
            "predicted_next_start": "",
            "predicted_next_end": "",
            "predicted_next_central": "",
            "timing_confidence": "None",
            "timing_status": "insufficient_data",
            "timing_reason": "No dated records found.",
            "timing_score": 0,
            "action_note": "Track this buyer until more history accumulates.",
            "fit_to_client": fit_by_buyer.get(buyer_key, 0),
            "buyer_due_rank": None,
            "timing_visibility": "hidden",
            "timing_label": "Tracking",
            "timing_marketing_text": "Insufficient data for prediction",
            "dominant_quarter": "",
            "dominant_quarter_fraction": 0.0,
            "top_categories": [],
            "days_until_window_open": None,
            "days_until_central": None,
        }

    cadence_timed = _collapse_to_unique_notice_dates(timed)
    timestamps = [item[0] for item in cadence_timed]
    records_sorted = [item[1] for item in cadence_timed]
    last_seen = timestamps[-1]
    gaps = _intervals(timestamps)
    median_gap = round(statistics.median(gaps), 1) if gaps else None
    mean_gap = round(statistics.mean(gaps), 1) if gaps else None
    stddev = round(statistics.stdev(gaps), 1) if len(gaps) >= 2 else None
    cv = _coefficient_of_variation(gaps)
    month_dist = _month_distribution(timestamps)
    quarter_dist = _quarter_distribution(timestamps)
    dominant_quarter, dominant_fraction = _dominant_quarter(quarter_dist)
    category_strength = _category_repeat_strength(records_sorted)
    top_categories = _top_categories(records_sorted)
    effective_notice_count = len(timestamps)
    confidence = _confidence(effective_notice_count, cv)
    fit_to_client = fit_by_buyer.get(buyer_key, 0)

    predicted_start: datetime | None = None
    predicted_end: datetime | None = None
    predicted_central: datetime | None = None
    seasonality_note = ""

    if confidence != "None" and median_gap is not None:
        weighted_gap = _weighted_gap(gaps) or median_gap
        adjusted_gap = (median_gap * 0.65) + (weighted_gap * 0.35)
        predicted_central = last_seen + timedelta(days=adjusted_gap)
        predicted_central, seasonality_note = _seasonality_adjustment(
            predicted_central,
            dominant_quarter,
            dominant_fraction,
            effective_notice_count,
        )
        half_width = _window_half_width(adjusted_gap, stddev, confidence, dominant_fraction, category_strength)
        predicted_start = predicted_central - timedelta(days=half_width)
        predicted_end = predicted_central + timedelta(days=half_width)

    status, days_until_central = _timing_status(now, predicted_start, predicted_end, predicted_central, confidence)
    score = _timing_score(status, confidence, cv, dominant_fraction, category_strength)
    reason = _timing_reason(
        confidence,
        total_notices,
        median_gap,
        mean_gap,
        cv,
        dominant_quarter,
        dominant_fraction,
        category_strength,
        top_categories,
        seasonality_note,
    )
    action = _action_note(status, confidence, fit_to_client, top_categories)

    # --- Timing visibility (T4) ---
    if confidence in ("High", "Medium"):
        timing_visibility = "full"
    elif confidence == "Weak":
        timing_visibility = "limited"
    else:
        timing_visibility = "hidden"

    # --- Timing label + marketing text (T5) ---
    actionable_statuses = {"due_soon", "overdue"}
    strong_confidence = {"High", "Medium"}
    if status in actionable_statuses and confidence in strong_confidence:
        timing_label = "Actionable"
        timing_marketing_text = "Buyer likely to publish soon based on historical cadence"
    elif confidence == "Weak":
        timing_label = "Watch"
        timing_marketing_text = "Some timing signal detected, monitor activity"
    else:
        timing_label = "Tracking"
        timing_marketing_text = "Insufficient data for prediction"

    return {
        "buyer_key": buyer_key,
        "buyer_name": buyer_name,
        "total_notices": total_notices,
        "last_seen_date": last_seen.strftime("%Y-%m-%d"),
        "median_gap_days": median_gap,
        "mean_gap_days": mean_gap,
        "gap_stddev": stddev,
        "month_distribution": month_dist,
        "quarter_distribution": quarter_dist,
        "category_repeat_strength": category_strength,
        "predicted_next_start": predicted_start.strftime("%Y-%m-%d") if predicted_start else "",
        "predicted_next_end": predicted_end.strftime("%Y-%m-%d") if predicted_end else "",
        "predicted_next_central": predicted_central.strftime("%Y-%m-%d") if predicted_central else "",
        "timing_confidence": confidence,
        "timing_status": status,
        "timing_reason": reason,
        "timing_score": score,
        "action_note": action,
        "fit_to_client": fit_to_client,
        "buyer_due_rank": None,
        "days_until_window_open": int((predicted_start - now).total_seconds() // 86400) if predicted_start else None,
        "days_until_central": days_until_central,
        "dominant_quarter": dominant_quarter or "",
        "dominant_quarter_fraction": round(dominant_fraction, 3),
        "top_categories": top_categories,
        "timing_visibility": timing_visibility,
        "timing_label": timing_label,
        "timing_marketing_text": timing_marketing_text,
    }


def _rank_records(records: list[dict[str, Any]]) -> None:
    ordered = sorted(
        records,
        key=lambda record: (
            STATUS_PRIORITY.get(record.get("timing_status"), 9),
            -int(record.get("timing_score") or 0),
            CONFIDENCE_ORDER.get(record.get("timing_confidence"), 9),
            -(int(record.get("fit_to_client") or 0)),
            record.get("buyer_name") or "",
        ),
    )
    for index, record in enumerate(ordered, start=1):
        record["buyer_due_rank"] = index


def compute_fit_by_buyer(
    buyer_profiles: dict[str, dict[str, Any]],
    history_by_buyer: dict[str, list[dict[str, Any]]],
    job_history: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    watchlist_records = compute_watchlist(buyer_profiles, history_by_buyer, job_history or [], now=now)
    return {
        _normalise_key(record.get("buyer_name")): int(record.get("fit_to_client") or 0)
        for record in watchlist_records
    }


def compute_buyer_timing(
    history_by_buyer: dict[str, list[dict[str, Any]]],
    buyer_profiles: dict[str, dict[str, Any]],
    fit_by_buyer: dict[str, int] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if now is None:
        now = datetime.now(timezone.utc)
    fit_lookup = fit_by_buyer or {}
    records = [
        _build_signal(buyer_key, buyer_records, buyer_profiles, fit_lookup, now)
        for buyer_key, buyer_records in history_by_buyer.items()
        if buyer_key
    ]
    _rank_records(records)
    return sorted(
        records,
        key=lambda record: (
            STATUS_PRIORITY.get(record.get("timing_status"), 9),
            -int(record.get("timing_score") or 0),
            record.get("buyer_due_rank") or 9999,
            record.get("buyer_name") or "",
        ),
    )


def load_inputs(state_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    buyer_profiles_file = state_dir / "buyer_profiles.json"
    buyer_history_file = state_dir / "buyer_history.jsonl"
    job_history_file = state_dir / "job_history.json"

    buyer_profiles: dict[str, dict[str, Any]] = {}
    if buyer_profiles_file.exists():
        try:
            loaded = json.loads(buyer_profiles_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                buyer_profiles = loaded
        except Exception as exc:
            log.warning("Could not load buyer_profiles.json: %s", exc)

    history_by_buyer: dict[str, list[dict[str, Any]]] = {}
    if buyer_history_file.exists():
        for line in buyer_history_file.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
                key = _normalise_key(record.get("buyer_name"))
                if key:
                    history_by_buyer.setdefault(key, []).append(record)
            except Exception as exc:
                log.warning("Skipping malformed buyer history record: %s", exc)
                continue

    job_history: list[dict[str, Any]] = []
    if job_history_file.exists():
        try:
            loaded_jobs = json.loads(job_history_file.read_text(encoding="utf-8"))
            if isinstance(loaded_jobs, list):
                job_history = loaded_jobs
        except Exception as exc:
            log.warning("Could not load job history file %s: %s", job_history_file, exc)

    return buyer_profiles, history_by_buyer, job_history


def _baseline_prediction(training_records: list[dict[str, Any]]) -> tuple[datetime | None, datetime | None, datetime | None]:
    timed = sorted(
        ((dt, record) for record in training_records if (dt := _record_dt(record)) is not None),
        key=lambda item: item[0],
    )
    collapsed = _collapse_to_unique_notice_dates(timed)
    timestamps = [dt for dt, _ in collapsed]
    if len(timestamps) < 2:
        return None, None, None
    gaps = _intervals(timestamps)
    if not gaps:
        return None, None, None
    median_gap = statistics.median(gaps)
    stddev = statistics.stdev(gaps) if len(gaps) >= 2 else None
    central = timestamps[-1] + timedelta(days=median_gap)
    half_width = _window_half_width(median_gap, stddev, "Weak", 0.0, 0.0)
    return central - timedelta(days=half_width), central, central + timedelta(days=half_width)


def backtest_buyer_timing(
    history_by_buyer: dict[str, list[dict[str, Any]]],
    buyer_profiles: dict[str, dict[str, Any]],
    fit_by_buyer: dict[str, int] | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    confidence_hits: dict[str, list[int]] = {"High": [], "Medium": [], "Weak": [], "None": []}
    notice_bucket_hits: dict[str, list[int]] = {"3-4": [], "5-7": [], "8+": []}
    model_abs_errors: list[int] = []
    baseline_abs_errors: list[int] = []
    model_window_hits = 0
    baseline_window_hits = 0
    tp = fp = fn = 0

    fit_lookup = fit_by_buyer or {}

    for buyer_key, records in history_by_buyer.items():
        timed_records = [record for record in records if _record_dt(record) is not None]
        timed_records.sort(key=lambda record: _record_dt(record) or datetime.min.replace(tzinfo=timezone.utc))

        if len(timed_records) < 3:
            continue

        # Leave one out: train on first N-1, test on last
        training = timed_records[:-1]
        holdout = timed_records[-1]
        holdout_dt = _record_dt(holdout)
        if holdout_dt is None:
            continue

        pred_start, pred_central, pred_end = _baseline_prediction(training)
        model_start, model_central, model_end = _baseline_prediction(training)

        model_hit = 0
        baseline_hit = 0

        if model_start and model_end:
            if model_start <= holdout_dt <= model_end:
                model_hit = 1
                model_window_hits += 1
            err = abs((model_central - holdout_dt).days) if model_central else None
            if err is not None:
                model_abs_errors.append(err)

        if pred_start and pred_end:
            if pred_start <= holdout_dt <= pred_end:
                baseline_hit = 1
                baseline_window_hits += 1
            err = abs((pred_central - holdout_dt).days) if pred_central else None
            if err is not None:
                baseline_abs_errors.append(err)

        n = len(timed_records)
        bucket = "8+" if n >= 8 else ("5-7" if n >= 5 else "3-4")
        notice_bucket_hits[bucket].append(model_hit)

        # Confidence for this buyer (using training set)
        train_signal = compute_buyer_timing(
            {buyer_key: training}, buyer_profiles, fit_by_buyer, now=datetime.now(timezone.utc)
        )
        confidence = train_signal[0].get("timing_confidence", "None") if train_signal else "None"
        confidence_hits[confidence].append(model_hit)

        results.append({
            "buyer_key": buyer_key,
            "n_records": n,
            "confidence": confidence,
            "model_hit": model_hit,
            "baseline_hit": baseline_hit,
            "holdout_date": holdout_dt.strftime("%Y-%m-%d"),
        })

    total = len(results)
    model_hit_rate = sum(r["model_hit"] for r in results) / total if total else 0
    baseline_hit_rate = sum(r["baseline_hit"] for r in results) / total if total else 0

    confidence_hit_rates = {
        conf: (sum(hits) / len(hits) if hits else None)
        for conf, hits in confidence_hits.items()
    }
    bucket_hit_rates = {
        bucket: (sum(hits) / len(hits) if hits else None)
        for bucket, hits in notice_bucket_hits.items()
    }

    return {
        "sample_count": total,
        "model_window_hit_rate": round(model_hit_rate, 3),
        "baseline_window_hit_rate": round(baseline_hit_rate, 3),
        "model_mean_abs_error_days": round(sum(model_abs_errors) / len(model_abs_errors), 1) if model_abs_errors else None,
        "baseline_mean_abs_error_days": round(sum(baseline_abs_errors) / len(baseline_abs_errors), 1) if baseline_abs_errors else None,
        "confidence_hit_rates": confidence_hit_rates,
        "notice_bucket_hit_rates": bucket_hit_rates,
        "results": results,
    }


# ---------------------------------------------------------------------------
# CSV field list
# ---------------------------------------------------------------------------

_CSV_FIELDS = [
    "buyer_key", "buyer_name", "total_notices", "last_seen_date",
    "timing_status", "timing_confidence", "timing_visibility",
    "timing_label", "timing_marketing_text",
    "predicted_next_start", "predicted_next_central", "predicted_next_end",
    "days_until_window_open", "days_until_central",
    "median_gap_days", "mean_gap_days", "gap_stddev",
    "category_repeat_strength", "dominant_quarter", "timing_score",
    "fit_to_client", "buyer_due_rank", "action_note",
]


def write_json(records: list[dict[str, Any]], path: Path, now: datetime | None = None) -> None:
    if now is None:
        now = datetime.now(timezone.utc)
    due_soon = sum(1 for r in records if r.get("timing_status") == "due_soon")
    due = sum(1 for r in records if r.get("timing_status") == "due")
    overdue = sum(1 for r in records if r.get("timing_status") == "overdue")
    actionable = sum(1 for r in records if r.get("timing_label") == "Actionable")
    visible = sum(1 for r in records if r.get("timing_visibility") in ("full", "limited"))

    payload = {
        "generated_at": now.isoformat(),
        "buyer_count": len(records),
        "due_soon_count": due_soon,
        "due_count": due,
        "overdue_count": overdue,
        "actionable_count": actionable,
        "visible_count": visible,
        "signals": records,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def write_csv(records: list[dict[str, Any]], path: Path) -> None:
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({k: record.get(k, "") for k in _CSV_FIELDS})


def build_and_write(
    run_dir: Path,
    state_dir: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc)

    buyer_profiles, history_by_buyer, job_history = load_inputs(state_dir)

    from src.buyer_watchlist import compute_watchlist
    fit_by_buyer: dict[str, int] = {}
    if buyer_profiles and history_by_buyer:
        try:
            watchlist_records = compute_watchlist(buyer_profiles, history_by_buyer, job_history, now=now)
            fit_by_buyer = {
                _normalise_key(r.get("buyer_name")): int(r.get("fit_to_client") or 0)
                for r in watchlist_records
            }
        except Exception as exc:
            log.warning("Could not compute fit_by_buyer: %s", exc)

    records = compute_buyer_timing(history_by_buyer, buyer_profiles, fit_by_buyer, now=now)

    signals_path = run_dir / "buyer_timing_signals.json"
    csv_path = run_dir / "buyer_timing_signals.csv"
    backtest_path = run_dir / "buyer_timing_backtest.json"

    write_json(records, signals_path, now=now)
    write_csv(records, csv_path)

    backtest = backtest_buyer_timing(history_by_buyer, buyer_profiles, fit_by_buyer)
    backtest_path.write_text(json.dumps(backtest, indent=2, default=str), encoding="utf-8")

    due_soon = sum(1 for r in records if r.get("timing_status") == "due_soon")
    due = sum(1 for r in records if r.get("timing_status") == "due")
    overdue = sum(1 for r in records if r.get("timing_status") == "overdue")
    actionable = sum(1 for r in records if r.get("timing_label") == "Actionable")
    visible = sum(1 for r in records if r.get("timing_visibility") in ("full", "limited"))

    return {
        "buyer_timing_status": "ok",
        "buyer_timing_count": len(records),
        "buyer_timing_due_soon": due_soon,
        "buyer_timing_due": due,
        "buyer_timing_overdue": overdue,
        "buyer_timing_slipped": 0,
        "buyer_timing_backtest_sample_count": backtest.get("sample_count", 0),
        "buyer_timing_file": str(signals_path),
        "buyer_timing_csv": str(csv_path),
        "buyer_timing_backtest_file": str(backtest_path),
        "timing_visible_count": visible,
        "timing_actionable_count": actionable,
    }


def run(context: dict) -> dict[str, Any]:
    run_dir: Path = context["run_dir"]
    state_dir: Path = context.get("state_dir", Path("state"))
    try:
        result = build_and_write(run_dir=run_dir, state_dir=state_dir)
        log.info(
            "Buyer timing: %d signals, %d due_soon, %d overdue, %d actionable, %d visible",
            result["buyer_timing_count"],
            result["buyer_timing_due_soon"],
            result["buyer_timing_overdue"],
            result.get("timing_actionable_count", 0),
            result.get("timing_visible_count", 0),
        )
        return result
    except Exception as exc:
        log.warning("Buyer timing failed: %s", exc)
        return {
            "buyer_timing_status": "error",
            "buyer_timing_count": 0,
            "buyer_timing_due_soon": 0,
            "buyer_timing_due": 0,
            "buyer_timing_overdue": 0,
            "buyer_timing_slipped": 0,
            "buyer_timing_backtest_sample_count": 0,
            "timing_visible_count": 0,
            "timing_actionable_count": 0,
        }
