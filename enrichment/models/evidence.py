from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EvidenceType = Literal["observed", "inferred", "estimated"]
EntityType = Literal["company", "contact", "buyer", "tender", "supplier"]


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    entity_key: str
    field_name: str
    field_value: Any
    source_provider: str
    source_url: str | None = None
    source_ref: str | None = None
    evidence_type: EvidenceType
    confidence: float = Field(ge=0.0, le=1.0)
    collected_at: datetime
    expires_at: datetime | None = None
    raw_snippet: str | None = None
    reasoning_note: str | None = None
    client_safe: bool
    run_id: str | None = None
    conflict: bool = False
    evidence_id: str | None = None

    @field_validator("entity_key", "field_name", "source_provider")
    @classmethod
    def _non_empty_string(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("value must be a non-empty string")
        return value.strip()

    @model_validator(mode="after")
    def _validate_field_value_and_safety(self) -> "EvidenceItem":
        if self.field_value is None:
            raise ValueError("field_value must not be None")
        if self.evidence_type != "observed" and self.client_safe:
            raise ValueError("inferred or estimated evidence cannot be client_safe")
        return self

    def is_expired(self, at: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= (at or datetime.now(self.expires_at.tzinfo))
