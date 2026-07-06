from __future__ import annotations

import csv
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DOC_PATHS = [
    ROOT / "docs" / "NETHERLANDS_OUTREACH_MESSAGES.md",
    ROOT / "docs" / "NETHERLANDS_DEMO_SCRIPT.md",
    ROOT / "docs" / "NETHERLANDS_SALES_BRIEF.md",
]
CSV_PATH = ROOT / "data" / "outreach" / "netherlands_company_targets.csv"
JSON_PATH = ROOT / "data" / "outreach" / "netherlands_linkedin_templates.json"

REQUIRED_CSV_COLUMNS = {
    "id",
    "company_name",
    "country",
    "region",
    "segment",
    "likely_relevance",
    "buyer_or_supplier",
    "website",
    "linkedin_url",
    "evidence_status",
    "outreach_priority",
    "suggested_angle",
    "notes",
}

REQUIRED_JSON_SECTIONS = {
    "founder_post",
    "connection_messages",
    "follow_up_messages",
    "email_subjects",
    "email_templates",
    "segment_specific_messages",
    "disclaimers",
}


class NetherlandsOutreachPackTest(unittest.TestCase):
    def test_docs_files_exist(self) -> None:
        for path in DOC_PATHS:
            self.assertTrue(path.exists(), str(path))
            self.assertGreater(path.stat().st_size, 100, str(path))

    def test_csv_exists_and_has_at_least_100_rows(self) -> None:
        self.assertTrue(CSV_PATH.exists())
        with CSV_PATH.open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))

        self.assertGreaterEqual(len(rows), 100)

    def test_required_csv_columns_exist(self) -> None:
        with CSV_PATH.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            self.assertIsNotNone(reader.fieldnames)
            self.assertTrue(REQUIRED_CSV_COLUMNS.issubset(set(reader.fieldnames or [])))

    def test_json_exists_parses_and_contains_required_sections(self) -> None:
        self.assertTrue(JSON_PATH.exists())
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

        self.assertTrue(REQUIRED_JSON_SECTIONS.issubset(set(data)))
        self.assertGreaterEqual(len(data["connection_messages"]), 5)
        self.assertGreaterEqual(len(data["follow_up_messages"]), 5)
        self.assertGreaterEqual(len(data["email_subjects"]), 5)
        self.assertGreaterEqual(len(data["email_templates"]), 3)

    def test_no_obvious_secret_references(self) -> None:
        paths = DOC_PATHS + [CSV_PATH, JSON_PATH]
        sensitive_terms = "|".join(
            [
                "service" + "_account",
                "client" + "_secret",
                "private" + "_key",
            ]
        )
        secret_pattern = re.compile(
            r"(api[_-]?key\s*=|secret\s*=|password\s*=|token\s*=|"
            r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----|"
            + sensitive_terms
            + r")",
            re.IGNORECASE,
        )
        for path in paths:
            self.assertFalse(secret_pattern.search(path.read_text(encoding="utf-8")), str(path))

    def test_unverified_claims_are_caveated(self) -> None:
        caveat_terms = ("sample", "demo", "research_needed", "not verified", "placeholder")

        for path in DOC_PATHS + [JSON_PATH]:
            content = path.read_text(encoding="utf-8").lower()
            self.assertTrue(any(term in content for term in caveat_terms), str(path))

        with CSV_PATH.open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))

        for row in rows:
            self.assertEqual(row["evidence_status"], "research_needed")
            combined = f"{row['evidence_status']} {row['notes']}".lower()
            self.assertTrue(any(term in combined for term in caveat_terms), row["id"])


if __name__ == "__main__":
    unittest.main()
