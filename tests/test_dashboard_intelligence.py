import json
import tempfile
import unittest
from pathlib import Path

from scripts.dashboard_intelligence import (
    ASSIGNMENT_PREFIX,
    build_dashboard_payload,
    load_dashboard_js,
    value_label,
    write_dashboard_js,
)


def _payload(tenders):
    return {
        "generated_at": "2025-06-04T12:00:00Z",
        "latestRun": {
            "generated_at": "2025-06-04T12:00:00Z",
            "manifest": {},
            "tenders": tenders,
        },
    }


class DashboardIntelligenceTests(unittest.TestCase):
    def test_nl_construction_terms_are_icp_matched_and_score_above_65(self):
        data = build_dashboard_payload(
            _payload(
                [
                    {
                        "id": "nl-1",
                        "source": "tenderned",
                        "country": "NL",
                        "title": "Renovatie brug en riolering openbare ruimte",
                        "buyer": "Gemeente Voorbeeldstad",
                        "deadline": "2025-07-15T10:00:00",
                        "publication_date": "2025-06-01",
                    }
                ]
            )
        )

        tender = data["latestRun"]["tenders"][0]
        self.assertIs(tender["icp_match"], True)
        self.assertGreaterEqual(tender["score"], 65)
        self.assertIs(tender["shortlist"], True)

    def test_shortlisted_cannot_exceed_icp_matched(self):
        data = build_dashboard_payload(
            _payload(
                [
                    {
                        "id": "nl-1",
                        "source": "tenderned",
                        "country": "NL",
                        "title": "Nieuwbouw civiel werk",
                        "buyer": "Rijkswaterstaat",
                        "deadline": "2025-07-01",
                    },
                    {
                        "id": "nl-2",
                        "source": "tenderned",
                        "country": "NL",
                        "title": "Kantoorartikelen",
                        "buyer": "Gemeente Voorbeeldstad",
                        "deadline": "2025-07-01",
                    },
                ]
            )
        )

        metrics = data["latestRun"]["metrics"]
        self.assertGreaterEqual(metrics["icp_matched"], metrics["shortlisted"])

    def test_expired_april_may_deadlines_do_not_count_as_active_or_shortlisted(self):
        data = build_dashboard_payload(
            _payload(
                [
                    {
                        "id": "expired-april",
                        "source": "tenderned",
                        "country": "NL",
                        "title": "Civiel onderhoud wegen",
                        "buyer": "Provincie Test",
                        "deadline": "2025-04-30",
                    },
                    {
                        "id": "expired-may",
                        "source": "tenderned",
                        "country": "NL",
                        "title": "Renovatie kade",
                        "buyer": "Havenbedrijf Test",
                        "deadline": "2025-05-31",
                    },
                ]
            )
        )

        self.assertEqual({row["status"] for row in data["latestRun"]["tenders"]}, {"expired"})
        self.assertEqual(data["latestRun"]["metrics"]["active_opportunities"], 0)
        self.assertEqual(data["latestRun"]["metrics"]["shortlisted"], 0)

    def test_buyers_export_contains_buyer_level_records(self):
        data = build_dashboard_payload(
            _payload(
                [
                    {
                        "id": "a",
                        "source": "tenderned",
                        "country": "NL",
                        "title": "Civiel onderhoud watergangen",
                        "buyer": "Gemeente A",
                        "deadline": "2025-07-01",
                        "publication_date": "2025-06-02",
                    },
                    {
                        "id": "b",
                        "source": "tenderned",
                        "country": "NL",
                        "title": "Ingenieursdiensten openbare ruimte",
                        "buyer": "Gemeente A",
                        "deadline": "2025-08-01",
                        "publication_date": "2025-06-03",
                    },
                ]
            )
        )

        buyers = data["latestRun"]["buyers"]
        self.assertEqual(len(buyers), 1)
        self.assertEqual(buyers[0]["buyer"], "Gemeente A")
        self.assertEqual(buyers[0]["opportunity_count"], 2)
        self.assertEqual(buyers[0]["active_opportunities"], 2)
        self.assertIn("recommended_action", buyers[0])

    def test_value_unknown_displays_cleanly_when_missing(self):
        self.assertEqual(value_label(None), "Value unknown")
        self.assertEqual(value_label(""), "Value unknown")

    def test_existing_dashboard_json_loads(self):
        original = _payload(
            [
                {
                    "id": "nl-1",
                    "source": "tenderned",
                    "country": "NL",
                    "title": "Rijkswaterstaat infrastructuur onderhoud",
                    "buyer": "Rijkswaterstaat",
                    "deadline": "2025-07-01",
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dashboard_data.js"
            path.write_text(f"{ASSIGNMENT_PREFIX}{json.dumps(original)};\n", encoding="utf-8")

            loaded = load_dashboard_js(path)
            normalized = build_dashboard_payload(loaded)
            write_dashboard_js(path, normalized)

            reloaded = load_dashboard_js(path)

        self.assertEqual(reloaded["latestRun"]["metrics"]["tenders_ingested"], 1)
        self.assertEqual(reloaded["latestRun"]["tenders"][0]["value_label"], "Value unknown")

    def test_local_export_paths_are_scrubbed_from_public_payload(self):
        data = build_dashboard_payload(
            {
                **_payload([]),
                "summary": {"data_source": r"C:\Dev\dutch_output\dutch_tenders.json"},
                "system_health": {"data_source": "/mnt/c/Users/bilal/export.json"},
            }
        )

        self.assertEqual(data["summary"]["data_source"], "static_demo_export")
        self.assertEqual(data["system_health"]["data_source"], "static_demo_export")


if __name__ == "__main__":
    unittest.main()
