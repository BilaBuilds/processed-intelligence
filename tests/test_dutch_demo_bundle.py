from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities.json"
ENRICHED_FIXTURE_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities_enriched.json"
BUILDER_PATH = ROOT / "scripts" / "build_dutch_demo_bundle.py"

REQUIRED_FIELDS = {
    "id",
    "title",
    "buyer",
    "country",
    "region",
    "source",
    "notice_url",
    "deadline",
    "published_at",
    "cpv_codes",
    "category",
    "estimated_value_eur",
    "estimated_value_gbp",
    "language",
    "summary_en",
    "summary_nl",
    "fit_score",
    "urgency",
    "recommended_action",
    "buyer_signal",
    "expansion_relevance",
    "data_status",
}


def load_builder_module():
    spec = importlib.util.spec_from_file_location("build_dutch_demo_bundle", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Dutch demo bundle builder.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DutchDemoBundleTest(unittest.TestCase):
    def load_fixture(self) -> list[dict]:
        with FIXTURE_PATH.open("r", encoding="utf-8") as fixture_file:
            return json.load(fixture_file)

    def test_fixture_exists(self) -> None:
        self.assertTrue(FIXTURE_PATH.exists())

    def test_fixture_has_at_least_12_opportunities(self) -> None:
        opportunities = self.load_fixture()
        self.assertGreaterEqual(len(opportunities), 12)
        nl_specific = [item for item in opportunities if item["id"].startswith("NL-DEMO")]
        cross_border = [item for item in opportunities if item["id"].startswith("EU-DEMO")]
        self.assertGreaterEqual(len(nl_specific), 8)
        self.assertGreaterEqual(len(cross_border), 4)

    def test_required_fields_exist(self) -> None:
        for opportunity in self.load_fixture():
            missing = REQUIRED_FIELDS - set(opportunity)
            self.assertEqual(missing, set(), opportunity.get("id"))
            self.assertIsInstance(opportunity["cpv_codes"], list)
            self.assertIn("sample_demo_not_verified_live_coverage", opportunity["data_status"])

    def test_average_fit_score_is_numeric_and_in_range(self) -> None:
        opportunities = self.load_fixture()
        average = sum(float(item["fit_score"]) for item in opportunities) / len(opportunities)
        self.assertIsInstance(average, float)
        self.assertGreaterEqual(average, 0)
        self.assertLessEqual(average, 100)

    def test_enriched_fixture_if_present_is_sanitized(self) -> None:
        if not ENRICHED_FIXTURE_PATH.exists():
            self.skipTest("Enriched Dutch demo fixture has not been generated.")

        enriched = json.loads(ENRICHED_FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(enriched), 3)
        for opportunity in enriched:
            self.assertIn("sample_demo_not_verified_live_coverage", opportunity["data_status"])
            vertex = opportunity.get("vertex_enrichment", {})
            self.assertIn(vertex.get("status"), {"generated", "dry_run_not_called"})
            self.assertNotIn("gen-lang-client", json.dumps(vertex))

    def test_dashboard_files_generate(self) -> None:
        builder = load_builder_module()
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir)
            with patch.object(builder, "EXPORT_DIR", export_dir), patch.object(
                builder, "JSON_PATH", export_dir / "dutch_dashboard_data.json"
            ), patch.object(builder, "JS_PATH", export_dir / "dutch_dashboard_data.js"), patch.object(
                builder, "HTML_PATH", export_dir / "index.html"
            ):
                bundle = builder.build_bundle()
                builder.write_bundle(bundle)

                data = json.loads((export_dir / "dutch_dashboard_data.json").read_text(encoding="utf-8"))
                js = (export_dir / "dutch_dashboard_data.js").read_text(encoding="utf-8")
                html = (export_dir / "index.html").read_text(encoding="utf-8")

        self.assertEqual(data["kpis"]["total_opportunities"], len(self.load_fixture()))
        self.assertIn("window.DUTCH_DASHBOARD_DATA", js)
        self.assertIn("dutch_dashboard_data.js", html)
        self.assertIn("Opportunity Cards", html)
        self.assertIn("Source Coverage", html)
        self.assertIn("Outreach Segments", html)

    def test_no_obvious_secret_references_in_netherlands_pack(self) -> None:
        paths = [
            ROOT / "docs" / "NETHERLANDS_MARKET_ENTRY_BRIEF.md",
            ROOT / "docs" / "NETHERLANDS_SOURCE_INVENTORY.md",
            ROOT / "docs" / "NETHERLANDS_DATA_MODEL.md",
            ROOT / "docs" / "NETHERLANDS_GTM_PLAYBOOK.md",
            FIXTURE_PATH,
            ENRICHED_FIXTURE_PATH,
            ROOT / "data" / "outreach" / "netherlands_target_segments.csv",
            ROOT / "scripts" / "build_dutch_demo_bundle.py",
            ROOT / "scripts" / "enrich_dutch_demo_with_vertex.py",
        ]
        secret_pattern = re.compile(
            r"(api[_-]?key\s*=|secret\s*=|password\s*=|token\s*=|-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----)",
            re.IGNORECASE,
        )
        for path in paths:
            self.assertFalse(secret_pattern.search(path.read_text(encoding="utf-8")), str(path))


if __name__ == "__main__":
    unittest.main()
