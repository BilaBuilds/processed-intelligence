from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from enrichment.connectors import tenderned_xml


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = []

    def get(self, url, auth=None, timeout=None):
        self.calls.append({"url": url, "auth": auth, "timeout": timeout})
        return self.response


class TenderNedXmlConnectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture_path = (
            Path(__file__).parent / "fixtures" / "tenderned" / "sample_publicatie.xml"
        )
        self.fixture_xml = self.fixture_path.read_text(encoding="utf-8")

    def test_extract_publicatie_id_from_url_and_raw_id(self) -> None:
        self.assertEqual(
            tenderned_xml.extract_publicatie_id(
                "https://www.tenderned.nl/aankondigingen/overzicht/publicaties/TN-123/public-xml"
            ),
            "TN-123",
        )
        self.assertEqual(tenderned_xml.extract_publicatie_id("TN-123"), "TN-123")

    def test_missing_credentials_returns_skipped_and_logs_safe_message(self) -> None:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"TENDERNED_XML_USERNAME", "TENDERNED_XML_PASSWORD"}
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertLogs(tenderned_xml.LOGGER, level=logging.INFO) as logs:
                result = tenderned_xml.fetch_publication_xml(
                    "TN-123",
                    load_env=False,
                )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "missing_credentials")
        log_text = "\n".join(logs.output)
        self.assertIn(tenderned_xml.MISSING_CREDENTIALS_MESSAGE, log_text)
        self.assertNotIn("Authorization", log_text)

    def test_mocked_successful_fetch_uses_basic_auth_without_logging_secret(self) -> None:
        session = FakeSession(FakeResponse(self.fixture_xml))
        with patch.dict(
            os.environ,
            {
                "TENDERNED_XML_USERNAME": "fixture-user",
                "TENDERNED_XML_PASSWORD": "fixture-password",
                "TENDERNED_XML_BASE_URL": "https://example.test/api",
            },
            clear=True,
        ):
            result = tenderned_xml.fetch_publication_xml(
                "TN-XML-DEMO-0001",
                session=session,
                load_env=False,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["xml_text"], self.fixture_xml)
        self.assertEqual(session.calls[0]["auth"], ("fixture-user", "fixture-password"))
        self.assertNotIn("fixture-password", result["source_url"])

    def test_401_and_403_handling_has_no_secret_material(self) -> None:
        for status_code in (401, 403):
            session = FakeSession(FakeResponse("denied", status_code=status_code))
            with patch.dict(
                os.environ,
                {
                    "TENDERNED_XML_USERNAME": "fixture-user",
                    "TENDERNED_XML_PASSWORD": "fixture-password",
                },
                clear=True,
            ):
                with self.assertLogs(tenderned_xml.LOGGER, level=logging.WARNING) as logs:
                    result = tenderned_xml.fetch_publication_xml(
                        "TN-123",
                        session=session,
                        load_env=False,
                    )

            self.assertEqual(result["reason"], "unauthorized")
            combined = "\n".join(logs.output + [str(result)])
            self.assertNotIn("fixture-password", combined)
            self.assertNotIn("Authorization", combined)

    def test_xml_parser_extracts_expected_fixture_fields(self) -> None:
        parsed = tenderned_xml.parse_publication_xml(self.fixture_xml)

        self.assertEqual(parsed["title"], "Onderhoud openbare gebouwen Voorbeeldstad")
        self.assertEqual(parsed["buyer"], "Gemeente Voorbeeldstad")
        self.assertIn("45453000", parsed["cpv_codes"])
        self.assertEqual(parsed["publication_date"], "2026-06-15")
        self.assertEqual(parsed["deadline_date"], "2026-08-01T12:00:00+02:00")
        self.assertEqual(parsed["currency"], "EUR")
        self.assertEqual(parsed["lots"][0]["title"], "Noordelijke wijkgebouwen")

    def test_normalized_object_has_processed_schema_keys(self) -> None:
        parsed = tenderned_xml.parse_publication_xml(self.fixture_xml)
        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = tenderned_xml.save_raw_xml(
                "TN-XML-DEMO-0001",
                self.fixture_xml,
                raw_dir=tmpdir,
            )
        parsed.update(
            {
                "publicatieId": "TN-XML-DEMO-0001",
                "source_url": "https://example.test/publicaties/TN-XML-DEMO-0001/public-xml",
                "raw_xml_path": raw_path,
            }
        )

        normalized = tenderned_xml.normalize_publication(parsed)

        for key in (
            "publicatieId",
            "source",
            "country",
            "language",
            "title",
            "description",
            "buyer",
            "cpv_codes",
            "publication_date",
            "deadline_date",
            "procedure_type",
            "notice_type",
            "contract_value",
            "currency",
            "lots",
            "links",
            "source_url",
            "raw_xml_path",
        ):
            self.assertIn(key, normalized)
        self.assertEqual(normalized["source"], "tenderned_xml")
        self.assertEqual(normalized["country"], "NL")
        self.assertEqual(normalized["language"], "nl")


if __name__ == "__main__":
    unittest.main()
