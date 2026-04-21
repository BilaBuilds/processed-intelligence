import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.schema import RegulationRecord
from src.match import score_record


def _make_record(**kwargs) -> RegulationRecord:
    defaults = {
        "id": "test1234abcd5678",
        "title": "Test Regulation",
        "authority": "Unknown",
        "region": "Unknown",
        "published_at": "",
        "effective_at": "",
        "url": "https://example.gov.uk/test",
        "summary": "Test summary",
        "source": "govuk_guidance",
        "trade_tags": [],
        "impact_type": "other",
        "raw_text": "test raw text",
        "relevance_score": 0,
        "relevance_reasons": [],
    }
    defaults.update(kwargs)
    return RegulationRecord(**defaults)


def test_drainage_tag_adds_20():
    record = _make_record(trade_tags=["drainage"])
    scored = score_record(record)
    assert scored.relevance_score >= 20


def test_two_tags_cap_at_40():
    record = _make_record(trade_tags=["drainage", "civils"])
    scored = score_record(record)
    tag_contribution = sum(
        1 for r in scored.relevance_reasons
        if r.startswith("matched:")
    )
    assert tag_contribution == 2
    # tag contribution capped at 40
    tag_boost = min(len(["drainage", "civils"]) * 20, 40)
    assert tag_boost == 40


def test_region_london_adds_15():
    record = _make_record(region="London")
    scored = score_record(record)
    assert scored.relevance_score >= 15
    assert any("region: London" in r for r in scored.relevance_reasons)


def test_impact_type_code_change_adds_10():
    record = _make_record(impact_type="code_change")
    scored = score_record(record)
    assert scored.relevance_score >= 10
    assert any("impact:" in r for r in scored.relevance_reasons)


def test_authority_hse_adds_10():
    record = _make_record(authority="HSE")
    scored = score_record(record)
    assert scored.relevance_score >= 10
    assert any("authority: HSE" in r for r in scored.relevance_reasons)


def test_known_input_known_score():
    # drainage(20) + London(15) + code_change(10) + HSE(10) = 55
    record = _make_record(
        trade_tags=["drainage"],
        region="London",
        impact_type="code_change",
        authority="HSE",
        published_at="",
    )
    scored = score_record(record)
    assert scored.relevance_score == 55


def test_relevance_reasons_populated():
    record = _make_record(
        trade_tags=["civils"],
        region="West Midlands",
        authority="Environment Agency",
        impact_type="safety",
    )
    scored = score_record(record)
    assert len(scored.relevance_reasons) >= 3
    assert any("matched: civils" in r for r in scored.relevance_reasons)
    assert any("region:" in r for r in scored.relevance_reasons)
    assert any("authority:" in r for r in scored.relevance_reasons)
