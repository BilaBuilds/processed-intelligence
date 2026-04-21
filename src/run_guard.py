"""
src/run_guard.py
================
Batch-aware run guard for the tender pipeline.

Checks if the last successful FTS batch was within a configurable cooldown
window. If so, marks the run as cooldown_skip unless TENDER_FORCE_RUN=true.

ENV:
  TENDER_RUN_COOLDOWN_HOURS  - cooldown window in hours (default: 6)
  TENDER_FORCE_RUN           - set to "true" to bypass cooldown (default: false)

State:
  data/last_fts_run.txt       - watermark written by fts_scraper after each run
  data/last_fts_batch_count.txt - count of records from last FTS fetch (written by ingest)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("run_guard")

DEFAULT_COOLDOWN_HOURS = 6
LAST_FTS_BATCH_COUNT_FILE = "last_fts_batch_count.txt"
LAST_FTS_RUN_FILE = "last_fts_run.txt"


def _read_int_file(path: Path, default: int = 0) -> int:
    if not path.exists():
        return default
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return default


def _read_datetime_file(path: Path) -> datetime | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, OSError):
        return None


def check_cooldown(data_dir: Path) -> dict:
    """
    Returns a dict with:
      run_mode: "full" | "cooldown_skip"
      cooldown_reason: str (explanation, empty if full)
      force_run: bool
    """
    force_run = os.getenv("TENDER_FORCE_RUN", "").strip().lower() in ("1", "true", "yes")
    cooldown_hours = int(os.getenv("TENDER_RUN_COOLDOWN_HOURS", str(DEFAULT_COOLDOWN_HOURS)))

    if force_run:
        log.info("Run guard: TENDER_FORCE_RUN=true, bypassing cooldown check.")
        return {"run_mode": "full", "cooldown_reason": "", "force_run": True}

    last_run_dt = _read_datetime_file(data_dir / LAST_FTS_RUN_FILE)
    last_batch_count = _read_int_file(data_dir / LAST_FTS_BATCH_COUNT_FILE, default=0)

    if last_run_dt is None:
        # No prior run — always proceed
        return {"run_mode": "full", "cooldown_reason": "", "force_run": False}

    if last_batch_count == 0:
        # Last FTS fetch returned nothing — no cooldown needed; proceed
        return {"run_mode": "full", "cooldown_reason": "", "force_run": False}

    now = datetime.now(timezone.utc)
    elapsed = now - last_run_dt
    cooldown_window = timedelta(hours=cooldown_hours)

    if elapsed < cooldown_window:
        remaining_minutes = int((cooldown_window - elapsed).total_seconds() / 60)
        reason = (
            f"Last FTS batch ({last_batch_count} records) was {int(elapsed.total_seconds() / 60)}m ago "
            f"(cooldown={cooldown_hours}h). {remaining_minutes}m remaining. "
            f"Set TENDER_FORCE_RUN=true to bypass."
        )
        log.info("Run guard: cooldown_skip — %s", reason)
        return {"run_mode": "cooldown_skip", "cooldown_reason": reason, "force_run": False}

    return {"run_mode": "full", "cooldown_reason": "", "force_run": False}


def save_fts_batch_count(data_dir: Path, count: int) -> None:
    """Persist the FTS record count from the latest ingest run."""
    try:
        (data_dir / LAST_FTS_BATCH_COUNT_FILE).write_text(str(count), encoding="utf-8")
    except OSError as exc:
        log.warning("Could not save FTS batch count: %s", exc)
