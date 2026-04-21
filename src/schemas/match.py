"""
src/schemas/match.py
====================
Data contract for supplier_matches.json — the primary output of the
supplier intelligence layer.

Every SupplierMatch record must be fully self-contained: a reader
should be able to understand why a supplier was matched to a tender
by reading the record alone, without re-running the pipeline.

SCHEMA_VERSION must be bumped on any field change.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class DimensionScore(BaseModel):
    """Score for one matching dimension, with full rationale."""
    score: float          # 0.0 – 1.0
    weight: float         # from market profile
    weighted: float       # score × weight × 100
    rationale: dict       # dimension-specific evidence


class MatchScoreBreakdown(BaseModel):
    capability_fit: DimensionScore
    regional_fit: DimensionScore
    value_band_fit: DimensionScore
    sector_experience: DimensionScore
    total: float          # sum of weighted scores


class SupplierMatch(BaseModel):
    # Run context
    run_id: str
    market_profile: str
    market_profile_version: str
    schema_version: str = SCHEMA_VERSION

    # What was matched
    tender_id: str
    tender_title: str
    tender_buyer: Optional[str] = None
    tender_region: Optional[str] = None
    tender_value: Optional[float] = None
    tender_deadline: Optional[str] = None
    tender_deadline_days: Optional[int] = None
    tender_verdict: Optional[str] = None  # BID / REVIEW from core pipeline
    tender_score: Optional[int] = None

    # Who was matched
    supplier_id: str
    supplier_name: str
    supplier_region: Optional[str] = None

    # Match outcome
    disqualified: bool = False
    disqualify_reason: Optional[str] = None
    total_score: float = 0.0
    above_threshold: bool = False
    score_breakdown: Optional[MatchScoreBreakdown] = None
    included_in_output: bool = False

    # Outreach targeting
    outreach_priority: Optional[str] = None   # high / medium / low

    # Audit
    timestamp: str = ""
    supplier_record_hash: Optional[str] = None  # SHA256 of normalised supplier record
