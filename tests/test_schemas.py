"""
tests/test_schemas.py
=====================
Validates that all schema models load correctly and that a real
decision_shortlist.json record round-trips cleanly through ShortlistedTender.
"""
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from src.schemas.shortlist import ShortlistedTender, SCHEMA_VERSION as SHORTLIST_VERSION
from src.schemas.supplier import SupplierRecord, SCHEMA_VERSION as SUPPLIER_VERSION
from src.schemas.match import SupplierMatch, SCHEMA_VERSION as MATCH_VERSION
from src.utils.region import decode_region, region_slug
from src.utils.value_bands import classify_value_band, value_in_range, value_in_sweet_spot


# ── Schema version sanity ────────────────────────────────────────────────────

def test_schema_versions_are_strings():
    assert isinstance(SHORTLIST_VERSION, str)
    assert isinstance(SUPPLIER_VERSION, str)
    assert isinstance(MATCH_VERSION, str)


# ── ShortlistedTender ────────────────────────────────────────────────────────

MINIMAL_TENDER = {
    "id": "fat:test-001",
    "title": "Test Tender",
}

FULL_TENDER_FIXTURE = {
    "id": "fat:035598-2026",
    "title": "Maintenance and Repair of HPLC Systems",
    "buyer": "MHRA",
    "buyer_name": "MHRA",
    "region": "Inner London — East",
    "value": 825000.0,
    "value_amount": 825000.0,
    "currency": "GBP",
    "cpv_codes": ["71900000"],
    "score": 50,
    "decision_verdict": "BID",
    "decision_confidence": 90,
    "decision_reasons": ["high_match_score"],
    "risk_flags": [],
    "provenance_refs": ["https://example.com/notice/1"],
}


def test_minimal_tender_loads():
    t = ShortlistedTender(**MINIMAL_TENDER)
    assert t.id == "fat:test-001"
    assert t.title == "Test Tender"
    assert t.cpv_codes == []
    assert t.decision_reasons == []


def test_full_tender_round_trips():
    t = ShortlistedTender(**FULL_TENDER_FIXTURE)
    assert t.id == "fat:035598-2026"
    assert t.effective_value == 825000.0
    assert t.effective_buyer == "MHRA"
    assert t.decision_verdict == "BID"


def test_tender_requires_id_and_title():
    with pytest.raises(ValidationError):
        ShortlistedTender(title="No ID")
    with pytest.raises(ValidationError):
        ShortlistedTender(id="no-title")


def test_real_shortlist_loads():
    """Round-trip the most recent real decision_shortlist.json."""
    runs_dir = Path(__file__).parent.parent / "data" / "runs"
    if not runs_dir.exists():
        pytest.skip("No runs directory — skipping real data test")
    run_dirs = sorted(runs_dir.iterdir())
    shortlist_path = None
    for rd in reversed(run_dirs):
        candidate = rd / "decision_shortlist.json"
        if candidate.exists():
            shortlist_path = candidate
            break
    if shortlist_path is None:
        pytest.skip("No decision_shortlist.json found in any run")

    data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    records = data.get("opportunities", data) if isinstance(data, dict) else data
    assert len(records) > 0, "Shortlist is empty"
    for raw in records:
        t = ShortlistedTender(**raw)
        assert t.id, f"Record missing id: {raw}"


# ── SupplierRecord ────────────────────────────────────────────────────────────

def test_supplier_record_csv_string_split():
    rec = SupplierRecord(
        supplier_id="SUP-001",
        name="Acme Ltd",
        capabilities="drainage, civils, groundworks",
        sectors="construction",
        flags="",
    )
    assert "drainage" in rec.capabilities
    assert "civils" in rec.capabilities
    assert rec.flags == []


def test_supplier_record_list_input():
    rec = SupplierRecord(
        supplier_id="SUP-002",
        name="BuildCo",
        capabilities=["drainage", "civils"],
        sectors=["construction", "utilities"],
    )
    assert len(rec.capabilities) == 2


def test_supplier_requires_id_and_name():
    with pytest.raises(ValidationError):
        SupplierRecord(name="No ID")
    with pytest.raises(ValidationError):
        SupplierRecord(supplier_id="no-name")


# ── SupplierMatch ─────────────────────────────────────────────────────────────

def test_supplier_match_minimal():
    m = SupplierMatch(
        run_id="2026-04-20_090000",
        market_profile="construction",
        market_profile_version="1.0",
        tender_id="fat:test-001",
        tender_title="Test Tender",
        supplier_id="SUP-001",
        supplier_name="Acme Ltd",
        timestamp="2026-04-20T09:00:00Z",
    )
    assert m.disqualified is False
    assert m.above_threshold is False
    assert m.schema_version == MATCH_VERSION


# ── Region utilities ──────────────────────────────────────────────────────────

def test_decode_region_nuts1():
    assert decode_region("UKD") == "North West England"


def test_decode_region_nuts2():
    assert decode_region("UKD3") == "Greater Manchester"


def test_decode_region_passthrough():
    assert decode_region("Greater Manchester") == "Greater Manchester"


def test_decode_region_none():
    assert decode_region(None) is None


def test_region_slug_london():
    assert region_slug("Inner London — East") == "london"
    assert region_slug("London") == "london"


def test_region_slug_unknown():
    assert region_slug("Somewhere Unknown") is None


# ── Value band utilities ──────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (5_000, "under_10k"),
    (25_000, "10k_50k"),
    (825_000, "750k_2m"),
    (6_000_000, "5m_10m"),
    (15_000_000, "over_10m"),
    (None, "unknown"),
])
def test_classify_value_band(value, expected):
    assert classify_value_band(value) == expected


def test_value_in_range():
    assert value_in_range(100_000, 50_000, 500_000) is True
    assert value_in_range(10_000, 50_000, 500_000) is False
    assert value_in_range(600_000, 50_000, 500_000) is False
    assert value_in_range(100_000, None, 500_000) is True
    assert value_in_range(None, 50_000, 500_000) is False


def test_value_in_sweet_spot():
    assert value_in_sweet_spot(120_000, 50_000, 500_000) is True
    assert value_in_sweet_spot(600_000, 50_000, 500_000) is False
