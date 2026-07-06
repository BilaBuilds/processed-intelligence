from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from enrichment.models.evidence import EvidenceItem
from enrichment.storage.evidence_ledger import EvidenceLedger


FIELDS = ("name", "title", "email", "phone", "company")
REPORT_FIELDS = (
    "company_name",
    "domain",
    "field_name",
    "source_provider",
    "confidence",
    "evidence_type",
    "client_safe",
    "status",
    "assumption",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill evidence ledger from enriched_output.csv.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("measurement_runs/phase1_batch_20260703/enriched_output.csv"),
    )
    parser.add_argument(
        "--ledger-db",
        type=Path,
        default=Path("measurement_runs/phase1_batch_20260703/evidence_ledger.sqlite3"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("measurement_runs/phase1_batch_20260703/migration_report.csv"),
    )
    parser.add_argument("--run-id", default="phase1_batch_20260703")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    migrate(
        input_path=args.input,
        ledger_path=args.ledger_db,
        report_path=args.report,
        run_id=args.run_id,
        dry_run=args.dry_run,
    )
    return 0


def migrate(
    input_path: Path,
    ledger_path: Path,
    report_path: Path,
    run_id: str,
    dry_run: bool = False,
) -> list[EvidenceItem]:
    evidence_items: list[EvidenceItem] = []
    report_rows: list[dict[str, Any]] = []
    default_collected_at = datetime.fromtimestamp(input_path.stat().st_mtime, UTC)

    with input_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            raw = _parse_raw(row.get("raw") or "{}")
            provenance = raw.get("field_provenance") if isinstance(raw, dict) else {}
            for field_name in FIELDS:
                value = row.get(field_name)
                if not value:
                    continue
                source = _source_for_field(field_name, row, provenance)
                collected_at = _collected_at_for_field(
                    field_name,
                    provenance,
                    default_collected_at,
                )
                confidence = _safe_float(row.get("confidence"))
                evidence_type = "estimated" if source == "pattern_guess" else "observed"
                client_safe = evidence_type == "observed" and confidence >= 0.75
                assumption = (
                    "source inferred from field_provenance"
                    if isinstance(provenance, dict) and field_name in provenance
                    else "source inferred from row source"
                )
                item = EvidenceItem(
                    entity_type="company" if field_name == "company" else "contact",
                    entity_key=_entity_key(row.get("company_name") or "", row.get("domain")),
                    field_name=field_name,
                    field_value=value,
                    source_provider=source,
                    source_url=raw.get("best_url") if isinstance(raw, dict) else None,
                    source_ref=None,
                    evidence_type=evidence_type,
                    confidence=confidence,
                    collected_at=collected_at,
                    expires_at=None,
                    raw_snippet=raw.get("best_snippet") if isinstance(raw, dict) else None,
                    reasoning_note=f"Migrated from enriched_output.csv; {assumption}.",
                    client_safe=client_safe,
                    run_id=run_id,
                )
                evidence_items.append(item)
                report_rows.append(
                    {
                        "company_name": row.get("company_name"),
                        "domain": row.get("domain"),
                        "field_name": field_name,
                        "source_provider": source,
                        "confidence": confidence,
                        "evidence_type": evidence_type,
                        "client_safe": client_safe,
                        "status": "dry_run" if dry_run else "stored",
                        "assumption": assumption,
                    }
                )

    if not dry_run:
        ledger = EvidenceLedger(ledger_path)
        for item in evidence_items:
            ledger.store(item)

    _write_report(report_path, report_rows)
    print(
        f"{'Would migrate' if dry_run else 'Migrated'} {len(evidence_items)} evidence items "
        f"from {input_path}."
    )
    return evidence_items


def _source_for_field(
    field_name: str,
    row: dict[str, str],
    provenance: Any,
) -> str:
    if isinstance(provenance, dict):
        field = provenance.get(field_name)
        if isinstance(field, dict) and field.get("source"):
            return str(field["source"])
    return (row.get("source") or "unknown").split("+")[0] or "unknown"


def _collected_at_for_field(
    field_name: str,
    provenance: Any,
    default_collected_at: datetime,
) -> datetime:
    if isinstance(provenance, dict):
        field = provenance.get(field_name)
        if isinstance(field, dict) and field.get("timestamp"):
            try:
                return datetime.fromisoformat(str(field["timestamp"]))
            except ValueError:
                pass
    return default_collected_at


def _entity_key(company_name: str, domain: str | None) -> str:
    return f"{' '.join(company_name.casefold().split())}|{(domain or 'unknown').casefold()}"


def _parse_raw(raw_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_float(value: str | None) -> float:
    try:
        return float(value or 0.0)
    except ValueError:
        return 0.0


def _write_report(report_path: Path, rows: list[dict[str, Any]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
