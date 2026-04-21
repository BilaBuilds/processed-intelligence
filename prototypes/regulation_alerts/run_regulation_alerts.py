#!/usr/bin/env python3
"""
OpenClaw Regs MVP - Regulation Change Intelligence Feed
Usage: python run_regulation_alerts.py [--dry-run] [--limit N] [--sources PATH] [--config-dir PATH]
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as top-level script
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from src.ingest import run_ingest
from src.normalize import run_normalize
from src.match import run_match
from src.select import run_select
from src.notify import run_notify
from src.manifest import build_manifest, write_manifest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")


def _load_json(path: Path) -> object:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="OpenClaw Regs MVP pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing artifacts")
    parser.add_argument("--limit", type=int, default=None, help="Cap fetch per source")
    parser.add_argument("--sources", type=str, default=None, help="Override sources.json path")
    parser.add_argument("--config-dir", type=str, default=None, help="Override config/ directory")
    args = parser.parse_args()

    started_at = _now_iso()
    run_id = _make_run_id()

    config_dir = Path(args.config_dir) if args.config_dir else BASE_DIR / "config"
    sources_path = Path(args.sources) if args.sources else config_dir / "sources.json"
    products_dir = config_dir / "products"
    clients_dir = config_dir / "clients"
    data_dir = BASE_DIR / "data" / "runs" / run_id

    logger.info(f"=== OpenClaw Regs MVP | run_id={run_id} ===")

    # 1. Load sources
    sources = _load_json(sources_path)
    products = [_load_json(p) for p in sorted(products_dir.glob("*.json"))]
    clients = [_load_json(c) for c in sorted(clients_dir.glob("*.json"))]

    ingest_status = "ok"
    normalize_status = "ok"
    match_status = "ok"
    products_status = "ok"
    clients_status = "ok"
    notify_status_val = "ok"
    raw_count = 0
    normalized_count = 0
    scored_count = 0
    source_health = {}
    product_summaries = {}
    client_summaries = {}

    # 2. Ingest
    try:
        raw_records, source_health = run_ingest(sources, data_dir, limit=args.limit, dry_run=args.dry_run)
        raw_count = len(raw_records)
        sources_ok = sum(1 for v in source_health.values() if v["status"] == "ok")
        sources_err = sum(1 for v in source_health.values() if v["status"] == "error")
    except Exception as e:
        logger.error(f"[pipeline] ingest failed: {e}")
        ingest_status = "error"
        raw_records = []
        sources_ok = 0
        sources_err = len(sources)

    # 3. Normalize
    try:
        normalized = run_normalize(raw_records, data_dir, dry_run=args.dry_run)
        normalized_count = len(normalized)
    except Exception as e:
        logger.error(f"[pipeline] normalize failed: {e}")
        normalize_status = "error"
        normalized = []

    # 4. Match
    try:
        scored = run_match(normalized, data_dir, dry_run=args.dry_run)
        scored_count = len(scored)
    except Exception as e:
        logger.error(f"[pipeline] match failed: {e}")
        match_status = "error"
        scored = []

    # 5. Select (products then clients)
    if not products:
        products_status = "no_products"
    if not clients:
        clients_status = "no_clients"

    product_results = {}
    client_results = {}
    try:
        product_results, client_results = run_select(
            scored, products, clients, data_dir, dry_run=args.dry_run
        )
        product_summaries = {pid: pr["summary"] for pid, pr in product_results.items()}
        client_summaries = {cid: cr["summary"] for cid, cr in client_results.items()}
        if products and products_status == "ok":
            products_status = "ok"
        if clients and clients_status == "ok":
            clients_status = "ok"
    except Exception as e:
        logger.error(f"[pipeline] select failed: {e}")
        products_status = "error"
        clients_status = "error"

    # 6. Notify
    try:
        client_results = run_notify(run_id, client_results, data_dir, dry_run=args.dry_run)
        client_summaries = {cid: cr["summary"] for cid, cr in client_results.items()}
    except Exception as e:
        logger.error(f"[pipeline] notify failed: {e}")
        notify_status_val = "error"

    clients_notified = sum(
        1 for cs in client_summaries.values() if cs.get("notified", False)
    )

    # 7. Write manifest
    completed_at = _now_iso()
    manifest = build_manifest(
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        ingest_status=ingest_status,
        raw_count=raw_count,
        normalize_status=normalize_status,
        normalized_count=normalized_count,
        match_status=match_status,
        scored_count=scored_count,
        products_status=products_status,
        products_generated=len(product_results),
        clients_status=clients_status,
        clients_notified=clients_notified,
        notify_status=notify_status_val,
        source_health=source_health,
        product_summaries=product_summaries,
        client_summaries=client_summaries,
    )

    if not args.dry_run:
        manifest_path = write_manifest(manifest, data_dir)
    else:
        manifest_path = data_dir / "run_manifest.json"
        logger.info("[pipeline] dry-run: manifest not written")

    # Print summary
    print(f"\nRun ID:   {run_id}")
    print(f"Sources:  {sources_ok} ok, {sources_err} error")
    print(f"Raw:      {raw_count} records")
    print(f"Scored:   {scored_count} records")
    print(f"Products: {len(product_results)} generated")
    print(f"Clients:  {len(client_summaries)} total, {clients_notified} notified")
    print(f"Manifest: {manifest_path}")
    if args.dry_run:
        print("(dry-run: no artifacts written)")


if __name__ == "__main__":
    main()
