from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from enrichment.models.evidence import EvidenceItem


SOCIAL_HOSTS = {
    "linkedin.com": "linkedin",
    "facebook.com": "facebook",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
    "instagram.com": "instagram",
}


@dataclass(frozen=True)
class SocialSignal:
    platform: str
    url: str
    label: str
    source_url: str
    confidence: float


@dataclass(frozen=True)
class SocialSignalReport:
    domain: str
    signals: list[SocialSignal]
    pages_checked: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "signals": [asdict(signal) for signal in self.signals],
            "evidence": [
                item.model_dump(mode="json")
                for item in self.evidence_items()
            ],
            "pages_checked": self.pages_checked,
            "notes": self.notes,
        }

    def evidence_items(self) -> list[EvidenceItem]:
        collected_at = datetime.now(UTC)
        entity_key = f"company|{self.domain or 'unknown'}"
        return [
            EvidenceItem(
                entity_type="company",
                entity_key=entity_key,
                field_name=f"{signal.platform}_url",
                field_value=signal.url,
                source_provider="social_signals",
                source_url=signal.source_url,
                source_ref=None,
                evidence_type="observed",
                confidence=1.0,
                collected_at=collected_at,
                expires_at=None,
                raw_snippet=signal.label,
                reasoning_note=f"Observed {signal.platform} link on {signal.source_url}.",
                client_safe=True,
            )
            for signal in self.signals
        ]


class SocialSignalScout:
    COMMON_PATHS = ("", "/about", "/contact", "/team", "/leadership")

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 5.0,
        max_pages: int = 5,
        user_agent: str = "hammers-social-signal-scout/1.0",
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_pages = max_pages
        self.user_agent = user_agent

    def discover(self, domain: str | None) -> SocialSignalReport:
        if not domain:
            return SocialSignalReport(
                domain="",
                signals=[],
                pages_checked=[],
                notes=["No domain supplied."],
            )

        base_url = self._base_url(domain)
        robots = self._robots_parser(base_url)
        pages = [urljoin(base_url, path) for path in self.COMMON_PATHS]
        checked: list[str] = []
        notes: list[str] = []
        signals: dict[str, SocialSignal] = {}

        for url in pages[: self.max_pages]:
            if robots is not None and not robots.can_fetch(self.user_agent, url):
                notes.append(f"Skipped by robots.txt: {url}")
                continue
            html = self._fetch(url)
            checked.append(url)
            if not html:
                continue
            for signal in self._signals_from_html(url, html):
                signals.setdefault(f"{signal.platform}:{signal.url}", signal)

        if not signals:
            notes.append("No public social links discovered on checked website pages.")

        return SocialSignalReport(
            domain=self._host(base_url),
            signals=sorted(signals.values(), key=lambda signal: (signal.platform, signal.url)),
            pages_checked=checked,
            notes=notes,
        )

    def _signals_from_html(self, source_url: str, html: str) -> list[SocialSignal]:
        soup = BeautifulSoup(html, "html.parser")
        signals: list[SocialSignal] = []

        for link in soup.select("a[href]"):
            href = link.get("href", "").strip()
            if not href:
                continue
            absolute_url = urljoin(source_url, href)
            platform = self._platform(absolute_url)
            if not platform:
                continue
            label = " ".join(link.get_text(" ", strip=True).split())
            signals.append(
                SocialSignal(
                    platform=platform,
                    url=self._clean_social_url(absolute_url),
                    label=label or platform,
                    source_url=source_url,
                    confidence=0.75,
                )
            )

        return signals

    def _fetch(self, url: str) -> str | None:
        try:
            response = self.session.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            return None

        content_type = response.headers.get("Content-Type", "")
        if content_type and "text/html" not in content_type:
            return None
        return response.text

    def _robots_parser(self, base_url: str) -> RobotFileParser | None:
        robots_url = urljoin(base_url, "/robots.txt")
        try:
            response = self.session.get(
                robots_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
        except requests.RequestException:
            return None
        if response.status_code >= 400:
            return None
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser

    def _base_url(self, domain: str) -> str:
        parsed = urlparse(domain if "://" in domain else f"https://{domain}")
        netloc = parsed.netloc or parsed.path
        return f"{parsed.scheme or 'https'}://{netloc}".rstrip("/")

    def _host(self, url: str) -> str:
        return urlparse(url).netloc.casefold().removeprefix("www.")

    def _platform(self, url: str) -> str | None:
        host = self._host(url)
        for social_host, platform in SOCIAL_HOSTS.items():
            if host == social_host or host.endswith(f".{social_host}"):
                return platform
        return None

    def _clean_social_url(self, url: str) -> str:
        parsed = urlparse(url)
        path = re.sub(r"/+$", "", parsed.path)
        return parsed._replace(query="", fragment="", path=path).geturl()
