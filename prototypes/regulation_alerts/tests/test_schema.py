import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.schema import RegulationRecord, make_record_id, validate_record, dict_to_record


def _valid_record_dict():
    return {
        "id": "abc123def456789a",
        "title": "Test Regulation",
        "authority": "HSE",
        "region": "London",
        "published_at": "2026-01-01",
        "effective_at": "",
        "url": "https://example.gov.uk/test",
        "summary": "A test summary",
        "source": "hse_construction",
        "trade_tags": ["civils"],
        "impact_type": "safety",
        "raw_text": "raw text here",
        "relevance_score": 45,
        "relevance_reasons": ["matched: civils"],
    }


def test_valid_record_passes():
    d = _valid_record_dict()
    record = dict_to_record(d)
    assert record.id == d["id"]
    assert record.trade_tags == ["civils"]
    assert record.relevance_score == 45


def test_missing_required_field_raises():
    d = _valid_record_dict()
    del d["title"]
    with pytest.raises(ValueError):
        dict_to_record(d)


def test_id_is_stable():
    url = "https://example.gov.uk/test"
    title = "Some Regulation Title"
    date = "2026-01-15"
    id1 = make_record_id(url, title, date)
    id2 = make_record_id(url, title, date)
    assert id1 == id2
    assert len(id1) == 16
