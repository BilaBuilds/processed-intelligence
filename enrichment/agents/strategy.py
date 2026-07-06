from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from enrichment.agents.evidence import EvidenceGraph


CIVILS_SIC_CODES = {
    "42110",
    "42120",
    "42130",
    "42210",
    "42220",
    "42910",
    "42990",
    "43110",
    "43120",
    "43130",
    "43290",
}


@dataclass(frozen=True)
class StrategicBrief:
    icp_score: float
    evidence_score: float
    expected_value: float
    commercial_angle: str
    next_best_step: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CommercialStrategyAgent:
    def build(
        self,
        graph: EvidenceGraph,
        quality_score: float,
        social_platforms: list[str] | None = None,
    ) -> StrategicBrief:
        social_platforms = social_platforms or []
        icp_score = self._icp_score(graph, social_platforms)
        evidence_score = self._evidence_score(graph)
        expected_value = round((icp_score * 0.45) + (quality_score * 0.35) + (evidence_score * 100 * 0.2), 2)
        angle = self._commercial_angle(graph)
        next_step = self._next_step(expected_value, evidence_score, quality_score)
        reasons = self._reasons(graph, quality_score, social_platforms)

        return StrategicBrief(
            icp_score=round(icp_score, 2),
            evidence_score=round(evidence_score, 3),
            expected_value=round(min(expected_value, 100), 2),
            commercial_angle=angle,
            next_best_step=next_step,
            reasons=reasons,
        )

    def _icp_score(self, graph: EvidenceGraph, social_platforms: list[str]) -> float:
        score = 35.0
        sic_codes = {claim.value for claim in graph.claims_for("sic_code")}
        if sic_codes & CIVILS_SIC_CODES:
            score += 35
        if graph.support_score("company_status", "active") >= 0.8:
            score += 10
        if graph.support_score("contact_name") >= 0.6:
            score += 8
        if graph.support_score("contact_email") >= 0.5:
            score += 7
        if social_platforms:
            score += 5
        return min(score, 100)

    def _evidence_score(self, graph: EvidenceGraph) -> float:
        required = (
            "company_name",
            "contact_name",
            "contact_title",
            "contact_email",
            "company_status",
        )
        scores = [graph.support_score(predicate) for predicate in required]
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    def _commercial_angle(self, graph: EvidenceGraph) -> str:
        sic_codes = {claim.value for claim in graph.claims_for("sic_code")}
        if "42990" in sic_codes:
            return (
                "lead with specialist civil engineering opportunity discovery and bid/no-bid focus"
            )
        if sic_codes & CIVILS_SIC_CODES:
            return (
                "lead with earlier surfacing of relevant public-sector construction opportunities"
            )
        if graph.support_score("contact_title") > 0:
            return "lead with practical pipeline relevance for the contact's commercial role"
        return "hold outreach until stronger sector evidence is available"

    def _next_step(
        self,
        expected_value: float,
        evidence_score: float,
        quality_score: float,
    ) -> str:
        if expected_value >= 80 and evidence_score >= 0.55 and quality_score >= 80:
            return "draft_for_human_approval"
        if expected_value >= 65:
            return "research_then_draft"
        return "defer_or_manual_research"

    def _reasons(
        self,
        graph: EvidenceGraph,
        quality_score: float,
        social_platforms: list[str],
    ) -> list[str]:
        reasons = [f"Quality score: {quality_score:g}"]
        sic_codes = [claim.value for claim in graph.claims_for("sic_code")]
        if sic_codes:
            reasons.append(f"SIC evidence: {', '.join(sorted(set(sic_codes)))}")
        if graph.support_score("contact_email") > 0:
            reasons.append("Contact route exists.")
        if social_platforms:
            reasons.append(f"Public social footprint: {', '.join(sorted(set(social_platforms)))}")
        return reasons
