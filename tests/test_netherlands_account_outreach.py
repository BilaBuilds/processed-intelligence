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
SCRIPT_PATH = ROOT / "scripts" / "generate_netherlands_account_outreach_with_vertex.py"
OUTPUT_CSV_PATH = ROOT / "data" / "outreach" / "netherlands_account_outreach_enriched.csv"
OUTPUT_JSON_PATH = ROOT / "data" / "outreach" / "netherlands_account_outreach_enriched.json"
REPORT_PATH = ROOT / "docs" / "NETHERLANDS_OUTREACH_PERSONALIZATION_REPORT.md"

REQUIRED_FIELDS = {
    "account_id",
    "company_name",
    "segment",
    "outreach_priority",
    "account_level_angle",
    "linkedin_connection_message",
    "linkedin_follow_up_message",
    "email_subject",
    "email_body_short",
    "source_validation_question",
    "pilot_offer_angle",
    "disclaimer",
    "vertex_status",
    "generated_at",
    "model",
    "project",
}


class NetherlandsAccountOutreachTest(unittest.TestCase):
    def test_script_exists(self) -> None:
        self.assertTrue(SCRIPT_PATH.exists())

    def test_dry_run_writes_parseable_outputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            output_csv = temp / "outreach.csv"
            output_json = temp / "outreach.json"
            output_report = temp / "outreach.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--dry-run",
                    "--output-csv",
                    str(output_csv),
                    "--output-json",
                    str(output_json),
                    "--output-report",
                    str(output_report),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Netherlands account outreach generation complete", result.stdout)
            with output_csv.open("r", encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(len(rows), 100)
            self.assertTrue(REQUIRED_FIELDS.issubset(rows[0].keys()))
            self.assertEqual({row["vertex_status"] for row in rows}, {"dry_run"})
            parsed = json.loads(output_json.read_text(encoding="utf-8"))
            self.assertEqual(parsed["metadata"]["project"], "configured_via_GOOGLE_CLOUD_PROJECT")
            self.assertEqual(parsed["metadata"]["record_count"], len(rows))

    def test_default_outputs_if_present_are_valid(self) -> None:
        if not OUTPUT_CSV_PATH.exists() or not OUTPUT_JSON_PATH.exists():
            self.skipTest("Account outreach outputs have not been generated.")
        with OUTPUT_CSV_PATH.open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))
        self.assertGreaterEqual(len(rows), 10)
        self.assertTrue(REQUIRED_FIELDS.issubset(rows[0].keys()))
        for row in rows:
            self.assertEqual(row["project"], "configured_via_GOOGLE_CLOUD_PROJECT")
            self.assertIn(row["model"], {"gemini-2.5-flash", "gemini-2.5-flash-lite"})
            joined = " ".join(row[field] for field in REQUIRED_FIELDS if field in row).lower()
            self.assertRegex(joined, r"sample|demo|research_needed|not_verified|not verified")
        parsed = json.loads(OUTPUT_JSON_PATH.read_text(encoding="utf-8"))
        self.assertEqual(parsed["metadata"]["project"], "configured_via_GOOGLE_CLOUD_PROJECT")
        self.assertEqual(len(parsed["accounts"]), len(rows))

    def test_no_personal_contacts_or_project_id_in_outputs(self) -> None:
        script_content = SCRIPT_PATH.read_text(encoding="utf-8")
        project_id = "gen-lang" + "-client-0994041741"
        self.assertNotIn(project_id, script_content)
        self.assertNotRegex(script_content, re.compile(r"(api[_-]?key\s*=|secret\s*=|password\s*=|token\s*=|service_account|client_secret|private_key)", re.IGNORECASE))

        paths = [path for path in [OUTPUT_CSV_PATH, OUTPUT_JSON_PATH, REPORT_PATH] if path.exists()]
        contact_words = "|".join(["ph" + "one", "mob" + "ile", "direct" + " dial", "contact" + " name"])
        forbidden = re.compile(
            r"("
            + re.escape(project_id)
            + r"|api[_-]?key\s*=|secret\s*=|password\s*=|token\s*=|"
            r"service_account|client_secret|private_key|"
            r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
            r"\b("
            + contact_words
            + r")\b)",
            re.IGNORECASE,
        )
        for path in paths:
            self.assertFalse(forbidden.search(path.read_text(encoding="utf-8")), str(path))

    def test_report_if_present_is_caveated(self) -> None:
        if not REPORT_PATH.exists():
            self.skipTest("Outreach personalization report has not been generated.")
        content = REPORT_PATH.read_text(encoding="utf-8").lower()
        self.assertIn("sample_demo", content)
        self.assertIn("research_needed", content)
        self.assertIn("no personal", content)
        self.assertIn("not_verified", content)


if __name__ == "__main__":
    unittest.main()
