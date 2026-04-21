"""
tests/test_market_profile.py
=============================
Validates every registered market profile and the profile loader.
Runs on every test invocation — catches YAML regressions before deployment.
"""
import pytest
from pathlib import Path
from pydantic import ValidationError

from src.market.profile import MarketProfile, load_profile
from src.market.registry import get_profile, list_markets, all_profiles

MARKETS_DIR = Path(__file__).parent.parent / "config" / "markets"


# ── Registry ──────────────────────────────────────────────────────────────────

def test_registry_has_markets():
    markets = list_markets()
    assert len(markets) >= 2
    assert "construction" in markets
    assert "social_housing" in markets


def test_all_registered_yamls_exist():
    """Every entry in the registry must have a corresponding YAML file."""
    from src.market.registry import _REGISTRY, _MARKETS_DIR
    for slug, filename in _REGISTRY.items():
        path = _MARKETS_DIR / filename
        assert path.exists(), f"Registry entry {slug!r} points to missing file: {path}"


# ── All profiles validate ─────────────────────────────────────────────────────

@pytest.mark.parametrize("market_id", ["construction", "social_housing"])
def test_profile_loads(market_id):
    profile = get_profile(market_id, force_reload=True)
    assert isinstance(profile, MarketProfile)
    assert profile.market_id == market_id


@pytest.mark.parametrize("market_id", ["construction", "social_housing"])
def test_required_fields_present(market_id):
    p = get_profile(market_id, force_reload=True)
    assert p.market_id
    assert p.version
    assert p.display_name
    assert p.scoring_weights is not None
    assert p.min_match_score > 0


@pytest.mark.parametrize("market_id", ["construction", "social_housing"])
def test_scoring_weights_sum_to_one(market_id):
    p = get_profile(market_id, force_reload=True)
    w = p.scoring_weights
    total = w.capability_fit + w.regional_fit + w.value_band_fit + w.sector_experience
    assert abs(total - 1.0) < 0.001, (
        f"{market_id}: scoring_weights sum to {total}, expected 1.0"
    )


@pytest.mark.parametrize("market_id", ["construction", "social_housing"])
def test_has_capability_keywords(market_id):
    p = get_profile(market_id, force_reload=True)
    assert len(p.capability_keywords.tier_1) >= 1
    assert len(p.capability_keywords.all_keywords) >= 3


@pytest.mark.parametrize("market_id", ["construction", "social_housing"])
def test_has_regional_tiers(market_id):
    p = get_profile(market_id, force_reload=True)
    assert len(p.regional_priority.tier_1) >= 1


@pytest.mark.parametrize("market_id", ["construction", "social_housing"])
def test_has_disqualifiers(market_id):
    p = get_profile(market_id, force_reload=True)
    assert "suspended" in p.disqualifier_flags
    assert "debarred" in p.disqualifier_flags


@pytest.mark.parametrize("market_id", ["construction", "social_housing"])
def test_value_bands_floor_lt_ceiling(market_id):
    p = get_profile(market_id, force_reload=True)
    vb = p.value_bands
    if vb.floor is not None and vb.ceiling is not None:
        assert vb.floor < vb.ceiling
    if vb.sweet_spot_min is not None and vb.sweet_spot_max is not None:
        assert vb.sweet_spot_min < vb.sweet_spot_max


# ── all_profiles() ────────────────────────────────────────────────────────────

def test_all_profiles_loads_all():
    profiles = all_profiles(force_reload=True)
    assert "construction" in profiles
    assert "social_housing" in profiles
    for slug, p in profiles.items():
        assert p.market_id == slug


# ── Every YAML in config/markets/ is registered ───────────────────────────────

def test_all_yamls_are_registered():
    """Prevent orphaned YAML files that nobody consumes."""
    from src.market.registry import _REGISTRY
    registered_files = set(_REGISTRY.values())
    actual_files = {f.name for f in MARKETS_DIR.glob("*.yaml")}
    orphans = actual_files - registered_files
    assert orphans == set(), (
        f"YAML files in config/markets/ not in registry: {orphans}. "
        "Add them to src/market/registry.py or remove them."
    )


# ── Profile loader edge cases ─────────────────────────────────────────────────

def test_load_profile_unknown_market():
    with pytest.raises(KeyError, match="Unknown market"):
        get_profile("nonexistent_market")


def test_load_profile_by_path(tmp_path):
    """load_profile() accepts an explicit path override."""
    yaml_content = """
market_id: test_market
version: "1.0"
display_name: Test Market
scoring_weights:
  capability_fit: 0.40
  regional_fit: 0.25
  value_band_fit: 0.20
  sector_experience: 0.15
"""
    p = tmp_path / "test_market.yaml"
    p.write_text(yaml_content)
    profile = load_profile(path=p)
    assert profile.market_id == "test_market"
    assert profile.version == "1.0"


def test_load_profile_invalid_weights(tmp_path):
    """Weights that don't sum to 1.0 must raise."""
    yaml_content = """
market_id: bad_weights
version: "1.0"
display_name: Bad Weights
scoring_weights:
  capability_fit: 0.50
  regional_fit: 0.50
  value_band_fit: 0.50
  sector_experience: 0.50
"""
    p = tmp_path / "bad_weights.yaml"
    p.write_text(yaml_content)
    with pytest.raises(ValueError, match="sum to 1.0"):
        load_profile(path=p)


def test_load_profile_missing_file():
    with pytest.raises(FileNotFoundError):
        load_profile(path=Path("/tmp/does_not_exist.yaml"))


# ── Regional tier lookup ──────────────────────────────────────────────────────

def test_regional_tier_lookup():
    p = get_profile("construction", force_reload=True)
    assert p.regional_priority.tier_for("london") == 1
    assert p.regional_priority.tier_for("south_east") == 1
    assert p.regional_priority.tier_for("east_of_england") == 2
    assert p.regional_priority.tier_for("wales") == 3
    assert p.regional_priority.tier_for("unknown_region") is None


# ── Outreach priority thresholds ──────────────────────────────────────────────

def test_outreach_priority_construction():
    p = get_profile("construction", force_reload=True)
    assert p.outreach_priority(80.0) == "high"
    assert p.outreach_priority(65.0) == "medium"
    assert p.outreach_priority(30.0) == "low"
