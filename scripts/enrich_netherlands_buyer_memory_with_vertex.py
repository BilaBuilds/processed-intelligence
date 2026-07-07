from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data" / "dutch" / "buyer_memory" / "netherlands_buyer_memory.json"
OUTPUT_PATH = ROOT / "data" / "dutch" / "buyer_memory" / "netherlands_buyer_memory_enriched.json"
REPORT_PATH = ROOT / "docs" / "NETHERLANDS_BUYER_MEMORY_BRIEF.md"

DEFAULT_MODEL = "gemini-2.5-flash"
PROJECT_OUTPUT_VALUE = "configured_via_GOOGLE_CLOUD_PROJECT"
DATA_STATUS = "sample_demo_research_needed_not_verified_live_coverage"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: Any, max_length: int = 320) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text.replace("\r", " ").replace("\n", " ")[:max_length]


def clamp_score(value: Any) -> str:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return "60"
    return str(max(0, min(100, score)))


def dry_run_enrichment(record: dict[str, Any], model: str, generated_at: str) -> dict[str, str]:
    value_bonus = {
        "water_authority": 88,
        "national_infrastructure_agency": 86,
        "municipality": 82,
        "province": 78,
        "eu_or_cross_border_sample": 76,
    }.get(record.get("buyer_type"), 70)
    return {
        "vertex_status": "dry_run",
        "buyer_signal_summary": f"Sample buyer-memory seed for {record.get('buyer_name')} based on demo opportunities only.",
        "likely_procurement_pattern": clean_text(record.get("procurement_theme")),
        "recommended_sales_angle": clean_text(record.get("relationship_angle")),
        "relevant_contractor_segments": clean_text(record.get("likely_supplier_fit")),
        "source_validation_question": "Which TenderNed, TED/EU, or buyer portal records would verify this sample buyer pattern?",
        "risk_note": "research_needed sample_demo not_verified; do not treat as live buyer history.",
        "enriched_priority_score": str(value_bonus),
        "enriched_generated_at": generated_at,
        "enriched_model": model,
        "project": PROJECT_OUTPUT_VALUE,
    }


def build_prompt(record: dict[str, Any]) -> str:
    payload = {
        "task": "Return one compact JSON object only. No markdown, no prose.",
        "required_keys": {
            "buyer_signal_summary": "short cautious summary beginning with sample_demo research_needed not_verified",
            "likely_procurement_pattern": "short pattern hypothesis",
            "recommended_sales_angle": "short founder sales angle",
            "relevant_contractor_segments": "semicolon-separated segments",
            "source_validation_question": "one question about TenderNed/TED/source validation",
            "risk_note": "short caveat including research_needed sample_demo not_verified",
            "priority_score": "integer 0-100",
        },
        "rules": {
            "no_live_coverage_claims": True,
            "no_verified_history_claims": True,
            "no_private_contacts_or_people": True,
            "keep_concise": True,
        },
        "buyer_memory_seed": {
            "buyer_name": record.get("buyer_name"),
            "buyer_type": record.get("buyer_type"),
            "country": record.get("country"),
            "region": record.get("region"),
            "categories": record.get("categories"),
            "observed_opportunity_count": record.get("observed_opportunity_count"),
            "procurement_theme": record.get("procurement_theme"),
            "likely_supplier_fit": record.get("likely_supplier_fit"),
            "relationship_angle": record.get("relationship_angle"),
            "data_status": record.get("data_status"),
            "caveat": record.get("caveat"),
        },
    }
    return json.dumps(payload, ensure_ascii=True)


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}


def response_text(response: Any) -> str:
    text = (getattr(response, "text", None) or "").strip()
    if text:
        return text
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) if content else []
    return " ".join((getattr(part, "text", "") or "").strip() for part in parts).strip()


def build_config(types: Any) -> Any:
    kwargs: dict[str, Any] = {
        "temperature": 0.1,
        "max_output_tokens": 420,
        "response_mime_type": "application/json",
    }
    if hasattr(types, "ThinkingConfig"):
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    return types.GenerateContentConfig(**kwargs)


def vertex_enrichment(record: dict[str, Any], model: str, generated_at: str, client: Any, types: Any) -> dict[str, str]:
    fallback = dry_run_enrichment(record, model, generated_at)
    try:
        response = client.models.generate_content(
            model=model,
            contents=build_prompt(record),
            config=build_config(types),
        )
        parsed = parse_json_object(response_text(response))
        if not parsed:
            raise ValueError("Vertex response did not contain parseable JSON.")
        return {
            "vertex_status": "generated",
            "buyer_signal_summary": clean_text(parsed.get("buyer_signal_summary") or fallback["buyer_signal_summary"]),
            "likely_procurement_pattern": clean_text(parsed.get("likely_procurement_pattern") or fallback["likely_procurement_pattern"]),
            "recommended_sales_angle": clean_text(parsed.get("recommended_sales_angle") or fallback["recommended_sales_angle"]),
            "relevant_contractor_segments": clean_text(parsed.get("relevant_contractor_segments") or fallback["relevant_contractor_segments"]),
            "source_validation_question": clean_text(parsed.get("source_validation_question") or fallback["source_validation_question"]),
            "risk_note": clean_text(parsed.get("risk_note") or fallback["risk_note"]),
            "enriched_priority_score": clamp_score(parsed.get("priority_score")),
            "enriched_generated_at": generated_at,
            "enriched_model": model,
            "project": PROJECT_OUTPUT_VALUE,
        }
    except Exception as exc:
        fallback["vertex_status"] = "error"
        fallback["risk_note"] = clean_text(f"Vertex enrichment failed; fallback used. {type(exc).__name__}. research_needed sample_demo not_verified")
        return fallback


def enrich_records(records: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    selected = records[: args.limit] if args.limit is not None else records
    client = None
    types = None
    if not args.dry_run:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION")
        if not project or not location:
            raise SystemExit("GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are required unless --dry-run is used.")
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise RuntimeError("Vertex enrichment requires google-genai. Use --dry-run for offline validation.") from exc
        client = genai.Client(vertexai=True, project=project, location=location)
        types = genai_types

    enriched = []
    for record in selected:
        output = dict(record)
        update = dry_run_enrichment(record, args.model, generated_at) if args.dry_run else vertex_enrichment(record, args.model, generated_at, client, types)
        output.update(update)
        if not re.search(r"research_needed|sample_demo|not_verified", output.get("risk_note", ""), re.IGNORECASE):
            output["risk_note"] = clean_text(output["risk_note"] + " research_needed sample_demo not_verified")
        enriched.append(output)
    return enriched


def write_output(records: list[dict[str, Any]], output: Path, model: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "metadata": {
                    "name": "Netherlands buyer memory enrichment",
                    "data_status": DATA_STATUS,
                    "model": model,
                    "project": PROJECT_OUTPUT_VALUE,
                    "record_count": len(records),
                },
                "buyers": records,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def write_report(records: list[dict[str, Any]], model: str, dry_run: bool, output_report: Path) -> None:
    status_counts = Counter(record.get("vertex_status", "unknown") for record in records)
    top_records = sorted(records, key=lambda item: int(item.get("enriched_priority_score", 0) or 0), reverse=True)[:8]
    mode = "dry-run heuristic" if dry_run else "Vertex AI Gemini Flash"
    lines = [
        "# Netherlands Buyer Memory Brief",
        "",
        "Status: sample_demo/research_needed buyer-memory intelligence. This is not verified live Dutch buyer coverage.",
        "",
        "## What Was Built",
        "",
        f"- Buyer-memory records: {len(records)}",
        f"- Enrichment mode: {mode}",
        f"- Model: {model}",
        "- Project reference in outputs: configured_via_GOOGLE_CLOUD_PROJECT",
        "",
        "## Why It Matters Commercially",
        "",
        "Buyer memory turns isolated sample opportunities into reusable account intelligence: recurring buyer themes, likely supplier fit, watch actions, and source-validation questions. This supports weekly digests, founder-led sales discovery, and future live TenderNed/TED integration without claiming verified live coverage.",
        "",
        "## Top Buyer Seeds",
        "",
    ]
    for record in top_records:
        lines.append(
            f"- {record.get('buyer_name')}: score {record.get('enriched_priority_score')} | "
            f"{record.get('likely_procurement_pattern')} | {record.get('recommended_sales_angle')}"
        )
    lines.extend(
        [
            "",
            "## Validation Next Steps",
            "",
            "1. Verify each buyer pattern against TenderNed/TED or official buyer portals before commercial use.",
            "2. Add source notice IDs, attribution, and retrieval timestamps when live ingestion exists.",
            "3. Keep buyer-memory records separate from private contacts or CRM data until privacy review is complete.",
            "4. Use buyer categories and CPV filters to reduce false positives before scaling alerts.",
            "",
            "## Caveats",
            "",
            "- Demo buyer memory is derived from sample opportunities.",
            "- No personal contacts, private relationships, incumbents, or verified buyer intent are included.",
            "- All unverified claims remain research_needed/sample_demo/not_verified.",
            "",
            "## Vertex Status Distribution",
            "",
        ]
    )
    lines.extend(f"- {status}: {count}" for status, count in sorted(status_counts.items()))
    lines.append("")
    output_report.parent.mkdir(parents=True, exist_ok=True)
    output_report.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich Netherlands buyer-memory records with optional Vertex AI.")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic local enrichment without calling Vertex.")
    parser.add_argument("--limit", type=int, default=None, help="Limit records processed for controlled Vertex batches.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini Flash or Flash-Lite model name.")
    parser.add_argument("--input", type=Path, default=INPUT_PATH, help="Input buyer-memory JSON path.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output enriched buyer-memory JSON path.")
    parser.add_argument("--output-report", type=Path, default=REPORT_PATH, help="Output buyer-memory Markdown report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer.")
    if "pro" in args.model.lower():
        raise SystemExit("Use Gemini Flash or Flash-Lite only for this workflow.")
    payload = load_json(args.input)
    records = payload.get("buyers", []) if isinstance(payload, dict) else []
    if not isinstance(records, list):
        raise SystemExit("Input buyer-memory JSON must contain a buyers list.")
    enriched = enrich_records(records, args)
    write_output(enriched, args.output, args.model)
    write_report(enriched, args.model, args.dry_run, args.output_report)
    statuses = Counter(record.get("vertex_status", "unknown") for record in enriched)
    print(f"Netherlands buyer memory enrichment complete: {len(enriched)} buyers, statuses {dict(sorted(statuses.items()))}, output {args.output}.")


if __name__ == "__main__":
    main()
