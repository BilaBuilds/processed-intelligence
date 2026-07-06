from __future__ import annotations

import csv
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from enrichment.cli import build_cache, build_provider, row_to_output_row, run_batch
from enrichment.config import AppConfig, CacheSettings, load_app_config
from enrichment.providers.hunter_io import HunterProvider
from enrichment.models import ContactRecord


class FakeWaterfall:
    def enrich(self, company_name: str, domain: str | None = None) -> ContactRecord | None:
        if company_name == "Missing":
            return None
        return ContactRecord(
            name="Jane Smith",
            email="jane@example.com",
            company=company_name,
            source="fake",
            confidence=0.8,
            raw={"evidence": "test"},
        )


class CliTest(unittest.TestCase):
    def test_row_to_output_row_adds_status_and_serialized_raw(self) -> None:
        row = row_to_output_row(
            "Acme",
            "example.com",
            ContactRecord(
                name="Jane Smith",
                source="fake",
                confidence=0.8,
                raw={"evidence": "test"},
            ),
        )

        self.assertEqual(row["status"], "enriched")
        self.assertEqual(row["raw"], '{"evidence": "test"}')

    def test_run_batch_writes_status_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "companies.csv"
            output_path = Path(temp_dir) / "out" / "enriched_output.csv"
            input_path.write_text(
                "company_name,domain\nAcme,example.com\nMissing,missing.example\n",
                encoding="utf-8",
            )

            run_batch(FakeWaterfall(), input_path, output_path)

            with output_path.open("r", encoding="utf-8", newline="") as output_file:
                rows = list(csv.DictReader(output_file))

            self.assertEqual(rows[0]["status"], "enriched")
            self.assertEqual(rows[1]["status"], "not_found")

    def test_build_cache_uses_temporary_path_when_disabled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = build_cache(
                AppConfig(cache=CacheSettings(enabled=False)),
                temp_dir=Path(temp_dir),
            )
            self.assertTrue(str(cache.path).startswith(temp_dir))

    def test_build_provider_creates_hunter_with_key(self) -> None:
        original = os.environ.get("HUNTER_API_KEY")
        os.environ["HUNTER_API_KEY"] = "test-key"
        try:
            provider = build_provider("hunter_io", AppConfig())
        finally:
            if original is None:
                os.environ.pop("HUNTER_API_KEY", None)
            else:
                os.environ["HUNTER_API_KEY"] = original

        self.assertIsInstance(provider, HunterProvider)

    def test_config_defaults_require_contact_route_for_fast_stop(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text("waterfall: {}\n", encoding="utf-8")

            config = load_app_config(config_path)

            self.assertTrue(config.waterfall.require_contact_route_for_fast_stop)


if __name__ == "__main__":
    unittest.main()
