"""
src/market/profile.py
=====================
Loads and validates a market profile YAML from config/markets/.

A MarketProfile is the control object for one supplier intelligence lane.
It parameterises the matching and scoring logic without touching code.

Usage:
    profile = load_profile("construction")
    # or
    profile = load_profile(path=Path("config/markets/construction.yaml"))
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

log = logging.getLogger("market.profile")

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MARKETS_DIR = _REPO_ROOT / "config" / "markets"


# ── Sub-models ────────────────────────────────────────────────────────────────

class CapabilityKeywords(BaseModel):
    tier_1: list[str] = Field(default_factory=list)
    tier_2: list[str] = Field(default_factory=list)
    tier_3: list[str] = Field(default_factory=list)

    @property
    def all_keywords(self) -> list[str]:
        return self.tier_1 + self.tier_2 + self.tier_3


class RegionalPriority(BaseModel):
    tier_1: list[str] = Field(default_factory=list)
    tier_2: list[str] = Field(default_factory=list)
    tier_3: list[str] = Field(default_factory=list)

    def tier_for(self, slug: Optional[str]) -> Optional[int]:
        """Return 1, 2, 3 or None if the slug is not in any tier."""
        if not slug:
            return None
        if slug in self.tier_1:
            return 1
        if slug in self.tier_2:
            return 2
        if slug in self.tier_3:
            return 3
        return None


class ValueBands(BaseModel):
    floor: Optional[float] = None
    ceiling: Optional[float] = None
    sweet_spot_min: Optional[float] = None
    sweet_spot_max: Optional[float] = None


class BuyerTypes(BaseModel):
    preferred: list[str] = Field(default_factory=list)
    neutral: list[str] = Field(default_factory=list)
    deprioritise: list[str] = Field(default_factory=list)


class ScoringWeights(BaseModel):
    capability_fit: float
    regional_fit: float
    value_band_fit: float
    sector_experience: float

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "ScoringWeights":
        total = round(
            self.capability_fit
            + self.regional_fit
            + self.value_band_fit
            + self.sector_experience,
            6,
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"scoring_weights must sum to 1.0, got {total}. "
                "Check capability_fit + regional_fit + value_band_fit + sector_experience."
            )
        return self


class OutreachPriorityThresholds(BaseModel):
    high: float = 75.0
    medium: float = 60.0


# ── Main model ────────────────────────────────────────────────────────────────

class MarketProfile(BaseModel):
    market_id: str
    version: str
    display_name: str
    description: Optional[str] = None

    cpv_codes: list[str] = Field(default_factory=list)
    sector_keywords: list[str] = Field(default_factory=list)

    capability_keywords: CapabilityKeywords = Field(default_factory=CapabilityKeywords)
    min_keyword_hits: int = 2

    regional_priority: RegionalPriority = Field(default_factory=RegionalPriority)
    value_bands: ValueBands = Field(default_factory=ValueBands)
    buyer_types: BuyerTypes = Field(default_factory=BuyerTypes)
    scoring_weights: ScoringWeights

    min_match_score: float = 45.0
    disqualifier_flags: list[str] = Field(default_factory=list)

    top_n_per_tender: int = 5
    outreach_priority_thresholds: OutreachPriorityThresholds = Field(
        default_factory=OutreachPriorityThresholds
    )

    model_config = {"extra": "allow"}

    @field_validator("market_id")
    @classmethod
    def market_id_is_slug(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"market_id must be a slug (alphanumeric + underscores), got: {v!r}")
        return v

    @field_validator("version")
    @classmethod
    def version_is_string(cls, v) -> str:
        return str(v)

    def outreach_priority(self, score: float) -> str:
        """Classify a match score into high / medium / low outreach priority."""
        if score >= self.outreach_priority_thresholds.high:
            return "high"
        if score >= self.outreach_priority_thresholds.medium:
            return "medium"
        return "low"


# ── Loader ────────────────────────────────────────────────────────────────────

def load_profile(
    market_id: Optional[str] = None,
    *,
    path: Optional[Path] = None,
) -> MarketProfile:
    """
    Load and validate a market profile.

    Args:
        market_id: slug name (e.g. "construction") — resolves to
                   config/markets/{market_id}.yaml
        path:      explicit Path override (for tests)

    Raises:
        FileNotFoundError: if the YAML does not exist
        ValueError: if the YAML fails schema validation
    """
    if path is not None:
        yaml_path = Path(path)
    elif market_id is not None:
        yaml_path = _MARKETS_DIR / f"{market_id}.yaml"
    else:
        raise ValueError("Provide either market_id or path.")

    if not yaml_path.exists():
        raise FileNotFoundError(f"Market profile not found: {yaml_path}")

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Market profile YAML must be a mapping, got: {type(raw)}")

    try:
        profile = MarketProfile(**raw)
    except Exception as exc:
        raise ValueError(f"Invalid market profile {yaml_path.name}: {exc}") from exc

    log.debug("Loaded market profile: %s v%s", profile.market_id, profile.version)
    return profile
