#!/usr/bin/env python3
"""
fts_scraper.py - Find a Tender OCDS API scraper.

Production goals:
    - explicit ingest modes: incremental, recovery, backfill
    - resumable backfill state separate from incremental watermark
    - mode-aware request caps
    - deterministic chunking and truthful metadata
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SCRIPT_VERSION = "3.0.0"
DEFAULT_BASE_DIR = Path(__file__).parent.parent
DEFAULT_ENDPOINT = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
VALID_MODES = {"incremental", "recovery", "backfill"}


@dataclass(frozen=True)
class Config:
    base_dir: Path = DEFAULT_BASE_DIR
    endpoint: str = DEFAULT_ENDPOINT
    accept_header: str = "application/json"
    user_agent: str = f"tender-intel-fts-scraper/{SCRIPT_VERSION}"
    lookback_days: int = 30
    recovery_days: int = 3
    backfill_chunk_days: int = 3
    limit_per_request: int = 100
    max_requests_incremental: int = 10
    max_requests_recovery: int = 25
    max_requests_backfill: int = 200
    timeout: int = 30
    retry_total: int = 3
    retry_backoff: float = 2.0
    max_429_attempts: int = 4
    polite_delay_seconds: float = 1.0
    ingest_mode: str = "incremental"
    backfill_start: str | None = None
    backfill_end: str | None = None

    @property
    def raw_dir(self) -> Path:
        return self.base_dir / "data" / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.base_dir / "data" / "processed"

    @property
    def log_dir(self) -> Path:
        return self.base_dir / "logs"

    @property
    def data_state_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def runtime_state_dir(self) -> Path:
        return self.base_dir / "state"

    @property
    def last_run_file(self) -> Path:
        return self.data_state_dir / "last_fts_run.txt"

    @property
    def backfill_state_file(self) -> Path:
        return self.runtime_state_dir / "fts_backfill_state.json"

    def validate(self) -> None:
        if self.ingest_mode not in VALID_MODES:
            raise ValueError(f"ingest_mode must be one of {sorted(VALID_MODES)}")
        if self.lookback_days <= 0:
            raise ValueError("lookback_days must be > 0")
        if self.recovery_days <= 0:
            raise ValueError("recovery_days must be > 0")
        if self.backfill_chunk_days <= 0:
            raise ValueError("backfill_chunk_days must be > 0")
        if self.limit_per_request <= 0:
            raise ValueError("limit_per_request must be > 0")
        if self.max_requests_incremental <= 0:
            raise ValueError("max_requests_incremental must be > 0")
        if self.max_requests_recovery <= 0:
            raise ValueError("max_requests_recovery must be > 0")
        if self.max_requests_backfill <= 0:
            raise ValueError("max_requests_backfill must be > 0")
        if self.timeout <= 0:
            raise ValueError("timeout must be > 0")
        if self.retry_total < 0:
            raise ValueError("retry_total must be >= 0")
        if self.retry_backoff < 0:
            raise ValueError("retry_backoff must be >= 0")
        if self.max_429_attempts <= 0:
            raise ValueError("max_429_attempts must be > 0")
        if self.polite_delay_seconds < 0:
            raise ValueError("polite_delay_seconds must be >= 0")
        if not self.endpoint.startswith("https://"):
            raise ValueError("endpoint must be https")

    def ensure_dirs(self) -> None:
        for directory in (
            self.raw_dir,
            self.processed_dir,
            self.log_dir,
            self.data_state_dir,
            self.runtime_state_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def max_requests_for_mode(self) -> int:
        if self.ingest_mode == "recovery":
            return self.max_requests_recovery
        if self.ingest_mode == "backfill":
            return self.max_requests_backfill
        return self.max_requests_incremental


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_z(dt: datetime) -> str:
    return normalize_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def ts_filename() -> str:
    return utc_now().strftime("%Y-%m-%d_%H%M%S")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return normalize_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False, default=str)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception as exc:
        logging.warning("Could not parse JSON state file %s: %s", path, exc)
        return {}


def get_last_run(cfg: Config) -> datetime:
    if cfg.last_run_file.exists():
        try:
            value = cfg.last_run_file.read_text(encoding="utf-8").strip()
            last = normalize_utc(datetime.fromisoformat(value))
            if last <= utc_now() + timedelta(minutes=5):
                return last
            logging.warning("Last run timestamp is in the future; using fallback window.")
        except Exception:
            logging.warning("Could not parse last run file; using fallback window.")
    return utc_now() - timedelta(days=cfg.lookback_days)


def save_last_run(cfg: Config, dt: datetime) -> None:
    atomic_write_text(cfg.last_run_file, normalize_utc(dt).isoformat())


def load_backfill_state(cfg: Config) -> dict[str, Any]:
    state = read_json_file(cfg.backfill_state_file)
    if state.get("mode") != "backfill":
        return {}
    return state


def save_backfill_state(cfg: Config, state: dict[str, Any]) -> None:
    atomic_write_json(cfg.backfill_state_file, state)


def clear_backfill_state(cfg: Config) -> None:
    if cfg.backfill_state_file.exists():
        cfg.backfill_state_file.unlink(missing_ok=True)


def parse_retry_after_seconds(retry_after_header: str | None, attempt: int) -> int:
    fallback = min(300, 2 ** (attempt + 4))
    if not retry_after_header:
        return fallback
    retry_after = retry_after_header.strip()
    if retry_after.isdigit():
        return max(1, min(600, int(retry_after)))
    try:
        parsed = normalize_utc(parsedate_to_datetime(retry_after))
        wait_seconds = int((parsed - utc_now()).total_seconds())
        return max(1, min(600, wait_seconds))
    except Exception:
        return fallback


def build_session(cfg: Config) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=cfg.retry_total,
        backoff_factor=cfg.retry_backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update(
        {"Accept": cfg.accept_header, "User-Agent": cfg.user_agent}
    )
    return session


def fetch_page(
    session: requests.Session,
    cfg: Config,
    updated_from: str,
    updated_to: str,
    cursor: str | None = None,
    stages: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "updatedFrom": updated_from,
        "updatedTo": updated_to,
        "limit": cfg.limit_per_request,
    }
    if cursor:
        params["cursor"] = cursor
    if stages:
        params["stages"] = stages

    logging.info("FTS request | params=%s", json.dumps(params, ensure_ascii=False))

    response: requests.Response | None = None
    for attempt in range(cfg.max_429_attempts):
        response = session.get(cfg.endpoint, params=params, timeout=cfg.timeout)
        if response.status_code != 429:
            break
        wait_seconds = parse_retry_after_seconds(
            response.headers.get("Retry-After"), attempt
        )
        logging.warning(
            "Rate limited (429). Waiting %ds (attempt %d/%d).",
            wait_seconds,
            attempt + 1,
            cfg.max_429_attempts,
        )
        time.sleep(wait_seconds)

    if response is None:
        raise RuntimeError("FTS request failed before receiving a response.")
    if response.status_code >= 400:
        logging.error(
            "FTS API error | status=%s | body=%s",
            response.status_code,
            response.text[:1200],
        )
        response.raise_for_status()

    try:
        payload = response.json()
    except Exception as exc:
        logging.error(
            "FTS JSON parse error | status=%s | exc=%s | body_sample=%s",
            response.status_code,
            exc,
            response.text[:400],
        )
        raise RuntimeError(f"FTS API returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("FTS response JSON was not an object.")
    return payload


def extract_cursor(payload: dict[str, Any]) -> str | None:
    for key in ("cursor", "nextCursor", "next_cursor", "nextPageCursor"):
        value = payload.get(key)
        if value:
            return str(value)
    for links_key in ("links", "_links"):
        links = payload.get(links_key, {})
        if not isinstance(links, dict):
            continue
        next_url = links.get("next", "")
        if not next_url:
            continue
        try:
            parsed = urlparse(str(next_url))
            query = parse_qs(parsed.query)
            cursor_vals = query.get("cursor", [])
            if cursor_vals:
                return cursor_vals[0]
        except Exception:
            pass
    meta = payload.get("meta", {})
    if isinstance(meta, dict):
        for key in ("cursor", "nextCursor", "next_cursor"):
            value = meta.get(key)
            if value:
                return str(value)
    return None


def extract_releases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    releases = payload.get("releases")
    if isinstance(releases, list):
        return [r for r in releases if isinstance(r, dict)]

    packages = payload.get("releasePackages")
    flattened: list[dict[str, Any]] = []
    if isinstance(packages, list):
        for package in packages:
            if not isinstance(package, dict):
                continue
            package_releases = package.get("releases", [])
            if isinstance(package_releases, list):
                for release in package_releases:
                    if isinstance(release, dict):
                        flattened.append(release)
            elif isinstance(package_releases, dict):
                flattened.append(package_releases)
        return flattened

    results = payload.get("results")
    if isinstance(results, list):
        return [item for item in results if isinstance(item, dict)]
    return []


def iter_pages(
    session: requests.Session,
    cfg: Config,
    updated_from: str,
    updated_to: str,
    stages: str | None = None,
) -> dict[str, Any]:
    cursor: str | None = None
    requests_made = 0
    seen_cursors: set[str] = set()
    releases: list[dict[str, Any]] = []
    hit_cap = False

    while requests_made < cfg.max_requests_for_mode():
        requests_made += 1
        try:
            payload = fetch_page(
                session=session,
                cfg=cfg,
                updated_from=updated_from,
                updated_to=updated_to,
                cursor=cursor,
                stages=stages,
            )
        except RuntimeError as exc:
            logging.warning(
                "FTS page fetch failed (keeping %d releases collected so far): %s",
                len(releases),
                exc,
            )
            break
        page_releases = extract_releases(payload)
        releases.extend(page_releases)
        if not page_releases and not extract_cursor(payload):
            break

        next_cursor = extract_cursor(payload)
        if not next_cursor:
            logging.info("No further cursor. Pagination complete.")
            break
        if next_cursor == cursor or next_cursor in seen_cursors:
            logging.warning("Repeated cursor detected. Stopping pagination.")
            break

        seen_cursors.add(next_cursor)
        cursor = next_cursor
        logging.info("Next cursor: %s", cursor[:80])
        if cfg.polite_delay_seconds:
            time.sleep(cfg.polite_delay_seconds)
    else:
        hit_cap = True
        logging.warning(
            "Hit mode-aware request cap (%d) for %s.",
            cfg.max_requests_for_mode(),
            cfg.ingest_mode,
        )

    return {
        "releases": releases,
        "request_count": requests_made,
        "hit_request_cap": hit_cap,
    }


def default_backfill_start(cfg: Config, now_utc: datetime) -> datetime:
    return now_utc - timedelta(days=cfg.lookback_days)


def resolve_backfill_bounds(cfg: Config, now_utc: datetime) -> tuple[datetime, datetime]:
    end_dt = parse_datetime(cfg.backfill_end) or now_utc
    start_dt = parse_datetime(cfg.backfill_start) or default_backfill_start(cfg, end_dt)
    if start_dt >= end_dt:
        raise ValueError("backfill_start must be earlier than backfill_end")
    return start_dt, end_dt


def build_chunk_windows(start_dt: datetime, end_dt: datetime, chunk_days: int) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    cursor = normalize_utc(start_dt)
    end_dt = normalize_utc(end_dt)
    delta = timedelta(days=chunk_days)
    while cursor < end_dt:
        chunk_end = min(cursor + delta, end_dt)
        windows.append((cursor, chunk_end))
        cursor = chunk_end
    return windows


def initialize_backfill_state(cfg: Config, now_utc: datetime) -> dict[str, Any]:
    start_dt, end_dt = resolve_backfill_bounds(cfg, now_utc)
    windows = build_chunk_windows(start_dt, end_dt, cfg.backfill_chunk_days)
    state = {
        "mode": "backfill",
        "backfill_start": start_dt.isoformat(),
        "backfill_end": end_dt.isoformat(),
        "chunk_days": cfg.backfill_chunk_days,
        "next_chunk_start": windows[0][0].isoformat() if windows else end_dt.isoformat(),
        "active_chunk_start": None,
        "active_chunk_end": None,
        "last_completed_chunk_start": None,
        "last_completed_chunk_end": None,
        "chunks_total": len(windows),
        "chunks_completed": 0,
        "request_count_total": 0,
        "updated_at": now_utc.isoformat(),
        "completed": False,
    }
    save_backfill_state(cfg, state)
    return state


def determine_windows(cfg: Config, now_utc: datetime) -> dict[str, Any]:
    if cfg.ingest_mode == "incremental":
        start_dt = get_last_run(cfg)
        end_dt = now_utc
        if start_dt >= end_dt:
            start_dt = end_dt - timedelta(minutes=15)

        # Enforce a minimum lookback window so frequent short runs still see meaningful data.
        # FTS updates on the order of hours; a window under 4h reliably returns 0 records.
        min_window_hours = int(os.getenv("TENDER_FTS_MIN_WINDOW_HOURS", "4"))
        min_start = end_dt - timedelta(hours=min_window_hours)
        if start_dt > min_start:
            logging.info(
                "FTS incremental window %.0f min is below minimum %dh floor — expanding start back to %s",
                (end_dt - start_dt).total_seconds() / 60,
                min_window_hours,
                min_start.strftime("%Y-%m-%dT%H:%MZ"),
            )
            start_dt = min_start

        return {
            "mode": "incremental",
            "windows": [(start_dt, end_dt)],
            "backfill_state": None,
            "backfill_state_file": None,
        }

    if cfg.ingest_mode == "recovery":
        end_dt = now_utc
        start_dt = end_dt - timedelta(days=cfg.recovery_days)
        return {
            "mode": "recovery",
            "windows": [(start_dt, end_dt)],
            "backfill_state": None,
            "backfill_state_file": None,
        }

    state = load_backfill_state(cfg)
    if not state:
        state = initialize_backfill_state(cfg, now_utc)

    backfill_end = parse_datetime(state.get("backfill_end")) or now_utc
    next_chunk_start = parse_datetime(state.get("next_chunk_start")) or backfill_end
    if next_chunk_start >= backfill_end:
        state["completed"] = True
        state["updated_at"] = now_utc.isoformat()
        save_backfill_state(cfg, state)
        return {
            "mode": "backfill",
            "windows": [],
            "backfill_state": state,
            "backfill_state_file": str(cfg.backfill_state_file),
        }

    chunk_end = min(next_chunk_start + timedelta(days=cfg.backfill_chunk_days), backfill_end)
    state["active_chunk_start"] = next_chunk_start.isoformat()
    state["active_chunk_end"] = chunk_end.isoformat()
    state["updated_at"] = now_utc.isoformat()
    save_backfill_state(cfg, state)
    return {
        "mode": "backfill",
        "windows": [(next_chunk_start, chunk_end)],
        "backfill_state": state,
        "backfill_state_file": str(cfg.backfill_state_file),
    }


def build_mode_metadata(
    cfg: Config,
    now_utc: datetime,
    windows: list[tuple[datetime, datetime]],
    backfill_state: dict[str, Any] | None,
) -> dict[str, Any]:
    window_start = windows[0][0] if windows else None
    window_end = windows[-1][1] if windows else None
    chunk_count = len(windows)
    chunks_completed = 0
    if backfill_state:
        chunk_count = int(backfill_state.get("chunks_total") or chunk_count)
        chunks_completed = int(backfill_state.get("chunks_completed") or 0)
    return {
        "ingest_mode": cfg.ingest_mode,
        "fts_window_start": window_start.isoformat() if window_start else None,
        "fts_window_end": window_end.isoformat() if window_end else None,
        "fts_chunk_count": chunk_count,
        "fts_chunks_completed": chunks_completed,
        "fts_backfill_state_file": str(cfg.backfill_state_file) if cfg.ingest_mode == "backfill" else None,
        "fts_backfill_completed": bool(backfill_state.get("completed")) if backfill_state else False,
        "fts_request_count": 0,
        "fts_hit_request_cap": False,
        "fts_partial_backfill": False,
        "fts_state_target": "backfill" if cfg.ingest_mode == "backfill" else "incremental",
    }


def fetch_fts_releases(cfg: Config | None = None) -> dict[str, Any]:
    """
    Fetch FTS releases plus operational metadata.
    Returns:
        {
            "releases": [...],
            "metadata": {...}
        }
    """
    if cfg is None:
        cfg = build_config_from_env()
    cfg.validate()
    cfg.ensure_dirs()

    started_dt = utc_now()
    plan = determine_windows(cfg, started_dt)
    windows = plan["windows"]
    backfill_state = plan["backfill_state"]
    metadata = build_mode_metadata(cfg, started_dt, windows, backfill_state)

    if not windows:
        logging.info("FTS backfill already complete; no remaining chunks.")
        metadata["fts_backfill_completed"] = True
        return {"releases": [], "metadata": metadata}

    logging.info("FTS ingest mode: %s", cfg.ingest_mode)
    all_releases: list[dict[str, Any]] = []
    total_requests = 0
    hit_request_cap = False
    chunks_completed = metadata["fts_chunks_completed"]

    with build_session(cfg) as session:
        for index, (chunk_start, chunk_end) in enumerate(windows, start=1):
            logging.info(
                "FTS chunk %d/%d | %s -> %s",
                index,
                len(windows),
                iso_z(chunk_start),
                iso_z(chunk_end),
            )
            page_result = iter_pages(
                session=session,
                cfg=cfg,
                updated_from=iso_z(chunk_start),
                updated_to=iso_z(chunk_end),
            )
            total_requests += int(page_result["request_count"])
            hit_request_cap = hit_request_cap or bool(page_result["hit_request_cap"])
            chunk_releases = page_result["releases"]
            all_releases.extend(chunk_releases)
            logging.info(
                "FTS chunk result | requests=%d | releases=%d | hit_cap=%s",
                page_result["request_count"],
                len(chunk_releases),
                page_result["hit_request_cap"],
            )

            if cfg.ingest_mode == "backfill":
                current_state = load_backfill_state(cfg) or {}
                current_state.update(
                    {
                        "mode": "backfill",
                        "active_chunk_start": chunk_start.isoformat(),
                        "active_chunk_end": chunk_end.isoformat(),
                        "request_count_total": int(current_state.get("request_count_total") or 0)
                        + int(page_result["request_count"]),
                        "updated_at": utc_now().isoformat(),
                    }
                )
                if page_result["hit_request_cap"]:
                    current_state["completed"] = False
                    save_backfill_state(cfg, current_state)
                    break

                chunks_completed += 1
                current_state["chunks_completed"] = chunks_completed
                current_state["last_completed_chunk_start"] = chunk_start.isoformat()
                current_state["last_completed_chunk_end"] = chunk_end.isoformat()
                current_state["next_chunk_start"] = chunk_end.isoformat()
                current_state["active_chunk_start"] = None
                current_state["active_chunk_end"] = None
                current_state["completed"] = chunk_end >= (parse_datetime(current_state.get("backfill_end")) or chunk_end)
                current_state["updated_at"] = utc_now().isoformat()
                save_backfill_state(cfg, current_state)

    metadata["fts_request_count"] = total_requests
    metadata["fts_hit_request_cap"] = hit_request_cap

    if cfg.ingest_mode == "backfill":
        final_state = load_backfill_state(cfg) or {}
        metadata["fts_chunks_completed"] = int(final_state.get("chunks_completed") or chunks_completed)
        metadata["fts_backfill_completed"] = bool(final_state.get("completed"))
        metadata["fts_partial_backfill"] = hit_request_cap or not metadata["fts_backfill_completed"]
    else:
        metadata["fts_chunks_completed"] = len(windows)
        metadata["fts_backfill_completed"] = False
        metadata["fts_partial_backfill"] = False

    if cfg.ingest_mode == "incremental" and not hit_request_cap:
        save_last_run(cfg, started_dt)
        logging.info("FTS incremental watermark updated -> %s", cfg.last_run_file)
    elif cfg.ingest_mode == "recovery":
        logging.info("FTS recovery run completed; incremental watermark preserved.")
    elif cfg.ingest_mode == "backfill":
        logging.info(
            "FTS backfill state updated -> %s | completed=%s | partial=%s",
            cfg.backfill_state_file,
            metadata["fts_backfill_completed"],
            metadata["fts_partial_backfill"],
        )

    logging.info("FTS: %d releases fetched", len(all_releases))
    return {
        "releases": [{"_source": "find_a_tender", **release} for release in all_releases],
        "metadata": metadata,
    }


def build_config_from_env(base_dir: Path | None = None) -> Config:
    root = Path(base_dir or os.getenv("TENDER_BASE_DIR") or DEFAULT_BASE_DIR)
    return Config(
        base_dir=root,
        lookback_days=int(os.getenv("FTS_LOOKBACK_DAYS", os.getenv("TENDER_FTS_LOOKBACK_DAYS", "30"))),
        recovery_days=int(os.getenv("TENDER_FTS_RECOVERY_DAYS", "3")),
        backfill_chunk_days=int(os.getenv("TENDER_FTS_BACKFILL_CHUNK_DAYS", "3")),
        limit_per_request=int(os.getenv("FTS_LIMIT", os.getenv("TENDER_FTS_LIMIT", "100"))),
        max_requests_incremental=int(os.getenv("TENDER_FTS_MAX_REQUESTS_INCREMENTAL", "10")),
        max_requests_recovery=int(os.getenv("TENDER_FTS_MAX_REQUESTS_RECOVERY", "25")),
        max_requests_backfill=int(os.getenv("TENDER_FTS_MAX_REQUESTS_BACKFILL", "200")),
        timeout=int(os.getenv("FTS_TIMEOUT", "30")),
        retry_total=int(os.getenv("FTS_RETRY_TOTAL", "3")),
        retry_backoff=float(os.getenv("FTS_RETRY_BACKOFF", "2.0")),
        max_429_attempts=int(os.getenv("FTS_MAX_429_ATTEMPTS", "4")),
        polite_delay_seconds=float(os.getenv("FTS_POLITE_DELAY", "1.0")),
        ingest_mode=os.getenv("TENDER_INGEST_MODE", "incremental").strip().lower(),
        backfill_start=os.getenv("TENDER_FTS_BACKFILL_START"),
        backfill_end=os.getenv("TENDER_FTS_BACKFILL_END"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FTS OCDS scraper")
    parser.add_argument("--base-dir", default=None)
    parser.add_argument("--ingest-mode", default=os.getenv("TENDER_INGEST_MODE", "incremental"))
    parser.add_argument("--lookback-days", type=int, default=int(os.getenv("TENDER_FTS_LOOKBACK_DAYS", "30")))
    parser.add_argument("--recovery-days", type=int, default=int(os.getenv("TENDER_FTS_RECOVERY_DAYS", "3")))
    parser.add_argument("--backfill-chunk-days", type=int, default=int(os.getenv("TENDER_FTS_BACKFILL_CHUNK_DAYS", "3")))
    parser.add_argument("--limit", type=int, default=int(os.getenv("TENDER_FTS_LIMIT", "100")))
    parser.add_argument("--max-requests-incremental", type=int, default=int(os.getenv("TENDER_FTS_MAX_REQUESTS_INCREMENTAL", "10")))
    parser.add_argument("--max-requests-recovery", type=int, default=int(os.getenv("TENDER_FTS_MAX_REQUESTS_RECOVERY", "25")))
    parser.add_argument("--max-requests-backfill", type=int, default=int(os.getenv("TENDER_FTS_MAX_REQUESTS_BACKFILL", "200")))
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retry-total", type=int, default=3)
    parser.add_argument("--retry-backoff", type=float, default=2.0)
    parser.add_argument("--max-429-attempts", type=int, default=4)
    parser.add_argument("--polite-delay", type=float, default=1.0)
    parser.add_argument("--backfill-start", default=os.getenv("TENDER_FTS_BACKFILL_START"))
    parser.add_argument("--backfill-end", default=os.getenv("TENDER_FTS_BACKFILL_END"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config(
        base_dir=Path(args.base_dir or os.getenv("TENDER_BASE_DIR") or DEFAULT_BASE_DIR),
        ingest_mode=str(args.ingest_mode).strip().lower(),
        lookback_days=args.lookback_days,
        recovery_days=args.recovery_days,
        backfill_chunk_days=args.backfill_chunk_days,
        limit_per_request=args.limit,
        max_requests_incremental=args.max_requests_incremental,
        max_requests_recovery=args.max_requests_recovery,
        max_requests_backfill=args.max_requests_backfill,
        timeout=args.timeout,
        retry_total=args.retry_total,
        retry_backoff=args.retry_backoff,
        max_429_attempts=args.max_429_attempts,
        polite_delay_seconds=args.polite_delay,
        backfill_start=args.backfill_start,
        backfill_end=args.backfill_end,
    )
    cfg.validate()
    cfg.ensure_dirs()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        result = fetch_fts_releases(cfg)
        metadata = result["metadata"]
        print(json.dumps(
            {
                "release_count": len(result["releases"]),
                "ingest_mode": metadata["ingest_mode"],
                "fts_window_start": metadata["fts_window_start"],
                "fts_window_end": metadata["fts_window_end"],
                "fts_request_count": metadata["fts_request_count"],
                "fts_hit_request_cap": metadata["fts_hit_request_cap"],
                "fts_backfill_completed": metadata["fts_backfill_completed"],
                "fts_partial_backfill": metadata["fts_partial_backfill"],
            },
            indent=2,
        ))
    except KeyboardInterrupt:
        logging.warning("FTS scrape interrupted.")
        sys.exit(1)
    except Exception:
        logging.exception("FTS scrape failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
