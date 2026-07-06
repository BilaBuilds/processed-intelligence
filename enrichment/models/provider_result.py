from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from enrichment.models.evidence import EvidenceItem


class ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    confidence: float = Field(ge=0.0, le=1.0)
    fields: dict[str, Any]
    evidence: list[EvidenceItem]
    reasoning: str

    @field_validator("provider", "reasoning")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("value must be a non-empty string")
        return value.strip()

    @model_validator(mode="after")
    def _fields_must_have_evidence(self) -> "ProviderResult":
        missing = [
            field_name
            for field_name, value in self.fields.items()
            if value is not None
            and not any(item.field_name == field_name for item in self.evidence)
        ]
        if missing:
            raise ValueError(
                "ProviderResult fields missing evidence: " + ", ".join(sorted(missing))
            )
        return self
