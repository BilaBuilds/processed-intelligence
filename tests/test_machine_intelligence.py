from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from enrichment.agents.evidence import graph_from_dict, graph_from_enriched_row
from enrichment.agents.account_intelligence import AccountIntelligenceAgent
from enrichment.agents.entity_resolution import EntityResolver
from enrichment.agents.policy import OutreachPolicyGate
from enrichment.agents.strategy import CommercialStrategyAgent
from enrichment.suppression import SuppressionList


class MachineIntelligenceTest(unittest.TestCase):
    def test_evidence_graph_builds_claim_ledger_from_enriched_row(self) -> None:
        raw = {
            "company_profile": {
                "company_status": "active",
                "sic_codes": ["42990"],
            },
            "officer": {
                "officer_role": "director",
                "appointed_on": "2011-01-01",
            },
        }
        row = {
            "company_name": "ACME LIMITED",
            "domain": "example.com",
            "name": "Jane Smith",
            "title": "Director",
            "email": "jane@example.com",
            "phone": "01276 674940",
            "company": "ACME LIMITED",
            "source": "companies_house+website_scrape",
            "confidence": "0.8",
        }

        graph = graph_from_enriched_row(row, raw)
        payload = graph.to_dict()

        self.assertGreaterEqual(graph.support_score("contact_email"), 0.8)
        self.assertGreaterEqual(graph.support_score("sic_code", "42990"), 0.9)
        self.assertEqual(
            graph_from_dict(payload).support_score("company_status", "active"),
            0.95,
        )

    def test_strategy_scores_civils_leads_above_generic_leads(self) -> None:
        civils_graph = graph_from_enriched_row(
            {
                "company_name": "ACME LIMITED",
                "company": "ACME LIMITED",
                "name": "Jane Smith",
                "title": "Director",
                "email": "jane@example.com",
                "confidence": "0.8",
            },
            {"company_profile": {"company_status": "active", "sic_codes": ["42990"]}},
        )
        generic_graph = graph_from_enriched_row(
            {
                "company_name": "Generic Limited",
                "company": "Generic Limited",
                "confidence": "0.3",
            },
            {},
        )

        agent = CommercialStrategyAgent()
        civils = agent.build(civils_graph, quality_score=90)
        generic = agent.build(generic_graph, quality_score=20)

        self.assertGreater(civils.expected_value, generic.expected_value)
        self.assertEqual(civils.next_best_step, "draft_for_human_approval")

    def test_policy_gate_blocks_suppressed_contacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            suppression = SuppressionList(Path(temp_dir) / "suppression.sqlite3")
            suppression.add("jane@example.com", reason="unsubscribe", source="test")
            gate = OutreachPolicyGate(suppression)

            decision = gate.evaluate(
                "jane@example.com",
                "example.com",
                evidence_score=0.8,
                quality_score=90,
            )

            self.assertFalse(decision.allowed)
            self.assertFalse(decision.policy_allowed)
            self.assertEqual(decision.status, "policy_blocked")
            self.assertIn("suppressed", decision.reasons)
            self.assertIn("ProcessEd Ltd", decision.required_footer)
            self.assertIn("Reply STOP to opt out", decision.required_footer)

    def test_entity_resolver_collapses_legal_suffix_and_www_domain(self) -> None:
        resolver = EntityResolver()

        first = resolver.resolve("ACME LIMITED", "https://www.example.com")
        second = resolver.resolve("Acme Ltd", "example.com")

        self.assertEqual(first.entity_key, second.entity_key)

    def test_account_intelligence_marks_generic_route_gap(self) -> None:
        graph = graph_from_enriched_row(
            {
                "company_name": "ACME LIMITED",
                "company": "ACME LIMITED",
                "name": "Jane Smith",
                "title": "Director",
                "email": "info@example.com",
                "phone": "01276 674940",
                "confidence": "0.8",
            },
            {"company_profile": {"company_status": "active", "sic_codes": ["42990"]}},
        )
        strategy = CommercialStrategyAgent().build(graph, quality_score=90)
        policy = OutreachPolicyGate().evaluate(
            "info@example.com",
            "example.com",
            strategy.evidence_score,
            90,
        )

        profile = AccountIntelligenceAgent().build(graph, strategy, policy)

        self.assertEqual(profile.account_tier, "tier_1")
        self.assertIn("Route is generic inbox, not person-specific.", profile.gaps)


if __name__ == "__main__":
    unittest.main()
