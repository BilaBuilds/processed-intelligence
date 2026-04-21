"""
src/schemas/shortlist.py
========================
Data contract for decision_shortlist.json — the handoff point between
the core demand pipeline and the supplier intelligence layer.

SCHEMA_VERSION must be bumped whenever a field is added, renamed, or removed.
The supplier layer records which version it consumed in its run manifest.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class ScoreBreakdown(BaseModel):
    keywords: int = 0
    keyword_matches: dict[str, Any] = Field(default_factory=dict)
    cpv_match: bool = False
    cpv_missing: bool = False
    region: int = 0
    region_matched: Optional[str] = None
    value: int = 0
    value_band: Optional[str] = None
    deadline: int = 0
    deadline_window: Optional[str] = None
    soft_value_penalty: int = 0
    value_filter_mode: Optional[str] = None

    model_config = {"extra": "allow"}


class StrategyContext(BaseModel):
    trade_classification: dict[str, Any] = Field(default_factory=dict)
    strategic_fit: dict[str, Any] = Field(default_factory=dict)
    narrative: Optional[str] = None
    recommendation: Optional[str] = None
    recommendation_reason: Optional[str] = None

    model_config = {"extra": "allow"}


class ShortlistedTender(BaseModel):
    """
    Canonical shape of one opportunity record as it exits the core pipeline.
    The supplier layer must consume this model — never raw dict access.
    """
    # Identity
    id: str
    title: str
    buyer: Optional[str] = None
    buyer_name: Optional[str] = None
    region: Optional[str] = None
    url: Optional[str] = None
    source_url: Optional[str] = None
    source: Optional[str] = None

    # Value
    value: Optional[float] = None
    value_amount: Optional[float] = None
    currency: str = "GBP"
    value_currency: str = "GBP"

    # Timing
    deadline: Optional[str] = None
    deadline_at: Optional[str] = None
    deadline_days: Optional[int] = None
    fetched_at: Optional[str] = None
    ingested_at: Optional[str] = None
    published_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Classification
    cpv_codes: list[str] = Field(default_factory=list)
    procurement_category: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    release_tags: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)

    # Scoring
    score: int = 0
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    scoring_version: Optional[str] = None
    soft_value_penalty: int = 0
    selection_bucket: Optional[str] = None

    # Decision
    decision_verdict: Optional[str] = None
    decision_confidence: Optional[int] = None
    decision_reasons: list[str] = Field(default_factory=list)
    decision_reason_codes: list[str] = Field(default_factory=list)
    decision_id: Optional[str] = None

    # Context
    context: StrategyContext = Field(default_factory=StrategyContext)

    # Provenance
    provenance_refs: list[str] = Field(default_factory=list)
    raw_id: Optional[str] = None
    opportunity_id: Optional[str] = None
    source_notice_id: Optional[str] = None

    model_config = {"extra": "allow"}

    @property
    def effective_value(self) -> Optional[float]:
        """Return the best available value figure."""
        return self.value_amount or self.value

    @property
    def effective_buyer(self) -> Optional[str]:
        """Return the best available buyer name."""
        return self.buyer_name or self.buyer

    @property
    def effective_region(self) -> Optional[str]:
        return self.region
