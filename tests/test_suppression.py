from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from enrichment.suppression import SuppressionList, ingest_bounce_or_unsubscribe


class SuppressionListTest(unittest.TestCase):
    def test_add_and_lookup_are_case_insensitive(self) -> None:
        with TemporaryDirectory() as temp_dir:
            suppression = SuppressionList(Path(temp_dir) / "suppression.sqlite3")

            suppression.add("Jane@Example.com", reason="unsubscribe", source="test")

            self.assertTrue(suppression.is_suppressed("jane@example.com"))
            self.assertTrue(suppression.is_suppressed(" JANE@EXAMPLE.COM "))
            self.assertFalse(suppression.is_suppressed("other@example.com"))

    def test_bulk_import_handles_duplicate_rows_without_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "suppression.csv"
            csv_path.write_text(
                "email,reason,source\n"
                "jane@example.com,unsubscribe,manual\n"
                "jane@example.com,bounce,mailbox\n",
                encoding="utf-8",
            )
            suppression = SuppressionList(temp_path / "suppression.sqlite3")

            imported = suppression.bulk_import(csv_path)

            self.assertEqual(imported, 2)
            self.assertTrue(suppression.is_suppressed("jane@example.com"))

    def test_bounce_or_unsubscribe_ingestion_adds_suppression(self) -> None:
        with TemporaryDirectory() as temp_dir:
            suppression = SuppressionList(Path(temp_dir) / "suppression.sqlite3")

            ingest_bounce_or_unsubscribe(
                "bounce@example.com",
                event_type="bounce",
                source="imap_bounce_scan",
                suppression_list=suppression,
            )

            self.assertTrue(suppression.is_suppressed("bounce@example.com"))


if __name__ == "__main__":
    unittest.main()
