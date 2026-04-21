"""
src/market/registry.py
======================
Maps market slugs to their profile YAML paths.
Add a new entry here when a new config/markets/*.yaml is created.

Design: intentionally a plain dict, not dynamic discovery.
Dynamic glob-loading of YAMLs hides what markets exist — an explicit
registry makes the available markets visible in code review and grep.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.market.profile import MarketProfile, load_profile

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MARKETS_DIR = _REPO_ROOT / "config" / "markets"

# ── Registry ──────────────────────────────────────────────────────────────────
# slug -> YAML filename (relative to config/markets/)
_REGISTRY: dict[str, str] = {
    "construction":   "construction.yaml",
    "social_housing": "social_housing.yaml",
}

# ── Cache — profiles are immutable within a process run ──────────────────────
_cache: dict[str, MarketProfile] = {}


def get_profile(market_id: str, *, force_reload: bool = False) -> MarketProfile:
    """
    Load and return a MarketProfile by slug.

    Profiles are cached after first load. Use force_reload=True in tests
    or if the YAML has been modified at runtime.

    Raises:
        KeyError: if market_id is not in the registry
        FileNotFoundError / ValueError: if the YAML is missing or invalid
    """
    if market_id not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(
            f"Unknown market: {market_id!r}. Available: {available}"
        )

    if market_id in _cache and not force_reload:
        return _cache[market_id]

    yaml_path = _MARKETS_DIR / _REGISTRY[market_id]
    profile = load_profile(path=yaml_path)
    _cache[market_id] = profile
    return profile


def list_markets() -> list[str]:
    """Return all registered market slugs in sorted order."""
    return sorted(_REGISTRY.keys())


def all_profiles(*, force_reload: bool = False) -> dict[str, MarketProfile]:
    """Load and return all registered market profiles."""
    return {slug: get_profile(slug, force_reload=force_reload) for slug in list_markets()}
