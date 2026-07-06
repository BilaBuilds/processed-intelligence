from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "enrich_netherlands_targets_with_vertex.py"
INPUT_PATH = ROOT / "data" / "outreach" / "netherlands_company_targets.csv"
OUTPUT_CSV_PATH = ROOT / "data" / "outreach" / "netherlands_company_targets_enriched.csv"
OUTPUT_JSON_PATH = ROOT / "data" / "outreach" / "netherlands_company_targets_enriched.json"
REPORT_PATH = ROOT / "docs" / "NETHERLANDS_TARGET_ENRICHMENT_REPORT.md"

ENRICHMENT_COLUMNS = {
    "vertex_status",
    "enriched_priority_score",
    "enriched_segment_fit",
    "enriched_suggested_angle",
    "enriched_pilot_hypothesis",
    "enriched_source_validation_question",
    "enriched_reasoning_note",
    "enriched_disclaimer",
    "enriched_model",
    "enriched_generated_at",
}


class NetherlandsTargetEnrichmentTest(unittest.TestCase):
    def test_script_exists(self) -> None:
        self.assertTrue(SCRIPT_PATH.exists())

    def test_dry_run_writes_parseable_outputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_csv = temp_path / "targets.csv"
            output_json = temp_path / "targets.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--dry-run",
                    "--output-csv",
                    str(output_csv),
                    "--output-json",
                    str(output_json),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Netherlands target enrichment complete", result.stdout)
            self.assertTrue(output_csv.exists())
            self.assertTrue(output_json.exists())

            with output_csv.open("r", encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))

            self.assertGreaterEqual(len(rows), 100)
            self.assertTrue(ENRICHMENT_COLUMNS.issubset(rows[0].keys()))
            self.assertEqual({row["vertex_status"] for row in rows}, {"dry_run"})

            parsed = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(parsed["metadata"]["record_count"], len(rows))
            self.assertEqual(parsed["metadata"]["project"], "configured_via_GOOGLE_CLOUD_PROJECT")

    def test_default_outputs_if_present_are_valid(self) -> None:
        if not OUTPUT_CSV_PATH.exists() or not OUTPUT_JSON_PATH.exists():
            self.skipTest("Default enriched outputs have not been generated.")

        with OUTPUT_CSV_PATH.open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))

        self.assertGreaterEqual(len(rows), 10)
        self.assertTrue(ENRICHMENT_COLUMNS.issubset(rows[0].keys()))
        for row in rows:
            score = row["enriched_priority_score"]
            if score:
                self.assertGreaterEqual(float(score), 0)
                self.assertLessEqual(float(score), 100)
            self.assertIn("research_needed", row["evidence_status"])
            self.assertRegex(row["enriched_disclaimer"].lower(), r"research_needed|sample|demo|not verified")

        parsed = json.loads(OUTPUT_JSON_PATH.read_text(encoding="utf-8"))
        self.assertIn("targets", parsed)
        self.assertEqual(len(parsed["targets"]), len(rows))

    def test_no_obvious_secrets_or_project_id_in_outputs(self) -> None:
        paths = [SCRIPT_PATH, INPUT_PATH]
        paths.extend(path for path in [OUTPUT_CSV_PATH, OUTPUT_JSON_PATH, REPORT_PATH] if path.exists())
        sensitive_terms = "|".join(["service" + "_account", "client" + "_secret", "private" + "_key"])
        project_id = "gen-lang" + "-client-0994041741"
        secret_pattern = re.compile(
            r"(api[_-]?key\s*=|secret\s*=|password\s*=|token\s*=|"
            r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----|"
            + sensitive_terms
            + r"|"
            + re.escape(project_id)
            + r")",
            re.IGNORECASE,
        )
        for path in paths:
            self.assertFalse(secret_pattern.search(path.read_text(encoding="utf-8")), str(path))

    def test_no_personal_contact_claims_in_outputs(self) -> None:
        paths = [INPUT_PATH]
        paths.extend(path for path in [OUTPUT_CSV_PATH, OUTPUT_JSON_PATH] if path.exists())
        at_sign = chr(64)
        contact_terms = "|".join(
            [
                "em" + "ail",
                "ph" + "one",
                "mob" + "ile",
                "direct" + " dial",
                "contact" + " name",
                "decision" + " maker",
            ]
        )
        contact_pattern = re.compile(
            r"("
            + re.escape(at_sign)
            + r"(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
            r"\b(?:"
            + contact_terms
            + r")\b)",
            re.IGNORECASE,
        )
        for path in paths:
            content = path.read_text(encoding="utf-8")
            self.assertFalse(contact_pattern.search(content), str(path))

    def test_report_if_present_is_caveated(self) -> None:
        if not REPORT_PATH.exists():
            self.skipTest("Target enrichment report has not been generated.")

        content = REPORT_PATH.read_text(encoding="utf-8").lower()
        self.assertIn("sample/demo", content)
        self.assertIn("research_needed", content)
        self.assertIn("not verified live coverage", content)


if __name__ == "__main__":
    unittest.main()
