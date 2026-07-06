from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from enrichment.agents.evidence import EvidenceGraph
from enrichment.agents.policy import PolicyDecision
from enrichment.agents.strategy import StrategicBrief


@dataclass(frozen=True)
class AccountIntelligenceProfile:
    account_tier: str
    priority_score: float
    strengths: list[str]
    gaps: list[str]
    recommended_research: list[str]
    next_best_action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AccountIntelligenceAgent:
    def build(
        self,
        graph: EvidenceGraph,
        strategic_brief: StrategicBrief,
        policy_decision: PolicyDecision,
    ) -> AccountIntelligenceProfile:
        priority_score = self._priority_score(strategic_brief, policy_decision)
        strengths = self._strengths(graph, strategic_brief, policy_decision)
        gaps = self._gaps(graph, policy_decision)
        tier = self._tier(priority_score, policy_decision.allowed)
        research = self._recommended_research(gaps, policy_decision)

        if policy_decision.allowed and priority_score >= 80:
            next_action = "prepare_approval_ready_draft"
        elif policy_decision.allowed and priority_score >= 65:
            next_action = "add_research_then_draft"
        elif not policy_decision.allowed:
            next_action = "resolve_policy_or_contact_gap"
        else:
            next_action = "defer_until_stronger_signal"

        return AccountIntelligenceProfile(
            account_tier=tier,
            priority_score=round(priority_score, 2),
            strengths=strengths,
            gaps=gaps,
            recommended_research=research,
            next_best_action=next_action,
        )

    def _priority_score(
        self,
        strategic_brief: StrategicBrief,
        policy_decision: PolicyDecision,
    ) -> float:
        score = strategic_brief.expected_value
        if not policy_decision.allowed:
            score -= 25
        if policy_decision.contact_route_type == "generic_inbox":
            score -= 4
        if policy_decision.contact_route_type == "personal_or_role_inbox":
            score += 3
        return max(0.0, min(100.0, score))

    def _strengths(
        self,
        graph: EvidenceGraph,
        strategic_brief: StrategicBrief,
        policy_decision: PolicyDecision,
    ) -> list[str]:
        strengths: list[str] = []
        if strategic_brief.icp_score >= 80:
            strengths.append("Strong ICP match.")
        if strategic_brief.evidence_score >= 0.7:
            strengths.append("High evidence support.")
        if graph.support_score("sic_code") > 0:
            strengths.append("Sector classification is source-backed.")
        if graph.support_score("contact_email") > 0:
            strengths.append("Contact route exists.")
        if policy_decision.allowed:
            strengths.append("Policy gate allows draft creation.")
        return strengths or ["No strong intelligence signals yet."]

    def _gaps(
        self,
        graph: EvidenceGraph,
        policy_decision: PolicyDecision,
    ) -> list[str]:
        gaps: list[str] = []
        if graph.support_score("contact_email") == 0:
            gaps.append("Missing email route.")
        if graph.support_score("contact_phone") == 0:
            gaps.append("Missing phone route.")
        if graph.support_score("sic_code") == 0:
            gaps.append("Missing sector classification.")
        if graph.support_score("contact_name") == 0:
            gaps.append("Missing named contact.")
        if policy_decision.contact_route_type == "generic_inbox":
            gaps.append("Route is generic inbox, not person-specific.")
        if not policy_decision.allowed:
            gaps.extend(policy_decision.reasons)
        return gaps

    def _recommended_research(
        self,
        gaps: list[str],
        policy_decision: PolicyDecision,
    ) -> list[str]:
        research: list[str] = []
        if "Route is generic inbox, not person-specific." in gaps:
            research.append("Find role-specific commercial, preconstruction, or bid contact.")
        if "Missing email route." in gaps:
            research.append("Search website contact pages and public documents for email route.")
        if "Missing named contact." in gaps:
            research.append("Resolve current senior commercial or bid stakeholder.")
        if not policy_decision.allowed:
            research.append("Resolve policy block before drafting.")
        return research or ["No additional research required before human review."]

    def _tier(self, priority_score: float, policy_allowed: bool) -> str:
        if not policy_allowed:
            return "blocked"
        if priority_score >= 85:
            return "tier_1"
        if priority_score >= 70:
            return "tier_2"
        if priority_score >= 55:
            return "tier_3"
        return "nurture"
