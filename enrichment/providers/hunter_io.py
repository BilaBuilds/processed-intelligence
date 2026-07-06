from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from enrichment.models import ContactRecord
from enrichment.models.evidence import EvidenceItem
from enrichment.providers.base import Provider


class HunterProvider(Provider):
    BASE_URL = "https://api.hunter.io/v2"

    def __init__(
        self,
        api_key: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 15.0,
        limit: int = 10,
        load_env: bool = True,
    ) -> None:
        if load_env:
            load_dotenv()
        self.api_key = api_key or os.getenv("HUNTER_API_KEY")
        if not self.api_key:
            raise ValueError("HUNTER_API_KEY is required")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.limit = limit

    def enrich(
        self,
        company_name: str,
        domain: str | None,
    ) -> ContactRecord | None:
        if not domain:
            return None
        normalized_domain = self._normalize_domain(domain)
        payload = self._domain_search(normalized_domain)
        data = payload.get("data") if isinstance(payload, dict) else {}
        emails = data.get("emails", []) if isinstance(data, dict) else []
        if not isinstance(emails, list) or not emails:
            return None

        candidate = self._best_email(emails)
        if not candidate:
            return None

        email = candidate.get("value")
        if not email:
            return None
        first_name = str(candidate.get("first_name") or "").strip()
        last_name = str(candidate.get("last_name") or "").strip()
        name = " ".join(part for part in (first_name, last_name) if part) or None
        title = candidate.get("position")
        confidence = self._confidence(candidate)
        sources = candidate.get("sources") if isinstance(candidate.get("sources"), list) else []
        source_url = self._source_url(sources)
        evidence = self._evidence_items(
            company_name,
            normalized_domain,
            email,
            name,
            title,
            confidence,
            candidate,
            source_url,
        )

        return ContactRecord(
            name=name,
            title=str(title) if title else None,
            email=str(email).casefold(),
            phone=None,
            company=company_name,
            source="hunter_io",
            confidence=confidence,
            raw={
                "domain": normalized_domain,
                "hunter": {
                    "organization": data.get("organization") if isinstance(data, dict) else None,
                    "pattern": data.get("pattern") if isinstance(data, dict) else None,
                    "accept_all": data.get("accept_all") if isinstance(data, dict) else None,
                    "selected_email": candidate,
                },
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
        )

    def _domain_search(self, domain: str) -> dict[str, Any]:
        return self._get(
            "/domain-search",
            params={
                "domain": domain,
                "limit": self.limit,
            },
        )

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged_params = dict(params or {})
        merged_params["api_key"] = self.api_key
        response = self.session.get(
            f"{self.BASE_URL}{path}",
            params=merged_params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _best_email(self, emails: list[dict[str, Any]]) -> dict[str, Any] | None:
        valid = [email for email in emails if isinstance(email, dict) and email.get("value")]
        if not valid:
            return None
        return sorted(
            valid,
            key=lambda item: (
                item.get("type") != "personal",
                self._department_rank(item),
                -self._confidence(item),
                not item.get("sources"),
            ),
        )[0]

    def _department_rank(self, item: dict[str, Any]) -> int:
        department = str(item.get("department") or "").casefold()
        position = str(item.get("position") or "").casefold()
        combined = f"{department} {position}"
        if any(word in combined for word in ("director", "commercial", "business development", "preconstruction")):
            return 0
        if any(word in combined for word in ("management", "executive", "operations")):
            return 1
        if item.get("type") == "generic":
            return 3
        return 2

    def _confidence(self, item: dict[str, Any]) -> float:
        raw_score = item.get("confidence") or item.get("score") or 0
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 0.0
        if score > 1:
            score = score / 100
        return round(max(0.0, min(score, 1.0)), 3)

    def _source_url(self, sources: list[Any]) -> str | None:
        for source in sources:
            if isinstance(source, dict) and source.get("uri"):
                return str(source["uri"])
        return None

    def _evidence_items(
        self,
        company_name: str,
        domain: str,
        email: str,
        name: str | None,
        title: Any,
        confidence: float,
        selected_email: dict[str, Any],
        source_url: str | None,
    ) -> list[EvidenceItem]:
        collected_at = datetime.now(UTC)
        entity_key = f"{' '.join(company_name.casefold().split())}|{domain}"
        sources = selected_email.get("sources")
        has_sources = isinstance(sources, list) and bool(sources)
        evidence_type = "observed" if has_sources else "inferred"
        client_safe = has_sources and confidence >= 0.75
        fields = {
            "email": email.casefold(),
            "name": name,
            "title": str(title) if title else None,
            "company": company_name,
        }
        evidence: list[EvidenceItem] = []
        for field_name, value in fields.items():
            if value is None:
                continue
            item_type = "company" if field_name == "company" else "contact"
            evidence.append(
                EvidenceItem(
                    entity_type=item_type,  # type: ignore[arg-type]
                    entity_key=entity_key,
                    field_name=field_name,
                    field_value=value,
                    source_provider="hunter_io",
                    source_url=source_url,
                    source_ref=str(selected_email.get("value") or email),
                    evidence_type=evidence_type,  # type: ignore[arg-type]
                    confidence=confidence,
                    collected_at=collected_at,
                    expires_at=None,
                    raw_snippet=str(selected_email)[:500],
                    reasoning_note=(
                        "Hunter Domain Search selected this email using type="
                        f"{selected_email.get('type')}, department={selected_email.get('department')}, "
                        f"position={selected_email.get('position')}, confidence={confidence}."
                    ),
                    client_safe=client_safe,
                )
            )
        return evidence

    def _normalize_domain(self, domain: str) -> str:
        parsed = urlparse(domain if "://" in domain else f"//{domain}")
        host = parsed.netloc or parsed.path
        return host.split("/", maxsplit=1)[0].removeprefix("www.").casefold()
