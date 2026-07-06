from __future__ import annotations

import json
import sqlite3
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from enrichment.cache import EnrichmentCache
from enrichment.models import ContactRecord
from enrichment.providers.base import Provider
from enrichment.waterfall import WaterfallEnrichment
from scripts.migrate_enrichment_cache_composite_key import migrate_cache


class FakeProvider(Provider):
    def __init__(self, record: ContactRecord | None = None, raises: bool = False) -> None:
        self.record = record
        self.raises = raises
        self.calls = 0

    def enrich(self, company_name: str, domain: str | None) -> ContactRecord | None:
        self.calls += 1
        if self.raises:
            raise RuntimeError("provider failed")
        return self.record


class FakePersonProvider(FakeProvider):
    input_kind = "person"


class AdvancingClock:
    def __init__(self) -> None:
        self.current = 0.0

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


class SlowProvider(FakeProvider):
    def __init__(self, clock: AdvancingClock, seconds: float) -> None:
        super().__init__(None)
        self.clock = clock
        self.seconds = seconds

    def enrich(self, company_name: str, domain: str | None) -> ContactRecord | None:
        self.calls += 1
        self.clock.advance(self.seconds)
        return None


class CacheWaterfallTest(unittest.TestCase):
    def test_waterfall_caches_hits_and_not_found_markers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache = EnrichmentCache(temp_path / "cache.sqlite3")
            log_path = temp_path / "enrichment.log"
            provider = FakeProvider(
                ContactRecord(name="Jane Smith", source="fake", confidence=0.8)
            )
            waterfall = WaterfallEnrichment([provider], cache, log_path)
            try:
                first = waterfall.enrich("Acme", "example.com")
                second = waterfall.enrich("  ACME  ", "example.com")
            finally:
                waterfall.close()

            self.assertEqual(first, second)
            self.assertEqual(provider.calls, 1)

            miss_provider = FakeProvider()
            miss_waterfall = WaterfallEnrichment([miss_provider], cache, log_path)
            try:
                self.assertIsNone(miss_waterfall.enrich("Missing Co"))
                self.assertIsNone(miss_waterfall.enrich("missing co"))
            finally:
                miss_waterfall.close()

            self.assertEqual(miss_provider.calls, 1)

    def test_waterfall_halts_after_first_high_confidence_hit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            first = FakeProvider(
                ContactRecord(email="hit@example.com", source="first", confidence=0.8)
            )
            second = FakeProvider(
                ContactRecord(phone="01276 674940", source="second", confidence=0.6)
            )
            waterfall = WaterfallEnrichment(
                [first, second],
                EnrichmentCache(temp_path / "cache.sqlite3"),
                temp_path / "enrichment.log",
            )

            try:
                record = waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            self.assertEqual(record.email, "hit@example.com")
            self.assertEqual(first.calls, 1)
            self.assertEqual(second.calls, 0)

            events = [
                json.loads(line)
                for line in (temp_path / "enrichment.log").read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("confidence_threshold", {event.get("stop_reason") for event in events})

    def test_waterfall_continues_after_high_confidence_identity_without_contact_route(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            identity = FakeProvider(
                ContactRecord(
                    name="Jane Smith",
                    title="Director",
                    company="ACME LIMITED",
                    source="companies_house",
                    confidence=0.9,
                )
            )
            contact = FakeProvider(
                ContactRecord(
                    email="jane@example.com",
                    source="hunter_io",
                    confidence=0.85,
                )
            )
            waterfall = WaterfallEnrichment(
                [identity, contact],
                EnrichmentCache(temp_path / "cache.sqlite3"),
                temp_path / "enrichment.log",
            )

            try:
                record = waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            self.assertEqual(record.name, "Jane Smith")
            self.assertEqual(record.email, "jane@example.com")
            self.assertEqual(identity.calls, 1)
            self.assertEqual(contact.calls, 1)

            events = [
                json.loads(line)
                for line in (temp_path / "enrichment.log").read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn(
                "waterfall_continued_for_contact_route",
                {event.get("event") for event in events},
            )

    def test_waterfall_respects_max_provider_calls_budget(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            providers = [FakeProvider(), FakeProvider(), FakeProvider()]
            waterfall = WaterfallEnrichment(
                providers,
                EnrichmentCache(temp_path / "cache.sqlite3"),
                temp_path / "enrichment.log",
                max_provider_calls=2,
            )

            try:
                record = waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            self.assertIsNone(record)
            self.assertEqual([provider.calls for provider in providers], [1, 1, 0])
            events = [
                json.loads(line)
                for line in (temp_path / "enrichment.log").read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("max_provider_calls", {event.get("stop_reason") for event in events})

    def test_waterfall_latency_ceiling_stops_before_next_provider(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            clock = AdvancingClock()
            slow = SlowProvider(clock, seconds=20)
            never_called = FakeProvider()
            waterfall = WaterfallEnrichment(
                [slow, never_called],
                EnrichmentCache(temp_path / "cache.sqlite3"),
                temp_path / "enrichment.log",
                max_latency_seconds=15,
                clock=clock,
            )

            try:
                record = waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            self.assertIsNone(record)
            self.assertEqual(slow.calls, 1)
            self.assertEqual(never_called.calls, 0)
            events = [
                json.loads(line)
                for line in (temp_path / "enrichment.log").read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("max_latency_seconds", {event.get("stop_reason") for event in events})

    def test_same_company_name_different_domain_uses_separate_cache_entries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            cache = EnrichmentCache(Path(temp_dir) / "cache.sqlite3")
            cache.set(
                "Acme",
                ContactRecord(email="one@example.com", source="domain_one", confidence=0.8),
                "www.example.com",
            )
            cache.set(
                "Acme",
                ContactRecord(email="two@example.net", source="domain_two", confidence=0.8),
                "https://example.net/about",
            )

            first = cache.get(" ACME ", "example.com")
            second = cache.get("acme", "example.net")

            self.assertEqual(first.email, "one@example.com")
            self.assertEqual(second.email, "two@example.net")

            cache.invalidate("Acme", "example.com")

            self.assertIsNone(cache.get("Acme", "example.com"))
            self.assertEqual(cache.get("Acme", "example.net").email, "two@example.net")

    def test_expired_not_found_allows_re_enrichment(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache_path = temp_path / "cache.sqlite3"
            cache = EnrichmentCache(
                cache_path,
                ttl=timedelta(days=30),
                not_found_ttl=timedelta(days=7),
            )
            cache.set_not_found("Acme", "example.com")
            stale_time = (datetime.now(UTC) - timedelta(days=8)).isoformat()
            with closing(sqlite3.connect(cache_path)) as connection:
                with connection:
                    connection.execute(
                        """
                        UPDATE enrichment_cache
                        SET cached_at = ?
                        WHERE company_name = ? AND domain = ?
                        """,
                        (stale_time, "acme", "example.com"),
                    )
            provider = FakeProvider(
                ContactRecord(email="fresh@example.com", source="fresh", confidence=0.8)
            )
            waterfall = WaterfallEnrichment(
                [provider],
                cache,
                temp_path / "enrichment.log",
            )

            try:
                record = waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            self.assertEqual(record.email, "fresh@example.com")
            self.assertEqual(provider.calls, 1)

    def test_cache_migration_script_is_idempotent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache_path = temp_path / "cache.sqlite3"
            report_path = temp_path / "migration_report.csv"
            payload = {
                "email": "info@example.com",
                "source": "legacy",
                "confidence": 0.8,
                "raw": {"best_url": "https://www.example.com/contact"},
            }
            with closing(sqlite3.connect(cache_path)) as connection:
                with connection:
                    connection.execute(
                        """
                        CREATE TABLE enrichment_cache (
                            company_name TEXT PRIMARY KEY,
                            record_json TEXT NOT NULL,
                            source TEXT,
                            cached_at TIMESTAMP NOT NULL
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO enrichment_cache (
                            company_name, record_json, source, cached_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        ("acme", json.dumps(payload), "legacy", datetime.now(UTC).isoformat()),
                    )

            migrate_cache(cache_path, report_path)
            migrate_cache(cache_path, report_path)

            with closing(sqlite3.connect(cache_path)) as connection:
                columns = connection.execute("PRAGMA table_info(enrichment_cache)").fetchall()
                primary_key_columns = [
                    row[1] for row in sorted(columns, key=lambda item: item[5]) if row[5]
                ]
                rows = connection.execute(
                    "SELECT company_name, domain, source FROM enrichment_cache"
                ).fetchall()

            self.assertEqual(primary_key_columns, ["company_name", "domain"])
            self.assertEqual(rows, [("acme", "example.com", "legacy")])
            self.assertIn("company_name,domain,status", report_path.read_text(encoding="utf-8"))

    def test_waterfall_logs_provider_errors_as_jsonl(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache = EnrichmentCache(temp_path / "cache.sqlite3")
            log_path = temp_path / "enrichment.log"
            fallback = FakeProvider(
                ContactRecord(name="Jane Smith", source="fallback", confidence=0.6)
            )
            waterfall = WaterfallEnrichment(
                [FakeProvider(raises=True), fallback],
                cache,
                log_path,
            )
            try:
                self.assertIsNotNone(waterfall.enrich("Acme"))
            finally:
                waterfall.close()

            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("provider_error", {event["event"] for event in events})
            self.assertIn("provider_hit", {event["event"] for event in events})

    def test_waterfall_merges_supplemental_email_and_phone(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache = EnrichmentCache(temp_path / "cache.sqlite3")
            log_path = temp_path / "enrichment.log"
            identity = FakeProvider(
                ContactRecord(
                    name="TRAFFORD, Graham James",
                    title="Director",
                    company="BACHY SOLETANCHE LIMITED",
                    source="companies_house",
                    confidence=0.7,
                    raw={"company_number": "00752082"},
                )
            )
            website = FakeProvider(
                ContactRecord(
                    email="info@bacsol.co.uk",
                    phone="01704 123456",
                    source="website_scrape",
                    confidence=0.6,
                    raw={"best_url": "https://bacsol.co.uk/contact"},
                )
            )
            pattern = FakePersonProvider(
                ContactRecord(
                    email="graham.trafford@bacsol.co.uk",
                    source="pattern_guess",
                    confidence=0.3,
                )
            )
            waterfall = WaterfallEnrichment(
                [identity, website, pattern],
                cache,
                log_path,
                enrich_full=True,
            )

            try:
                record = waterfall.enrich("Bachy Soletanche", "bacsol.co.uk")
            finally:
                waterfall.close()

            self.assertEqual(record.name, "TRAFFORD, Graham James")
            self.assertEqual(record.email, "info@bacsol.co.uk")
            self.assertEqual(record.phone, "01704 123456")
            self.assertEqual(
                record.source,
                "companies_house+website_scrape",
            )
            self.assertEqual(
                record.raw["supplements"][0]["filled_fields"],
                ["email", "phone"],
            )
            self.assertEqual(record.raw["field_provenance"]["name"]["provider"], "FakeProvider")
            self.assertEqual(
                record.raw["field_provenance"]["email"]["source"],
                "website_scrape",
            )

    def test_waterfall_merge_never_overwrites_existing_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache = EnrichmentCache(temp_path / "cache.sqlite3")
            log_path = temp_path / "enrichment.log"
            first = FakeProvider(
                ContactRecord(
                    email="original@example.com",
                    phone=None,
                    source="first",
                    confidence=0.4,
                )
            )
            second = FakeProvider(
                ContactRecord(
                    email="replacement@example.com",
                    phone="01276 674940",
                    source="second",
                    confidence=0.4,
                )
            )
            waterfall = WaterfallEnrichment(
                [first, second],
                cache,
                log_path,
                enrich_full=True,
            )

            try:
                record = waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            self.assertEqual(record.email, "original@example.com")
            self.assertEqual(record.phone, "01276 674940")
            self.assertEqual(record.raw["supplements"][0]["filled_fields"], ["phone"])
            self.assertEqual(
                record.raw["supplements"][0]["skipped_existing_fields"],
                ["email"],
            )

    def test_waterfall_upgrades_weak_contact_route_with_stronger_hunter_route(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache = EnrichmentCache(temp_path / "cache.sqlite3")
            log_path = temp_path / "enrichment.log"
            website = FakeProvider(
                ContactRecord(
                    name="Enquiries Team",
                    title="Office",
                    email="info@example.com",
                    source="website_scrape",
                    confidence=0.6,
                )
            )
            hunter = FakeProvider(
                ContactRecord(
                    name="Jane Smith",
                    title="Commercial Director",
                    email="jane.smith@example.com",
                    source="hunter_io",
                    confidence=0.92,
                )
            )
            waterfall = WaterfallEnrichment(
                [website, hunter],
                cache,
                log_path,
                enrich_full=True,
            )

            try:
                record = waterfall.enrich("Acme", "example.com")
            finally:
                waterfall.close()

            self.assertEqual(record.email, "jane.smith@example.com")
            self.assertEqual(record.name, "Jane Smith")
            self.assertEqual(record.title, "Commercial Director")
            self.assertEqual(record.source, "website_scrape+hunter_io")
            self.assertEqual(
                record.raw["supplements"][0]["upgraded_fields"],
                ["name", "title", "email"],
            )
            self.assertEqual(
                record.raw["field_provenance"]["email"]["source"],
                "hunter_io",
            )
            self.assertEqual(record.raw["field_provenance"]["email"]["confidence"], 0.92)


if __name__ == "__main__":
    unittest.main()
