from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from enrichment.models import ContactRecord
from enrichment.models.evidence import EvidenceItem
from enrichment.providers.base import Provider


class CompaniesHouseProvider(Provider):
    BASE_URL = "https://api.company-information.service.gov.uk"
    AUTO_ACCEPT_THRESHOLD = 0.8
    LOW_CONFIDENCE_CAP = 0.49
    CONSTRUCTION_SIC_PREFIXES = (
        "41",
        "42",
        "43",
        "711",
        "74902",
        "081",
        "089",
        "236",
        "239",
    )

    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("COMPANIES_HOUSE_API_KEY")
        if not self.api_key:
            raise ValueError("COMPANIES_HOUSE_API_KEY is required")

        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.timeout = timeout

    def enrich(
        self,
        company_name: str,
        domain: str | None,
    ) -> ContactRecord | None:
        selected = self._find_company(company_name, domain)
        if selected is None:
            return None

        company = selected.company
        company_number = company.get("company_number")
        if not company_number:
            return None

        director = self._find_senior_director(company_number)
        if director is None:
            return None

        company_profile = selected.profile or self._company_profile(company_number)
        officer_appointments = self._officer_appointments(director)
        needs_review = selected.score < self.AUTO_ACCEPT_THRESHOLD
        confidence = 0.7 if not needs_review else min(
            round(selected.score, 3),
            self.LOW_CONFIDENCE_CAP,
        )

        evidence = self._evidence_items(
            company_name,
            domain,
            company,
            company_profile or {},
            director,
            selected,
            needs_review,
        )

        return ContactRecord(
            name=director.get("name"),
            title="Director",
            email=None,
            phone=None,
            company=company.get("title") or company_name,
            source="companies_house",
            confidence=confidence,
            raw={
                "company": company,
                "company_profile": company_profile,
                "officer": director,
                "officer_appointments": officer_appointments,
                "domain": domain,
                "candidate_match": selected.to_dict(),
                "candidate_matches": selected.all_matches,
                "needs_review": needs_review,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
        )

    def _find_company(
        self,
        company_name: str,
        domain: str | None,
    ) -> "CandidateMatch | None":
        response = self._get(
            "/search/companies",
            params={
                "q": company_name,
                "items_per_page": 5,
            },
        )
        items = response.get("items", [])
        if not items:
            return None

        matches = [
            self._score_candidate(company_name, domain, item)
            for item in items[:5]
        ]
        matches.sort(key=lambda match: match.score, reverse=True)
        selected = matches[0]
        selected.all_matches = [match.to_dict() for match in matches]
        return selected

    def _find_senior_director(self, company_number: str) -> dict[str, Any] | None:
        officers = self._all_officers(company_number)
        directors = [
            officer
            for officer in officers
            if self._is_current_director(officer)
        ]
        if not directors:
            return None

        return sorted(directors, key=self._appointed_on_sort_key)[0]

    def _all_officers(self, company_number: str) -> list[dict[str, Any]]:
        officers: list[dict[str, Any]] = []
        start_index = 0
        items_per_page = 100
        while True:
            response = self._get(
                f"/company/{company_number}/officers",
                params={
                    "items_per_page": items_per_page,
                    "start_index": start_index,
                    "order_by": "appointed_on",
                },
            )
            items = response.get("items", [])
            if not isinstance(items, list) or not items:
                break
            officers.extend(items)
            total_results = int(response.get("total_results") or len(officers))
            start_index += len(items)
            if start_index >= total_results or len(items) < items_per_page:
                break
        return officers

    def _company_profile(self, company_number: str) -> dict[str, Any] | None:
        return self._get_optional(f"/company/{company_number}")

    def _officer_appointments(self, officer: dict[str, Any]) -> dict[str, Any] | None:
        appointments_path = (
            officer.get("links", {})
            .get("officer", {})
            .get("appointments")
        )
        if not appointments_path:
            return None

        return self._get_optional(
            appointments_path,
            params={"items_per_page": 100},
        )

    def _is_current_director(self, officer: dict[str, Any]) -> bool:
        return (
            officer.get("officer_role") == "director"
            and officer.get("resigned_on") is None
        )

    def _score_candidate(
        self,
        company_name: str,
        domain: str | None,
        company: dict[str, Any],
    ) -> "CandidateMatch":
        company_number = company.get("company_number")
        profile = self._company_profile(company_number) if company_number else None
        profile = profile or {}
        title = str(company.get("title") or profile.get("company_name") or "")
        sic_codes = [
            str(code)
            for code in profile.get("sic_codes", [])
            if code is not None
        ]
        name_similarity = self._name_similarity(company_name, title)
        domain_similarity = self._domain_similarity(domain, title)
        postcode_match = self._postcode_match(company, profile)
        sic_relevant = self._has_construction_sic(sic_codes)
        sic_known = bool(sic_codes)
        sic_mismatch = sic_known and not sic_relevant

        score = (0.45 * name_similarity) + (0.35 * domain_similarity)
        if sic_relevant:
            score += 0.25
        if postcode_match:
            score += 0.1
        if sic_mismatch:
            score = min(score, 0.45)

        reasons = [
            f"name_similarity={name_similarity:.3f}",
            f"domain_similarity={domain_similarity:.3f}",
        ]
        if sic_relevant:
            reasons.append("construction_sic_match")
        elif sic_mismatch:
            reasons.append("sic_mismatch_rejected_for_auto_accept")
        else:
            reasons.append("sic_unknown")
        if postcode_match:
            reasons.append("postcode_match")

        return CandidateMatch(
            company=company,
            profile=profile,
            score=round(min(score, 1.0), 3),
            reasons=reasons,
            sic_codes=sic_codes,
            sic_mismatch=sic_mismatch,
        )

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}{path}"

        for attempt in range(self.max_retries + 1):
            response = self.session.get(
                url,
                auth=(self.api_key, ""),
                params=params,
                timeout=self.timeout,
            )

            if response.status_code != 429:
                response.raise_for_status()
                return response.json()

            if attempt == self.max_retries:
                response.raise_for_status()

            time.sleep(self._retry_delay(response, attempt))

        raise RuntimeError("unreachable retry state")

    def _get_optional(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            return self._get(path, params=params)
        except requests.RequestException:
            return None

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        return self.backoff_seconds * (2**attempt)

    def _appointed_on_sort_key(self, officer: dict[str, Any]) -> tuple[date, str]:
        appointed_on = officer.get("appointed_on")
        if not appointed_on:
            return date.max, officer.get("name", "")

        try:
            return date.fromisoformat(appointed_on), officer.get("name", "")
        except ValueError:
            return date.max, officer.get("name", "")

    def _name_similarity(self, left: str | None, right: str | None) -> float:
        left_normalized = self._normalize_company_text(left)
        right_normalized = self._normalize_company_text(right)
        if not left_normalized or not right_normalized:
            return 0.0
        return SequenceMatcher(None, left_normalized, right_normalized).ratio()

    def _domain_similarity(self, domain: str | None, company_title: str | None) -> float:
        domain_name = self._domain_company_name(domain)
        if not domain_name:
            return 0.0
        return self._name_similarity(domain_name, company_title)

    def _domain_company_name(self, domain: str | None) -> str:
        if not domain:
            return ""
        value = str(domain).strip().casefold()
        if not value:
            return ""
        if "://" not in value:
            value = f"//{value}"
        parsed = urlparse(value)
        host = parsed.netloc or parsed.path
        host = host.split("/", maxsplit=1)[0].split(":", maxsplit=1)[0]
        host = host.removeprefix("www.")
        parts = host.split(".")
        if len(parts) >= 3 and parts[-2] in {"co", "org", "gov", "ac"}:
            stem = ".".join(parts[:-2])
        elif len(parts) >= 2:
            stem = ".".join(parts[:-1])
        else:
            stem = host
        return stem.replace(".", " ")

    def _normalize_company_text(self, value: str | None) -> str:
        if not value:
            return ""
        normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold())
        suffixes = {
            "ltd",
            "limited",
            "plc",
            "llp",
            "uk",
            "group",
            "company",
            "co",
        }
        tokens = [
            token
            for token in normalized.split()
            if token and token not in suffixes
        ]
        return " ".join(tokens)

    def _postcode_match(
        self,
        company: dict[str, Any],
        profile: dict[str, Any],
    ) -> bool:
        search_postcode = self._extract_postcode(company.get("address"))
        profile_postcode = self._extract_postcode(profile.get("registered_office_address"))
        return bool(search_postcode and profile_postcode and search_postcode == profile_postcode)

    def _extract_postcode(self, value: Any) -> str:
        if not value:
            return ""
        if isinstance(value, dict):
            pieces = [
                str(value.get(key) or "")
                for key in ("postal_code", "postcode", "address_line_1", "locality", "region")
            ]
            text = " ".join(pieces)
        else:
            text = str(value)
        match = re.search(
            r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",
            text.upper(),
        )
        return re.sub(r"\s+", "", match.group(0)) if match else ""

    def _has_construction_sic(self, sic_codes: list[str]) -> bool:
        return any(
            code.startswith(prefix)
            for code in sic_codes
            for prefix in self.CONSTRUCTION_SIC_PREFIXES
        )

    def _evidence_items(
        self,
        input_company_name: str,
        domain: str | None,
        company: dict[str, Any],
        profile: dict[str, Any],
        director: dict[str, Any],
        selected: "CandidateMatch",
        needs_review: bool,
    ) -> list[EvidenceItem]:
        collected_at = datetime.now(UTC)
        entity_key = f"{' '.join(input_company_name.casefold().split())}|{(domain or 'unknown').casefold()}"
        company_number = company.get("company_number")
        registered_name = company.get("title") or profile.get("company_name")
        fields: list[tuple[str, Any, str, float, str | None]] = [
            ("company_number", company_number, "company", 0.95, "Companies House company number from search result."),
            ("registered_name", registered_name, "company", 0.95, "Companies House registered company name."),
            ("sic_codes", profile.get("sic_codes"), "company", 0.95, "Companies House SIC codes from company profile."),
            (
                "registered_address",
                profile.get("registered_office_address"),
                "company",
                0.9,
                "Companies House registered office address from company profile.",
            ),
            (
                "director_name",
                director.get("name"),
                "contact",
                selected.score,
                (
                    "Selected active director by earliest appointed_on="
                    f"{director.get('appointed_on')}; match_score={selected.score}; "
                    f"needs_review={str(needs_review).lower()}."
                ),
            ),
            (
                "officers",
                [director],
                "contact",
                selected.score,
                (
                    "Officer list filtered to active directors and sorted by "
                    f"appointed_on ascending; selected {director.get('name')}."
                ),
            ),
        ]
        evidence: list[EvidenceItem] = []
        for field_name, value, entity_type, confidence, note in fields:
            if value is None:
                continue
            evidence.append(
                EvidenceItem(
                    entity_type=entity_type,  # type: ignore[arg-type]
                    entity_key=entity_key,
                    field_name=field_name,
                    field_value=value,
                    source_provider="companies_house",
                    source_url=(
                        f"{self.BASE_URL}/company/{company_number}"
                        if company_number
                        else self.BASE_URL
                    ),
                    source_ref=str(company_number) if company_number else None,
                    evidence_type="observed",
                    confidence=round(float(confidence), 3),
                    collected_at=collected_at,
                    expires_at=None,
                    raw_snippet=json_safe_snippet(value),
                    reasoning_note=note,
                    client_safe=confidence >= self.AUTO_ACCEPT_THRESHOLD and not needs_review,
                )
            )
        return evidence


@dataclass
class CandidateMatch:
    company: dict[str, Any]
    profile: dict[str, Any]
    score: float
    reasons: list[str]
    sic_codes: list[str]
    sic_mismatch: bool
    all_matches: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_number": self.company.get("company_number"),
            "title": self.company.get("title"),
            "score": self.score,
            "reasons": self.reasons,
            "sic_codes": self.sic_codes,
            "sic_mismatch": self.sic_mismatch,
        }


def json_safe_snippet(value: Any) -> str:
    text = str(value)
    return text[:500]
