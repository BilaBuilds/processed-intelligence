"""
src/entities.py
===============
Canonical runtime entities for ProcessEd.

These dataclasses are the source-of-truth schemas shared across:
    - procurement pipeline outputs
    - decision persistence
    - risk signal persistence
    - outreach/compliance state
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ProcurementOpportunity:
    opportunity_id: str
    source: str
    source_notice_id: str
    ocid: str | None
    buyer_name: str | None
    title: str | None
    region: str | None
    value_amount: float | None
    value_currency: str | None
    deadline_at: str | None
    status: str | None
    release_tags: list[str] = field(default_factory=list)
    source_url: str | None = None
    published_at: str | None = None
    updated_at: str | None = None
    ingested_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionEvent:
    decision_id: str
    opportunity_id: str
    verdict: str
    confidence: int
    reason_codes: list[str]
    risk_flags: list[str]
    score_total: int
    scoring_version: str
    model_version: str | None
    provenance_refs: list[str]
    decided_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SupplierEntity:
    supplier_id: str
    legal_name: str
    aliases: list[str] = field(default_factory=list)
    registration_number: str | None = None
    owner_links: list[str] = field(default_factory=list)
    sanctions_markers: list[str] = field(default_factory=list)
    debarment_markers: list[str] = field(default_factory=list)
    performance_markers: list[str] = field(default_factory=list)
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskSignal:
    risk_signal_id: str
    subject_type: str
    subject_id: str
    signal_type: str
    severity: str
    confidence: int
    evidence_source: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LeadActivationRecord:
    lead_id: str
    account_name: str
    contact_name: str | None
    contact_channel: str
    lawful_basis_path: str
    outreach_stage: str
    suppression_state: str
    response_status: str
    call_booked: bool
    pilot_started: bool
    last_contacted_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

