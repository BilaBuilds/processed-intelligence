"""
src/supplier_runner.py
======================
Minimal pipeline wrapper for the supplier intelligence layer.

Consumes the post-decision shortlist artifact, runs deterministic supplier
matching, and returns manifest-friendly summary fields to the main pipeline.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from src.market.registry import get_profile
from src.supplier.ingest_suppliers import ingest_suppliers
from src.supplier.match_suppliers import load_shortlist, match_suppliers
from src.supplier.normalize_suppliers import normalize_suppliers

log = logging.getLogger("supplier.runner")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUPPLIER_SOURCE = REPO_ROOT / "tests" / "fixtures" / "suppliers_construction.csv"
DEFAULT_MARKET_PROFILE = "construction"
ENV_SUPPLIER_SOURCE = "TENDER_SUPPLIER_SOURCE"
ENV_MARKET_PROFILE = "TENDER_SUPPLIER_MARKET"


def _resolve_supplier_source(context: dict) -> Path:
    configured = os.getenv(ENV_SUPPLIER_SOURCE) or context.get("supplier_source_file")
    return Path(configured) if configured else DEFAULT_SUPPLIER_SOURCE


def _resolve_market_profile(context: dict) -> str:
    return os.getenv(ENV_MARKET_PROFILE) or context.get("supplier_market_profile") or DEFAULT_MARKET_PROFILE


def _skipped_result(context: dict) -> dict:
    return {
        "supplier_match_status": "skipped",
        "supplier_match_tenders_processed": 0,
        "supplier_match_suppliers_evaluated": 0,
        "supplier_match_matches_total": 0,
        "supplier_match_matches_included": 0,
        "supplier_match_suppliers_excluded": 0,
        "supplier_match_market_profile": _resolve_market_profile(context),
        "supplier_match_market_profile_version": None,
        "supplier_match_source_file": str(_resolve_supplier_source(context)),
        "supplier_matches_file": None,
    }


def run(context: dict) -> dict:
    """
    Run supplier matching against the decision shortlist.

    Returns a compact result dict for manifest/context updates. Raises on
    unexpected supplier ingest/normalize/match failures; the pipeline treats
    this step as non-fatal.
    """
    run_dir = Path(context["run_dir"])
    shortlist_file = context.get("shortlist_file")

    if not shortlist_file:
        log.info("Supplier match skipped: no shortlist_file present in context.")
        return _skipped_result(context)

    tenders = load_shortlist(Path(shortlist_file))
    if not tenders:
        log.info("Supplier match skipped: decision shortlist is empty.")
        return _skipped_result(context)

    supplier_source = _resolve_supplier_source(context)
    profile_slug = _resolve_market_profile(context)
    output_path = run_dir / "supplier_matches.json"

    raw_suppliers, _ingest_result = ingest_suppliers(supplier_source)
    suppliers, _normalize_result = normalize_suppliers(raw_suppliers)
    profile = get_profile(profile_slug, force_reload=True)
    _matches, match_result = match_suppliers(
        tenders=tenders,
        suppliers=suppliers,
        profile=profile,
        run_id=str(context.get("run_id", run_dir.name)),
        output_path=output_path,
    )

    log.info(
        "Supplier match complete: tenders=%d suppliers=%d included=%d excluded=%d",
        match_result.tenders_processed,
        match_result.suppliers_evaluated,
        match_result.matches_included,
        match_result.suppliers_excluded,
    )

    return {
        "supplier_match_status": "ok",
        "supplier_match_tenders_processed": match_result.tenders_processed,
        "supplier_match_suppliers_evaluated": match_result.suppliers_evaluated,
        "supplier_match_matches_total": match_result.matches_total,
        "supplier_match_matches_included": match_result.matches_included,
        "supplier_match_suppliers_excluded": match_result.suppliers_excluded,
        "supplier_match_market_profile": match_result.market_profile,
        "supplier_match_market_profile_version": match_result.market_profile_version,
        "supplier_match_source_file": str(supplier_source),
        "supplier_matches_file": output_path,
    }
