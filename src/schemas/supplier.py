"""
src/schemas/supplier.py
=======================
Canonical data contract for a supplier record after normalisation.

Input (CSV) columns:
    supplier_id, name, region, capabilities, sectors,
    accreditations, value_min, value_max, flags

SCHEMA_VERSION must be bumped on any field change.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "1.0"


class SupplierRecord(BaseModel):
    supplier_id: str
    name: str
    region: Optional[str] = None
    region_normalised: Optional[str] = None  # set by normalize_suppliers.py

    # Capability and sector tags — normalised to lowercase stripped strings
    capabilities: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    accreditations: list[str] = Field(default_factory=list)

    # Commercial range (£)
    value_min: Optional[float] = None
    value_max: Optional[float] = None

    # Disqualifying flags — if any match a market profile disqualifier, supplier is excluded
    flags: list[str] = Field(default_factory=list)

    # Source tracing
    source_file: Optional[str] = None
    source_row: Optional[int] = None

    model_config = {"extra": "allow"}

    @field_validator("capabilities", "sectors", "accreditations", "flags", mode="before")
    @classmethod
    def split_csv_string(cls, v):
        """Accept comma-separated string or list."""
        if isinstance(v, str):
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [x.strip().lower() for x in v if x]
        return []
