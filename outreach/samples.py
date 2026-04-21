"""
Sample bundle generation from existing run artifacts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(os.getenv("TENDER_BASE_DIR", str(Path(__file__).resolve().parent.parent))).expanduser().resolve()
RUNS_DIR = BASE_DIR / "data" / "runs"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def latest_successful_run_id(runs_dir: Path = RUNS_DIR) -> str:
    candidates: list[str] = []
    if not runs_dir.exists():
        raise FileNotFoundError(f"No runs directory found at {runs_dir}")
    for run_dir in sorted((path for path in runs_dir.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True):
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.exists():
            continue
        manifest = load_json(manifest_path)
        if str(manifest.get("status") or "").startswith("success"):
            candidates.append(run_dir.name)
    if not candidates:
        raise FileNotFoundError("No successful run manifests found.")
    return candidates[0]


def load_run_bucket(run_dir: Path, bucket_name: str) -> list[dict[str, Any]]:
    if bucket_name == "shortlist":
        shortlist_json = run_dir / "shortlist.json"
        shortlist_jsonl = run_dir / "shortlist.jsonl"
        if shortlist_json.exists():
            return list(load_json(shortlist_json).get("opportunities", []))
        return load_jsonl(shortlist_jsonl)
    if bucket_name == "review":
        return load_jsonl(run_dir / "review_candidates.jsonl")
    if bucket_name == "market_intelligence":
        market_path = run_dir / "market_intelligence.jsonl"
        if market_path.exists():
            return load_jsonl(market_path)
        rejected = load_jsonl(run_dir / "rejected_tenders.jsonl")
        return [
            row
            for row in rejected
            if "award" in set(row.get("rejection_reasons") or [])
            or "awardUpdate" in set(row.get("rejection_reasons") or [])
        ]
    raise ValueError(f"Unsupported bucket: {bucket_name}")


def text_blob(record: dict[str, Any]) -> str:
    parts = [
        str(record.get("title") or ""),
        str(record.get("description") or ""),
        str(record.get("buyer_name") or record.get("buyer") or ""),
        " ".join(str(code) for code in (record.get("cpv_codes") or [])),
    ]
    return " ".join(part for part in parts if part).lower()


def split_terms(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def relevance_score(record: dict[str, Any], contact: dict[str, Any]) -> int:
    score = 0
    contact_region = str(contact.get("region") or "").strip().lower()
    record_region = str(record.get("region") or "").strip().lower()
    if contact_region and record_region:
        if contact_region in record_region or record_region in contact_region:
            score += 2
    contact_sectors = split_terms(contact.get("sectors"))
    if contact_sectors:
        haystack = text_blob(record)
        for sector in contact_sectors:
            if sector in haystack:
                score += 1
    return score


def prioritize_records(records: list[dict[str, Any]], contact: dict[str, Any]) -> list[dict[str, Any]]:
    indexed = list(enumerate(records))
    indexed.sort(key=lambda item: (-relevance_score(item[1], contact), item[0]))
    return [item[1] for item in indexed]


def compact_item(record: dict[str, Any], bucket: str) -> dict[str, Any]:
    return {
        "bucket": bucket,
        "id": record.get("id") or record.get("opportunity_id") or record.get("ocid"),
        "title": record.get("title"),
        "buyer_name": record.get("buyer_name") or record.get("buyer"),
        "region": record.get("region"),
        "deadline_at": record.get("deadline_at") or record.get("deadline"),
        "value_amount": record.get("value_amount") if record.get("value_amount") is not None else record.get("value"),
        "value_currency": record.get("value_currency") or record.get("currency"),
        "source_url": record.get("source_url") or record.get("url"),
        "score": record.get("score"),
        "selection_bucket": record.get("selection_bucket") or bucket,
    }


def build_sample_bundle(
    *,
    run_id: str,
    contact: dict[str, Any],
    runs_dir: Path = RUNS_DIR,
    shortlist_limit: int = 3,
    review_limit: int = 2,
    intelligence_limit: int = 2,
) -> dict[str, Any]:
    run_dir = runs_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    shortlisted = prioritize_records(load_run_bucket(run_dir, "shortlist"), contact)[:shortlist_limit]
    review_candidates = prioritize_records(load_run_bucket(run_dir, "review"), contact)[:review_limit]
    market_intelligence = prioritize_records(load_run_bucket(run_dir, "market_intelligence"), contact)[:intelligence_limit]

    items = (
        [compact_item(record, "shortlist") for record in shortlisted]
        + [compact_item(record, "review") for record in review_candidates]
        + [compact_item(record, "market_intelligence") for record in market_intelligence]
    )

    return {
        "run_id": run_id,
        "contact_id": contact.get("id"),
        "company_name": contact.get("company_name"),
        "contact_name": contact.get("contact_name"),
        "region": contact.get("region"),
        "sectors": contact.get("sectors"),
        "cta": "Subscribe for a weekly shortlist",
        "counts": {
            "shortlist": len(shortlisted),
            "review": len(review_candidates),
            "market_intelligence": len(market_intelligence),
        },
        "shortlist": [compact_item(record, "shortlist") for record in shortlisted],
        "review_candidates": [compact_item(record, "review") for record in review_candidates],
        "market_intelligence": [compact_item(record, "market_intelligence") for record in market_intelligence],
        "items": items,
    }
