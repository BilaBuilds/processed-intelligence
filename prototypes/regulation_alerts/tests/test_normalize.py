import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.normalize import (
    _normalize_region,
    _infer_trade_tags,
    _classify_impact_type,
    _trim_summary,
    normalize_record,
)


def test_region_greater_london():
    assert _normalize_region("National", "works in Greater London area") == "London"


def test_region_birmingham():
    assert _normalize_region("National", "project in Birmingham city centre") == "West Midlands"


def test_region_unknown():
    assert _normalize_region("National", "some unrelated text about trees") == "Unknown"


def test_trade_tag_sewer_gives_drainage():
    tags = _infer_trade_tags("New sewer installation guidance from Environment Agency")
    assert "drainage" in tags


def test_trade_tag_highway_gives_civils():
    tags = _infer_trade_tags("Highway maintenance requirements for carriageway works")
    assert "civils" in tags


def test_impact_type_consultation():
    impact = _classify_impact_type("Public consultation on drainage regulations")
    assert impact == "consultation"


def test_impact_type_permit():
    impact = _classify_impact_type("Environmental permit required for discharge to controlled waters")
    assert impact == "permit"


def test_summary_trimmed_to_500():
    long_text = "word " * 200  # 1000 chars
    result = _trim_summary(long_text)
    assert len(result) <= 500


def test_normalize_record_full():
    raw = {
        "title": "New Drainage Guidance",
        "url": "https://gov.uk/drainage-guide",
        "authority": "Environment Agency",
        "region": "National",
        "source": "ea_publications",
        "raw_text": "New sewer guidance affecting surface water in Birmingham area",
        "date_hint": "2026-03-15",
        "shield_status": "ok",
        "shield_categories": "none",
    }
    record = normalize_record(raw)
    assert record is not None
    assert record.published_at == "2026-03-15"
    assert "drainage" in record.trade_tags
    assert record.region == "West Midlands"
