from __future__ import annotations

from abc import ABC, abstractmethod

from enrichment.models import ContactRecord


class Provider(ABC):
    input_kind = "company"

    @abstractmethod
    def enrich(
        self,
        company_name: str,
        domain: str | None,
    ) -> ContactRecord | None:
        raise NotImplementedError
