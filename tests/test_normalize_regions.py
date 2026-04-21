import unittest

from src import normalize


class TestNormalizeRegionDecode(unittest.TestCase):
    def test_decode_ons_region_code(self) -> None:
        raw = {
            "_source": "find_a_tender",
            "id": "notice-1",
            "ocid": "ocds-test-1",
            "date": "2026-04-01T00:00:00Z",
            "tender": {
                "title": "Groundworks package",
                "description": "Construction works",
                "status": "active",
                "value": {"amount": 250000, "currency": "GBP"},
                "tenderPeriod": {"endDate": "2026-04-20T00:00:00Z"},
            },
            "parties": [
                {
                    "roles": ["buyer"],
                    "name": "Test Buyer",
                    "address": {"region": "UKH11"},
                }
            ],
        }

        rec = normalize.normalize_record(raw)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["region"], "East Anglia")

    def test_keep_plain_text_region(self) -> None:
        raw = {
            "_source": "contracts_finder",
            "id": "notice-2",
            "ocid": "ocds-test-2",
            "date": "2026-04-01T00:00:00Z",
            "tender": {
                "title": "Refurbishment package",
                "description": "Construction works",
                "status": "active",
                "value": {"amount": 250000, "currency": "GBP"},
                "tenderPeriod": {"endDate": "2026-04-20T00:00:00Z"},
            },
            "parties": [
                {
                    "roles": ["buyer"],
                    "name": "Test Buyer",
                    "address": {"region": "East Midlands"},
                }
            ],
        }

        rec = normalize.normalize_record(raw)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["region"], "East Midlands")


if __name__ == "__main__":
    unittest.main()

