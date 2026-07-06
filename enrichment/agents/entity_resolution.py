from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlparse


LEGAL_SUFFIXES = (
    "limited",
    "ltd",
    "plc",
    "llp",
    "limited liability partnership",
)


@dataclass(frozen=True)
class EntityIdentity:
    company_name: str
    normalized_company: str
    domain: str | None
    normalized_domain: str | None
    entity_key: str

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


class EntityResolver:
    def resolve(self, company_name: str, domain: str | None = None) -> EntityIdentity:
        normalized_company = self.normalize_company(company_name)
        normalized_domain = self.normalize_domain(domain)
        key_parts = [normalized_company]
        if normalized_domain:
            key_parts.append(normalized_domain)
        return EntityIdentity(
            company_name=company_name.strip(),
            normalized_company=normalized_company,
            domain=domain.strip() if domain else None,
            normalized_domain=normalized_domain,
            entity_key="|".join(part for part in key_parts if part),
        )

    def normalize_company(self, company_name: str) -> str:
        value = company_name.casefold()
        value = re.sub(r"[^a-z0-9& ]+", " ", value)
        value = " ".join(value.split())
        parts = value.split()
        while parts and parts[-1] in LEGAL_SUFFIXES:
            parts.pop()
        return " ".join(parts) or value

    def normalize_domain(self, domain: str | None) -> str | None:
        if not domain:
            return None
        parsed = urlparse(domain if "://" in domain else f"//{domain}")
        host = (parsed.netloc or parsed.path).casefold().strip("/")
        host = host.removeprefix("www.")
        return host or None
