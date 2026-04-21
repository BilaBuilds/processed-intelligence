#!/usr/bin/env python3
"""
scripts/run_supplier_match.py
==============================
Standalone end-to-end supplier matching validation.

Loads the latest (or specified) decision_shortlist.json, runs it through
the full supplier intelligence pipeline, writes supplier_matches.json, and
prints a structured report.

Usage:
    python3 scripts/run_supplier_match.py
    python3 scripts/run_supplier_match.py --run-id 2026-04-21_155843
    python3 scripts/run_supplier_match.py --suppliers path/to/suppliers.csv
    python3 scripts/run_supplier_match.py --market social_housing
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure repo root is on the path when run directly
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from src.supplier.ingest_suppliers import ingest_suppliers
from src.supplier.normalize_suppliers import normalize_suppliers
from src.supplier.match_suppliers import load_shortlist, match_suppliers
from src.market.registry import get_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("run_supplier_match")

DEFAULT_SUPPLIER_CSV = _REPO_ROOT / "tests" / "fixtures" / "suppliers_construction.csv"
DEFAULT_MARKET = "construction"
TOP_N_REPORT = 3


def resolve_shortlist(run_id: str | None) -> tuple[Path, str]:
    runs_dir = _REPO_ROOT / "data" / "runs"
    if not runs_dir.exists():
        raise FileNotFoundError(f"Runs directory not found: {runs_dir}")

    if run_id:
        shortlist_path = runs_dir / run_id / "decision_shortlist.json"
        if not shortlist_path.exists():
            raise FileNotFoundError(f"No shortlist at: {shortlist_path}")
        return shortlist_path, run_id

    run_dirs = sorted(runs_dir.iterdir(), reverse=True)
    for rd in run_dirs:
        candidate = rd / "decision_shortlist.json"
        if candidate.exists():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            records = data if isinstance(data, list) else data.get("opportunities", [])
            if records:
                return candidate, rd.name

    raise FileNotFoundError("No non-empty decision_shortlist.json found in data/runs/")


def print_report(tenders, matches, result, profile) -> None:
    from collections import defaultdict

    print()
    print("=" * 70)
    print("  SUPPLIER MATCH REPORT")
    print("=" * 70)
    print(f"  Market profile : {profile.market_id} v{profile.version}")
    print(f"  Tenders        : {result.tenders_processed}")
    print(f"  Suppliers eval : {result.suppliers_evaluated}")
    print(f"  Excluded       : {result.suppliers_excluded}")
    print(f"  Included       : {result.matches_included} (score ≥ {profile.min_match_score}, top {profile.top_n_per_tender}/tender)")
    print()

    by_tender: dict[str, list] = defaultdict(list)
    for m in matches:
        by_tender[m.tender_id].append(m)

    for tender in tenders:
        tid = tender.id
        tender_matches = by_tender.get(tid, [])
        included = [m for m in tender_matches if m.included_in_output]
        value_str = f"£{tender.effective_value:,.0f}" if tender.effective_value else "value unknown"
        print(f"  ── {tender.title[:60]}")
        print(f"     {tender.decision_verdict or '?'} | {value_str} | {tender.effective_region or 'region unknown'}")

        if not included:
            all_above = [m for m in tender_matches if m.above_threshold and not m.disqualified]
            if not all_above:
                print(f"     No suppliers met threshold ({profile.min_match_score})")
            else:
                print(f"     {len(all_above)} above threshold but none in top-N")
        else:
            for rank, m in enumerate(included[:TOP_N_REPORT], 1):
                bd = m.score_breakdown
                cap = f"cap={bd.capability_fit.weighted:.1f}" if bd else "—"
                reg = f"reg={bd.regional_fit.weighted:.1f}" if bd else "—"
                val = f"val={bd.value_band_fit.weighted:.1f}" if bd else "—"
                sec = f"sec={bd.sector_experience.weighted:.1f}" if bd else "—"
                prio = m.outreach_priority or "—"
                print(f"     #{rank} {m.supplier_name:<35} {m.total_score:5.1f}  [{cap} {reg} {val} {sec}]  {prio}")
        print()

    # Exclusion summary
    if result.exclusion_reasons:
        print(f"  Excluded suppliers ({result.suppliers_excluded} unique):")
        seen = set()
        for reason in result.exclusion_reasons:
            sid = reason.split(":")[0]
            if sid not in seen:
                seen.add(sid)
                print(f"     {reason}")
        print()

    # Scoring quality flags
    print("  SCORING QUALITY FLAGS")
    print("  ─────────────────────")
    _flag_scoring_quality(tenders, matches, profile)
    print("=" * 70)
    print()


def _flag_scoring_quality(tenders, matches, profile) -> None:
    from collections import defaultdict

    by_tender = defaultdict(list)
    for m in matches:
        by_tender[m.tender_id].append(m)

    flags = []
    for tender in tenders:
        tid = tender.id
        tender_matches = [m for m in by_tender[tid] if not m.disqualified]
        if not tender_matches:
            continue

        top = max(tender_matches, key=lambda m: m.total_score)
        if top.score_breakdown is None:
            continue

        bd = top.score_breakdown
        cap_pct = bd.capability_fit.weighted / top.total_score * 100 if top.total_score > 0 else 0
        reg_pct = bd.regional_fit.weighted / top.total_score * 100 if top.total_score > 0 else 0

        # Flag: capability dominates > 55% of total score
        if cap_pct > 55 and top.total_score >= profile.min_match_score:
            flags.append(
                f"  ⚠  capability_fit dominates ({cap_pct:.0f}% of score) for '{tender.title[:50]}'"
            )

        # Flag: tender over profile ceiling
        if tender.effective_value and profile.value_bands.ceiling:
            if tender.effective_value > profile.value_bands.ceiling:
                flags.append(
                    f"  ⚠  Tender value £{tender.effective_value:,.0f} exceeds market ceiling "
                    f"£{profile.value_bands.ceiling:,.0f}: '{tender.title[:45]}'"
                )

        # Flag: suspiciously high score (top score ≥ 90)
        if top.total_score >= 90:
            flags.append(
                f"  ⚠  Score {top.total_score:.1f} ≥ 90 for {top.supplier_name} on '{tender.title[:45]}'"
            )

    if not flags:
        print("  ✓  No scoring anomalies detected")
    else:
        for f in flags:
            print(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run supplier match E2E validation")
    parser.add_argument("--run-id", default=None, help="Pipeline run ID (default: latest non-empty)")
    parser.add_argument("--suppliers", default=str(DEFAULT_SUPPLIER_CSV), help="Supplier CSV/JSON path")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="Market profile slug (default: construction)")
    args = parser.parse_args()

    # 1. Resolve shortlist
    shortlist_path, run_id = resolve_shortlist(args.run_id)
    log.info("Shortlist: %s (%s)", shortlist_path, run_id)

    tenders = load_shortlist(shortlist_path)
    log.info("Loaded %d tenders (BID/REVIEW/NO_BID)", len(tenders))

    # 2. Load suppliers
    supplier_path = Path(args.suppliers)
    raw_suppliers, ingest_result = ingest_suppliers(supplier_path)
    log.info("Ingested %d supplier rows (%d skipped)", ingest_result.rows_returned, ingest_result.rows_skipped)

    suppliers, norm_result = normalize_suppliers(raw_suppliers)
    log.info("Normalised %d suppliers (%d skipped)", norm_result.records_out, norm_result.records_skipped)

    # 3. Load market profile
    profile = get_profile(args.market, force_reload=True)
    log.info("Market profile: %s v%s", profile.market_id, profile.version)

    # 4. Run matching
    output_path = _REPO_ROOT / "data" / "runs" / run_id / "supplier_matches.json"
    matches, result = match_suppliers(
        tenders=tenders,
        suppliers=suppliers,
        profile=profile,
        run_id=run_id,
        output_path=output_path,
    )

    log.info("Output: %s", output_path)

    # 5. Print report
    print_report(tenders, matches, result, profile)


if __name__ == "__main__":
    main()
