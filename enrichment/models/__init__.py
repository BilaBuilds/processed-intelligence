from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContactRecord:
    name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    source: str | None = None
    confidence: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


__all__ = ["ContactRecord"]
