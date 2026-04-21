import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .schema import RegulationRecord, record_to_dict
from .ledger import load_seen_ids, append_seen_ids, make_ledger_entry

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _matches_include_keywords(record: RegulationRecord, keywords: List[str]) -> bool:
    if not keywords:
        return True
    text = (record.title + " " + record.summary + " " + record.raw_text).lower()
    return any(kw.lower() in text for kw in keywords)


def _matches_exclude_keywords(record: RegulationRecord, keywords: List[str]) -> bool:
    if not keywords:
        return False
    text = (record.title + " " + record.summary + " " + record.raw_text).lower()
    return any(kw.lower() in text for kw in keywords)


def select_for_product(
    scored: List[RegulationRecord],
    product: dict,
) -> Tuple[List[dict], dict]:
    """
    Apply product filters and return (shortlist_dicts, filter_stages).
    """
    stages: Dict[str, int] = {}
    working = list(scored)
    stages["initial"] = len(working)

    include_kws = product.get("include_keywords", [])
    exclude_kws = product.get("exclude_keywords", [])
    regions = product.get("regions", [])
    trade_tags = product.get("trade_tags", [])
    impact_types = product.get("impact_types", [])
    min_score = product.get("min_score", 0)

    if include_kws:
        working = [r for r in working if _matches_include_keywords(r, include_kws)]
    stages["after_include_keywords"] = len(working)

    if exclude_kws:
        working = [r for r in working if not _matches_exclude_keywords(r, exclude_kws)]
    stages["after_exclude_keywords"] = len(working)

    if regions:
        working = [r for r in working if r.region in regions]
    stages["after_region"] = len(working)

    if trade_tags:
        working = [r for r in working if any(t in r.trade_tags for t in trade_tags)]
    stages["after_trade_tags"] = len(working)

    if impact_types:
        working = [r for r in working if r.impact_type in impact_types]
    stages["after_impact_types"] = len(working)

    working = [r for r in working if r.relevance_score >= min_score]
    stages["after_min_score"] = len(working)

    working.sort(key=lambda r: r.relevance_score, reverse=True)
    shortlist_size = product.get("shortlist_size", 10)
    shortlist = working[:shortlist_size]

    return [record_to_dict(r) for r in shortlist], stages


def run_select(
    scored: List[RegulationRecord],
    products: List[dict],
    clients: List[dict],
    run_dir: Path,
    dry_run: bool = False,
    seen_dir: Optional[Path] = None,
) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """
    Run selection for all products and clients.
    Returns (product_results, client_results).
    Each value has keys: shortlist, summary.
    """
    product_results: Dict[str, dict] = {}
    client_results: Dict[str, dict] = {}
    run_id = run_dir.name

    # Seen-ledger lives at data/seen/ adjacent to data/runs/
    if seen_dir is None:
        seen_dir = run_dir.parent.parent / "seen"

    # --- Products ---
    for product in products:
        if not product.get("enabled", True):
            continue
        product_id = product["id"]
        shortlist, stages = select_for_product(scored, product)

        summary = {
            "product_id": product_id,
            "display_name": product.get("display_name", product_id),
            "run_id": run_id,
            "generated_at": _now_iso(),
            "item_count": len(shortlist),
            "filter_stages": stages,
        }

        product_results[product_id] = {"shortlist": shortlist, "summary": summary}

        if not dry_run:
            prod_dir = run_dir / "products" / product_id
            prod_dir.mkdir(parents=True, exist_ok=True)
            with open(prod_dir / "product_shortlist.json", "w") as f:
                json.dump(shortlist, f, indent=2, ensure_ascii=True)
            with open(prod_dir / "product_summary.json", "w") as f:
                json.dump(summary, f, indent=2, ensure_ascii=True)
            logger.info(f"[select] product {product_id}: {len(shortlist)} items")

    # --- Clients ---
    for client in clients:
        if not client.get("active", True):
            continue
        client_id = client["client_id"]
        subscribed = client.get("subscribed_products", [])
        client_filters = client.get("filters", {})
        client_min_score = client_filters.get("min_score", 0)
        client_regions = client_filters.get("regions", [])
        authority_whitelist = client_filters.get("authority_whitelist", [])

        # Merge + dedupe shortlists from subscribed products
        merged: Dict[str, dict] = {}
        for prod_id in subscribed:
            if prod_id in product_results:
                for item in product_results[prod_id]["shortlist"]:
                    merged[item["id"]] = item

        # Apply client filters
        filtered = list(merged.values())
        if client_min_score:
            filtered = [r for r in filtered if r["relevance_score"] >= client_min_score]
        if client_regions:
            filtered = [r for r in filtered if r["region"] in client_regions]
        if authority_whitelist:
            filtered = [r for r in filtered if r["authority"] in authority_whitelist]

        filtered.sort(key=lambda r: r["relevance_score"], reverse=True)

        # Novelty tracking via seen-ledger
        seen_ids = load_seen_ids(client_id, seen_dir)
        new_records = [r for r in filtered if r["id"] not in seen_ids]
        new_count = len(new_records)

        if not dry_run and new_records:
            entries = [make_ledger_entry(r["id"], run_id) for r in new_records]
            append_seen_ids(client_id, entries, seen_dir)

        summary = {
            "client_id": client_id,
            "display_name": client.get("display_name", client_id),
            "run_id": run_id,
            "generated_at": _now_iso(),
            "subscribed_products": subscribed,
            "item_count": len(filtered),
            "new_count": new_count,
            "notified": False,
            "notify_status": "skipped",
        }

        client_results[client_id] = {
            "shortlist": filtered,
            "new_records": new_records,
            "summary": summary,
            "notify_config": client.get("notify", {}),
        }

        if not dry_run:
            client_dir = run_dir / "clients" / client_id
            client_dir.mkdir(parents=True, exist_ok=True)
            shortlist_payload = {"records": filtered, "new_records": new_records}
            with open(client_dir / "client_shortlist.json", "w") as f:
                json.dump(shortlist_payload, f, indent=2, ensure_ascii=True)
            with open(client_dir / "client_summary.json", "w") as f:
                json.dump(summary, f, indent=2, ensure_ascii=True)
            logger.info(f"[select] client {client_id}: {len(filtered)} items, {new_count} new")

    return product_results, client_results
