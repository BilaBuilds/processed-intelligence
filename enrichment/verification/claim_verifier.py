from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from enrichment.gates.client_safe import get_client_safe_claims
from enrichment.models import ContactRecord
from enrichment.storage.evidence_ledger import EvidenceLedger


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    safe_fields: dict[str, Any] = field(default_factory=dict)
    unsafe_fields: dict[str, dict[str, Any]] = field(default_factory=dict)


class ClaimVerifier:
    def __init__(
        self,
        ledger: EvidenceLedger | None = None,
        ledger_path: str | Path | None = None,
        min_confidence: float = 0.75,
    ) -> None:
        self.ledger = ledger or EvidenceLedger(ledger_path) if ledger_path else ledger or EvidenceLedger()
        self.min_confidence = min_confidence

    def verify_enriched_record(self, record: ContactRecord) -> VerificationResult:
        entity_key = self._entity_key(record)
        safe_claims = get_client_safe_claims(
            entity_key,
            min_confidence=self.min_confidence,
            ledger_path=self.ledger.path,
        )
        safe_fields = {
            field_name: claim["value"]
            for field_name, claim in safe_claims.items()
        }
        blocking: list[str] = []
        warnings: list[str] = []
        unsafe: dict[str, dict[str, Any]] = {}

        for field_name in ("name", "title", "email", "phone", "company"):
            value = getattr(record, field_name)
            if value is None:
                continue
            evidence = self.ledger.get_by_field(entity_key, field_name)
            if not evidence:
                blocking.append(f"{field_name} has no evidence")
                unsafe[field_name] = {"value": value, "reason": "missing_evidence"}
                continue
            if field_name not in safe_fields:
                best = evidence[0]
                reason = self._unsafe_reason(best)
                if field_name == "email":
                    blocking.append(f"email unsafe: {reason}")
                else:
                    warnings.append(f"{field_name} unsafe: {reason}")
                unsafe[field_name] = {"value": value, "reason": reason}

        return VerificationResult(
            passed=not blocking,
            blocking_issues=blocking,
            warnings=warnings,
            safe_fields=safe_fields,
            unsafe_fields=unsafe,
        )

    def _entity_key(self, record: ContactRecord) -> str:
        raw_key = record.raw.get("entity_key") if isinstance(record.raw, dict) else None
        if raw_key:
            return str(raw_key)
        company = (record.company or "").casefold().strip()
        domain = ""
        if isinstance(record.raw, dict):
            domain = str(record.raw.get("domain") or "").casefold().strip()
        return f"{company}|{domain or 'unknown'}"

    def _unsafe_reason(self, evidence: Any) -> str:
        if evidence.conflict:
            return "unresolved_conflict"
        if evidence.confidence < self.min_confidence:
            return "low_confidence"
        if evidence.evidence_type != "observed":
            return f"not_observed:{evidence.evidence_type}"
        if evidence.source_provider == "pattern_guess":
            return "pattern_guess_not_smtp_verified"
        if evidence.source_provider == "companies_house" and "needs_review=true" in (
            evidence.reasoning_note or ""
        ).casefold():
            return "companies_house_needs_review"
        if evidence.expires_at:
            return "expired_or_not_client_safe"
        return "not_client_safe"
