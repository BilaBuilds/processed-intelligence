from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import urlparse

from enrichment.models import ContactRecord
from enrichment.models.evidence import EvidenceItem
from enrichment.providers.base import Provider
from enrichment.verify import get_mx_records, smtp_verify


NAME_PART_PATTERN = re.compile(r"[^a-z0-9]")


class PatternGuessProvider(Provider):
    input_kind = "person"

    def __init__(
        self,
        smtp_enabled: bool = True,
        smtp_timeout: float = 10.0,
    ) -> None:
        self.smtp_enabled = smtp_enabled
        self.smtp_timeout = smtp_timeout

    def enrich(
        self,
        company_name: str,
        domain: str | None,
    ) -> ContactRecord | None:
        if not domain:
            return None

        domain = self._normalize_domain(domain)
        first_name, last_name = self._parse_name(company_name)
        if not first_name or not last_name:
            return None

        mx_records = get_mx_records(domain)
        if not mx_records:
            return None

        first_inconclusive: str | None = None
        for email in self._patterns(first_name, last_name, domain):
            if not self.smtp_enabled:
                return self._record(
                    company_name,
                    email,
                    domain,
                    0.3,
                    "smtp_disabled",
                )

            for mx_host in mx_records:
                verified = smtp_verify(email, mx_host, timeout=self.smtp_timeout)
                if verified is True:
                    return self._record(company_name, email, domain, 0.5, "verified")
                if verified is None and first_inconclusive is None:
                    first_inconclusive = email

        if first_inconclusive is not None:
            return self._record(
                company_name,
                first_inconclusive,
                domain,
                0.3,
                "inconclusive",
            )

        return None

    def _parse_name(self, name: str) -> tuple[str | None, str | None]:
        parts = [self._normalize_name_part(part) for part in name.split()]
        parts = [part for part in parts if part]
        if len(parts) < 2:
            return None, None
        return parts[0], parts[-1]

    def _normalize_name_part(self, value: str) -> str:
        return NAME_PART_PATTERN.sub("", value.casefold())

    def _patterns(
        self,
        first_name: str,
        last_name: str,
        domain: str,
    ) -> Iterable[str]:
        candidates = (
            f"{first_name}.{last_name}@{domain}",
            f"{first_name}{last_name}@{domain}",
            f"{first_name[0]}.{last_name}@{domain}",
            f"{first_name}@{domain}",
            f"{first_name[0]}{last_name}@{domain}",
        )
        return dict.fromkeys(candidates)

    def _normalize_domain(self, domain: str) -> str:
        parsed = urlparse(domain if "://" in domain else f"//{domain}")
        return (parsed.netloc or parsed.path).strip("/").casefold()

    def _record(
        self,
        name: str,
        email: str,
        domain: str,
        confidence: float,
        verification: str,
    ) -> ContactRecord:
        pattern = email.split("@", maxsplit=1)[0]
        evidence = EvidenceItem(
            entity_type="contact",
            entity_key=f"{' '.join(name.casefold().split())}|{domain.casefold()}",
            field_name="email",
            field_value=email,
            source_provider="pattern_guess",
            source_url=None,
            source_ref=None,
            evidence_type="estimated",
            confidence=confidence,
            collected_at=datetime.now(UTC),
            expires_at=None,
            raw_snippet=None,
            reasoning_note=(
                f"Generated email using pattern '{pattern}' for domain {domain}; "
                f"SMTP verification outcome={verification}."
            ),
            client_safe=False,
        )
        return ContactRecord(
            name=name,
            title=None,
            email=email,
            phone=None,
            company=None,
            source="pattern_guess",
            confidence=confidence,
            raw={
                "domain": domain,
                "verification": verification,
                "evidence": [evidence.model_dump(mode="json")],
            },
        )
