from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from enrichment.agents.outreach import (
    CreativeCopywriter,
    DraftPolicyError,
    HermesOutreachOrchestrator,
    PersonaMap,
    ResearchProfile,
    build_hermes_dashboard,
)
from enrichment.agents.policy import OutreachPolicyGate
from enrichment.agents.social_signals import SocialSignalReport
from enrichment.suppression import SuppressionList


class NoopSocialScout:
    def discover(self, domain):
        return SocialSignalReport(domain=domain or "", signals=[], pages_checked=[], notes=[])


class ExplodingCopywriter:
    def __init__(self, policy_gate):
        self.policy_gate = policy_gate

    def build(self, profile, persona):
        raise AssertionError("suppressed lead reached draft generation")


class HermesOutreachTest(unittest.TestCase):
    def test_outreach_orchestrator_writes_sub_agent_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            enriched_csv = temp_path / "enriched.csv"
            outreach_dir = temp_path / "outreach"
            raw = {
                "company_profile": {
                    "company_number": "12345678",
                    "company_status": "active",
                    "sic_codes": ["42990"],
                    "registered_office_address": {"locality": "Burscough"},
                },
                "officer": {
                    "officer_role": "director",
                    "appointed_on": "2020-01-01",
                },
                "officer_appointments": {"active_count": 3},
                "supplements": [
                    {
                        "provider": "WebsiteScrapeProvider",
                        "filled_fields": ["email", "phone"],
                    }
                ],
            }
            with enriched_csv.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
                        "status",
                        "company_name",
                        "domain",
                        "name",
                        "title",
                        "email",
                        "phone",
                        "company",
                        "source",
                        "confidence",
                        "quality_score",
                        "recommended_action",
                        "raw",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "status": "enriched",
                        "company_name": "Acme",
                        "domain": "example.com",
                        "name": "SMITH, Jane",
                        "title": "Director",
                        "email": "jane@example.com",
                        "phone": "01276 674940",
                        "company": "ACME LIMITED",
                        "source": "companies_house+website_scrape",
                        "confidence": "0.8",
                        "quality_score": "88",
                        "recommended_action": "ready_for_outreach",
                        "raw": json.dumps(raw),
                    }
                )

            orchestrator = HermesOutreachOrchestrator()
            orchestrator.social = NoopSocialScout()
            artifacts = orchestrator.build_from_csv(
                enriched_csv,
                outreach_dir,
            )

            self.assertEqual(len(artifacts), 1)
            self.assertTrue(artifacts[0].truth_qa.passed)
            self.assertEqual(artifacts[0].operator_review.status, "approval_ready")
            self.assertIn("ProcessEd Ltd", artifacts[0].draft.body)
            self.assertIn("Reply STOP to opt out", artifacts[0].draft.body)
            self.assertTrue((outreach_dir / "001-acme.json").exists())
            self.assertTrue((outreach_dir / "001-acme.md").exists())

    def test_suppressed_email_never_reaches_draft_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            enriched_csv = temp_path / "enriched.csv"
            outreach_dir = temp_path / "outreach"
            enriched_csv.write_text(
                "status,company_name,domain,name,title,email,phone,company,source,"
                "confidence,quality_score,recommended_action,raw\n"
                "enriched,Acme,example.com,Jane Smith,Director,jane@example.com,"
                "01276 674940,ACME LIMITED,test,0.8,88,ready_for_outreach,{}\n",
                encoding="utf-8",
            )
            suppression = SuppressionList(temp_path / "suppression.sqlite3")
            suppression.add("jane@example.com", reason="unsubscribe", source="test")

            orchestrator = HermesOutreachOrchestrator()
            orchestrator.social = NoopSocialScout()
            orchestrator.policy = OutreachPolicyGate(suppression)
            orchestrator.copywriter = ExplodingCopywriter(orchestrator.policy)

            artifacts = orchestrator.build_from_csv(enriched_csv, outreach_dir)

            self.assertEqual(artifacts, [])

    def test_direct_copywriter_call_enforces_suppression_gate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            suppression = SuppressionList(Path(temp_dir) / "suppression.sqlite3")
            suppression.add("jane@example.com", reason="unsubscribe", source="test")
            copywriter = CreativeCopywriter(OutreachPolicyGate(suppression))
            profile = ResearchProfile(
                company_name="ACME LIMITED",
                contact_name="Jane Smith",
                title="Director",
                email="jane@example.com",
                phone="",
                evidence=[],
                raw_highlights={"quality_score": "90"},
                social_signals={},
                evidence_graph={"claims": []},
            )
            persona = PersonaMap(
                likely_persona="Director",
                likely_priorities=[],
                outreach_angle="surface relevant opportunities",
                tone="direct",
            )

            with self.assertRaises(DraftPolicyError):
                copywriter.build(profile, persona)

    def test_dashboard_contains_metrics_and_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            enriched_csv = temp_path / "enriched.csv"
            outreach_dir = temp_path / "outreach"
            dashboard = temp_path / "report.html"
            enriched_csv.write_text(
                "status,company_name,domain,name,title,email,phone,company,source,"
                "confidence,quality_score,recommended_action,raw\n"
                "enriched,Acme,example.com,Jane Smith,Director,jane@example.com,"
                "01276 674940,ACME LIMITED,test,0.8,88,ready_for_outreach,{}\n",
                encoding="utf-8",
            )
            orchestrator = HermesOutreachOrchestrator()
            orchestrator.social = NoopSocialScout()
            artifacts = orchestrator.build_from_csv(
                enriched_csv,
                outreach_dir,
            )

            build_hermes_dashboard(
                enriched_csv,
                artifacts,
                {"run_id": "test_run"},
                dashboard,
            )

            html = dashboard.read_text(encoding="utf-8")
            self.assertIn("Hermes Lead Report", html)
            self.assertIn("ACME LIMITED", html)
            self.assertIn("View draft", html)


if __name__ == "__main__":
    unittest.main()
