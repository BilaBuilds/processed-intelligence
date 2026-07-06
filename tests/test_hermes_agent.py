from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import enrichment.agents.outreach as outreach
from enrichment.agents.hermes import HermesAgent
from enrichment.agents.memory import HermesMemoryStore
from enrichment.agents.social_signals import SocialSignalReport
from enrichment.models import ContactRecord


class FakeWaterfall:
    def __init__(self) -> None:
        self.calls = 0

    def enrich(self, company_name: str, domain: str | None = None) -> ContactRecord | None:
        self.calls += 1
        if company_name == "Missing":
            return None
        return ContactRecord(
            name="Jane Smith",
            title="Director",
            email="jane@example.com",
            phone="01276 674940",
            company=company_name,
            source="test",
            confidence=0.8,
            raw={"domain": domain},
        )

    def close(self) -> None:
        pass


class NoopSocialScout:
    def discover(self, domain):
        return SocialSignalReport(domain=domain or "", signals=[], pages_checked=[], notes=[])


class HermesAgentTest(unittest.TestCase):
    def test_enrich_csv_writes_output_and_summary(self) -> None:
        original_social_scout = outreach.SocialSignalScout
        outreach.SocialSignalScout = lambda: NoopSocialScout()
        with TemporaryDirectory() as temp_dir:
            try:
                temp_path = Path(temp_dir)
                input_path = temp_path / "leads.csv"
                output_path = temp_path / "runs" / "run_1" / "enriched_output.csv"
                summary_path = temp_path / "runs" / "run_1" / "summary.json"
                input_path.write_text(
                    "company_name,domain\nAcme,example.com\nMissing,missing.example\n",
                    encoding="utf-8",
                )

                summary = HermesAgent(
                    FakeWaterfall(),
                    memory=HermesMemoryStore(temp_path / "memory"),
                ).enrich_csv(
                    input_path,
                    output_path,
                    summary_path,
                    run_id="run_1",
                )

                with output_path.open("r", encoding="utf-8", newline="") as output_file:
                    rows = list(csv.DictReader(output_file))
                summary_data = json.loads(summary_path.read_text(encoding="utf-8"))

                self.assertEqual(summary.run_id, "run_1")
                self.assertEqual(summary.total, 2)
                self.assertEqual(summary.enriched, 1)
                self.assertEqual(summary.with_email, 1)
                self.assertEqual(summary.with_phone, 1)
                self.assertEqual(summary.drafts_created, 1)
                self.assertEqual(summary.qa_passed, 1)
                self.assertEqual(summary.approval_ready, 1)
                self.assertTrue((output_path.parent / "report.html").exists())
                self.assertTrue((output_path.parent / "outreach").exists())
                self.assertEqual(rows[0]["recommended_action"], "ready_for_outreach")
                self.assertEqual(rows[1]["recommended_action"], "research_manually")
                self.assertEqual(summary_data["run_id"], "run_1")
            finally:
                outreach.SocialSignalScout = original_social_scout

    def test_enrich_csv_reuses_duplicate_entity_results(self) -> None:
        original_social_scout = outreach.SocialSignalScout
        outreach.SocialSignalScout = lambda: NoopSocialScout()
        with TemporaryDirectory() as temp_dir:
            try:
                temp_path = Path(temp_dir)
                input_path = temp_path / "leads.csv"
                output_path = temp_path / "runs" / "run_1" / "enriched_output.csv"
                summary_path = temp_path / "runs" / "run_1" / "summary.json"
                input_path.write_text(
                    "company_name,domain\nAcme Limited,www.example.com\nACME LTD,example.com\n",
                    encoding="utf-8",
                )
                waterfall = FakeWaterfall()

                HermesAgent(
                    waterfall,
                    memory=HermesMemoryStore(temp_path / "memory"),
                ).enrich_csv(input_path, output_path, summary_path, run_id="run_1")

                self.assertEqual(waterfall.calls, 1)
            finally:
                outreach.SocialSignalScout = original_social_scout


if __name__ == "__main__":
    unittest.main()
