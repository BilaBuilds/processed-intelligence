"""
tests/test_supplier_match.py
==============================
Full pytest coverage for src/supplier/match_suppliers.py.

Validates:
    - determinism: same input = same output every call
    - exclusion: suspended / disqualifier flags hard-excluded before scoring
    - scoring dimensions: capability, region, value band, sector
    - ranking: per-tender sort descending, top-N cap
    - threshold: below min_match_score suppliers not in output
    - output file: valid JSON, schema-conformant
    - load_shortlist: happy path, missing file, invalid JSON, schema error
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.market.profile import MarketProfile, ScoringWeights
from src.schemas.match import SupplierMatch
from src.schemas.shortlist import ShortlistedTender
from src.schemas.supplier import SupplierRecord
from src.supplier.match_suppliers import (
    MatchResult,
    _check_exclusion,
    _score_capability,
    _score_region,
    _score_sector,
    _score_value_band,
    load_shortlist,
    match_suppliers,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

PROFILE_DATA = {
    "market_id": "construction",
    "version": "1.0",
    "display_name": "Construction",
    "capability_keywords": {
        "tier_1": ["civil engineering", "drainage"],
        "tier_2": ["earthworks", "groundworks"],
        "tier_3": ["construction"],
    },
    "min_keyword_hits": 2,
    "regional_priority": {
        "tier_1": ["london", "south_east"],
        "tier_2": ["east_midlands", "west_midlands"],
        "tier_3": ["north_west", "wales"],
    },
    "value_bands": {
        "floor": 50_000,
        "ceiling": 5_000_000,
        "sweet_spot_min": 100_000,
        "sweet_spot_max": 2_000_000,
    },
    "buyer_types": {"preferred": [], "neutral": [], "deprioritise": []},
    "scoring_weights": {
        "capability_fit": 0.40,
        "regional_fit": 0.25,
        "value_band_fit": 0.20,
        "sector_experience": 0.15,
    },
    "sector_keywords": ["civil engineering", "drainage", "highways"],
    "min_match_score": 45.0,
    "disqualifier_flags": ["suspended", "debarred", "insolvent"],
    "top_n_per_tender": 3,
    "outreach_priority_thresholds": {"high": 75, "medium": 60},
}


@pytest.fixture
def profile() -> MarketProfile:
    return MarketProfile(**PROFILE_DATA)


@pytest.fixture
def tender() -> ShortlistedTender:
    return ShortlistedTender(
        id="T-001",
        title="Drainage and civil engineering works",
        buyer_name="London Borough of Anywhere",
        region="London",
        value_amount=500_000.0,
        score=72,
        decision_verdict="BID",
    )


def _make_supplier(
    supplier_id: str = "S-001",
    name: str = "Apex Civil Ltd",
    region: str = "London",
    capabilities: list[str] | None = None,
    sectors: list[str] | None = None,
    value_min: float | None = 50_000,
    value_max: float | None = 2_000_000,
    flags: list[str] | None = None,
) -> SupplierRecord:
    return SupplierRecord(
        supplier_id=supplier_id,
        name=name,
        region=region,
        region_normalised=region,
        capabilities=capabilities if capabilities is not None else ["civil engineering", "drainage", "groundworks"],
        sectors=sectors if sectors is not None else ["civil engineering", "construction"],
        value_min=value_min,
        value_max=value_max,
        flags=flags if flags is not None else [],
    )


# ── Determinism ───────────────────────────────────────────────────────────────

def test_deterministic_same_score_on_repeat(profile, tender):
    supplier = _make_supplier()
    matches1, _ = match_suppliers([tender], [supplier], profile, run_id="run1")
    matches2, _ = match_suppliers([tender], [supplier], profile, run_id="run1")
    assert matches1[0].total_score == matches2[0].total_score
    assert matches1[0].score_breakdown.total == matches2[0].score_breakdown.total


def test_deterministic_score_breakdown_fields_identical(profile, tender):
    supplier = _make_supplier()
    m1, _ = match_suppliers([tender], [supplier], profile, run_id="run1")
    m2, _ = match_suppliers([tender], [supplier], profile, run_id="run1")
    bd1 = m1[0].score_breakdown
    bd2 = m2[0].score_breakdown
    assert bd1.capability_fit.weighted == bd2.capability_fit.weighted
    assert bd1.regional_fit.weighted == bd2.regional_fit.weighted
    assert bd1.value_band_fit.weighted == bd2.value_band_fit.weighted
    assert bd1.sector_experience.weighted == bd2.sector_experience.weighted


def test_deterministic_ordering_stable(profile, tender):
    suppliers = [_make_supplier(f"S-{i:03d}", f"Supplier {i}") for i in range(10)]
    m1, _ = match_suppliers([tender], suppliers, profile, run_id="run1")
    m2, _ = match_suppliers([tender], suppliers, profile, run_id="run1")
    ids1 = [m.supplier_id for m in m1]
    ids2 = [m.supplier_id for m in m2]
    assert ids1 == ids2


# ── Exclusions ────────────────────────────────────────────────────────────────

def test_suspended_supplier_excluded(profile, tender):
    supplier = _make_supplier(flags=["suspended"])
    matches, result = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert matches[0].disqualified is True
    assert matches[0].total_score == 0.0
    assert matches[0].included_in_output is False
    assert result.suppliers_excluded == 1


def test_debarred_supplier_excluded(profile, tender):
    supplier = _make_supplier(flags=["debarred"])
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert matches[0].disqualified is True


def test_insolvent_supplier_excluded(profile, tender):
    supplier = _make_supplier(flags=["insolvent"])
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert matches[0].disqualified is True


def test_suspended_always_excluded_even_if_not_in_profile_disqualifiers():
    p = MarketProfile(**{**PROFILE_DATA, "disqualifier_flags": []})
    supplier = _make_supplier(flags=["suspended"])
    tender = ShortlistedTender(id="T-1", title="Works")
    matches, _ = match_suppliers([tender], [supplier], p, run_id="r1")
    assert matches[0].disqualified is True


def test_excluded_supplier_has_disqualify_reason(profile, tender):
    supplier = _make_supplier(flags=["suspended"])
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert matches[0].disqualify_reason is not None
    assert "suspended" in matches[0].disqualify_reason


def test_non_disqualifying_flags_not_excluded(profile, tender):
    supplier = _make_supplier(flags=["iso9001", "constructionline"])
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert matches[0].disqualified is False


def test_check_exclusion_direct(profile):
    good = _make_supplier(flags=["chas"])
    bad = _make_supplier(flags=["debarred"])
    assert _check_exclusion(good, profile) == (False, None)
    excl, reason = _check_exclusion(bad, profile)
    assert excl is True
    assert reason is not None


# ── Capability scoring ────────────────────────────────────────────────────────

def test_capability_score_tier1_hits(profile):
    # Pass sectors=[] so only the explicit capabilities are counted
    supplier = _make_supplier(capabilities=["civil engineering", "drainage"], sectors=[])
    dim = _score_capability(supplier, profile)
    assert dim.score > 0.0
    assert dim.rationale["hit_count"] == 2


def test_capability_score_below_min_hits_returns_zero(profile):
    # Only one keyword hit (min is 2) — both capabilities and sectors set explicitly
    supplier = _make_supplier(capabilities=["painting"], sectors=["civil engineering"])
    dim = _score_capability(supplier, profile)
    assert dim.score == 0.0
    assert dim.rationale["below_min"] is True


def test_capability_score_capped_at_one(profile):
    all_caps = (
        profile.capability_keywords.tier_1
        + profile.capability_keywords.tier_2
        + profile.capability_keywords.tier_3
    )
    supplier = _make_supplier(capabilities=all_caps)
    dim = _score_capability(supplier, profile)
    assert dim.score <= 1.0


def test_capability_weighted_uses_profile_weight(profile):
    supplier = _make_supplier(capabilities=["civil engineering", "drainage"])
    dim = _score_capability(supplier, profile)
    assert abs(dim.weighted - dim.score * dim.weight * 100) < 0.01


def test_capability_sectors_contribute_to_hits(profile):
    # Capability keywords are checked in both capabilities AND sectors
    supplier = _make_supplier(capabilities=["civil engineering"], sectors=["drainage"])
    dim = _score_capability(supplier, profile)
    assert dim.rationale["hit_count"] >= 2


# ── Regional scoring ──────────────────────────────────────────────────────────

def test_region_tier1_scores_full(profile):
    supplier = _make_supplier(region="London")
    dim = _score_region(supplier, profile)
    assert dim.score == 1.0


def test_region_tier2_scores_partial(profile):
    supplier = _make_supplier(region="East Midlands")
    dim = _score_region(supplier, profile)
    assert dim.score == 0.6


def test_region_tier3_scores_low(profile):
    supplier = _make_supplier(region="Wales")
    dim = _score_region(supplier, profile)
    assert dim.score == 0.3


def test_region_unknown_scores_zero(profile):
    supplier = _make_supplier(region="Atlantis")
    dim = _score_region(supplier, profile)
    assert dim.score == 0.0


def test_region_none_scores_zero(profile):
    s = SupplierRecord(
        supplier_id="x", name="X",
        region=None, region_normalised=None,
        capabilities=[], sectors=[], flags=[],
    )
    dim = _score_region(s, profile)
    assert dim.score == 0.0


# ── Value band scoring ────────────────────────────────────────────────────────

def test_value_in_range_and_sweet_spot_scores_full(profile, tender):
    supplier = _make_supplier(value_min=100_000, value_max=2_000_000)
    tender_with_value = ShortlistedTender(id="T", title="T", value_amount=500_000.0)
    dim = _score_value_band(supplier, tender_with_value, profile)
    assert dim.score == 1.0


def test_value_in_range_outside_sweet_spot_scores_partial(profile):
    supplier = _make_supplier(value_min=50_000, value_max=5_000_000)
    tender = ShortlistedTender(id="T", title="T", value_amount=80_000.0)
    dim = _score_value_band(supplier, tender, profile)
    # 80k is in supplier range but below sweet_spot_min (100k)
    assert dim.score == 0.6


def test_value_outside_supplier_range_scores_low(profile):
    supplier = _make_supplier(value_min=200_000, value_max=500_000)
    tender = ShortlistedTender(id="T", title="T", value_amount=50_000.0)
    dim = _score_value_band(supplier, tender, profile)
    assert dim.score < 0.6


def test_value_unknown_tender_value_partial_credit(profile):
    supplier = _make_supplier(value_min=100_000, value_max=500_000)
    tender = ShortlistedTender(id="T", title="T")  # no value
    dim = _score_value_band(supplier, tender, profile)
    assert dim.score == 0.3


def test_value_unknown_both_returns_zero(profile):
    supplier = SupplierRecord(
        supplier_id="x", name="X",
        capabilities=[], sectors=[], flags=[],
    )
    tender = ShortlistedTender(id="T", title="T")
    dim = _score_value_band(supplier, tender, profile)
    assert dim.score == 0.0


# ── Sector scoring ────────────────────────────────────────────────────────────

def test_sector_overlap_scores_nonzero(profile):
    supplier = _make_supplier(sectors=["civil engineering", "drainage"])
    dim = _score_sector(supplier, profile)
    assert dim.score > 0.0
    assert "civil engineering" in dim.rationale["matched"]


def test_sector_no_overlap_scores_zero(profile):
    # Both capabilities and sectors must be off-profile for zero score
    supplier = _make_supplier(capabilities=["catering", "cleaning"], sectors=["retail", "hospitality"])
    dim = _score_sector(supplier, profile)
    assert dim.score == 0.0


def test_sector_capabilities_also_contribute(profile):
    supplier = _make_supplier(
        capabilities=["civil engineering"], sectors=["unrelated"]
    )
    dim = _score_sector(supplier, profile)
    assert "civil engineering" in dim.rationale["matched"]


# ── Ranking and top-N ─────────────────────────────────────────────────────────

def test_suppliers_sorted_by_score_desc(profile, tender):
    strong = _make_supplier("S-strong", capabilities=["civil engineering", "drainage", "groundworks"], region="London")
    weak = _make_supplier("S-weak", capabilities=["construction"], sectors=["unrelated"], region="Wales", value_min=None, value_max=None)
    matches, _ = match_suppliers([tender], [strong, weak], profile, run_id="r1")
    non_excl = [m for m in matches if not m.disqualified]
    scores = [m.total_score for m in non_excl]
    assert scores == sorted(scores, reverse=True)


def test_top_n_limits_included_per_tender(profile, tender):
    suppliers = [_make_supplier(f"S-{i:03d}", f"Sup {i}") for i in range(10)]
    matches, result = match_suppliers([tender], suppliers, profile, run_id="r1")
    included = [m for m in matches if m.included_in_output]
    assert len(included) <= profile.top_n_per_tender
    assert result.matches_included <= profile.top_n_per_tender


def test_top_n_override(profile, tender):
    suppliers = [_make_supplier(f"S-{i:03d}", f"Sup {i}") for i in range(10)]
    matches, result = match_suppliers([tender], suppliers, profile, run_id="r1", top_n=2)
    included = [m for m in matches if m.included_in_output]
    assert len(included) <= 2


def test_below_threshold_not_included(profile):
    # Supplier with no matching capabilities or region → score near 0
    supplier = SupplierRecord(
        supplier_id="S-low", name="Low Score Co",
        capabilities=[], sectors=[], flags=[],
    )
    tender = ShortlistedTender(id="T", title="T")
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert all(not m.included_in_output for m in matches)


def test_above_threshold_included(profile, tender):
    supplier = _make_supplier(capabilities=["civil engineering", "drainage", "groundworks", "earthworks"], region="London")
    matches, result = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert result.matches_included >= 1
    included = [m for m in matches if m.included_in_output]
    assert len(included) >= 1
    assert included[0].above_threshold is True


# ── Outreach priority ─────────────────────────────────────────────────────────

def test_outreach_priority_high_for_high_score(profile, tender):
    supplier = _make_supplier(capabilities=["civil engineering", "drainage", "groundworks", "earthworks"], region="London")
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    m = matches[0]
    if m.total_score >= profile.outreach_priority_thresholds.high:
        assert m.outreach_priority == "high"


def test_outreach_priority_none_for_excluded(profile, tender):
    supplier = _make_supplier(flags=["suspended"])
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert matches[0].outreach_priority is None


# ── Multiple tenders ──────────────────────────────────────────────────────────

def test_multiple_tenders_scored_independently(profile):
    t1 = ShortlistedTender(id="T-1", title="Drainage works", value_amount=300_000.0, region="London")
    t2 = ShortlistedTender(id="T-2", title="Highway improvement", value_amount=800_000.0, region="South East England")
    supplier = _make_supplier()
    matches, result = match_suppliers([t1, t2], [supplier], profile, run_id="r1")
    assert result.tenders_processed == 2
    t1_matches = [m for m in matches if m.tender_id == "T-1"]
    t2_matches = [m for m in matches if m.tender_id == "T-2"]
    assert len(t1_matches) == 1
    assert len(t2_matches) == 1


def test_result_counts_correct(profile, tender):
    good = _make_supplier("S-1")
    suspended = _make_supplier("S-2", flags=["suspended"])
    matches, result = match_suppliers([tender], [good, suspended], profile, run_id="r1")
    assert result.tenders_processed == 1
    assert result.suppliers_evaluated == 2
    assert result.matches_total == 2
    assert result.suppliers_excluded == 1


# ── Output file ───────────────────────────────────────────────────────────────

def test_output_file_written(profile, tender, tmp_path):
    supplier = _make_supplier()
    out = tmp_path / "supplier_matches.json"
    match_suppliers([tender], [supplier], profile, run_id="r1", output_path=out)
    assert out.exists()


def test_output_file_is_valid_json(profile, tender, tmp_path):
    supplier = _make_supplier()
    out = tmp_path / "supplier_matches.json"
    match_suppliers([tender], [supplier], profile, run_id="r1", output_path=out)
    records = json.loads(out.read_text())
    assert isinstance(records, list)
    assert len(records) >= 1


def test_output_records_have_required_fields(profile, tender, tmp_path):
    supplier = _make_supplier()
    out = tmp_path / "supplier_matches.json"
    match_suppliers([tender], [supplier], profile, run_id="r1", output_path=out)
    records = json.loads(out.read_text())
    required = {
        "tender_id", "supplier_id", "total_score",
        "market_profile_version", "schema_version",
        "disqualified", "included_in_output",
    }
    for rec in records:
        assert required.issubset(rec.keys()), f"Missing fields: {required - rec.keys()}"


def test_output_no_path_does_not_raise(profile, tender):
    supplier = _make_supplier()
    matches, result = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert result.output_path is None
    assert len(matches) == 1


def test_output_records_schema_version(profile, tender, tmp_path):
    from src.schemas.match import SCHEMA_VERSION
    supplier = _make_supplier()
    out = tmp_path / "supplier_matches.json"
    match_suppliers([tender], [supplier], profile, run_id="r1", output_path=out)
    records = json.loads(out.read_text())
    for rec in records:
        assert rec["schema_version"] == SCHEMA_VERSION


def test_output_market_profile_version(profile, tender, tmp_path):
    supplier = _make_supplier()
    out = tmp_path / "supplier_matches.json"
    match_suppliers([tender], [supplier], profile, run_id="r1", output_path=out)
    records = json.loads(out.read_text())
    for rec in records:
        assert rec["market_profile_version"] == profile.version


# ── load_shortlist ────────────────────────────────────────────────────────────

def test_load_shortlist_missing_file():
    with pytest.raises(FileNotFoundError):
        load_shortlist(Path("/tmp/__nonexistent_shortlist__.json"))


def test_load_shortlist_invalid_json(tmp_path):
    f = tmp_path / "shortlist.json"
    f.write_text("not json", encoding="utf-8")
    with pytest.raises((ValueError, Exception)):
        load_shortlist(f)


def test_load_shortlist_not_array(tmp_path):
    f = tmp_path / "shortlist.json"
    f.write_text('{"key": "value"}', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON array"):
        load_shortlist(f)


def test_load_shortlist_schema_error(tmp_path):
    f = tmp_path / "shortlist.json"
    # Missing required fields
    f.write_text('[{"wrong_field": "x"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="validation errors"):
        load_shortlist(f)


def test_load_shortlist_valid(tmp_path):
    records = [
        {"id": "T-001", "title": "Civil works", "score": 72},
        {"id": "T-002", "title": "Drainage project", "score": 60},
    ]
    f = tmp_path / "shortlist.json"
    f.write_text(json.dumps(records), encoding="utf-8")
    tenders = load_shortlist(f)
    assert len(tenders) == 2
    assert all(isinstance(t, ShortlistedTender) for t in tenders)
    assert tenders[0].id == "T-001"


# ── Score breakdown completeness ──────────────────────────────────────────────

def test_score_breakdown_present_for_non_excluded(profile, tender):
    supplier = _make_supplier()
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    m = matches[0]
    assert m.disqualified is False
    assert m.score_breakdown is not None
    bd = m.score_breakdown
    assert bd.capability_fit is not None
    assert bd.regional_fit is not None
    assert bd.value_band_fit is not None
    assert bd.sector_experience is not None


def test_score_breakdown_none_for_excluded(profile, tender):
    supplier = _make_supplier(flags=["suspended"])
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert matches[0].score_breakdown is None


def test_total_score_equals_sum_of_weighted(profile, tender):
    supplier = _make_supplier()
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    m = matches[0]
    if m.score_breakdown:
        bd = m.score_breakdown
        expected = round(
            bd.capability_fit.weighted
            + bd.regional_fit.weighted
            + bd.value_band_fit.weighted
            + bd.sector_experience.weighted,
            2,
        )
        assert abs(m.total_score - expected) < 0.01


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_suppliers_returns_empty(profile, tender):
    matches, result = match_suppliers([tender], [], profile, run_id="r1")
    assert matches == []
    assert result.matches_total == 0


def test_empty_tenders_returns_empty(profile):
    supplier = _make_supplier()
    matches, result = match_suppliers([], [supplier], profile, run_id="r1")
    assert matches == []
    assert result.tenders_processed == 0


def test_supplier_with_multiple_disqualifying_flags(profile, tender):
    supplier = _make_supplier(flags=["suspended", "debarred"])
    matches, result = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert matches[0].disqualified is True
    assert result.suppliers_excluded == 1


def test_run_id_present_in_all_records(profile, tender):
    supplier = _make_supplier()
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="test-run-123")
    assert all(m.run_id == "test-run-123" for m in matches)


def test_supplier_record_hash_present(profile, tender):
    supplier = _make_supplier()
    matches, _ = match_suppliers([tender], [supplier], profile, run_id="r1")
    assert all(m.supplier_record_hash is not None for m in matches)


# ── Fixture-based integration test ───────────────────────────────────────────

def test_construction_csv_fixture_end_to_end(tmp_path):
    """Full round-trip: ingest CSV → normalize → match against a tender."""
    from src.supplier.ingest_suppliers import ingest_suppliers
    from src.supplier.normalize_suppliers import normalize_suppliers
    from src.market.registry import get_profile

    fixtures = Path(__file__).parent / "fixtures"
    raw, _ = ingest_suppliers(fixtures / "suppliers_construction.csv")
    suppliers, norm_result = normalize_suppliers(raw)
    assert norm_result.records_out > 0

    profile = get_profile("construction", force_reload=True)
    tender = ShortlistedTender(
        id="T-INTEG-001",
        title="Drainage and civil engineering groundworks",
        buyer_name="London Borough of Southwark",
        region="London",
        value_amount=750_000.0,
        score=80,
        decision_verdict="BID",
    )

    out = tmp_path / "supplier_matches.json"
    matches, result = match_suppliers(
        [tender], suppliers, profile, run_id="test-run", output_path=out
    )

    assert result.tenders_processed == 1
    assert result.matches_total == norm_result.records_out
    assert out.exists()
    records = json.loads(out.read_text())
    assert len(records) == norm_result.records_out

    included = [r for r in records if r["included_in_output"]]
    assert len(included) <= profile.top_n_per_tender
    for r in included:
        assert r["total_score"] >= profile.min_match_score
        assert r["above_threshold"] is True
