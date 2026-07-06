from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PROVIDER_ORDER = (
    "companies_house",
    "website_scrape",
    "hunter_io",
    "pattern_guess",
)


@dataclass(frozen=True)
class CacheSettings:
    enabled: bool = True
    path: Path = Path("enrichment_cache.sqlite3")
    ttl_days: int = 30
    not_found_ttl_days: int = 7

    @property
    def ttl(self) -> timedelta:
        return timedelta(days=self.ttl_days)

    @property
    def not_found_ttl(self) -> timedelta:
        return timedelta(days=self.not_found_ttl_days)


@dataclass(frozen=True)
class WebsiteScrapeSettings:
    timeout_seconds: float = 5.0
    max_pages: int = 4
    user_agent: str = "enrichment-bot/1.0"


@dataclass(frozen=True)
class CompaniesHouseSettings:
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_seconds: float = 1.0


@dataclass(frozen=True)
class SmtpSettings:
    enabled: bool = False
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class HunterSettings:
    timeout_seconds: float = 15.0
    limit: int = 10


@dataclass(frozen=True)
class WaterfallSettings:
    confidence_threshold: float = 0.7
    enrich_full: bool = False
    max_provider_calls: int = 3
    max_latency_seconds: float = 15.0
    require_contact_route_for_fast_stop: bool = True


@dataclass(frozen=True)
class AppConfig:
    cache: CacheSettings = field(default_factory=CacheSettings)
    providers: tuple[str, ...] = DEFAULT_PROVIDER_ORDER
    website_scrape: WebsiteScrapeSettings = field(default_factory=WebsiteScrapeSettings)
    companies_house: CompaniesHouseSettings = field(
        default_factory=CompaniesHouseSettings
    )
    hunter: HunterSettings = field(default_factory=HunterSettings)
    smtp: SmtpSettings = field(default_factory=SmtpSettings)
    waterfall: WaterfallSettings = field(default_factory=WaterfallSettings)
    log_path: Path = Path("enrichment.log")


def load_app_config(path: Path) -> AppConfig:
    raw = _load_yaml(path)
    cache = raw.get("cache") or {}
    website_scrape = raw.get("website_scrape") or {}
    companies_house = raw.get("companies_house") or {}
    hunter = raw.get("hunter") or {}
    smtp = raw.get("smtp") or {}
    waterfall = raw.get("waterfall") or {}

    return AppConfig(
        cache=CacheSettings(
            enabled=bool(cache.get("enabled", True)),
            path=Path(cache.get("path", "enrichment_cache.sqlite3")),
            ttl_days=int(cache.get("ttl_days", 30)),
            not_found_ttl_days=int(cache.get("not_found_ttl_days", 7)),
        ),
        providers=tuple(raw.get("providers") or DEFAULT_PROVIDER_ORDER),
        website_scrape=WebsiteScrapeSettings(
            timeout_seconds=float(website_scrape.get("timeout_seconds", 5.0)),
            max_pages=int(website_scrape.get("max_pages", 4)),
            user_agent=str(website_scrape.get("user_agent", "enrichment-bot/1.0")),
        ),
        companies_house=CompaniesHouseSettings(
            timeout_seconds=float(companies_house.get("timeout_seconds", 30.0)),
            max_retries=int(companies_house.get("max_retries", 3)),
            backoff_seconds=float(companies_house.get("backoff_seconds", 1.0)),
        ),
        hunter=HunterSettings(
            timeout_seconds=float(hunter.get("timeout_seconds", 15.0)),
            limit=int(hunter.get("limit", 10)),
        ),
        smtp=SmtpSettings(
            enabled=bool(smtp.get("enabled", False)),
            timeout_seconds=float(smtp.get("timeout_seconds", 10.0)),
        ),
        waterfall=WaterfallSettings(
            confidence_threshold=float(waterfall.get("confidence_threshold", 0.7)),
            enrich_full=bool(waterfall.get("enrich_full", False)),
            max_provider_calls=int(waterfall.get("max_provider_calls", 3)),
            max_latency_seconds=float(waterfall.get("max_latency_seconds", 15.0)),
            require_contact_route_for_fast_stop=bool(
                waterfall.get("require_contact_route_for_fast_stop", True)
            ),
        ),
        log_path=Path(raw.get("log_path", "enrichment.log")),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}
