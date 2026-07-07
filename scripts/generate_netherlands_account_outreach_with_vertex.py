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
INPUT_CSV_PATH = ROOT / "data" / "outreach" / "netherlands_company_targets_enriched.csv"
TEMPLATES_PATH = ROOT / "data" / "outreach" / "netherlands_linkedin_templates.json"
OUTREACH_MESSAGES_PATH = ROOT / "docs" / "NETHERLANDS_OUTREACH_MESSAGES.md"
SALES_BRIEF_PATH = ROOT / "docs" / "NETHERLANDS_SALES_BRIEF.md"
OPPORTUNITIES_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities_enriched.json"
OUTPUT_CSV_PATH = ROOT / "data" / "outreach" / "netherlands_account_outreach_enriched.csv"
OUTPUT_JSON_PATH = ROOT / "data" / "outreach" / "netherlands_account_outreach_enriched.json"
REPORT_PATH = ROOT / "docs" / "NETHERLANDS_OUTREACH_PERSONALIZATION_REPORT.md"

DEFAULT_MODEL = "gemini-2.5-flash"
PROJECT_OUTPUT_VALUE = "configured_via_GOOGLE_CLOUD_PROJECT"
DISCLAIMER = "sample_demo research_needed not_verified; no personal contacts; not verified live coverage"

OUTPUT_FIELDS = [
    "account_id",
    "company_name",
    "segment",
    "outreach_priority",
    "account_level_angle",
    "linkedin_connection_message",
    "linkedin_follow_up_message",
    "email_subject",
    "email_body_short",
    "source_validation_question",
    "pilot_offer_angle",
    "disclaimer",
    "vertex_status",
    "generated_at",
    "model",
    "project",
]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path, max_chars: int = 900) -> str:
    if not path.exists():
        return ""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip()[:max_chars]


def clean_text(value: Any, max_length: int = 650) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = text.replace("\r", " ").replace("\n", " ")
    replacements = {
        "email address": "outreach channel",
        "emails": "outreach messages",
        "phone": "call",
        "mobile": "call",
        "contact name": "role owner",
        "decision maker": "bid or commercial owner",
        "verified relationship": "validation hypothesis",
        "live coverage": "sample coverage workflow",
    }
    for source, replacement in replacements.items():
        text = re.sub(rf"\b{re.escape(source)}\b", replacement, text, flags=re.IGNORECASE)
    return text[:max_length]


def ensure_caveat(text: str, max_length: int = 650) -> str:
    cleaned = clean_text(text, max_length=max_length)
    if not re.search(r"sample|demo|research_needed|not verified", cleaned, re.IGNORECASE):
        cleaned = f"{cleaned} This is sample/demo and research_needed, not verified live coverage."
    return cleaned[:max_length]


def context_summary() -> dict[str, Any]:
    opportunities = load_json(OPPORTUNITIES_PATH) or []
    templates = load_json(TEMPLATES_PATH) or {}
    categories = Counter(item.get("category", "unknown") for item in opportunities if isinstance(item, dict))
    return {
        "opportunity_count": len(opportunities) if isinstance(opportunities, list) else 0,
        "top_categories": dict(categories.most_common(6)),
        "template_disclaimers": templates.get("disclaimers", []),
        "sales_brief_excerpt": load_text(SALES_BRIEF_PATH),
        "outreach_message_excerpt": load_text(OUTREACH_MESSAGES_PATH),
    }


def dry_run_outreach(row: dict[str, str], model: str, generated_at: str) -> dict[str, str]:
    company = row.get("company_name", "this research account")
    segment = row.get("segment", "Netherlands procurement team")
    relevance = row.get("likely_relevance", "Dutch/EU procurement monitoring")
    suggested = row.get("enriched_suggested_angle") or row.get("suggested_angle") or "validate Netherlands source coverage"
    question = row.get("enriched_source_validation_question") or "Which Dutch/EU sources would need validation before this sample account is useful?"
    return {
        "account_id": row.get("id", ""),
        "company_name": company,
        "segment": segment,
        "outreach_priority": row.get("outreach_priority", ""),
        "account_level_angle": ensure_caveat(f"For {company}, test a {segment} angle around {relevance}: {suggested}", 320),
        "linkedin_connection_message": ensure_caveat(
            f"Hello, I am testing a sample/demo Netherlands procurement intelligence workflow for {segment}. I would value practical feedback from {company} on whether ranked Dutch/EU source validation would be useful.",
            300,
        ),
        "linkedin_follow_up_message": ensure_caveat(
            f"Thanks for taking a look. The Netherlands pack is sample/demo only, but it shows buyer signals, source caveats, and ranked opportunities for {relevance}. Would this save qualification time for {company}?",
            340,
        ),
        "email_subject": "Research-needed Netherlands procurement intelligence feedback",
        "email_body_short": ensure_caveat(
            f"Hello,\n\nI am testing a Netherlands procurement intelligence workflow for {segment}. The current pack is sample/demo only, not verified live coverage. For {company}, the hypothesis is {relevance}. Could you give blunt feedback on whether this source validation and ranking workflow would save qualification time?\n\nBest,\nProcessEd Intelligence",
            620,
        ),
        "source_validation_question": ensure_caveat(question, 300),
        "pilot_offer_angle": ensure_caveat(
            f"Offer a four-week sample-to-live validation pilot around agreed CPVs, buyer categories, and regions before making any coverage claims for {company}.",
            320,
        ),
        "disclaimer": DISCLAIMER,
        "vertex_status": "dry_run",
        "generated_at": generated_at,
        "model": model,
        "project": PROJECT_OUTPUT_VALUE,
    }


def build_prompt(row: dict[str, str], summary: dict[str, Any]) -> str:
    payload = {
        "task": "Return one compact JSON object only. No markdown, no prose.",
        "required_keys": {
            "account_level_angle": "short sample_demo research_needed angle",
            "linkedin_connection_message": "generic salutation, no personal name, max 300 chars, include sample/demo caveat",
            "linkedin_follow_up_message": "generic follow-up, no personal name, include sample/demo caveat",
            "email_subject": "short subject, no personal name",
            "email_body_short": "short plain-text body, no personal names, no email addresses, include sample/demo caveat",
            "source_validation_question": "one source-validation question",
            "pilot_offer_angle": "one four-week pilot angle",
        },
        "rules": {
            "no_personal_names": True,
            "no_email_addresses": True,
            "no_phone_numbers": True,
            "no_verified_relationships": True,
            "no_live_coverage_claims": True,
            "tone": "senior founder, calm, credible, direct",
        },
        "account": {
            "account_id": row.get("id"),
            "company_name": row.get("company_name"),
            "segment": row.get("segment"),
            "country": row.get("country"),
            "region": row.get("region"),
            "likely_relevance": row.get("likely_relevance"),
            "outreach_priority": row.get("outreach_priority"),
            "suggested_angle": row.get("suggested_angle"),
            "enriched_suggested_angle": row.get("enriched_suggested_angle"),
            "enriched_pilot_hypothesis": row.get("enriched_pilot_hypothesis"),
            "source_validation_question": row.get("enriched_source_validation_question"),
            "evidence_status": row.get("evidence_status"),
        },
        "project_context": {
            "opportunity_count": summary["opportunity_count"],
            "top_categories": summary["top_categories"],
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
        "max_output_tokens": 520,
        "response_mime_type": "application/json",
    }
    if hasattr(types, "ThinkingConfig"):
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    return types.GenerateContentConfig(**kwargs)


def vertex_outreach(row: dict[str, str], model: str, generated_at: str, client: Any, types: Any, summary: dict[str, Any]) -> dict[str, str]:
    fallback = dry_run_outreach(row, model, generated_at)
    try:
        response = client.models.generate_content(
            model=model,
            contents=build_prompt(row, summary),
            config=build_config(types),
        )
        parsed = parse_json_object(response_text(response))
        if not parsed:
            raise ValueError("Vertex response did not contain parseable JSON.")
        output = dict(fallback)
        for key in [
            "account_level_angle",
            "linkedin_connection_message",
            "linkedin_follow_up_message",
            "email_subject",
            "email_body_short",
            "source_validation_question",
            "pilot_offer_angle",
        ]:
            max_len = 620 if key == "email_body_short" else 340
            output[key] = ensure_caveat(parsed.get(key) or fallback[key], max_len)
        output["vertex_status"] = "generated"
        output["disclaimer"] = DISCLAIMER
        output["generated_at"] = generated_at
        output["model"] = model
        output["project"] = PROJECT_OUTPUT_VALUE
        return output
    except Exception as exc:
        fallback["vertex_status"] = "error"
        fallback["pilot_offer_angle"] = ensure_caveat(f"Vertex outreach generation failed; fallback used. {type(exc).__name__}. {fallback['pilot_offer_angle']}", 340)
        return fallback


def generate_rows(rows: list[dict[str, str]], args: argparse.Namespace) -> list[dict[str, str]]:
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    selected = rows[: args.limit] if args.limit is not None else rows
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
            raise RuntimeError("Vertex outreach generation requires google-genai. Use --dry-run for offline validation.") from exc
        client = genai.Client(vertexai=True, project=project, location=location)
        types = genai_types

    output_rows = []
    for row in selected:
        output = dry_run_outreach(row, args.model, generated_at) if args.dry_run else vertex_outreach(row, args.model, generated_at, client, types, summary)
        output_rows.append(output)
    return output_rows


def write_outputs(rows: list[dict[str, str]], output_csv: Path, output_json: Path, model: str) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    output_json.write_text(
        json.dumps(
            {
                "metadata": {
                    "name": "Netherlands account outreach personalization",
                    "data_status": "sample_demo_research_needed_not_verified_live_coverage",
                    "model": model,
                    "project": PROJECT_OUTPUT_VALUE,
                    "record_count": len(rows),
                },
                "accounts": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def write_report(rows: list[dict[str, str]], model: str, dry_run: bool, output_report: Path) -> None:
    status_counts = Counter(row.get("vertex_status", "unknown") for row in rows)
    priority_counts = Counter(row.get("outreach_priority", "unknown") for row in rows)
    mode = "dry-run heuristic" if dry_run else "Vertex AI Gemini Flash"
    lines = [
        "# Netherlands Outreach Personalization Report",
        "",
        "Status: account-level sample_demo/research_needed outreach copy. No personal contacts, private inboxes, call numbers, or verified relationships are included.",
        "",
        "## What Was Generated",
        "",
        f"- Account outreach rows: {len(rows)}",
        f"- Generation mode: {mode}",
        f"- Model: {model}",
        "- Project reference in outputs: configured_via_GOOGLE_CLOUD_PROJECT",
        "",
        "## Commercial Use",
        "",
        "The output converts placeholder target accounts into cautious founder-led outreach drafts. It is useful for feedback conversations, pilot scoping, and validating whether ranked Netherlands/TED/TenderNed procurement intelligence is commercially relevant before live coverage claims are made.",
        "",
        "## Priority Mix",
        "",
    ]
    lines.extend(f"- {priority}: {count}" for priority, count in sorted(priority_counts.items()))
    lines.extend(
        [
            "",
            "## Safety Controls",
            "",
            "- Generic salutations only; no personal names are generated.",
            "- No private emails, call numbers, or direct contact data are generated.",
            "- Every row carries a sample_demo/research_needed/not_verified disclaimer.",
            "- Copy asks for source validation and feedback, not a purchase based on claimed live coverage.",
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
    parser = argparse.ArgumentParser(description="Generate Netherlands account-level outreach copy with optional Vertex AI.")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic local copy without calling Vertex.")
    parser.add_argument("--limit", type=int, default=None, help="Limit accounts processed for controlled Vertex batches.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini Flash or Flash-Lite model name.")
    parser.add_argument("--input-csv", type=Path, default=INPUT_CSV_PATH, help="Input enriched target CSV path.")
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV_PATH, help="Output outreach CSV path.")
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON_PATH, help="Output outreach JSON path.")
    parser.add_argument("--output-report", type=Path, default=REPORT_PATH, help="Output outreach Markdown report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer.")
    if "pro" in args.model.lower():
        raise SystemExit("Use Gemini Flash or Flash-Lite only for this workflow.")
    rows = load_csv(args.input_csv)
    output_rows = generate_rows(rows, args)
    write_outputs(output_rows, args.output_csv, args.output_json, args.model)
    write_report(output_rows, args.model, args.dry_run, args.output_report)
    statuses = Counter(row.get("vertex_status", "unknown") for row in output_rows)
    print(f"Netherlands account outreach generation complete: {len(output_rows)} accounts, statuses {dict(sorted(statuses.items()))}, csv {args.output_csv}, json {args.output_json}.")


if __name__ == "__main__":
    main()
