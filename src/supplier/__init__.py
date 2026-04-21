# src/supplier — supply intelligence layer
# Consumes core pipeline outputs. Never imported by core pipeline modules.
from src.supplier.ingest_suppliers import ingest_suppliers, IngestResult
from src.supplier.normalize_suppliers import normalize_suppliers, NormalizeResult
from src.supplier.match_suppliers import match_suppliers, load_shortlist, MatchResult

__all__ = [
    "ingest_suppliers",
    "IngestResult",
    "normalize_suppliers",
    "NormalizeResult",
    "match_suppliers",
    "load_shortlist",
    "MatchResult",
]
