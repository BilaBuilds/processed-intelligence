"""
Tests for src/sector_pack.py

Covers:
- Default sector loads (construction)
- Social housing sector loads
- Fallback to default when unknown sector requested
- ScoringConfig fields are correctly populated from YAML
- clear_cache works
- TENDER_SECTOR env var respected
"""

from __future__ import annotations

import os

import pytest

from src.sector_pack import SectorPack, ScoringConfig, get_pack, clear_cache


@pytest.fixture(autouse=True)
def reset_cache_and_env(monkeypatch):
    """Ensure cache is clean and TENDER_SECTOR env var is reset for each test."""
    clear_cache()
    monkeypatch.delenv("TENDER_SECTOR", raising=False)
    yield
    clear_cache()


class TestConstructionPack:

    def test_loads_without_error(self):
        pack = get_pack("construction")
        assert isinstance(pack, SectorPack)

    def test_sector_name(self):
        pack = get_pack("construction")
        assert pack.sector == "construction"

    def test_keyword_weights_non_empty(self):
        pack = get_pack("construction")
        assert len(pack.scoring.keyword_weights) > 0

    def test_construction_keyword_present(self):
        pack = get_pack("construction")
        assert "construction" in pack.scoring.keyword_weights
        assert pack.scoring.keyword_weights["construction"] > 0

    def test_disqualify_keywords_non_empty(self):
        pack = get_pack("construction")
        assert len(pack.scoring.disqualify_keywords) > 0

    def test_disqualify_software_present(self):
        pack = get_pack("construction")
        assert "software" in pack.scoring.disqualify_keywords

    def test_region_weights_non_empty(self):
        pack = get_pack("construction")
        assert len(pack.scoring.region_weights) > 0

    def test_london_in_region_weights(self):
        pack = get_pack("construction")
        assert "london" in pack.scoring.region_weights

    def test_value_bands_non_empty(self):
        pack = get_pack("construction")
        assert len(pack.scoring.value_bands) > 0

    def test_value_bands_are_triples(self):
        pack = get_pack("construction")
        for band in pack.scoring.value_bands:
            assert len(band) == 3
            lo, hi, score = band
            assert lo < hi
            assert score > 0

    def test_niche_yaml_path_exists(self):
        pack = get_pack("construction")
        assert pack.niche_yaml_path.exists()

    def test_niche_has_trades(self):
        pack = get_pack("construction")
        assert "trades" in pack.niche

    def test_meta_has_display_name(self):
        pack = get_pack("construction")
        assert pack.meta.get("display_name")

    def test_meta_has_outreach_templates(self):
        pack = get_pack("construction")
        assert "outreach_templates" in pack.meta


class TestSocialHousingPack:

    def test_loads_without_error(self):
        pack = get_pack("social_housing")
        assert isinstance(pack, SectorPack)

    def test_sector_name(self):
        pack = get_pack("social_housing")
        assert pack.sector == "social_housing"

    def test_retrofit_keyword_present(self):
        pack = get_pack("social_housing")
        assert "retrofit" in pack.scoring.keyword_weights

    def test_decarbonisation_keyword_present(self):
        pack = get_pack("social_housing")
        assert "decarbonisation" in pack.scoring.keyword_weights

    def test_planned_maintenance_keyword_present(self):
        pack = get_pack("social_housing")
        assert "planned maintenance" in pack.scoring.keyword_weights

    def test_different_keywords_from_construction(self):
        construction = get_pack("construction")
        social = get_pack("social_housing")
        # Social housing has retrofit; construction does not
        assert "retrofit" in social.scoring.keyword_weights
        assert "retrofit" not in construction.scoring.keyword_weights

    def test_niche_has_trades(self):
        pack = get_pack("social_housing")
        assert "trades" in pack.niche

    def test_meta_display_name(self):
        pack = get_pack("social_housing")
        assert "Social Housing" in pack.meta.get("display_name", "")


class TestPackCachingAndEnvVar:

    def test_cache_returns_same_object(self):
        p1 = get_pack("construction")
        p2 = get_pack("construction")
        assert p1 is p2

    def test_clear_cache_forces_reload(self):
        p1 = get_pack("construction")
        clear_cache()
        p2 = get_pack("construction")
        assert p1 is not p2

    def test_env_var_selects_sector(self, monkeypatch):
        monkeypatch.setenv("TENDER_SECTOR", "social_housing")
        pack = get_pack()  # no argument — reads env var
        assert pack.sector == "social_housing"

    def test_default_sector_when_no_env_var(self):
        pack = get_pack()
        assert pack.sector == "construction"

    def test_unknown_sector_falls_back_to_construction(self):
        pack = get_pack("totally_unknown_sector_xyz")
        assert pack.sector == "construction"
