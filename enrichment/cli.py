from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from enrichment.cache import EnrichmentCache
from enrichment.config import AppConfig, load_app_config
from enrichment.models import ContactRecord
from enrichment.providers import (
    CompaniesHouseProvider,
    HunterProvider,
    PatternGuessProvider,
    Provider,
    WebsiteScrapeProvider,
)
from enrichment.serialization import public_record_payload, record_to_dict
from enrichment.waterfall import WaterfallEnrichment


OUTPUT_FIELDS = (
    "status",
    "company_name",
    "domain",
    "name",
    "title",
    "email",
    "phone",
    "company",
    "source",
    "confidence",
    "raw",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run contact enrichment.")
    parser.add_argument("--company", help="Company or contact name to enrich.")
    parser.add_argument("--domain", help="Company website domain.")
    parser.add_argument(
        "--batch",
        type=Path,
        help="CSV file with company_name and domain columns.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("config.yaml"),
        help="Path to config.yaml.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("enriched_output.csv"),
        help="Output CSV path for batch runs.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Use a temporary cache for this run.",
    )
    return parser


def main() -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    if args.batch and args.company:
        parser.error("--company and --batch are mutually exclusive")
    if not args.batch and not args.company:
        parser.error("provide --company or --batch")

    config = load_app_config(args.config)
    providers = build_providers(config)
    with tempfile.TemporaryDirectory() as temp_dir:
        cache = build_cache(config, no_cache=args.no_cache, temp_dir=Path(temp_dir))
        waterfall = WaterfallEnrichment(
            providers,
            cache,
            config.log_path,
            confidence_threshold=config.waterfall.confidence_threshold,
            enrich_full=config.waterfall.enrich_full,
            max_provider_calls=config.waterfall.max_provider_calls,
            max_latency_seconds=config.waterfall.max_latency_seconds,
            require_contact_route_for_fast_stop=(
                config.waterfall.require_contact_route_for_fast_stop
            ),
        )

        try:
            if args.batch:
                run_batch(waterfall, args.batch, args.output)
                print(f"Wrote {args.output}")
                return 0

            record = waterfall.enrich(args.company, args.domain)
            payload = public_record_payload(record)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0 if record is not None else 1
        finally:
            waterfall.close()


def build_cache(
    config: AppConfig,
    no_cache: bool = False,
    temp_dir: Path | None = None,
) -> EnrichmentCache:
    if no_cache or not config.cache.enabled:
        base_dir = temp_dir or Path(".")
        return EnrichmentCache(
            base_dir / "enrichment_runtime_cache.sqlite3",
            ttl=config.cache.ttl,
            not_found_ttl=config.cache.not_found_ttl,
        )
    return EnrichmentCache(
        config.cache.path,
        ttl=config.cache.ttl,
        not_found_ttl=config.cache.not_found_ttl,
    )


def build_providers(config: AppConfig) -> list[Provider]:
    provider_names = config.providers
    providers: list[Provider] = []

    for provider_name in provider_names:
        provider = build_provider(provider_name, config)
        if provider is not None:
            providers.append(provider)

    return providers


def build_provider(provider_name: str, config: AppConfig) -> Provider | None:
    if provider_name == "companies_house":
        try:
            return CompaniesHouseProvider(
                max_retries=config.companies_house.max_retries,
                backoff_seconds=config.companies_house.backoff_seconds,
                timeout=config.companies_house.timeout_seconds,
            )
        except ValueError:
            print(
                "Skipping companies_house: COMPANIES_HOUSE_API_KEY is not set.",
                file=sys.stderr,
            )
            return None
    if provider_name == "website_scrape":
        return WebsiteScrapeProvider(
            timeout=config.website_scrape.timeout_seconds,
            max_pages=config.website_scrape.max_pages,
            user_agent=config.website_scrape.user_agent,
        )
    if provider_name == "hunter_io":
        try:
            return HunterProvider(
                timeout=config.hunter.timeout_seconds,
                limit=config.hunter.limit,
            )
        except ValueError:
            print(
                "Skipping hunter_io: HUNTER_API_KEY is not set.",
                file=sys.stderr,
            )
            return None
    if provider_name == "pattern_guess":
        return PatternGuessProvider(
            smtp_enabled=config.smtp.enabled,
            smtp_timeout=config.smtp.timeout_seconds,
        )

    raise ValueError(f"Unknown provider: {provider_name}")


def run_batch(
    waterfall: WaterfallEnrichment,
    input_path: Path,
    output_path: Path,
) -> None:
    with input_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        missing_columns = {"company_name", "domain"} - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(
                f"Batch CSV missing columns: {', '.join(sorted(missing_columns))}"
            )

        rows = [
            row_to_output_row(
                row["company_name"],
                row.get("domain") or None,
                waterfall.enrich(row["company_name"], row.get("domain") or None),
            )
            for row in reader
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def row_to_output_row(
    company_name: str,
    domain: str | None,
    record: ContactRecord | None,
) -> dict[str, str | float | None]:
    record_data = record_to_dict(record)
    return {
        "status": "enriched" if record is not None else "not_found",
        "company_name": company_name,
        "domain": domain,
        "name": record_data.get("name"),
        "title": record_data.get("title"),
        "email": record_data.get("email"),
        "phone": record_data.get("phone"),
        "company": record_data.get("company"),
        "source": record_data.get("source"),
        "confidence": record_data.get("confidence"),
        "raw": json.dumps(record_data.get("raw", {}), sort_keys=True),
    }


if __name__ == "__main__":
    raise SystemExit(main())
