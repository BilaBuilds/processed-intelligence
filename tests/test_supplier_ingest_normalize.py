"""
tests/test_supplier_ingest_normalize.py
========================================
Tests for supplier ingest and normalise stages.
Uses both synthetic fixtures and the real construction CSV fixture.
"""
import json
import pytest
from pathlib import Path

from src.supplier.ingest_suppliers import ingest_suppliers, IngestResult, REQUIRED_COLUMNS
from src.supplier.normalize_suppliers import normalize_suppliers, supplier_hash
from src.schemas.supplier import SupplierRecord

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONSTRUCTION_CSV = FIXTURES_DIR / "suppliers_construction.csv"


# ── ingest_suppliers — CSV ────────────────────────────────────────────────────

def test_ingest_construction_csv():
    records, result = ingest_suppliers(CONSTRUCTION_CSV)
    assert result.ok
    assert result.rows_read == 15
    assert result.rows_returned == 15   # all rows have supplier_id + name
    assert result.rows_skipped == 0
    assert isinstance(records[0], dict)


def test_ingest_attaches_source_metadata():
    records, _ = ingest_suppliers(CONSTRUCTION_CSV)
    for rec in records:
        assert "source_file" in rec
        assert "source_row" in rec
        assert rec["source_row"] >= 2  # row 1 is header


def test_ingest_csv_missing_file():
    with pytest.raises(FileNotFoundError):
        ingest_suppliers(Path("/tmp/does_not_exist.csv"))


def test_ingest_unsupported_extension(tmp_path):
    bad = tmp_path / "suppliers.xlsx"
    bad.write_text("data")
    with pytest.raises(ValueError, match="Unsupported"):
        ingest_suppliers(bad)


def test_ingest_csv_skips_missing_required(tmp_path):
    csv_content = "supplier_id,name,region\nSUP-001,Acme,London\n,No ID,London\nSUP-003,,London\n"
    f = tmp_path / "test.csv"
    f.write_text(csv_content)
    records, result = ingest_suppliers(f)
    assert result.rows_read == 3
    assert result.rows_returned == 1
    assert result.rows_skipped == 2
    assert len(result.skip_reasons) == 2


def test_ingest_json_format(tmp_path):
    data = [
        {"supplier_id": "SUP-001", "name": "Acme Ltd", "region": "London"},
        {"supplier_id": "SUP-002", "name": "BuildCo", "region": "South East England"},
    ]
    f = tmp_path / "suppliers.json"
    f.write_text(json.dumps(data))
    records, result = ingest_suppliers(f)
    assert result.rows_returned == 2
    assert records[0]["supplier_id"] == "SUP-001"


def test_ingest_json_skips_non_dict_items(tmp_path):
    data = [
        {"supplier_id": "SUP-001", "name": "Acme"},
        "not a dict",
        42,
    ]
    f = tmp_path / "mixed.json"
    f.write_text(json.dumps(data))
    records, result = ingest_suppliers(f)
    assert result.rows_returned == 1
    assert result.rows_skipped == 2


def test_ingest_json_not_a_list(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"supplier_id": "SUP-001"}))
    records, result = ingest_suppliers(f)
    assert result.rows_returned == 0
    assert any("list" in w for w in result.warnings)


def test_ingest_bom_handling(tmp_path):
    """Excel-exported CSVs have a UTF-8 BOM — must be stripped cleanly."""
    content = "supplier_id,name\nSUP-001,Acme Ltd\n"
    f = tmp_path / "bom.csv"
    f.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
    records, result = ingest_suppliers(f)
    assert result.rows_returned == 1
    assert records[0]["supplier_id"] == "SUP-001"


# ── normalize_suppliers ───────────────────────────────────────────────────────

def test_normalize_construction_fixture():
    raw, _ = ingest_suppliers(CONSTRUCTION_CSV)
    records, result = normalize_suppliers(raw)
    # Fixture has 1 suspended + 1 no_public_sector_experience + 1 missing region
    # — all should normalise; flags are data, not a reason to skip at this stage
    assert result.records_out == 15
    assert result.records_skipped == 0
    assert all(isinstance(r, SupplierRecord) for r in records)


def test_normalize_capabilities_are_lowercase():
    raw = [{"supplier_id": "SUP-001", "name": "Acme", "capabilities": "Drainage,CIVILS,Groundworks"}]
    records, result = normalize_suppliers(raw)
    assert result.records_out == 1
    assert "drainage" in records[0].capabilities
    assert "civils" in records[0].capabilities
    assert "groundworks" in records[0].capabilities


def test_normalize_region_decodes_nuts_code():
    raw = [{"supplier_id": "SUP-001", "name": "Acme", "region": "UKD3"}]
    records, _ = normalize_suppliers(raw)
    assert records[0].region == "Greater Manchester"
    assert records[0].region_normalised == "Greater Manchester"


def test_normalize_region_passthrough_readable():
    raw = [{"supplier_id": "SUP-001", "name": "Acme", "region": "London"}]
    records, _ = normalize_suppliers(raw)
    assert records[0].region == "London"


def test_normalize_missing_region_is_none():
    raw = [{"supplier_id": "SUP-009", "name": "Badger Builders Ltd", "region": ""}]
    records, _ = normalize_suppliers(raw)
    assert records[0].region is None


def test_normalize_value_coercion():
    raw = [{"supplier_id": "SUP-001", "name": "Acme", "value_min": "£50,000", "value_max": "2000000"}]
    records, _ = normalize_suppliers(raw)
    assert records[0].value_min == 50000.0
    assert records[0].value_max == 2000000.0


def test_normalize_value_blank_becomes_none():
    raw = [{"supplier_id": "SUP-001", "name": "Acme", "value_min": "", "value_max": None}]
    records, _ = normalize_suppliers(raw)
    assert records[0].value_min is None
    assert records[0].value_max is None


def test_normalize_flags_present():
    raw, _ = ingest_suppliers(CONSTRUCTION_CSV)
    records, _ = normalize_suppliers(raw)
    suspended = next(r for r in records if r.supplier_id == "SUP-013")
    assert "suspended" in suspended.flags


def test_normalize_empty_flags_field():
    raw = [{"supplier_id": "SUP-001", "name": "Acme", "flags": ""}]
    records, _ = normalize_suppliers(raw)
    assert records[0].flags == []


def test_normalize_skips_invalid_record():
    """A record missing supplier_id must be skipped with a reason recorded."""
    raw = [
        {"supplier_id": "SUP-001", "name": "Good Record"},
        {"name": "Missing ID"},  # no supplier_id
    ]
    records, result = normalize_suppliers(raw)
    assert result.records_out == 1
    assert result.records_skipped == 1
    assert len(result.skip_reasons) == 1


def test_normalize_hash_is_stable():
    raw = [{"supplier_id": "SUP-001", "name": "Acme", "capabilities": "drainage,civils"}]
    records1, _ = normalize_suppliers(raw)
    records2, _ = normalize_suppliers(raw)
    assert supplier_hash(records1[0]) == supplier_hash(records2[0])


def test_normalize_hash_differs_on_changed_input():
    raw_a = [{"supplier_id": "SUP-001", "name": "Acme", "capabilities": "drainage"}]
    raw_b = [{"supplier_id": "SUP-001", "name": "Acme", "capabilities": "civils"}]
    records_a, _ = normalize_suppliers(raw_a)
    records_b, _ = normalize_suppliers(raw_b)
    assert supplier_hash(records_a[0]) != supplier_hash(records_b[0])


def test_normalize_empty_input():
    records, result = normalize_suppliers([])
    assert records == []
    assert result.records_in == 0
    assert result.records_out == 0


# ── Integration: full ingest → normalize pipeline ────────────────────────────

def test_full_pipeline_construction():
    raw, ingest_result = ingest_suppliers(CONSTRUCTION_CSV)
    records, norm_result = normalize_suppliers(raw)

    assert ingest_result.ok
    assert norm_result.ok
    assert norm_result.records_out == ingest_result.rows_returned

    # Spot check specific records
    sup_001 = next(r for r in records if r.supplier_id == "SUP-001")
    assert sup_001.name == "Apex Civil Engineering Ltd"
    assert "civil engineering" in sup_001.capabilities
    assert "drainage" in sup_001.capabilities
    assert sup_001.value_min == 50000.0
    assert sup_001.value_max == 2000000.0

    # SUP-009 has no region — should not crash
    sup_009 = next(r for r in records if r.supplier_id == "SUP-009")
    assert sup_009.region is None

    # SUP-013 is suspended
    sup_013 = next(r for r in records if r.supplier_id == "SUP-013")
    assert "suspended" in sup_013.flags
