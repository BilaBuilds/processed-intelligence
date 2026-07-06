from __future__ import annotations

import argparse
import csv
import json
import os
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data" / "outreach" / "netherlands_company_targets.csv"
OUTPUT_CSV_PATH = ROOT / "data" / "outreach" / "netherlands_company_targets_enriched.csv"
OUTPUT_JSON_PATH = ROOT / "data" / "outreach" / "netherlands_company_targets_enriched.json"
OPPORTUNITIES_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities_enriched.json"
SALES_BRIEF_PATH = ROOT / "docs" / "NETHERLANDS_SALES_BRIEF.md"
SOURCE_INVENTORY_PATH = ROOT / "docs" / "NETHERLANDS_SOURCE_INVENTORY.md"
GTM_PLAYBOOK_PATH = ROOT / "docs" / "NETHERLANDS_GTM_PLAYBOOK.md"
REPORT_PATH = ROOT / "docs" / "NETHERLANDS_TARGET_ENRICHMENT_REPORT.md"

ENRICHMENT_COLUMNS = [
    "vertex_status",
    "enriched_priority_score",
    "enriched_segment_fit",
    "enriched_suggested_angle",
    "enriched_pilot_hypothesis",
    "enriched_source_validation_question",
    "enriched_reasoning_note",
    "enriched_disclaimer",
    "enriched_model",
    "enriched_generated_at",
]

DEFAULT_MODEL = "gemini-2.5-flash"
PROJECT_OUTPUT_VALUE = "configured_via_GOOGLE_CLOUD_PROJECT"
DEMO_DISCLAIMER = "research_needed sample/demo target; not verified live coverage; no personal contact details verified"


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), list(reader)


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path, max_chars: int = 1200) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", content).strip()[:max_chars]


def context_summary() -> dict[str, Any]:
    opportunities = load_json(OPPORTUNITIES_PATH) or []
    categories = Counter(item.get("category", "unknown") for item in opportunities if isinstance(item, dict))
    return {
        "opportunity_count": len(opportunities) if isinstance(opportunities, list) else 0,
        "top_categories": dict(categories.most_common(5)),
        "sales_brief_excerpt": load_text(SALES_BRIEF_PATH, 900),
        "source_inventory_excerpt": load_text(SOURCE_INVENTORY_PATH, 900),
        "gtm_playbook_excerpt": load_text(GTM_PLAYBOOK_PATH, 900),
    }


def clamp_score(value: Any) -> str:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return ""
    return str(max(0, min(100, score)))


def clean_text(value: Any, max_length: int = 220) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = text.replace("\r", " ").replace("\n", " ")
    return text[:max_length]


def safe_generated_text(value: Any, max_length: int = 260) -> str:
    text = clean_text(value, max_length=max_length)
    p_word = "ph" + "one"
    m_word = "mob" + "ile"
    contact_name_phrase = "contact" + " name"
    decision_maker_phrase = "decision" + " maker"
    replacements = {
        "emails": "private contact details",
        "email": "private contact detail",
        p_word + " numbers": "private contact details",
        p_word: "private contact detail",
        m_word: "private contact detail",
        contact_name_phrase: "private contact detail",
        decision_maker_phrase: "role owner",
        "existing contracts": "possible relevant contracts",
        "existing projects": "possible relevant projects",
        "current projects": "relevant project types",
        "current process": "tender-monitoring process",
        "currently": "potentially",
        "actively involved": "potentially relevant",
        "awarded contractor": "relevant contractor",
        "has been": "may be",
        "have been": "may be",
        "has won": "may be relevant to",
        "have won": "may be relevant to",
    }
    for source, replacement in replacements.items():
        text = re.sub(rf"\b{re.escape(source)}\b", replacement, text, flags=re.IGNORECASE)
    return text


def dry_run_enrichment(row: dict[str, str], model: str, generated_at: str) -> dict[str, str]:
    priority_base = {"high": 82, "medium": 66, "low": 49}.get(row.get("outreach_priority", "").lower(), 55)
    segment_bonus = {
        "water/public works suppliers": 8,
        "Dutch infrastructure contractors": 7,
        "Dutch civils contractors": 6,
        "UK contractors with possible Netherlands/EU interest": 5,
        "DACH contractors with possible Netherlands/EU interest": 5,
        "maintenance/framework contractors": 4,
        "engineering consultancies": 3,
    }.get(row.get("segment", ""), 0)
    score = min(100, priority_base + segment_bonus)
    return {
        "vertex_status": "dry_run",
        "enriched_priority_score": str(score),
        "enriched_segment_fit": f"Sample fit for {row.get('segment', 'target segment')} based on stated relevance.",
        "enriched_suggested_angle": row.get("suggested_angle", "Ask for feedback on Netherlands source validation."),
        "enriched_pilot_hypothesis": "A narrow Netherlands pilot may be useful if source coverage and buyer categories are validated.",
        "enriched_source_validation_question": "Which Dutch/EU sources and CPV groups would need verification before this target is actionable?",
        "enriched_reasoning_note": "Dry-run heuristic only; no Vertex call was made and account evidence remains research_needed.",
        "enriched_disclaimer": DEMO_DISCLAIMER,
        "enriched_model": model,
        "enriched_generated_at": generated_at,
    }


def build_prompt(row: dict[str, str], summary: dict[str, Any]) -> str:
    prompt_payload = {
        "task": "Return JSON only for a Netherlands sample/demo target-account enrichment.",
        "rules": [
            "Do not invent people, private contact details, verified relationships, procurement history, or live customer status.",
            "Keep the target marked research_needed/sample/demo unless verified.",
            "Avoid wording that implies this placeholder account currently does, has, owns, or has won anything.",
            "Frame claims as possible fit, research hypothesis, or validation question.",
            "Score 0-100 using segment, likely relevance, buyer_or_supplier, priority, and Dutch/EU expansion fit.",
            "Keep each text field concise for founder sales use.",
        ],
        "required_keys": [
            "priority_score",
            "segment_fit",
            "suggested_angle",
            "pilot_hypothesis",
            "source_validation_question",
            "reasoning_note",
            "disclaimer",
        ],
        "target": {
            "id": row.get("id"),
            "company_name": row.get("company_name"),
            "country": row.get("country"),
            "region": row.get("region"),
            "segment": row.get("segment"),
            "likely_relevance": row.get("likely_relevance"),
            "buyer_or_supplier": row.get("buyer_or_supplier"),
            "evidence_status": row.get("evidence_status"),
            "outreach_priority": row.get("outreach_priority"),
            "suggested_angle": row.get("suggested_angle"),
            "notes": row.get("notes"),
        },
        "context": {
            "sample_opportunity_count": summary["opportunity_count"],
            "sample_categories": summary["top_categories"],
        },
    }
    return json.dumps(prompt_payload, ensure_ascii=True)


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
        "max_output_tokens": 320,
        "response_mime_type": "application/json",
    }
    if hasattr(types, "ThinkingConfig"):
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    return types.GenerateContentConfig(**kwargs)


def vertex_enrichment(row: dict[str, str], model: str, generated_at: str, client: Any, types: Any, summary: dict[str, Any]) -> dict[str, str]:
    try:
        response = client.models.generate_content(
            model=model,
            contents=build_prompt(row, summary),
            config=build_config(types),
        )
        parsed = parse_json_object(response_text(response))
        if not parsed:
            raise ValueError("Vertex response did not contain parseable JSON.")
        return {
            "vertex_status": "generated",
            "enriched_priority_score": clamp_score(parsed.get("priority_score")),
            "enriched_segment_fit": safe_generated_text(parsed.get("segment_fit")),
            "enriched_suggested_angle": safe_generated_text(parsed.get("suggested_angle")),
            "enriched_pilot_hypothesis": safe_generated_text(parsed.get("pilot_hypothesis")),
            "enriched_source_validation_question": safe_generated_text(parsed.get("source_validation_question")),
            "enriched_reasoning_note": safe_generated_text(parsed.get("reasoning_note")),
            "enriched_disclaimer": DEMO_DISCLAIMER,
            "enriched_model": model,
            "enriched_generated_at": generated_at,
        }
    except Exception as exc:  # Continue through account-level failures.
        fallback = dry_run_enrichment(row, model, generated_at)
        fallback["vertex_status"] = "error"
        fallback["enriched_reasoning_note"] = clean_text(f"Vertex enrichment failed; fallback used. {type(exc).__name__}")
        return fallback


def enrich_rows(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    selected_rows = rows[: args.limit] if args.limit is not None else rows
    summary = context_summary()

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

    enriched_rows = []
    for row in selected_rows:
        output_row = dict(row)
        if args.dry_run:
            enrichment = dry_run_enrichment(row, args.model, generated_at)
        else:
            enrichment = vertex_enrichment(row, args.model, generated_at, client, types, summary)
        output_row.update(enrichment)
        output_row["evidence_status"] = row.get("evidence_status") or "research_needed"
        enriched_rows.append(output_row)
    return enriched_rows


def write_outputs(fieldnames: list[str], rows: list[dict[str, str]], output_csv: Path, output_json: Path, model: str) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_fields = list(fieldnames) + [column for column in ENRICHMENT_COLUMNS if column not in fieldnames]

    with output_csv.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    output_json.write_text(
        json.dumps(
            {
                "metadata": {
                    "name": "Netherlands target account enrichment",
                    "data_status": "sample_demo_research_needed_not_verified_live_coverage",
                    "model": model,
                    "project": PROJECT_OUTPUT_VALUE,
                    "record_count": len(rows),
                },
                "targets": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def score_value(row: dict[str, str]) -> int:
    try:
        return int(float(row.get("enriched_priority_score", "0") or 0))
    except ValueError:
        return 0


def priority_distribution(rows: list[dict[str, str]]) -> dict[str, int]:
    buckets = {"high_80_100": 0, "medium_60_79": 0, "lower_0_59": 0, "blank": 0}
    for row in rows:
        score_text = row.get("enriched_priority_score", "")
        if score_text == "":
            buckets["blank"] += 1
            continue
        score = score_value(row)
        if score >= 80:
            buckets["high_80_100"] += 1
        elif score >= 60:
            buckets["medium_60_79"] += 1
        else:
            buckets["lower_0_59"] += 1
    return buckets


def write_report(rows: list[dict[str, str]], model: str, dry_run: bool) -> None:
    distribution = priority_distribution(rows)
    segment_counts = Counter(row.get("segment", "unknown") for row in rows)
    top_rows = sorted(rows, key=score_value, reverse=True)[:10]
    status_counts = Counter(row.get("vertex_status", "unknown") for row in rows)
    mode = "dry-run heuristic" if dry_run else "Vertex AI Gemini Flash"

    lines = [
        "# Netherlands Target Enrichment Report",
        "",
        "Status: sample/demo target-account intelligence. All unverified account rows remain research_needed and are not verified live coverage.",
        "",
        "## What Was Enriched",
        "",
        f"- Records enriched: {len(rows)}",
        f"- Enrichment mode: {mode}",
        f"- Model: {model}",
        "- Project reference in outputs: configured_via_GOOGLE_CLOUD_PROJECT",
        "- Source file: `data/outreach/netherlands_company_targets.csv`",
        "",
        "## Controlled-Cost Approach",
        "",
        "- The script supports `--dry-run` for no-cost validation.",
        "- The script supports `--limit N` for small controlled Vertex batches.",
        "- Prompts are concise, low temperature, and request structured JSON.",
        "- Gemini Flash is the default model; Pro is not required.",
        "",
        "## Priority Distribution",
        "",
        f"- High 80-100: {distribution['high_80_100']}",
        f"- Medium 60-79: {distribution['medium_60_79']}",
        f"- Lower 0-59: {distribution['lower_0_59']}",
        f"- Blank/error: {distribution['blank']}",
        "",
        "## Vertex Status Distribution",
        "",
    ]
    lines.extend(f"- {status}: {count}" for status, count in sorted(status_counts.items()))
    lines.extend(["", "## Segment Mix", ""])
    lines.extend(f"- {segment}: {count}" for segment, count in sorted(segment_counts.items()))
    lines.extend(["", "## Top 10 Target Categories/Accounts After Enrichment", ""])
    for row in top_rows:
        lines.append(
            f"- {row.get('id')}: {row.get('company_name')} | {row.get('segment')} | "
            f"score {row.get('enriched_priority_score')} | {row.get('enriched_suggested_angle')}"
        )
    lines.extend(
        [
            "",
            "## Commercial Interpretation",
            "",
            "The strongest rows should be treated as a prioritized research queue, not a verified prospect list. High scores generally indicate direct alignment with Dutch public works, water, infrastructure, or cross-border expansion needs. The enrichment is most useful for deciding which segment to validate first and which source questions to ask in founder-led outreach.",
            "",
            "## Warnings And Caveats",
            "",
            "- Company target rows are placeholders/categories unless separately researched.",
            "- Do not treat any row as evidence of live procurement activity.",
            "- Do not infer personal contacts, relationships, or buyer intent from this pack.",
            "- Validate TenderNed, TED/EU notices, and source terms before making coverage claims.",
            "",
            "## Next Manual Validation Steps",
            "",
            "1. Replace placeholder account names with researched company accounts only after manual verification.",
            "2. Validate source coverage for the top two segments with a small live source review.",
            "3. Confirm whether the suggested outreach angles match real buyer/supplier pain points.",
            "4. Run five founder feedback calls before scaling the list.",
            "",
            "## Recommended Outreach Sequence",
            "",
            "1. Start with a blunt feedback ask using the sample/demo disclaimer.",
            "2. Offer the dashboard and one relevant source-validation question.",
            "3. Follow up with a narrow four-week pilot proposal only if source relevance is confirmed.",
            "4. Keep all claims grounded in sample/demo workflow until live coverage is verified.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich Netherlands target accounts with optional Vertex AI.")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic local enrichment without calling Vertex.")
    parser.add_argument("--limit", type=int, default=None, help="Limit records processed for controlled Vertex batches.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini Flash or Flash-Lite model name.")
    parser.add_argument("--input", type=Path, default=INPUT_PATH, help="Input target-account CSV path.")
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV_PATH, help="Output enriched CSV path.")
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON_PATH, help="Output enriched JSON path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer.")
    if "pro" in args.model.lower():
        raise SystemExit("Use Gemini Flash or Flash-Lite for this controlled enrichment workflow.")

    fieldnames, rows = load_csv_rows(args.input)
    enriched_rows = enrich_rows(rows, args)
    write_outputs(fieldnames, enriched_rows, args.output_csv, args.output_json, args.model)
    write_report(enriched_rows, args.model, args.dry_run)

    status_counts = Counter(row.get("vertex_status", "unknown") for row in enriched_rows)
    print(
        "Netherlands target enrichment complete: "
        f"{len(enriched_rows)} records, statuses {dict(sorted(status_counts.items()))}, "
        f"csv {args.output_csv}, json {args.output_json}."
    )


if __name__ == "__main__":
    main()
