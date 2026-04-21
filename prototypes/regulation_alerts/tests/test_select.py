import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.schema import RegulationRecord
from src.select import select_for_product, run_select


def _make_record(
    id="test001",
    title="Test",
    authority="HSE",
    region="London",
    score=50,
    trade_tags=None,
    impact_type="safety",
    summary="",
    raw_text="",
) -> RegulationRecord:
    return RegulationRecord(
        id=id,
        title=title,
        authority=authority,
        region=region,
        published_at="2026-01-01",
        effective_at="",
        url=f"https://example.gov.uk/{id}",
        summary=summary or title,
        source="govuk_guidance",
        trade_tags=trade_tags or [],
        impact_type=impact_type,
        raw_text=raw_text or title,
        relevance_score=score,
        relevance_reasons=["test reason"],
    )


def _base_product(**kwargs):
    defaults = {
        "id": "test_product",
        "display_name": "Test Product",
        "enabled": True,
        "min_score": 0,
        "shortlist_size": 10,
        "include_keywords": [],
        "exclude_keywords": [],
        "regions": [],
        "trade_tags": [],
        "impact_types": [],
        "allow_null_effective_date": True,
        "notify": True,
    }
    defaults.update(kwargs)
    return defaults


def test_include_keywords_filter():
    records = [
        _make_record("r1", title="Sewer drainage works update", raw_text="sewer drainage works update"),
        _make_record("r2", title="Planning permission changes", raw_text="planning permission changes"),
    ]
    product = _base_product(include_keywords=["drainage"])
    shortlist, stages = select_for_product(records, product)
    ids = [r["id"] for r in shortlist]
    assert "r1" in ids
    assert "r2" not in ids


def test_exclude_keywords_filter():
    records = [
        _make_record("r1", title="Sewer update", raw_text="sewer update drainage"),
        _make_record("r2", title="Highway works", raw_text="highway carriageway works"),
    ]
    product = _base_product(exclude_keywords=["highway"])
    shortlist, stages = select_for_product(records, product)
    ids = [r["id"] for r in shortlist]
    assert "r1" in ids
    assert "r2" not in ids


def test_region_filter_empty_means_no_filter():
    records = [
        _make_record("r1", region="London"),
        _make_record("r2", region="West Midlands"),
        _make_record("r3", region="National"),
    ]
    product = _base_product(regions=[])
    shortlist, _ = select_for_product(records, product)
    assert len(shortlist) == 3


def test_min_score_filter():
    records = [
        _make_record("r1", score=50),
        _make_record("r2", score=15),
        _make_record("r3", score=30),
    ]
    product = _base_product(min_score=25)
    shortlist, stages = select_for_product(records, product)
    assert stages["after_min_score"] == 2
    scores = [r["relevance_score"] for r in shortlist]
    assert all(s >= 25 for s in scores)


def test_client_merge_deduplicates():
    record = _make_record("dup001", title="Duplicate Record", score=50)
    product_a = _base_product(id="prod_a")
    product_b = _base_product(id="prod_b")
    scored = [record]

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test_run"
        client = {
            "client_id": "test_client",
            "display_name": "Test Client",
            "active": True,
            "subscribed_products": ["prod_a", "prod_b"],
            "filters": {"min_score": 0, "regions": [], "authority_whitelist": []},
            "notify": {"channel": "discord", "webhook_env_var": "TEST_WEBHOOK"},
        }
        _, client_results = run_select(scored, [product_a, product_b], [client], run_dir, dry_run=True)
        assert client_results["test_client"]["summary"]["item_count"] == 1


def test_filter_stages_counts():
    records = [
        _make_record("r1", title="sewer works London", raw_text="sewer works in London", region="London", score=40, trade_tags=["drainage"]),
        _make_record("r2", title="highway Birmingham", raw_text="highway Birmingham", region="West Midlands", score=30, trade_tags=["civils"]),
        _make_record("r3", title="sewer Oxford", raw_text="sewer works Oxford", region="Unknown", score=10),
    ]
    product = _base_product(include_keywords=["sewer"], min_score=20)
    shortlist, stages = select_for_product(records, product)
    assert stages["initial"] == 3
    assert stages["after_include_keywords"] == 2  # r1 and r3
    assert stages["after_min_score"] == 1  # only r1 >= 20


def test_empty_run_no_crash():
    product = _base_product()
    shortlist, stages = select_for_product([], product)
    assert shortlist == []
    assert stages["initial"] == 0
    assert stages["after_min_score"] == 0
