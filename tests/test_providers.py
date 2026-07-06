from __future__ import annotations

import unittest

from enrichment.providers.companies_house import CompaniesHouseProvider
from enrichment.providers.hunter_io import HunterProvider
import enrichment.providers.pattern_guess as pattern_guess
from enrichment.providers.pattern_guess import PatternGuessProvider
from enrichment.providers.website_scrape import WebsiteScrapeProvider


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("request failed")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self.payload)


class ProviderTest(unittest.TestCase):
    def test_companies_house_adds_profile_and_appointments_detail(self) -> None:
        provider = CompaniesHouseProvider(api_key="test-key")

        def fake_get(path, params=None):
            if path == "/search/companies":
                return {
                    "items": [
                        {
                            "company_number": "12345678",
                            "title": "ACME LIMITED",
                        }
                    ]
                }
            if path == "/company/12345678/officers":
                return {
                    "items": [
                        {
                            "name": "Current Director",
                            "officer_role": "director",
                            "appointed_on": "2020-01-01",
                            "links": {
                                "officer": {
                                    "appointments": "/officers/abc/appointments"
                                }
                            },
                        }
                    ]
                }
            if path == "/company/12345678":
                return {"sic_codes": ["42990"], "company_status": "active"}
            if path == "/officers/abc/appointments":
                return {"items": [{"appointed_to": {"company_name": "ACME LIMITED"}}]}
            raise AssertionError(path)

        provider._get = fake_get

        record = provider.enrich("Acme", "example.com")

        self.assertEqual(record.raw["company_profile"]["sic_codes"], ["42990"])
        self.assertEqual(
            record.raw["officer_appointments"]["items"][0]["appointed_to"][
                "company_name"
            ],
            "ACME LIMITED",
        )

    def test_companies_house_ignores_resigned_directors(self) -> None:
        provider = CompaniesHouseProvider(api_key="test-key")
        provider._get = lambda path, params=None: {
            "items": [
                {
                    "name": "Old Resigned",
                    "officer_role": "director",
                    "appointed_on": "1992-01-01",
                    "resigned_on": "2000-01-01",
                },
                {
                    "name": "Current Earliest",
                    "officer_role": "director",
                    "appointed_on": "2010-01-01",
                },
                {
                    "name": "Current Latest",
                    "officer_role": "director",
                    "appointed_on": "2020-01-01",
                },
            ]
        }

        director = provider._find_senior_director("12345678")

        self.assertEqual(director["name"], "Current Earliest")

    def test_companies_house_uses_domain_signal_to_disambiguate_candidates(self) -> None:
        provider = CompaniesHouseProvider(api_key="test-key")

        def fake_get(path, params=None):
            if path == "/search/companies":
                self.assertEqual(params["items_per_page"], 5)
                return {
                    "items": [
                        {
                            "company_number": "11111111",
                            "title": "ACME RESTAURANTS LIMITED",
                        },
                        {
                            "company_number": "22222222",
                            "title": "ACME CIVILS LIMITED",
                        },
                    ]
                }
            if path == "/company/11111111":
                return {"sic_codes": ["56101"], "company_status": "active"}
            if path == "/company/22222222":
                return {"sic_codes": ["42990"], "company_status": "active"}
            if path == "/company/22222222/officers":
                return {
                    "items": [
                        {
                            "name": "Correct Director",
                            "officer_role": "director",
                            "appointed_on": "2015-01-01",
                        }
                    ],
                    "total_results": 1,
                }
            raise AssertionError(path)

        provider._get = fake_get

        record = provider.enrich("Acme", "https://www.acme-civils.co.uk")

        self.assertEqual(record.company, "ACME CIVILS LIMITED")
        self.assertEqual(record.name, "Correct Director")
        self.assertFalse(record.raw["needs_review"])
        self.assertGreaterEqual(record.raw["candidate_match"]["score"], 0.8)

    def test_companies_house_sic_mismatch_rejects_false_positive_auto_accept(self) -> None:
        provider = CompaniesHouseProvider(api_key="test-key")

        def fake_get(path, params=None):
            if path == "/search/companies":
                return {
                    "items": [
                        {
                            "company_number": "11111111",
                            "title": "ACME CIVILS LIMITED",
                        }
                    ]
                }
            if path == "/company/11111111":
                return {"sic_codes": ["56101"], "company_status": "active"}
            if path == "/company/11111111/officers":
                return {
                    "items": [
                        {
                            "name": "Restaurant Director",
                            "officer_role": "director",
                            "appointed_on": "2015-01-01",
                        }
                    ],
                    "total_results": 1,
                }
            raise AssertionError(path)

        provider._get = fake_get

        record = provider.enrich("Acme Civils", "acme-civils.co.uk")

        self.assertTrue(record.raw["needs_review"])
        self.assertLess(record.confidence, 0.8)
        self.assertTrue(record.raw["candidate_match"]["sic_mismatch"])
        self.assertIn(
            "sic_mismatch_rejected_for_auto_accept",
            record.raw["candidate_match"]["reasons"],
        )

    def test_companies_house_officer_pagination_gets_more_than_100_officers(self) -> None:
        provider = CompaniesHouseProvider(api_key="test-key")

        def fake_get(path, params=None):
            self.assertEqual(path, "/company/12345678/officers")
            start_index = params.get("start_index", 0)
            if start_index == 0:
                return {
                    "items": [
                        {
                            "name": f"Director {index}",
                            "officer_role": "director",
                            "appointed_on": "2020-01-01",
                        }
                        for index in range(100)
                    ],
                    "total_results": 101,
                }
            if start_index == 100:
                return {
                    "items": [
                        {
                            "name": "Longest Tenured",
                            "officer_role": "director",
                            "appointed_on": "1999-01-01",
                        }
                    ],
                    "total_results": 101,
                }
            raise AssertionError(params)

        provider._get = fake_get

        director = provider._find_senior_director("12345678")

        self.assertEqual(director["name"], "Longest Tenured")

    def test_companies_house_low_confidence_match_sets_needs_review(self) -> None:
        provider = CompaniesHouseProvider(api_key="test-key")

        def fake_get(path, params=None):
            if path == "/search/companies":
                return {
                    "items": [
                        {
                            "company_number": "11111111",
                            "title": "ACME HOLDINGS LIMITED",
                        }
                    ]
                }
            if path == "/company/11111111":
                return {"company_status": "active"}
            if path == "/company/11111111/officers":
                return {
                    "items": [
                        {
                            "name": "Uncertain Director",
                            "officer_role": "director",
                            "appointed_on": "2015-01-01",
                        }
                    ],
                    "total_results": 1,
                }
            raise AssertionError(path)

        provider._get = fake_get

        record = provider.enrich("Acme", "totally-different-domain.co.uk")

        self.assertTrue(record.raw["needs_review"])
        self.assertLess(record.confidence, 0.8)
        self.assertLess(record.raw["candidate_match"]["score"], 0.8)

    def test_pattern_guess_prefers_verified_address(self) -> None:
        original_get_mx_records = pattern_guess.get_mx_records
        original_smtp_verify = pattern_guess.smtp_verify
        try:
            pattern_guess.get_mx_records = lambda domain: ["mx.example.com"]
            pattern_guess.smtp_verify = (
                lambda email, mx_host, timeout=10.0: email == "jane.smith@example.com"
            )

            record = PatternGuessProvider().enrich("Jane Smith", "example.com")

            self.assertIsNotNone(record)
            self.assertEqual(record.email, "jane.smith@example.com")
            self.assertEqual(record.confidence, 0.5)
        finally:
            pattern_guess.get_mx_records = original_get_mx_records
            pattern_guess.smtp_verify = original_smtp_verify

    def test_hunter_provider_returns_best_email_with_evidence(self) -> None:
        payload = {
            "data": {
                "domain": "example.com",
                "organization": "Acme",
                "emails": [
                    {
                        "value": "info@example.com",
                        "type": "generic",
                        "confidence": 96,
                        "sources": [{"uri": "https://example.com/contact"}],
                    },
                    {
                        "value": "jane@example.com",
                        "type": "personal",
                        "confidence": 88,
                        "first_name": "Jane",
                        "last_name": "Smith",
                        "position": "Commercial Director",
                        "department": "management",
                        "sources": [{"uri": "https://example.com/team"}],
                    },
                ],
            }
        }
        session = FakeSession(payload)
        provider = HunterProvider(api_key="test-key", session=session, timeout=3, limit=5)

        record = provider.enrich("Acme", "https://www.example.com")

        self.assertEqual(record.email, "jane@example.com")
        self.assertEqual(record.name, "Jane Smith")
        self.assertEqual(record.title, "Commercial Director")
        self.assertEqual(record.confidence, 0.88)
        self.assertEqual(record.raw["evidence"][0]["source_provider"], "hunter_io")
        self.assertEqual(record.raw["evidence"][0]["evidence_type"], "observed")
        self.assertEqual(session.calls[0]["params"]["domain"], "example.com")
        self.assertNotIn("test-key", session.calls[0]["url"])

    def test_hunter_provider_marks_unsourced_email_not_client_safe(self) -> None:
        payload = {
            "data": {
                "domain": "example.com",
                "emails": [
                    {
                        "value": "info@example.com",
                        "type": "generic",
                        "confidence": 80,
                        "sources": [],
                    },
                ],
            }
        }
        provider = HunterProvider(api_key="test-key", session=FakeSession(payload))

        record = provider.enrich("Acme", "example.com")

        self.assertEqual(record.raw["evidence"][0]["evidence_type"], "inferred")
        self.assertFalse(record.raw["evidence"][0]["client_safe"])

    def test_pattern_guess_can_run_with_smtp_disabled(self) -> None:
        original_get_mx_records = pattern_guess.get_mx_records
        try:
            pattern_guess.get_mx_records = lambda domain: ["mx.example.com"]

            record = PatternGuessProvider(smtp_enabled=False).enrich(
                "Jane Smith",
                "example.com",
            )

            self.assertIsNotNone(record)
            self.assertEqual(record.confidence, 0.3)
            self.assertEqual(record.raw["verification"], "smtp_disabled")
        finally:
            pattern_guess.get_mx_records = original_get_mx_records

    def test_website_scrape_extracts_role_and_email(self) -> None:
        html = """
        <html>
          <body>
            <p>Jane Smith - Preconstruction Director</p>
            <a href="mailto:jane@example.com">Email Jane</a>
          </body>
        </html>
        """
        provider = WebsiteScrapeProvider()
        candidates, emails, phones = provider._extract_candidates(
            "https://example.com",
            html,
        )

        self.assertEqual(emails, ["jane@example.com"])
        self.assertEqual(phones, [])
        self.assertEqual(candidates[0].name, "Jane Smith")
        self.assertEqual(candidates[0].title, "Preconstruction Director")

    def test_website_scrape_extracts_phone(self) -> None:
        html = """
        <html>
          <body>
            <p>Call our team on 01704 123456</p>
          </body>
        </html>
        """
        provider = WebsiteScrapeProvider()
        candidates, emails, phones = provider._extract_candidates(
            "https://example.com",
            html,
        )

        self.assertEqual(emails, [])
        self.assertEqual(phones, ["01704 123456"])
        self.assertEqual(candidates[0].phone, "01704 123456")


if __name__ == "__main__":
    unittest.main()
