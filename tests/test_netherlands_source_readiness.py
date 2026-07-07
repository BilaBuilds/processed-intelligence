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
SCRIPT_PATH = ROOT / "scripts" / "enrich_netherlands_sources_with_vertex.py"
OUTPUT_JSON_PATH = ROOT / "data" / "dutch" / "source_readiness" / "netherlands_source_readiness.json"
OUTPUT_CSV_PATH = ROOT / "data" / "dutch" / "source_readiness" / "netherlands_source_readiness.csv"
REPORT_PATH = ROOT / "docs" / "NETHERLANDS_LIVE_SOURCE_READINESS.md"

REQUIRED_FIELDS = {
    "source_name",
    "country_scope",
    "coverage_type",
    "likely_access_method",
    "integration_difficulty_1_5",
    "commercial_value_1_5",
    "legal_data_risk_1_5",
    "required_auth_or_credentials",
    "likely_fields_available",
    "likely_missing_fields",
    "recommended_first_test",
    "live_integration_priority",
    "caveat",
    "vertex_status",
    "vertex_reasoning_note",
    "generated_at",
    "model",
    "project",
}

REQUIRED_SOURCES = {
    "TenderNed",
    "TED/EU notices",
    "EU Public Procurement Data Space",
    "Dutch public works / municipal procurement portals",
    "Dutch water authority procurement",
    "Dutch infrastructure/transport procurement",
    "Dutch framework/maintenance procurement sources",
    "Dutch buyer categories",
    "CPV groups",
}


class NetherlandsSourceReadinessTest(unittest.TestCase):
    def test_script_exists(self) -> None:
        self.assertTrue(SCRIPT_PATH.exists())

    def test_dry_run_writes_parseable_outputs_without_vertex(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_json = temp_path / "readiness.json"
            output_csv = temp_path / "readiness.csv"
            output_report = temp_path / "readiness.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--dry-run",
                    "--output-json",
                    str(output_json),
                    "--output-csv",
                    str(output_csv),
                    "--output-report",
                    str(output_report),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Netherlands source readiness complete", result.stdout)
            self.assertTrue(output_json.exists())
            self.assertTrue(output_csv.exists())

            with output_csv.open("r", encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))

            self.assertGreaterEqual(len(rows), len(REQUIRED_SOURCES))
            self.assertTrue(REQUIRED_FIELDS.issubset(rows[0].keys()))
            self.assertEqual({row["vertex_status"] for row in rows}, {"dry_run"})
            self.assertTrue(REQUIRED_SOURCES.issubset({row["source_name"] for row in rows}))

            parsed = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(parsed["metadata"]["project"], "configured_via_GOOGLE_CLOUD_PROJECT")
            self.assertEqual(parsed["metadata"]["record_count"], len(rows))
            self.assertEqual(len(parsed["sources"]), len(rows))

    def test_default_outputs_if_present_are_caveated_and_structured(self) -> None:
        if not OUTPUT_JSON_PATH.exists() or not OUTPUT_CSV_PATH.exists():
            self.skipTest("Default source readiness outputs have not been generated.")

        with OUTPUT_CSV_PATH.open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))

        self.assertGreaterEqual(len(rows), len(REQUIRED_SOURCES))
        self.assertTrue(REQUIRED_FIELDS.issubset(rows[0].keys()))
        self.assertTrue(REQUIRED_SOURCES.issubset({row["source_name"] for row in rows}))
        for row in rows:
            for score_field in ["integration_difficulty_1_5", "commercial_value_1_5", "legal_data_risk_1_5"]:
                self.assertGreaterEqual(int(row[score_field]), 1)
                self.assertLessEqual(int(row[score_field]), 5)
            self.assertRegex(row["caveat"].lower(), r"research_needed|sample_demo|not_verified")
            self.assertIn(row["model"], {"gemini-2.5-flash", "gemini-2.5-flash-lite"})
            self.assertEqual(row["project"], "configured_via_GOOGLE_CLOUD_PROJECT")

        parsed = json.loads(OUTPUT_JSON_PATH.read_text(encoding="utf-8"))
        self.assertEqual(parsed["metadata"]["project"], "configured_via_GOOGLE_CLOUD_PROJECT")
        self.assertEqual(parsed["metadata"]["record_count"], len(rows))

    def test_report_if_present_has_required_sections(self) -> None:
        if not REPORT_PATH.exists():
            self.skipTest("Readiness report has not been generated.")

        content = REPORT_PATH.read_text(encoding="utf-8").lower()
        for phrase in [
            "source-by-source assessment",
            "recommended integration order",
            "what can be tested without credentials",
            "what needs credentials or api keys",
            "data model gaps",
            "legal and data caveats",
            "next 7-day implementation plan",
            "commercial product impact",
            "not verified",
        ]:
            self.assertIn(phrase, content)

    def test_no_obvious_secrets_or_project_id_in_outputs(self) -> None:
        paths = [SCRIPT_PATH]
        paths.extend(path for path in [OUTPUT_JSON_PATH, OUTPUT_CSV_PATH, REPORT_PATH] if path.exists())
        project_id = "gen-lang" + "-client-0994041741"
        sensitive_terms = "|".join(["service" + "_account", "client" + "_secret", "private" + "_key"])
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


if __name__ == "__main__":
    unittest.main()
