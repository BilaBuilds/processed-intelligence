"""
src/ingest.py
=============
Step 1 - Ingest

Scrapes raw tenders from all sources and writes raw_tenders.jsonl.

Sources:
  1. Contracts Finder  (primary - open REST API)
  2. Find a Tender     (secondary - uses fts_scraper.py)

If a source fails, the run continues with a source health flag in context.
The pipeline only hard-fails if ALL sources fail.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger("ingest")

CONTRACTS_FINDER_URL = (
    "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
    "?limit=100&offset=0&releaseTag=tender"
)


def parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def latest_record_timestamp(records: list[dict]) -> str | None:
    latest: datetime | None = None
    for rec in records:
        candidate = (
            parse_iso_utc(rec.get("date"))
            or parse_iso_utc((rec.get("tender", {}) or {}).get("datePublished"))
            or parse_iso_utc((rec.get("tender", {}) or {}).get("dateModified"))
        )
        if candidate and (latest is None or candidate > latest):
            latest = candidate
    return latest.isoformat() if latest else None


def fetch_contracts_finder() -> dict:
    log.info("Fetching Contracts Finder...")
    headers = {"Accept": "application/json"}
    resp = requests.get(CONTRACTS_FINDER_URL, headers=headers, timeout=30)
    resp.raise_for_status()
    releases = resp.json().get("releases", [])
    log.info("Contracts Finder: %d releases fetched", len(releases))

    # Count by release_tag for visibility / audit
    tag_counts: dict[str, int] = {}
    for r in releases:
        for tag in r.get("tag", []) or []:
            tag_str = str(tag).strip()
            if tag_str:
                tag_counts[tag_str] = tag_counts.get(tag_str, 0) + 1

    log.info(
        "CF release_tag distribution: %s",
        ", ".join(f"{t}={c}" for t, c in sorted(tag_counts.items())),
    )

    return {
        "records": [{"_source": "contracts_finder", **r} for r in releases],
        "cf_release_tag_counts": tag_counts,
    }


def fetch_find_a_tender() -> list[dict]:
    log.info("Fetching Find a Tender (FTS)...")

    from src.fts_scraper import build_config_from_env, fetch_fts_releases

    cfg = build_config_from_env()
    cfg.validate()

    result = fetch_fts_releases(cfg)
    releases = result["releases"]
    metadata = result["metadata"]
    log.info("Find a Tender: %d releases fetched", len(releases))
    return {"records": releases, "metadata": metadata}


def run(context: dict) -> dict:
    run_dir: Path = context["run_dir"]
    data_dir: Path = context.get("data_dir") or run_dir.parent.parent
    raw_file = run_dir / "raw_tenders.jsonl"

    all_raw: list[dict] = []
    source_health: dict[str, str] = {}
    source_counts: dict[str, int] = {}
    source_freshness: dict[str, str | None] = {}
    cf_release_tag_counts: dict[str, int] = {}

    fts_metadata: dict[str, object] = {}

    sources = [
        ("find_a_tender", fetch_find_a_tender),
        ("contracts_finder", fetch_contracts_finder),
    ]

    for source_name, fetch_fn in sources:
        try:
            raw_result = fetch_fn()
            if isinstance(raw_result, dict) and "records" in raw_result:
                records = raw_result.get("records", [])
                if source_name == "find_a_tender":
                    fts_metadata = dict(raw_result.get("metadata") or {})
                elif source_name == "contracts_finder":
                    cf_release_tag_counts = raw_result.get("cf_release_tag_counts", {})
            else:
                records = raw_result
            all_raw.extend(records)
            source_health[source_name] = f"ok ({len(records)} records)"
            source_counts[source_name] = len(records)
            source_freshness[source_name] = latest_record_timestamp(records)
        except Exception as exc:
            log.warning("Source '%s' failed: %s - continuing with other sources", source_name, exc)
            source_health[source_name] = f"failed: {exc}"
            source_counts[source_name] = 0
            source_freshness[source_name] = None

    if not all_raw:
        raise RuntimeError("All sources failed - no data to process.")

    with open(raw_file, "w", encoding="utf-8") as f:
        for record in all_raw:
            f.write(json.dumps(record, default=str) + "\n")

    log.info(
        "Ingest complete: %d raw records from %d sources -> %s",
        len(all_raw),
        len(sources),
        raw_file.name,
    )

    for source, status in source_health.items():
        log.info("  Source health | %s: %s", source, status)

    # Persist FTS batch count for cooldown guard
    fts_count = source_counts.get("find_a_tender", 0)
    try:
        from src.run_guard import save_fts_batch_count
        save_fts_batch_count(data_dir, fts_count)
    except Exception as exc:
        log.warning("Could not save FTS batch count: %s", exc)

    return {
        "raw_count": len(all_raw),
        "raw_file": raw_file,
        "source_health": source_health,
        "ingest_counts_by_source": source_counts,
        "source_freshness": source_freshness,
        "cf_release_tag_counts": cf_release_tag_counts,
        **fts_metadata,
    }
