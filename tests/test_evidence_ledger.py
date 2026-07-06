from __future__ import annotations

import csv
import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from enrichment.cache import EnrichmentCache
from enrichment.gates.client_safe import get_client_safe_claims
from enrichment.models import ContactRecord
from enrichment.models.evidence import EvidenceItem
from enrichment.models.provider_result import ProviderResult
from enrichment.providers.base import Provider
from enrichment.storage.evidence_ledger import EvidenceLedger
from enrichment.verification.claim_verifier import ClaimVerifier
from enrichment.waterfall import WaterfallEnrichment
from scripts.migrate_to_evidence_ledger import migrate


class ResultProvider(Provider):
    def __init__(self, result: ProviderResult | None) -> None:
        self.result = result

    def enrich(self, company_name: str, domain: str | None):
        return self.result


def evidence(
    field_name: str = "email",
    field_value: object = "info@example.com",
    confidence: float = 0.9,
    evidence_type: str = "observed",
    client_safe: bool = True,
    source_provider: str = "website_scrape",
    collected_at: datetime | None = None,
    expires_at: datetime | None = None,
    reasoning_note: str | None = "observed on website",
    entity_key: str = "acme|example.com",
) -> EvidenceItem:
    return EvidenceItem(
        entity_type="contact",
        entity_key=entity_key,
        field_name=field_name,
        field_value=field_value,
        source_provider=source_provider,
        source_url="https://example.com/contact",
        source_ref=None,
        evidence_type=evidence_type,  # type: ignore[arg-type]
        confidence=confidence,
        collected_at=collected_at or datetime.now(UTC),
        expires_at=expires_at,
        raw_snippet=str(field_value),
        reasoning_note=reasoning_note,
        client_safe=client_safe,
        run_id="test_run",
    )


class EvidenceLedgerTest(unittest.TestCase):
    def test_evidence_item_validates_required_fields(self) -> None:
        item = evidence()
        self.assertEqual(item.field_name, "email")
        self.assertEqual(item.confidence, 0.9)

    def test_evidence_item_rejects_invalid_confidence(self) -> None:
        with self.assertRaises(ValidationError):
            evidence(confidence=1.1)
        with self.assertRaises(ValidationError):
            evidence(confidence=-0.1)

    def test_evidence_item_rejects_invalid_evidence_type(self) -> None:
        with self.assertRaises(ValidationError):
            evidence(evidence_type="rumour")

    def test_provider_result_cannot_return_fields_without_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            ProviderResult(
                provider="test",
                confidence=0.9,
                fields={"email": "info@example.com", "phone": "01276 674940"},
                evidence=[evidence("email", "info@example.com")],
                reasoning="test",
            )

    def test_waterfall_stores_evidence_separately_from_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            ledger = EvidenceLedger(temp_path / "ledger.sqlite3")
            item = evidence()
            result = ProviderResult(
                provider="website_scrape",
                confidence=0.9,
                fields={"email": "info@example.com", "company": "Acme"},
                evidence=[item, evidence("company", "Acme", entity_key=item.entity_key)],
                reasoning="website contact page",
            )
            waterfall = WaterfallEnrichment(
                [ResultProvider(result)],
                EnrichmentCache(temp_path / "cache.sqlite3"),
                temp_path / "enrichment.log",
                evidence_ledger=ledger,
                run_id="test_run",
            )
            try:
                record = waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            self.assertEqual(record.email, "info@example.com")
            self.assertIn("email", record.raw["field_evidence_ids"])
            self.assertEqual(len(ledger.get_by_entity_key("acme|example.com")), 2)

    def test_higher_confidence_evidence_wins(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            ledger = EvidenceLedger(temp_path / "ledger.sqlite3")
            low = ProviderResult(
                provider="low",
                confidence=0.4,
                fields={"email": "low@example.com"},
                evidence=[evidence("email", "low@example.com", confidence=0.4, client_safe=False, source_provider="low")],
                reasoning="low confidence",
            )
            high = ProviderResult(
                provider="high",
                confidence=0.9,
                fields={"email": "high@example.com"},
                evidence=[evidence("email", "high@example.com", confidence=0.9, source_provider="high")],
                reasoning="high confidence",
            )
            waterfall = WaterfallEnrichment(
                [ResultProvider(low), ResultProvider(high)],
                EnrichmentCache(temp_path / "cache.sqlite3"),
                temp_path / "enrichment.log",
                enrich_full=True,
                evidence_ledger=ledger,
            )
            try:
                record = waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            self.assertEqual(record.email, "high@example.com")

    def test_conflicting_evidence_is_preserved_not_overwritten(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            ledger = EvidenceLedger(temp_path / "ledger.sqlite3")
            first = ProviderResult(
                provider="a",
                confidence=0.6,
                fields={"email": "a@example.com"},
                evidence=[evidence("email", "a@example.com", 0.6, client_safe=False, source_provider="a")],
                reasoning="a",
            )
            second = ProviderResult(
                provider="b",
                confidence=0.7,
                fields={"email": "b@example.com"},
                evidence=[evidence("email", "b@example.com", 0.7, client_safe=False, source_provider="b")],
                reasoning="b",
            )
            waterfall = WaterfallEnrichment(
                [ResultProvider(first), ResultProvider(second)],
                EnrichmentCache(temp_path / "cache.sqlite3"),
                temp_path / "enrichment.log",
                enrich_full=True,
                evidence_ledger=ledger,
            )
            try:
                waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            items = ledger.get_by_field("acme|example.com", "email")
            self.assertEqual({item.field_value for item in items}, {"a@example.com", "b@example.com"})
            self.assertTrue(any(item.conflict for item in items))

    def test_expired_evidence_is_excluded_from_client_safe_output(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = EvidenceLedger(Path(temp_dir) / "ledger.sqlite3")
            ledger.store(evidence(expires_at=datetime.now(UTC) - timedelta(days=1)))
            claims = get_client_safe_claims("acme|example.com", ledger_path=ledger.path)
            self.assertEqual(claims, {})

    def test_inferred_field_cannot_be_marked_client_safe(self) -> None:
        with self.assertRaises(ValidationError):
            evidence(evidence_type="inferred", client_safe=True)

    def test_guessed_email_without_smtp_verification_is_not_client_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = EvidenceLedger(Path(temp_dir) / "ledger.sqlite3")
            ledger.store(
                evidence(
                    evidence_type="estimated",
                    client_safe=False,
                    source_provider="pattern_guess",
                    confidence=0.5,
                    reasoning_note="SMTP verification outcome=inconclusive",
                )
            )
            claims = get_client_safe_claims("acme|example.com", min_confidence=0.1, ledger_path=ledger.path)
            self.assertNotIn("email", claims)

    def test_companies_house_low_confidence_match_is_not_client_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = EvidenceLedger(Path(temp_dir) / "ledger.sqlite3")
            ledger.store(
                evidence(
                    field_name="director_name",
                    field_value="Jane Smith",
                    source_provider="companies_house",
                    confidence=0.9,
                    reasoning_note="match_score=0.4; needs_review=true",
                )
            )
            claims = get_client_safe_claims("acme|example.com", ledger_path=ledger.path)
            self.assertNotIn("director_name", claims)

    def test_ledger_query_by_entity_key_returns_all_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = EvidenceLedger(Path(temp_dir) / "ledger.sqlite3")
            ledger.store(evidence("email", "info@example.com"))
            ledger.store(evidence("phone", "01276 674940"))
            self.assertEqual(len(ledger.get_by_entity_key("acme|example.com")), 2)

    def test_ledger_query_by_field_name_returns_all_field_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = EvidenceLedger(Path(temp_dir) / "ledger.sqlite3")
            ledger.store(evidence("email", "info@example.com"))
            ledger.store(evidence("phone", "01276 674940"))
            self.assertEqual(len(ledger.get_by_field("acme|example.com", "email")), 1)

    def test_migration_from_old_enriched_output_handles_gracefully(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            csv_path = temp_path / "enriched_output.csv"
            report_path = temp_path / "migration_report.csv"
            ledger_path = temp_path / "ledger.sqlite3"
            with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=["status", "company_name", "domain", "name", "title", "email", "phone", "company", "source", "confidence", "raw"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "status": "enriched",
                        "company_name": "Acme",
                        "domain": "example.com",
                        "name": "",
                        "title": "",
                        "email": "info@example.com",
                        "phone": "",
                        "company": "Acme",
                        "source": "website_scrape",
                        "confidence": "0.6",
                        "raw": json.dumps({"best_url": "https://example.com/contact"}),
                    }
                )

            first = migrate(csv_path, ledger_path, report_path, "test_run")
            second = migrate(csv_path, ledger_path, report_path, "test_run")

            ledger = EvidenceLedger(ledger_path)
            self.assertEqual(len(first), 2)
            self.assertEqual(len(second), 2)
            self.assertEqual(len(ledger.get_by_entity_key("acme|example.com")), 2)
            self.assertTrue(report_path.exists())

    def test_claim_verifier_rejects_blocking_issues_and_allows_warnings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = EvidenceLedger(Path(temp_dir) / "ledger.sqlite3")
            ledger.store(evidence("phone", "01276 674940", confidence=0.9))
            record = ContactRecord(
                email="unsafe@example.com",
                phone="01276 674940",
                company="Acme",
                raw={"domain": "example.com"},
            )
            result = ClaimVerifier(ledger=ledger).verify_enriched_record(record)

            self.assertFalse(result.passed)
            self.assertIn("email has no evidence", result.blocking_issues)
            self.assertEqual(result.safe_fields["phone"], "01276 674940")


if __name__ == "__main__":
    unittest.main()
