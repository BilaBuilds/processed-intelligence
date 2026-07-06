from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from enrichment.cache import EnrichmentCache
from enrichment.models import ContactRecord
from enrichment.models.evidence import EvidenceItem
from enrichment.models.provider_result import ProviderResult
from enrichment.providers.base import Provider
from enrichment.storage.evidence_ledger import EvidenceLedger


class WaterfallEnrichment:
    def __init__(
        self,
        providers: Sequence[Provider],
        cache: EnrichmentCache,
        log_path: str | Path = "enrichment.log",
        confidence_threshold: float = 0.7,
        enrich_full: bool = False,
        max_provider_calls: int = 3,
        max_latency_seconds: float = 15.0,
        require_contact_route_for_fast_stop: bool = True,
        clock: Callable[[], float] | None = None,
        evidence_ledger: EvidenceLedger | None = None,
        run_id: str | None = None,
    ) -> None:
        self.providers = list(providers)
        self.cache = cache
        self.confidence_threshold = confidence_threshold
        self.enrich_full = enrich_full
        self.max_provider_calls = max_provider_calls
        self.max_latency_seconds = max_latency_seconds
        self.require_contact_route_for_fast_stop = require_contact_route_for_fast_stop
        self.clock = clock or time.monotonic
        self.evidence_ledger = evidence_ledger
        self.run_id = run_id
        self.logger = self._build_logger(Path(log_path))

    def enrich(
        self,
        company_name: str,
        domain: str | None = None,
    ) -> ContactRecord | None:
        lead_started_at = self.clock()
        providers_called = 0
        final_provider: str | None = None
        stop_reason: str | None = None

        cached_record = self.cache.get_cached_record(company_name, domain)
        if cached_record is not None:
            if cached_record.source == EnrichmentCache.NOT_FOUND_SOURCE:
                self._log(company_name, domain, "cache_not_found", None)
                self._log_lead_summary(
                    company_name,
                    domain,
                    providers_called,
                    lead_started_at,
                    None,
                    "cache_not_found",
                )
                return None

            self._log(company_name, domain, "cache_hit", cached_record.source)
            self._log_lead_summary(
                company_name,
                domain,
                providers_called,
                lead_started_at,
                cached_record.source,
                "cache_hit",
            )
            return cached_record

        enriched_record: ContactRecord | None = None

        for provider in self.providers:
            elapsed = self.clock() - lead_started_at
            if providers_called >= self.max_provider_calls:
                stop_reason = "max_provider_calls"
                self._log(
                    company_name,
                    domain,
                    "waterfall_stopped",
                    None,
                    {
                        "stop_reason": stop_reason,
                        "providers_called": providers_called,
                        "max_provider_calls": self.max_provider_calls,
                    },
                )
                break
            if elapsed >= self.max_latency_seconds:
                stop_reason = "max_latency_seconds"
                self._log(
                    company_name,
                    domain,
                    "waterfall_stopped",
                    None,
                    {
                        "stop_reason": stop_reason,
                        "total_latency_seconds": round(elapsed, 3),
                        "max_latency_seconds": self.max_latency_seconds,
                    },
                )
                break

            provider_name = provider.__class__.__name__
            input_name = self._provider_input(provider, company_name, enriched_record)
            if input_name is None:
                self._log(company_name, domain, "provider_skipped", provider_name)
                continue

            provider_started_at = self.clock()
            try:
                providers_called += 1
                provider_output = provider.enrich(input_name, domain)
            except Exception as error:
                self._log(
                    company_name,
                    domain,
                    "provider_error",
                    provider_name,
                    {
                        "error": str(error),
                        "error_type": error.__class__.__name__,
                        "provider_latency_seconds": round(
                            self.clock() - provider_started_at,
                            3,
                        ),
                    },
                )
                continue

            provider_latency = self.clock() - provider_started_at
            if provider_output is None:
                self._log(
                    company_name,
                    domain,
                    "provider_miss",
                    provider_name,
                    {"provider_latency_seconds": round(provider_latency, 3)},
                )
                continue

            record, evidence_items = self._normalize_provider_output(
                provider_output,
                provider_name,
                company_name,
                domain,
            )
            evidence_ids = self._store_provider_evidence(
                company_name,
                domain,
                provider_name,
                evidence_items,
            )

            if enriched_record is None:
                enriched_record = record
                self._attach_evidence_ids(enriched_record, evidence_ids)
                final_provider = provider_name
                self._ensure_field_provenance(
                    enriched_record,
                    provider_name,
                    record.source,
                )
                self._log(
                    company_name,
                    domain,
                    "provider_hit",
                    provider_name,
                    {
                        "source": record.source,
                        "confidence": record.confidence,
                        "provider_latency_seconds": round(provider_latency, 3),
                    },
                )
                if (
                    not self.enrich_full
                    and record.confidence >= self.confidence_threshold
                    and self._can_stop_after_hit(record)
                ):
                    stop_reason = "confidence_threshold"
                    self._log(
                        company_name,
                        domain,
                        "waterfall_stopped",
                        provider_name,
                        {
                            "stop_reason": stop_reason,
                            "confidence": record.confidence,
                            "confidence_threshold": self.confidence_threshold,
                        },
                    )
                    break
                if (
                    not self.enrich_full
                    and record.confidence >= self.confidence_threshold
                    and not self._can_stop_after_hit(record)
                ):
                    self._log(
                        company_name,
                        domain,
                        "waterfall_continued_for_contact_route",
                        provider_name,
                        {
                            "confidence": record.confidence,
                            "confidence_threshold": self.confidence_threshold,
                            "has_email": bool(record.email),
                            "has_phone": bool(record.phone),
                        },
                    )
                continue

            merge_result = self._merge_record(enriched_record, record, provider_name)
            self._attach_evidence_ids(enriched_record, evidence_ids)
            self._select_highest_confidence_evidence(enriched_record, evidence_items, evidence_ids)
            if merge_result["filled_fields"]:
                final_provider = self._combine_sources(final_provider, provider_name)
            self._log(
                company_name,
                domain,
                "provider_supplement",
                provider_name,
                {
                    **merge_result,
                    "source": record.source,
                    "confidence": record.confidence,
                    "provider_latency_seconds": round(provider_latency, 3),
                },
            )

        if enriched_record is not None:
            self.cache.set(company_name, enriched_record, domain)
            self._log_lead_summary(
                company_name,
                domain,
                providers_called,
                lead_started_at,
                final_provider or enriched_record.source,
                stop_reason or "completed_with_hit",
            )
            return enriched_record

        self.cache.set_not_found(company_name, domain)
        self._log(company_name, domain, "all_missed", None)
        self._log_lead_summary(
            company_name,
            domain,
            providers_called,
            lead_started_at,
            None,
            stop_reason or "all_missed",
        )
        return None

    def _build_logger(self, log_path: Path) -> logging.Logger:
        logger_name = f"enrichment.waterfall.{log_path.resolve()}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if logger.handlers:
            return logger

        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        return logger

    def _log(
        self,
        company_name: str,
        domain: str | None,
        event: str,
        provider: str | None,
        extra: dict[str, object] | None = None,
    ) -> None:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "company_name": company_name,
            "domain": domain,
            "provider": provider,
        }
        if extra:
            payload.update(extra)

        self.logger.info(json.dumps(payload, sort_keys=True))

    def _log_lead_summary(
        self,
        company_name: str,
        domain: str | None,
        providers_called: int,
        started_at: float,
        final_provider: str | None,
        stop_reason: str,
    ) -> None:
        self._log(
            company_name,
            domain,
            "lead_complete",
            final_provider,
            {
                "total_providers_called": providers_called,
                "total_latency_seconds": round(self.clock() - started_at, 3),
                "final_provider": final_provider,
                "stop_reason": stop_reason,
            },
        )

    def close(self) -> None:
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)

    def _provider_input(
        self,
        provider: Provider,
        company_name: str,
        current_record: ContactRecord | None,
    ) -> str | None:
        if provider.input_kind == "person":
            if current_record is None or not current_record.name:
                return None
            return self._person_name_for_guessing(current_record.name)

        return company_name

    def _can_stop_after_hit(self, record: ContactRecord) -> bool:
        if not self.require_contact_route_for_fast_stop:
            return True
        return bool(record.email or record.phone)

    def _person_name_for_guessing(self, name: str) -> str:
        if "," not in name:
            return name

        surname, remainder = name.split(",", maxsplit=1)
        return f"{remainder.strip()} {surname.strip()}".strip()

    def _merge_record(
        self,
        target: ContactRecord,
        supplement: ContactRecord,
        provider_name: str,
    ) -> dict[str, Any]:
        filled_fields: list[str] = []
        upgraded_fields: list[str] = []
        skipped_existing_fields: list[str] = []
        timestamp = datetime.now(UTC).isoformat()

        for field_name in ("name", "title", "email", "phone", "company"):
            if getattr(target, field_name) is None and getattr(supplement, field_name):
                setattr(target, field_name, getattr(supplement, field_name))
                filled_fields.append(field_name)
                self._record_field_source(
                    target,
                    field_name,
                    provider_name,
                    supplement.source,
                    timestamp,
                    supplement.confidence,
                )
            elif self._should_upgrade_field(target, supplement, field_name):
                setattr(target, field_name, getattr(supplement, field_name))
                upgraded_fields.append(field_name)
                self._record_field_source(
                    target,
                    field_name,
                    provider_name,
                    supplement.source,
                    timestamp,
                    supplement.confidence,
                    replace=True,
                )
            elif getattr(target, field_name) is not None and getattr(supplement, field_name):
                skipped_existing_fields.append(field_name)

        if filled_fields or upgraded_fields:
            target.confidence = max(target.confidence, supplement.confidence)
            target.source = self._combine_sources(target.source, supplement.source)
        self._attach_supplement(
            target,
            supplement,
            provider_name,
            filled_fields,
            upgraded_fields,
            skipped_existing_fields,
            timestamp,
        )
        return {
            "filled_fields": filled_fields,
            "upgraded_fields": upgraded_fields,
            "skipped_existing_fields": skipped_existing_fields,
            "merge_timestamp": timestamp,
        }

    def _should_upgrade_field(
        self,
        target: ContactRecord,
        supplement: ContactRecord,
        field_name: str,
    ) -> bool:
        if field_name == "company":
            return False
        current_value = getattr(target, field_name)
        new_value = getattr(supplement, field_name)
        if current_value is None or not new_value or current_value == new_value:
            return False
        existing_confidence = self._field_confidence(target, field_name)
        if supplement.confidence <= existing_confidence:
            return False
        if field_name in {"email", "phone"}:
            return True
        if field_name in {"name", "title"} and supplement.email and supplement.source == "hunter_io":
            return True
        return False

    def _field_confidence(self, record: ContactRecord, field_name: str) -> float:
        provenance = record.raw.get("field_provenance") if isinstance(record.raw, dict) else {}
        if isinstance(provenance, dict):
            field = provenance.get(field_name)
            if isinstance(field, dict):
                try:
                    return float(field.get("confidence", record.confidence))
                except (TypeError, ValueError):
                    return record.confidence
        return record.confidence

    def _combine_sources(
        self,
        existing_source: str | None,
        new_source: str | None,
    ) -> str | None:
        sources = [
            source
            for source in (existing_source or "").split("+")
            if source
        ]
        if new_source and new_source not in sources:
            sources.append(new_source)
        return "+".join(sources) if sources else new_source

    def _attach_supplement(
        self,
        target: ContactRecord,
        supplement: ContactRecord,
        provider_name: str,
        filled_fields: list[str],
        upgraded_fields: list[str],
        skipped_existing_fields: list[str],
        timestamp: str,
    ) -> None:
        supplements = target.raw.setdefault("supplements", [])
        if isinstance(supplements, list):
            supplements.append(
                {
                    "provider": provider_name,
                    "source": supplement.source,
                    "confidence": supplement.confidence,
                    "filled_fields": filled_fields,
                    "upgraded_fields": upgraded_fields,
                    "skipped_existing_fields": skipped_existing_fields,
                    "timestamp": timestamp,
                    "record": self._record_payload(supplement),
                }
            )

    def _ensure_field_provenance(
        self,
        record: ContactRecord,
        provider_name: str,
        source: str | None,
    ) -> None:
        timestamp = datetime.now(UTC).isoformat()
        for field_name in ("name", "title", "email", "phone", "company"):
            if getattr(record, field_name):
                self._record_field_source(
                    record,
                    field_name,
                    provider_name,
                    source,
                    timestamp,
                    record.confidence,
                )

    def _record_field_source(
        self,
        record: ContactRecord,
        field_name: str,
        provider_name: str,
        source: str | None,
        timestamp: str,
        confidence: float,
        replace: bool = False,
    ) -> None:
        provenance = record.raw.setdefault("field_provenance", {})
        if isinstance(provenance, dict) and (replace or field_name not in provenance):
            provenance[field_name] = {
                "provider": provider_name,
                "source": source,
                "timestamp": timestamp,
                "confidence": confidence,
            }

    def _record_payload(self, record: ContactRecord) -> dict[str, Any]:
        return {
            "name": record.name,
            "title": record.title,
            "email": record.email,
            "phone": record.phone,
            "company": record.company,
            "source": record.source,
            "confidence": record.confidence,
            "raw": record.raw,
        }

    def _normalize_provider_output(
        self,
        output: ContactRecord | ProviderResult,
        provider_name: str,
        company_name: str,
        domain: str | None,
    ) -> tuple[ContactRecord, list[EvidenceItem]]:
        if isinstance(output, ProviderResult):
            record = ContactRecord(
                name=output.fields.get("name"),
                title=output.fields.get("title"),
                email=output.fields.get("email"),
                phone=output.fields.get("phone"),
                company=output.fields.get("company") or company_name,
                source=output.provider,
                confidence=output.confidence,
                raw={
                    "domain": domain,
                    "entity_key": self._entity_key(company_name, domain),
                    "provider_reasoning": output.reasoning,
                },
            )
            return record, output.evidence

        evidence_payload = output.raw.get("evidence") if isinstance(output.raw, dict) else None
        if isinstance(evidence_payload, list):
            evidence = [
                EvidenceItem.model_validate(item)
                for item in evidence_payload
            ]
        else:
            evidence = self._compatibility_evidence(
                output,
                provider_name,
                company_name,
                domain,
            )
        output.raw.setdefault("entity_key", self._entity_key(company_name, domain))
        return output, evidence

    def _compatibility_evidence(
        self,
        record: ContactRecord,
        provider_name: str,
        company_name: str,
        domain: str | None,
    ) -> list[EvidenceItem]:
        source_provider = record.source or self._provider_source_name(provider_name)
        entity_key = self._entity_key(company_name, domain)
        collected_at = datetime.now(UTC)
        evidence: list[EvidenceItem] = []
        provenance = record.raw.get("field_provenance") if isinstance(record.raw, dict) else {}
        for field_name in ("name", "title", "email", "phone", "company"):
            value = getattr(record, field_name)
            if value is None:
                continue
            field_provenance = provenance.get(field_name, {}) if isinstance(provenance, dict) else {}
            field_source = field_provenance.get("source") or source_provider
            confidence = self._field_confidence(record, field_name)
            evidence_type = "estimated" if field_source == "pattern_guess" else "observed"
            client_safe = evidence_type == "observed" and confidence >= 0.75
            evidence.append(
                EvidenceItem(
                    entity_type="company" if field_name == "company" else "contact",
                    entity_key=entity_key,
                    field_name=field_name,
                    field_value=value,
                    source_provider=str(field_source),
                    source_url=record.raw.get("best_url") if isinstance(record.raw, dict) else None,
                    source_ref=None,
                    evidence_type=evidence_type,
                    confidence=confidence,
                    collected_at=collected_at,
                    expires_at=None,
                    raw_snippet=record.raw.get("best_snippet") if isinstance(record.raw, dict) else None,
                    reasoning_note=(
                        f"Compatibility evidence synthesized from {provider_name}; "
                        f"field provenance source={field_source}."
                    ),
                    client_safe=client_safe,
                    run_id=self.run_id,
                )
            )
        return evidence

    def _store_provider_evidence(
        self,
        company_name: str,
        domain: str | None,
        provider_name: str,
        evidence_items: list[EvidenceItem],
    ) -> dict[str, str]:
        if self.evidence_ledger is None:
            return {}
        evidence_ids: dict[str, str] = {}
        for evidence in evidence_items:
            existing = self.evidence_ledger.get_by_field(
                evidence.entity_key,
                evidence.field_name,
            )
            conflict = any(
                item.field_value != evidence.field_value
                for item in existing
            )
            if conflict:
                evidence = evidence.model_copy(update={"conflict": True})
                self.evidence_ledger.mark_conflicts(evidence.entity_key, evidence.field_name)
                self._log(
                    company_name,
                    domain,
                    "evidence_conflict_detected",
                    provider_name,
                    {
                        "field_name": evidence.field_name,
                        "field_value": str(evidence.field_value),
                        "source_provider": evidence.source_provider,
                    },
                )
            evidence_id = self.evidence_ledger.store(evidence)
            evidence_ids[evidence.field_name] = evidence_id
            self._log(
                company_name,
                domain,
                "evidence_created",
                provider_name,
                {
                    "field_name": evidence.field_name,
                    "confidence": evidence.confidence,
                    "evidence_id": evidence_id,
                    "source_provider": evidence.source_provider,
                },
            )
            if evidence.confidence < 0.75:
                self._log(
                    company_name,
                    domain,
                    "evidence_rejected_low_confidence",
                    provider_name,
                    {
                        "field_name": evidence.field_name,
                        "confidence": evidence.confidence,
                        "threshold": 0.75,
                    },
                )
        return evidence_ids

    def _attach_evidence_ids(
        self,
        record: ContactRecord,
        evidence_ids: dict[str, str],
    ) -> None:
        if not evidence_ids:
            return
        field_ids = record.raw.setdefault("field_evidence_ids", {})
        if isinstance(field_ids, dict):
            for field_name, evidence_id in evidence_ids.items():
                field_ids.setdefault(field_name, evidence_id)

    def _select_highest_confidence_evidence(
        self,
        record: ContactRecord,
        evidence_items: list[EvidenceItem],
        evidence_ids: dict[str, str],
    ) -> None:
        for evidence in evidence_items:
            field_name = evidence.field_name
            if field_name not in {"name", "title", "email", "phone", "company"}:
                continue
            current = getattr(record, field_name)
            if current is None:
                continue
            current_evidence_id = record.raw.get("field_evidence_ids", {}).get(field_name)
            if not current_evidence_id:
                continue
            if evidence.field_value == current:
                continue
            current_items = (
                self.evidence_ledger.get_by_field(evidence.entity_key, field_name)
                if self.evidence_ledger
                else []
            )
            selected = sorted(
                current_items,
                key=lambda item: (item.confidence, item.collected_at),
                reverse=True,
            )[0] if current_items else evidence
            if selected.field_value != current:
                setattr(record, field_name, selected.field_value)
                field_ids = record.raw.setdefault("field_evidence_ids", {})
                if isinstance(field_ids, dict) and selected.evidence_id:
                    field_ids[field_name] = selected.evidence_id
                self._log(
                    record.company or "",
                    record.raw.get("domain") if isinstance(record.raw, dict) else None,
                    "evidence_selected_for_final",
                    selected.source_provider,
                    {
                        "field_name": field_name,
                        "selected_confidence": selected.confidence,
                        "selected_evidence_id": selected.evidence_id,
                    },
                )

    def _entity_key(self, company_name: str, domain: str | None) -> str:
        company = " ".join(company_name.casefold().split())
        return f"{company}|{(domain or 'unknown').casefold()}"

    def _provider_source_name(self, provider_name: str) -> str:
        name = provider_name.removesuffix("Provider")
        chars: list[str] = []
        for index, char in enumerate(name):
            if char.isupper() and index:
                chars.append("_")
            chars.append(char.casefold())
        return "".join(chars)


def enrich_waterfall(
    providers: Iterable[Provider],
    company_name: str,
    domain: str | None = None,
) -> ContactRecord | None:
    for provider in providers:
        record = provider.enrich(company_name, domain)
        if record is not None:
            return record
    return None
