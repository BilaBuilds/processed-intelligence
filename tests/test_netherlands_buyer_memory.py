from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_netherlands_buyer_memory.py"
ENRICH_SCRIPT = ROOT / "scripts" / "enrich_netherlands_buyer_memory_with_vertex.py"
MEMORY_PATH = ROOT / "data" / "dutch" / "buyer_memory" / "netherlands_buyer_memory.json"
ENRICHED_PATH = ROOT / "data" / "dutch" / "buyer_memory" / "netherlands_buyer_memory_enriched.json"
REPORT_PATH = ROOT / "docs" / "NETHERLANDS_BUYER_MEMORY_BRIEF.md"

BASE_FIELDS = {
    "buyer_id",
    "buyer_name",
    "country",
    "region",
    "buyer_type",
    "categories",
    "observed_opportunity_count",
    "sample_sources",
    "procurement_theme",
    "likely_supplier_fit",
    "timing_signal",
    "relationship_angle",
    "recommended_watch_action",
    "data_status",
    "caveat",
}

ENRICHED_FIELDS = {
    "vertex_status",
    "buyer_signal_summary",
    "likely_procurement_pattern",
    "recommended_sales_angle",
    "relevant_contractor_segments",
    "source_validation_question",
    "risk_note",
    "enriched_priority_score",
    "enriched_generated_at",
    "enriched_model",
    "project",
}


class NetherlandsBuyerMemoryTest(unittest.TestCase):
    def test_scripts_exist(self) -> None:
        self.assertTrue(BUILD_SCRIPT.exists())
        self.assertTrue(ENRICH_SCRIPT.exists())

    def test_build_script_writes_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "memory.json"
            result = subprocess.run(
                [sys.executable, str(BUILD_SCRIPT), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Netherlands buyer memory built", result.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            buyers = payload["buyers"]
            self.assertGreaterEqual(len(buyers), 10)
            self.assertTrue(BASE_FIELDS.issubset(buyers[0].keys()))
            self.assertIn("configured_via_GOOGLE_CLOUD_PROJECT", payload["metadata"]["project"])

    def test_dry_run_enrichment_writes_expected_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            memory = temp / "memory.json"
            enriched = temp / "enriched.json"
            report = temp / "buyer_memory.md"
            subprocess.run([sys.executable, str(BUILD_SCRIPT), "--output", str(memory)], cwd=ROOT, check=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ENRICH_SCRIPT),
                    "--dry-run",
                    "--input",
                    str(memory),
                    "--output",
                    str(enriched),
                    "--output-report",
                    str(report),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Netherlands buyer memory enrichment complete", result.stdout)
            buyers = json.loads(enriched.read_text(encoding="utf-8"))["buyers"]
            self.assertGreaterEqual(len(buyers), 10)
            self.assertTrue((BASE_FIELDS | ENRICHED_FIELDS).issubset(buyers[0].keys()))
            self.assertEqual({buyer["vertex_status"] for buyer in buyers}, {"dry_run"})
            for buyer in buyers:
                self.assertEqual(buyer["project"], "configured_via_GOOGLE_CLOUD_PROJECT")
                self.assertRegex((buyer["data_status"] + " " + buyer["caveat"] + " " + buyer["risk_note"]).lower(), r"research_needed|sample_demo|not_verified")

    def test_default_outputs_if_present_are_valid(self) -> None:
        if not MEMORY_PATH.exists() or not ENRICHED_PATH.exists():
            self.skipTest("Buyer memory outputs have not been generated.")
        memory = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        enriched = json.loads(ENRICHED_PATH.read_text(encoding="utf-8"))
        self.assertEqual(memory["metadata"]["project"], "configured_via_GOOGLE_CLOUD_PROJECT")
        self.assertEqual(enriched["metadata"]["project"], "configured_via_GOOGLE_CLOUD_PROJECT")
        self.assertGreaterEqual(len(enriched["buyers"]), 10)
        for buyer in enriched["buyers"]:
            self.assertTrue((BASE_FIELDS | ENRICHED_FIELDS).issubset(buyer.keys()))
            self.assertLessEqual(float(buyer["enriched_priority_score"]), 100)
            self.assertEqual(buyer["project"], "configured_via_GOOGLE_CLOUD_PROJECT")

    def test_report_if_present_is_caveated(self) -> None:
        if not REPORT_PATH.exists():
            self.skipTest("Buyer memory report has not been generated.")
        content = REPORT_PATH.read_text(encoding="utf-8").lower()
        self.assertIn("sample_demo", content)
        self.assertIn("research_needed", content)
        self.assertIn("not verified", content)

    def test_no_obvious_secrets_or_personal_contacts(self) -> None:
        paths = [BUILD_SCRIPT, ENRICH_SCRIPT]
        paths.extend(path for path in [MEMORY_PATH, ENRICHED_PATH, REPORT_PATH] if path.exists())
        project_id = "gen-lang" + "-client-0994041741"
        secret_terms = "|".join(["service" + "_account", "client" + "_secret", "private" + "_key"])
        forbidden = re.compile(
            r"("
            + re.escape(project_id)
            + r"|api[_-]?key\s*=|secret\s*=|password\s*=|token\s*=|"
            + secret_terms
            + r"|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
            r"\b(phone|mobile|direct dial|contact name|decision maker)\b)",
            re.IGNORECASE,
        )
        for path in paths:
            self.assertFalse(forbidden.search(path.read_text(encoding="utf-8")), str(path))


if __name__ == "__main__":
    unittest.main()
