from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class EvidenceClaim:
    subject: str
    predicate: str
    value: str
    source: str
    confidence: float
    observed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    @property
    def key(self) -> str:
        return "|".join(
            (
                self.subject.casefold(),
                self.predicate.casefold(),
                self.value.casefold(),
                self.source.casefold(),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceGraph:
    def __init__(self, claims: list[EvidenceClaim] | None = None) -> None:
        self._claims: dict[str, EvidenceClaim] = {}
        for claim in claims or []:
            self.add(claim)

    @property
    def claims(self) -> list[EvidenceClaim]:
        return list(self._claims.values())

    def add(self, claim: EvidenceClaim) -> None:
        current = self._claims.get(claim.key)
        if current is None or claim.confidence > current.confidence:
            self._claims[claim.key] = claim

    def add_claim(
        self,
        subject: str,
        predicate: str,
        value: Any,
        source: str,
        confidence: float,
        url: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> None:
        if value is None or value == "":
            return
        self.add(
            EvidenceClaim(
                subject=str(subject),
                predicate=str(predicate),
                value=str(value),
                source=source,
                confidence=confidence,
                url=url,
                raw=raw or {},
            )
        )

    def claims_for(self, predicate: str) -> list[EvidenceClaim]:
        wanted = predicate.casefold()
        return [
            claim
            for claim in self.claims
            if claim.predicate.casefold() == wanted
        ]

    def support_score(self, predicate: str, value: str | None = None) -> float:
        claims = self.claims_for(predicate)
        if value:
            normalized_value = value.casefold()
            claims = [
                claim
                for claim in claims
                if claim.value.casefold() == normalized_value
            ]
        if not claims:
            return 0.0
        return round(max(claim.confidence for claim in claims), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [
                claim.to_dict()
                for claim in sorted(
                    self.claims,
                    key=lambda item: (
                        item.subject.casefold(),
                        item.predicate.casefold(),
                        item.source.casefold(),
                        item.value.casefold(),
                    ),
                )
            ]
        }


def graph_from_enriched_row(row: dict[str, str], raw: dict[str, Any]) -> EvidenceGraph:
    graph = EvidenceGraph()
    company_name = row.get("company") or row.get("company_name") or "unknown_company"
    source = row.get("source") or "enrichment"
    confidence = _safe_float(row.get("confidence"))

    graph.add_claim(company_name, "company_name", company_name, source, confidence)
    graph.add_claim(company_name, "domain", row.get("domain"), "input", 0.9)
    graph.add_claim(company_name, "contact_name", row.get("name"), source, confidence)
    graph.add_claim(company_name, "contact_title", row.get("title"), source, confidence)
    graph.add_claim(company_name, "contact_email", row.get("email"), source, confidence)
    graph.add_claim(company_name, "contact_phone", row.get("phone"), source, confidence)

    company_profile = raw.get("company_profile")
    if isinstance(company_profile, dict):
        graph.add_claim(
            company_name,
            "company_status",
            company_profile.get("company_status"),
            "companies_house",
            0.95,
            raw=company_profile,
        )
        for code in company_profile.get("sic_codes") or []:
            graph.add_claim(company_name, "sic_code", code, "companies_house", 0.9)
        address = company_profile.get("registered_office_address")
        if isinstance(address, dict):
            graph.add_claim(
                company_name,
                "registered_office",
                ", ".join(str(part) for part in address.values() if part),
                "companies_house",
                0.8,
            )

    officer = raw.get("officer")
    if isinstance(officer, dict):
        graph.add_claim(company_name, "officer_role", officer.get("officer_role"), "companies_house", 0.9)
        graph.add_claim(company_name, "officer_appointed_on", officer.get("appointed_on"), "companies_house", 0.85)

    supplements = raw.get("supplements")
    if isinstance(supplements, list):
        for supplement in supplements:
            if not isinstance(supplement, dict):
                continue
            record = supplement.get("record")
            if not isinstance(record, dict):
                continue
            supplement_source = supplement.get("source") or supplement.get("provider") or "supplement"
            supplement_confidence = _safe_float(supplement.get("confidence"))
            graph.add_claim(company_name, "contact_email", record.get("email"), str(supplement_source), supplement_confidence)
            graph.add_claim(company_name, "contact_phone", record.get("phone"), str(supplement_source), supplement_confidence)

    return graph


def graph_from_dict(payload: dict[str, Any]) -> EvidenceGraph:
    claims = []
    for item in payload.get("claims", []):
        if not isinstance(item, dict):
            continue
        try:
            claims.append(EvidenceClaim(**item))
        except (TypeError, ValueError):
            continue
    return EvidenceGraph(claims)


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
