from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from enrichment.agents.memory import HermesMemoryStore


class HermesMemoryTest(unittest.TestCase):
    def test_record_run_updates_company_and_contact_memory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            enriched_csv = temp_path / "enriched.csv"
            with enriched_csv.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=[
                        "company_name",
                        "domain",
                        "name",
                        "email",
                        "phone",
                        "company",
                        "source",
                        "quality_score",
                        "recommended_action",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "company_name": "Acme",
                        "domain": "example.com",
                        "name": "Jane Smith",
                        "email": "jane@example.com",
                        "phone": "01276 674940",
                        "company": "ACME LIMITED",
                        "source": "test",
                        "quality_score": "88",
                        "recommended_action": "ready_for_outreach",
                    }
                )

            memory = HermesMemoryStore(temp_path / "memory")
            memory.record_run("run_1", enriched_csv, {"total": 1})

            company_memory = json.loads(
                (temp_path / "memory" / "company_memory.json").read_text(
                    encoding="utf-8"
                )
            )
            contact_memory = json.loads(
                (temp_path / "memory" / "contact_memory.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(company_memory["acme limited"]["best_email"], "jane@example.com")
            self.assertEqual(contact_memory["jane@example.com"]["company"], "ACME LIMITED")

