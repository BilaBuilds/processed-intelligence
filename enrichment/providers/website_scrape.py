from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from enrichment.models import ContactRecord
from enrichment.models.evidence import EvidenceItem
from enrichment.providers.base import Provider


EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_PATTERN = re.compile(
    r"(?:\+44\s?|0)(?:\d[\d\s().-]{8,}\d)",
    re.IGNORECASE,
)
ROLE_KEYWORDS = (
    "Director",
    "Manager",
    "Head of",
    "Bid",
    "Preconstruction",
)
ROLE_PATTERN = re.compile(
    r"\b(Director|Manager|Head of|Bid|Preconstruction)\b",
    re.IGNORECASE,
)
NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){1,3}$")


@dataclass
class ScrapedCandidate:
    name: str | None
    title: str | None
    email: str | None
    phone: str | None
    url: str
    snippet: str
    rank: int


class WebsiteScrapeProvider(Provider):
    COMMON_PATHS = ("/about", "/team", "/contact", "/leadership")

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 5.0,
        max_pages: int = 4,
        user_agent: str = "enrichment-bot",
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_pages = max_pages
        self.user_agent = user_agent

    def enrich(
        self,
        company_name: str,
        domain: str | None,
    ) -> ContactRecord | None:
        if not domain:
            return None

        base_url = self._base_url(domain)
        urls = self._candidate_urls(base_url)
        robots = self._robots_parser(base_url)
        candidates: list[ScrapedCandidate] = []
        pages: list[dict[str, Any]] = []

        for url in urls[: self.max_pages]:
            if robots is not None and not robots.can_fetch(self.user_agent, url):
                pages.append({"url": url, "skipped": "robots.txt"})
                continue

            html = self._fetch(url)
            if html is None:
                pages.append({"url": url, "fetched": False})
                continue

            page_candidates, emails, phones = self._extract_candidates(url, html)
            candidates.extend(page_candidates)
            pages.append(
                {
                    "url": url,
                    "fetched": True,
                    "emails": emails,
                    "phones": phones,
                    "candidate_count": len(page_candidates),
                }
            )

        best = self._best_candidate(candidates)
        if best is None:
            return None
        evidence = self._evidence_items(company_name, domain, best)

        return ContactRecord(
            name=best.name,
            title=best.title,
            email=best.email,
            phone=best.phone,
            company=company_name,
            source="website_scrape",
            confidence=0.6,
            raw={
                "domain": domain,
                "pages": pages,
                "best_snippet": best.snippet,
                "best_url": best.url,
                "evidence": [
                    item.model_dump(mode="json")
                    for item in evidence
                ],
            },
        )

    def _base_url(self, domain: str) -> str:
        parsed = urlparse(domain if "://" in domain else f"https://{domain}")
        netloc = parsed.netloc or parsed.path
        return f"{parsed.scheme or 'https'}://{netloc}".rstrip("/")

    def _candidate_urls(self, base_url: str) -> list[str]:
        return [base_url, *[urljoin(base_url, path) for path in self.COMMON_PATHS]]

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
        if "text/html" not in content_type and content_type:
            return None

        return response.text

    def _extract_candidates(
        self,
        url: str,
        html: str,
    ) -> tuple[list[ScrapedCandidate], list[str], list[str]]:
        soup = BeautifulSoup(html, "html.parser")
        emails = self._extract_emails(soup)
        phones = self._extract_phones(soup)
        lines = self._text_lines(soup)
        candidates = self._role_candidates(url, lines, emails, phones)

        if not candidates:
            candidates = [
                ScrapedCandidate(
                    name=None,
                    title=None,
                    email=email,
                    phone=phones[0] if phones else None,
                    url=url,
                    snippet=email,
                    rank=len(ROLE_KEYWORDS),
                )
                for email in emails
            ]

        if not candidates and phones:
            candidates = [
                ScrapedCandidate(
                    name=None,
                    title=None,
                    email=None,
                    phone=phones[0],
                    url=url,
                    snippet=phones[0],
                    rank=len(ROLE_KEYWORDS) + 1,
                )
            ]

        return candidates, emails, phones

    def _extract_emails(self, soup: BeautifulSoup) -> list[str]:
        emails: list[str] = []

        for link in soup.select("a[href^='mailto:']"):
            href = link.get("href", "")
            emails.extend(EMAIL_PATTERN.findall(href))

        emails.extend(EMAIL_PATTERN.findall(soup.get_text(" ", strip=True)))
        return sorted(set(email.lower() for email in emails))

    def _extract_phones(self, soup: BeautifulSoup) -> list[str]:
        phones: list[str] = []

        for link in soup.select("a[href^='tel:']"):
            href = link.get("href", "")
            phone = href.removeprefix("tel:").strip()
            if phone:
                phones.append(phone)

        phones.extend(PHONE_PATTERN.findall(soup.get_text(" ", strip=True)))
        return sorted(set(self._normalize_phone(phone) for phone in phones if phone))

    def _text_lines(self, soup: BeautifulSoup) -> list[str]:
        for element in soup(["script", "style", "noscript"]):
            element.decompose()

        return [
            line.strip()
            for line in soup.get_text("\n", strip=True).splitlines()
            if line.strip()
        ]

    def _role_candidates(
        self,
        url: str,
        lines: list[str],
        emails: list[str],
        phones: list[str],
    ) -> list[ScrapedCandidate]:
        candidates: list[ScrapedCandidate] = []

        for index, line in enumerate(lines):
            role_match = ROLE_PATTERN.search(line)
            if role_match is None:
                continue

            role_keyword = self._role_keyword(line)
            snippet_lines = lines[max(0, index - 1) : index + 2]
            snippet = " | ".join(snippet_lines)
            title = self._title_from_line(line, role_keyword)
            name = self._name_from_lines(line, snippet_lines)
            rank = self._keyword_rank(role_keyword)
            candidates.append(
                ScrapedCandidate(
                    name=name,
                    title=title,
                    email=emails[0] if emails else None,
                    phone=phones[0] if phones else None,
                    url=url,
                    snippet=snippet,
                    rank=rank,
                )
            )

        return candidates

    def _role_keyword(self, line: str) -> str:
        normalized_line = line.casefold()
        for keyword in ROLE_KEYWORDS:
            if keyword.casefold() in normalized_line:
                return keyword
        return ROLE_PATTERN.search(line).group(1)

    def _title_from_line(self, line: str, keyword: str) -> str:
        for separator in (" - ", " | ", ": ", ", "):
            if separator in line:
                parts = [part.strip() for part in line.split(separator) if part.strip()]
                for part in parts:
                    if ROLE_PATTERN.search(part) and len(part) <= 80:
                        return part

        if len(line) <= 80:
            return line
        return keyword.title()

    def _name_from_lines(
        self,
        line: str,
        snippet_lines: list[str],
    ) -> str | None:
        before_role = ROLE_PATTERN.split(line, maxsplit=1)[0].strip(" ,-:|")
        if self._looks_like_name(before_role):
            return before_role

        for candidate in snippet_lines:
            clean_candidate = candidate.strip(" ,-:|")
            if self._looks_like_name(clean_candidate):
                return clean_candidate

        return None

    def _looks_like_name(self, value: str) -> bool:
        if not value or len(value) > 60:
            return False
        if ROLE_PATTERN.search(value) or EMAIL_PATTERN.search(value):
            return False
        return bool(NAME_PATTERN.match(value))

    def _keyword_rank(self, keyword: str) -> int:
        normalized = keyword.casefold()
        for index, role_keyword in enumerate(ROLE_KEYWORDS):
            if normalized == role_keyword.casefold():
                return index
        return len(ROLE_KEYWORDS)

    def _best_candidate(
        self,
        candidates: list[ScrapedCandidate],
    ) -> ScrapedCandidate | None:
        if not candidates:
            return None

        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.rank,
                candidate.email is None,
                candidate.phone is None,
                candidate.name is None,
            ),
        )[0]

    def _normalize_phone(self, phone: str) -> str:
        return " ".join(phone.replace("\xa0", " ").split())

    def _evidence_items(
        self,
        company_name: str,
        domain: str,
        candidate: ScrapedCandidate,
    ) -> list[EvidenceItem]:
        collected_at = datetime.now(UTC)
        entity_key = f"{' '.join(company_name.casefold().split())}|{domain.casefold()}"
        fields = {
            "name": candidate.name,
            "title": candidate.title,
            "email": candidate.email,
            "phone": candidate.phone,
            "company": company_name,
        }
        evidence: list[EvidenceItem] = []
        for field_name, value in fields.items():
            if value is None:
                continue
            evidence.append(
                EvidenceItem(
                    entity_type="company" if field_name == "company" else "contact",
                    entity_key=entity_key,
                    field_name=field_name,
                    field_value=value,
                    source_provider="website_scrape",
                    source_url=candidate.url,
                    source_ref=None,
                    evidence_type="observed",
                    confidence=0.6,
                    collected_at=collected_at,
                    expires_at=None,
                    raw_snippet=candidate.snippet,
                    reasoning_note=(
                        f"Found on {candidate.url}; role/email/phone inferred from "
                        f"nearby page context with rank {candidate.rank}."
                    ),
                    client_safe=False,
                )
            )
        return evidence
