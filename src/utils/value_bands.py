"""
src/utils/value_bands.py
========================
Value band classification shared by the core pipeline and supplier layer.

Single source of truth — do not re-implement band logic in supplier modules.
"""
from __future__ import annotations

from typing import Optional


def classify_value_band(value: Optional[float]) -> str:
    """Return a human-readable value band label for a contract value (£)."""
    if value is None:
        return "unknown"
    if value < 10_000:
        return "under_10k"
    if value < 50_000:
        return "10k_50k"
    if value < 100_000:
        return "50k_100k"
    if value < 250_000:
        return "100k_250k"
    if value < 500_000:
        return "250k_500k"
    if value < 750_000:
        return "500k_750k"
    if value < 2_000_000:
        return "750k_2m"
    if value < 5_000_000:
        return "2m_5m"
    if value < 10_000_000:
        return "5m_10m"
    return "over_10m"


def value_in_range(
    value: Optional[float],
    floor: Optional[float],
    ceiling: Optional[float],
) -> bool:
    """Return True if value falls within [floor, ceiling] (inclusive, None = unbounded)."""
    if value is None:
        return False
    if floor is not None and value < floor:
        return False
    if ceiling is not None and value > ceiling:
        return False
    return True


def value_in_sweet_spot(
    value: Optional[float],
    sweet_spot_min: Optional[float],
    sweet_spot_max: Optional[float],
) -> bool:
    """Return True if value is within the preferred sweet-spot range."""
    return value_in_range(value, sweet_spot_min, sweet_spot_max)
