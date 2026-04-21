import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ALLOWED_STATUSES = {"ok", "skipped", "error", "no_products", "no_clients"}


def _validate_status(status: str, field: str) -> str:
    if status not in ALLOWED_STATUSES:
        logger.error(f"[manifest] invalid status '{status}' for field '{field}' — defaulting to 'error'")
        return "error"
    return status


def build_manifest(
    run_id: str,
    started_at: str,
    completed_at: str,
    ingest_status: str,
    raw_count: int,
    normalize_status: str,
    normalized_count: int,
    match_status: str,
    scored_count: int,
    products_status: str,
    products_generated: int,
    clients_status: str,
    clients_notified: int,
    notify_status: str,
    source_health: Dict[str, dict],
    product_summaries: Dict[str, dict],
    client_summaries: Dict[str, dict],
) -> dict:
    return {
        "run_id": run_id,
        "product": "regulation_alerts",
        "started_at": started_at,
        "completed_at": completed_at,
        "steps": {
            "ingest": {
                "status": _validate_status(ingest_status, "ingest"),
                "raw_count": raw_count,
            },
            "normalize": {
                "status": _validate_status(normalize_status, "normalize"),
                "normalized_count": normalized_count,
            },
            "match": {
                "status": _validate_status(match_status, "match"),
                "scored_count": scored_count,
            },
            "products": {
                "status": _validate_status(products_status, "products"),
                "generated_count": products_generated,
            },
            "clients": {
                "status": _validate_status(clients_status, "clients"),
                "notified_count": clients_notified,
            },
            "notify": {
                "status": _validate_status(notify_status, "notify"),
            },
        },
        "source_health": source_health,
        "products": product_summaries,
        "clients": client_summaries,
    }


def write_manifest(manifest: dict, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "run_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)
    logger.info(f"[manifest] written to {manifest_path}")
    return manifest_path
