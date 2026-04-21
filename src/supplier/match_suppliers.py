"""
src/supplier/match_suppliers.py
================================
Phase 4 — deterministic supplier matching engine.

Reads the core pipeline's decision_shortlist.json and scores every
supplier record against every shortlisted tender using the market profile
scoring weights. No AI, no fuzzy ranking, no randomness.

Scoring dimensions (weights from MarketProfile.scoring_weights):
    capability_fit    — capability keyword overlap, tier-weighted
    regional_fit      — supplier region vs market profile region tiers
    value_band_fit    — tender value vs supplier commercial range
    sector_experience — supplier sector tags vs market sector keywords

Exclusions (hard, before scoring):
    - Any supplier whose flags intersect profile.disqualifier_flags
    - Suspended suppliers are always excluded (safety net even if profile
      omits 'suspended' from disqualifier_flags)

Output:
    supplier_matches.json — list of SupplierMatch records, grouped per
    tender, sorted score desc, top_n_per_tender kept per tender.

Usage:
    from src.supplier.match_suppliers import match_suppliers, MatchResult
    records, result = match_suppliers(
        tenders=shortlisted_tenders,
        suppliers=supplier_records,
        profile=market_profile,
        run_id="2026-04-21_151116",
        output_path=run_dir / "supplier_matches.json",
    )
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.market.profile import MarketProfile
from src.schemas.match import (
    DimensionScore,
    MatchScoreBreakdown,
    SCHEMA_VERSION,
    SupplierMatch,
)
from src.schemas.shortlist import ShortlistedTender
from src.schemas.supplier import SupplierRecord
from src.supplier.normalize_suppliers import supplier_hash
from src.utils.region import region_slug

log = logging.getLogger("supplier.match")

# Tier point values for capability keyword matching.
_TIER_POINTS = {1: 3, 2: 2, 3: 1}
_ALWAYS_EXCLUDED_FLAGS = frozenset({"suspended"})


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class MatchResult:
    tenders_processed: int = 0
    suppliers_evaluated: int = 0
    matches_total: int = 0          # all scored (inc. below threshold)
    matches_included: int = 0       # in output (above threshold, top N)
    suppliers_excluded: int = 0
    exclusion_reasons: list[str] = field(default_factory=list)
    market_profile: str = ""
    market_profile_version: str = ""
    output_path: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.tenders_processed > 0


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _score_capability(
    supplier: SupplierRecord,
    profile: MarketProfile,
) -> DimensionScore:
    """
    Score capability keyword overlap between supplier and market profile.

    Each tier_1 hit scores 3 pts, tier_2 = 2 pts, tier_3 = 1 pt.
    The raw score is normalised against the maximum possible
    (all tier_1 keywords present).  If fewer than min_keyword_hits
    distinct keywords match, score = 0.0.
    """
    supplier_tags = set(supplier.capabilities) | set(supplier.sectors)

    tier1 = profile.capability_keywords.tier_1
    tier2 = profile.capability_keywords.tier_2
    tier3 = profile.capability_keywords.tier_3

    hits: dict[str, int] = {}  # keyword -> tier
    raw = 0
    for kw in tier1:
        if kw in supplier_tags:
            hits[kw] = 1
            raw += _TIER_POINTS[1]
    for kw in tier2:
        if kw in supplier_tags:
            hits[kw] = 2
            raw += _TIER_POINTS[2]
    for kw in tier3:
        if kw in supplier_tags:
            hits[kw] = 3
            raw += _TIER_POINTS[3]

    if len(hits) < profile.min_keyword_hits:
        score = 0.0
    else:
        max_possible = len(tier1) * _TIER_POINTS[1] or 1
        score = min(1.0, raw / max_possible)

    weight = profile.scoring_weights.capability_fit
    return DimensionScore(
        score=round(score, 4),
        weight=weight,
        weighted=round(score * weight * 100, 2),
        rationale={
            "hits": hits,
            "hit_count": len(hits),
            "raw_points": raw,
            "min_keyword_hits_required": profile.min_keyword_hits,
            "below_min": len(hits) < profile.min_keyword_hits,
        },
    )


def _score_region(
    supplier: SupplierRecord,
    profile: MarketProfile,
) -> DimensionScore:
    """
    Score supplier region against market profile regional priority tiers.

    tier_1 → 1.0, tier_2 → 0.6, tier_3 → 0.3, no match → 0.0.
    """
    slug = region_slug(supplier.region_normalised or supplier.region)
    tier = profile.regional_priority.tier_for(slug) if slug else None

    tier_scores = {1: 1.0, 2: 0.6, 3: 0.3}
    score = tier_scores.get(tier, 0.0) if tier else 0.0

    weight = profile.scoring_weights.regional_fit
    return DimensionScore(
        score=round(score, 4),
        weight=weight,
        weighted=round(score * weight * 100, 2),
        rationale={
            "supplier_region": supplier.region_normalised or supplier.region,
            "slug": slug,
            "tier": tier,
        },
    )


def _score_value_band(
    supplier: SupplierRecord,
    tender: ShortlistedTender,
    profile: MarketProfile,
) -> DimensionScore:
    """
    Score the overlap between tender value, supplier range, and market sweet spot.

    Full score (1.0): tender value is within both the supplier's range AND
                      the market sweet spot.
    Partial (0.5):    tender value is within the supplier's range only, or
                      within the sweet spot but supplier range is unknown.
    Zero (0.0):       tender value is outside the supplier's declared range, or
                      both ranges are entirely unknown.
    """
    tender_value = tender.effective_value
    sup_min = supplier.value_min
    sup_max = supplier.value_max
    ss_min = profile.value_bands.sweet_spot_min
    ss_max = profile.value_bands.sweet_spot_max

    if tender_value is None:
        # No tender value — partial credit if supplier has a range
        score = 0.3 if (sup_min is not None or sup_max is not None) else 0.0
        rationale = {"reason": "tender_value_unknown"}
    else:
        in_supplier_range = _in_range(tender_value, sup_min, sup_max)
        in_sweet_spot = _in_range(tender_value, ss_min, ss_max)

        if in_supplier_range and in_sweet_spot:
            score = 1.0
        elif in_supplier_range:
            score = 0.6
        elif in_sweet_spot and (sup_min is None and sup_max is None):
            score = 0.5
        elif in_sweet_spot:
            score = 0.2
        else:
            score = 0.0

        rationale = {
            "tender_value": tender_value,
            "supplier_min": sup_min,
            "supplier_max": sup_max,
            "sweet_spot_min": ss_min,
            "sweet_spot_max": ss_max,
            "in_supplier_range": in_supplier_range,
            "in_sweet_spot": in_sweet_spot,
        }

    weight = profile.scoring_weights.value_band_fit
    return DimensionScore(
        score=round(score, 4),
        weight=weight,
        weighted=round(score * weight * 100, 2),
        rationale=rationale,
    )


def _in_range(value: float, lo: Optional[float], hi: Optional[float]) -> bool:
    """True if value is within [lo, hi], treating None bounds as open."""
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def _score_sector(
    supplier: SupplierRecord,
    profile: MarketProfile,
) -> DimensionScore:
    """
    Score supplier sectors against market profile sector keywords.

    Count how many of the profile's sector_keywords appear in the
    supplier's sectors list.  Normalise against the total keyword count.
    """
    if not profile.sector_keywords:
        weight = profile.scoring_weights.sector_experience
        return DimensionScore(
            score=0.0,
            weight=weight,
            weighted=0.0,
            rationale={"reason": "no_sector_keywords_in_profile"},
        )

    supplier_sectors = set(supplier.sectors) | set(supplier.capabilities)
    matched = [kw for kw in profile.sector_keywords if kw in supplier_sectors]
    score = min(1.0, len(matched) / len(profile.sector_keywords))

    weight = profile.scoring_weights.sector_experience
    return DimensionScore(
        score=round(score, 4),
        weight=weight,
        weighted=round(score * weight * 100, 2),
        rationale={
            "matched": matched,
            "matched_count": len(matched),
            "total_keywords": len(profile.sector_keywords),
        },
    )


# ── Exclusion check ───────────────────────────────────────────────────────────

def _check_exclusion(
    supplier: SupplierRecord,
    profile: MarketProfile,
) -> tuple[bool, Optional[str]]:
    """
    Return (is_excluded, reason_string).

    Hard exclusion if any supplier flag is in the profile's
    disqualifier_flags or in the always-excluded set.
    """
    supplier_flags = set(supplier.flags)
    profile_disqualifiers = set(profile.disqualifier_flags) | _ALWAYS_EXCLUDED_FLAGS
    bad_flags = supplier_flags & profile_disqualifiers
    if bad_flags:
        return True, f"disqualifying flags: {sorted(bad_flags)}"
    return False, None


# ── Core match function ───────────────────────────────────────────────────────

def _score_one(
    tender: ShortlistedTender,
    supplier: SupplierRecord,
    profile: MarketProfile,
    run_id: str,
) -> SupplierMatch:
    """Score one supplier against one tender. Never raises."""
    ts = datetime.now(timezone.utc).isoformat()

    excluded, excl_reason = _check_exclusion(supplier, profile)
    if excluded:
        return SupplierMatch(
            run_id=run_id,
            market_profile=profile.market_id,
            market_profile_version=profile.version,
            schema_version=SCHEMA_VERSION,
            tender_id=tender.id,
            tender_title=tender.title,
            tender_buyer=tender.effective_buyer,
            tender_region=tender.effective_region,
            tender_value=tender.effective_value,
            tender_deadline=tender.deadline_at or tender.deadline,
            tender_deadline_days=tender.deadline_days,
            tender_verdict=tender.decision_verdict,
            tender_score=tender.score,
            supplier_id=supplier.supplier_id,
            supplier_name=supplier.name,
            supplier_region=supplier.region_normalised or supplier.region,
            disqualified=True,
            disqualify_reason=excl_reason,
            total_score=0.0,
            above_threshold=False,
            score_breakdown=None,
            included_in_output=False,
            outreach_priority=None,
            timestamp=ts,
            supplier_record_hash=supplier_hash(supplier),
        )

    cap = _score_capability(supplier, profile)
    reg = _score_region(supplier, profile)
    val = _score_value_band(supplier, tender, profile)
    sec = _score_sector(supplier, profile)

    total = round(cap.weighted + reg.weighted + val.weighted + sec.weighted, 2)
    above = total >= profile.min_match_score

    breakdown = MatchScoreBreakdown(
        capability_fit=cap,
        regional_fit=reg,
        value_band_fit=val,
        sector_experience=sec,
        total=total,
    )

    return SupplierMatch(
        run_id=run_id,
        market_profile=profile.market_id,
        market_profile_version=profile.version,
        schema_version=SCHEMA_VERSION,
        tender_id=tender.id,
        tender_title=tender.title,
        tender_buyer=tender.effective_buyer,
        tender_region=tender.effective_region,
        tender_value=tender.effective_value,
        tender_deadline=tender.deadline_at or tender.deadline,
        tender_deadline_days=tender.deadline_days,
        tender_verdict=tender.decision_verdict,
        tender_score=tender.score,
        supplier_id=supplier.supplier_id,
        supplier_name=supplier.name,
        supplier_region=supplier.region_normalised or supplier.region,
        disqualified=False,
        disqualify_reason=None,
        total_score=total,
        above_threshold=above,
        score_breakdown=breakdown,
        included_in_output=False,  # set by caller after ranking
        outreach_priority=profile.outreach_priority(total) if above else None,
        timestamp=ts,
        supplier_record_hash=supplier_hash(supplier),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def match_suppliers(
    tenders: list[ShortlistedTender],
    suppliers: list[SupplierRecord],
    profile: MarketProfile,
    run_id: str,
    output_path: Optional[Path] = None,
    top_n: Optional[int] = None,
) -> tuple[list[SupplierMatch], MatchResult]:
    """
    Match every supplier against every tender.

    Args:
        tenders:     ShortlistedTender records from decision_shortlist.json
        suppliers:   normalised SupplierRecord list
        profile:     loaded MarketProfile for this lane
        run_id:      pipeline run identifier (written into every record)
        output_path: if given, write supplier_matches.json here
        top_n:       override profile.top_n_per_tender

    Returns:
        (all_matches, result)
        all_matches — every SupplierMatch evaluated, including excluded and
                      below-threshold records; caller can filter as needed.
        result      — summary counts for manifest.
    """
    n = top_n if top_n is not None else profile.top_n_per_tender

    result = MatchResult(
        tenders_processed=len(tenders),
        market_profile=profile.market_id,
        market_profile_version=profile.version,
    )

    all_matches: list[SupplierMatch] = []

    for tender in tenders:
        tender_matches: list[SupplierMatch] = []
        for supplier in suppliers:
            result.suppliers_evaluated += 1
            m = _score_one(tender, supplier, profile, run_id)
            if m.disqualified:
                result.suppliers_excluded += 1
                result.exclusion_reasons.append(
                    f"{supplier.supplier_id}: {m.disqualify_reason}"
                )
            result.matches_total += 1
            tender_matches.append(m)

        # Sort: non-excluded by score desc, then excluded (score=0) at end
        tender_matches.sort(
            key=lambda m: (0 if m.disqualified else 1, m.total_score),
            reverse=True,
        )

        # Mark top N above-threshold as included
        included = 0
        for m in tender_matches:
            if not m.disqualified and m.above_threshold and included < n:
                m.included_in_output = True
                included += 1
                result.matches_included += 1

        all_matches.extend(tender_matches)

    if output_path is not None:
        _write_output(all_matches, output_path)
        result.output_path = str(output_path)
        log.info(
            "Supplier match: %d tenders × %d suppliers → %d included → %s",
            result.tenders_processed,
            len(suppliers),
            result.matches_included,
            output_path.name,
        )
    else:
        log.info(
            "Supplier match: %d tenders × %d suppliers → %d included (no output path)",
            result.tenders_processed,
            len(suppliers),
            result.matches_included,
        )

    return all_matches, result


def _write_output(matches: list[SupplierMatch], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [m.model_dump() for m in matches]
    path.write_text(
        json.dumps(records, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Convenience loader ────────────────────────────────────────────────────────

def load_shortlist(shortlist_path: Path) -> list[ShortlistedTender]:
    """
    Load and validate decision_shortlist.json into ShortlistedTender records.

    Raises:
        FileNotFoundError: if path does not exist
        ValueError: if JSON is invalid or a record fails schema validation
    """
    if not shortlist_path.exists():
        raise FileNotFoundError(f"Shortlist not found: {shortlist_path}")

    raw = json.loads(shortlist_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"decision_shortlist.json must be a JSON array, got: {type(raw)}")

    tenders: list[ShortlistedTender] = []
    errors: list[str] = []
    for i, item in enumerate(raw):
        try:
            tenders.append(ShortlistedTender(**item))
        except Exception as exc:
            errors.append(f"record {i}: {exc}")

    if errors:
        raise ValueError(
            f"Shortlist validation errors ({len(errors)}):\n" + "\n".join(errors[:5])
        )

    return tenders
