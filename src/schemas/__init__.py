"""
src/schemas
===========
Versioned data contracts for all inter-layer boundaries.

Import these models anywhere you consume pipeline outputs — do not
access shortlist/supplier/match dicts by raw string key outside the
layer that produces them.

Schema versions are bumped in the SCHEMA_VERSION constant of each
module when fields are added, renamed, or removed.
"""
from src.schemas.shortlist import ShortlistedTender, ScoreBreakdown, StrategyContext
from src.schemas.supplier import SupplierRecord
from src.schemas.match import SupplierMatch, MatchScoreBreakdown

__all__ = [
    "ShortlistedTender",
    "ScoreBreakdown",
    "StrategyContext",
    "SupplierRecord",
    "SupplierMatch",
    "MatchScoreBreakdown",
]
