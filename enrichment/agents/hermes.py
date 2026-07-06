from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from enrichment.cache import EnrichmentCache
from enrichment.agents.entity_resolution import EntityResolver
from enrichment.agents.outreach import (
    HermesOutreachOrchestrator,
    build_hermes_dashboard,
)
from enrichment.agents.memory import HermesMemoryStore
from enrichment.config import AppConfig, load_app_config
from enrichment.models import ContactRecord
from enrichment.serialization import record_to_dict
from enrichment.waterfall import WaterfallEnrichment


HERMES_OUTPUT_FIELDS = (
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
    "quality_score",
    "recommended_action",
    "raw",
)


@dataclass(frozen=True)
class HermesRunSummary:
    run_id: str
    input_path: str
    output_path: str
    summary_path: str
    total: int
    enriched: int
    with_email: int
    with_phone: int
    high_quality: int
    outreach_dir: str
    dashboard_path: str
    machine_trace_path: str
    drafts_created: int
    qa_passed: int
    approval_ready: int
    policy_allowed: int
    policy_blocked: int
    avg_expected_value: float


class HermesAgent:
    def __init__(
        self,
        waterfall: WaterfallEnrichment,
        memory: HermesMemoryStore | None = None,
    ) -> None:
        self.waterfall = waterfall
        self.memory = memory or HermesMemoryStore()
        self.entity_resolver = EntityResolver()

    @classmethod
    def from_config(cls, config_path: Path) -> "HermesAgent":
        load_dotenv()
        from enrichment.cli import build_cache, build_providers

        config = load_app_config(config_path)
        cache = build_cache(config)
        waterfall = WaterfallEnrichment(
            build_providers(config),
            cache,
            config.log_path,
        )
        return cls(waterfall)

    def enrich_one(
        self,
        company_name: str,
        domain: str | None = None,
    ) -> ContactRecord | None:
        return self.waterfall.enrich(company_name, domain)

    def enrich_csv(
        self,
        input_path: Path,
        output_path: Path,
        summary_path: Path,
        run_id: str | None = None,
    ) -> HermesRunSummary:
        rows = self._read_input_rows(input_path)
        output_rows = []
        batch_records: dict[str, ContactRecord | None] = {}

        for row in rows:
            company_name = row["company_name"].strip()
            domain = (row.get("domain") or "").strip() or None
            identity = self.entity_resolver.resolve(company_name, domain)
            if identity.entity_key not in batch_records:
                batch_records[identity.entity_key] = self.enrich_one(company_name, domain)
            record = batch_records[identity.entity_key]
            output_rows.append(self._output_row(company_name, domain, record))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=HERMES_OUTPUT_FIELDS)
            writer.writeheader()
            writer.writerows(output_rows)

        outreach_dir = output_path.parent / "outreach"
        artifacts = HermesOutreachOrchestrator().build_from_csv(
            output_path,
            outreach_dir,
        )
        dashboard_path = output_path.parent / "report.html"
        machine_trace_path = output_path.parent / "machine_trace.json"

        summary = self._summary(
            input_path,
            output_path,
            summary_path,
            output_rows,
            outreach_dir,
            dashboard_path,
            machine_trace_path,
            artifacts,
            run_id,
        )
        build_hermes_dashboard(output_path, artifacts, asdict(summary), dashboard_path)
        self._write_machine_trace(machine_trace_path, artifacts, asdict(summary))
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", encoding="utf-8") as summary_file:
            json.dump(asdict(summary), summary_file, indent=2, sort_keys=True)
            summary_file.write("\n")

        self.memory.record_run(summary.run_id, output_path, asdict(summary))
        return summary

    def close(self) -> None:
        self.waterfall.close()

    def _read_input_rows(self, input_path: Path) -> list[dict[str, str]]:
        with input_path.open("r", encoding="utf-8-sig", newline="") as input_file:
            reader = csv.DictReader(input_file)
            missing = {"company_name", "domain"} - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"Hermes input CSV missing columns: {', '.join(sorted(missing))}"
                )
            return [dict(row) for row in reader]

    def _output_row(
        self,
        company_name: str,
        domain: str | None,
        record: ContactRecord | None,
    ) -> dict[str, str | float | None]:
        data = record_to_dict(record)
        quality_score = self._quality_score(record)
        return {
            "status": "enriched" if record else "not_found",
            "company_name": company_name,
            "domain": domain,
            "name": data.get("name"),
            "title": data.get("title"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "company": data.get("company"),
            "source": data.get("source"),
            "confidence": data.get("confidence"),
            "quality_score": quality_score,
            "recommended_action": self._recommended_action(record, quality_score),
            "raw": json.dumps(data.get("raw", {}), sort_keys=True),
        }

    def _quality_score(self, record: ContactRecord | None) -> float:
        if record is None:
            return 0.0

        score = record.confidence * 60
        if record.name:
            score += 10
        if record.title:
            score += 5
        if record.email:
            score += 15
        if record.phone:
            score += 10
        return round(min(score, 100), 2)

    def _recommended_action(
        self,
        record: ContactRecord | None,
        quality_score: float,
    ) -> str:
        if record is None:
            return "research_manually"
        if quality_score >= 80 and record.email:
            return "ready_for_outreach"
        if record.email or record.phone:
            return "review_then_outreach"
        return "needs_contact_research"

    def _summary(
        self,
        input_path: Path,
        output_path: Path,
        summary_path: Path,
        rows: list[dict[str, Any]],
        outreach_dir: Path,
        dashboard_path: Path,
        machine_trace_path: Path,
        artifacts: list[Any],
        run_id: str | None = None,
    ) -> HermesRunSummary:
        run_id = run_id or datetime.now(UTC).strftime("hermes_%Y%m%d_%H%M%S")
        enriched_rows = [row for row in rows if row["status"] == "enriched"]
        high_quality_rows = [
            row
            for row in enriched_rows
            if float(row.get("quality_score") or 0) >= 80
        ]
        policy_allowed = 0
        expected_values: list[float] = []
        for artifact in artifacts:
            policy = artifact.research_profile.policy_decision or {}
            strategy = artifact.research_profile.strategic_brief or {}
            if policy.get("allowed"):
                policy_allowed += 1
            expected_values.append(self._safe_float(strategy.get("expected_value")))
        return HermesRunSummary(
            run_id=run_id,
            input_path=input_path.as_posix(),
            output_path=output_path.as_posix(),
            summary_path=summary_path.as_posix(),
            total=len(rows),
            enriched=len(enriched_rows),
            with_email=sum(1 for row in enriched_rows if row.get("email")),
            with_phone=sum(1 for row in enriched_rows if row.get("phone")),
            high_quality=len(high_quality_rows),
            outreach_dir=outreach_dir.as_posix(),
            dashboard_path=dashboard_path.as_posix(),
            machine_trace_path=machine_trace_path.as_posix(),
            drafts_created=len(artifacts),
            qa_passed=sum(1 for artifact in artifacts if artifact.truth_qa.passed),
            approval_ready=sum(
                1
                for artifact in artifacts
                if artifact.operator_review.status == "approval_ready"
            ),
            policy_allowed=policy_allowed,
            policy_blocked=len(artifacts) - policy_allowed,
            avg_expected_value=round(
                sum(expected_values) / len(expected_values),
                2,
            )
            if expected_values
            else 0.0,
        )

    def _write_machine_trace(
        self,
        machine_trace_path: Path,
        artifacts: list[Any],
        summary: dict[str, Any],
    ) -> None:
        trace = {
            "summary": summary,
            "artifacts": [
                {
                    "lead_id": artifact.lead_id,
                    "company_name": artifact.research_profile.company_name,
                    "email": artifact.research_profile.email,
                    "evidence_graph": artifact.research_profile.evidence_graph,
                    "strategic_brief": artifact.research_profile.strategic_brief,
                    "policy_decision": artifact.research_profile.policy_decision,
                    "account_intelligence": artifact.research_profile.account_intelligence,
                    "truth_qa": asdict(artifact.truth_qa),
                    "operator_review": asdict(artifact.operator_review),
                    "artifact_path": artifact.artifact_path,
                }
                for artifact in artifacts
            ],
        }
        machine_trace_path.parent.mkdir(parents=True, exist_ok=True)
        machine_trace_path.write_text(
            json.dumps(trace, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
