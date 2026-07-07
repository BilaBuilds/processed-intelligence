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
SOURCE_INVENTORY_PATH = ROOT / "docs" / "NETHERLANDS_SOURCE_INVENTORY.md"
DATA_MODEL_PATH = ROOT / "docs" / "NETHERLANDS_DATA_MODEL.md"
MARKET_BRIEF_PATH = ROOT / "docs" / "NETHERLANDS_MARKET_ENTRY_BRIEF.md"
DEMO_OPPORTUNITIES_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities.json"
ENRICHED_OPPORTUNITIES_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities_enriched.json"
OUTPUT_JSON_PATH = ROOT / "data" / "dutch" / "source_readiness" / "netherlands_source_readiness.json"
OUTPUT_CSV_PATH = ROOT / "data" / "dutch" / "source_readiness" / "netherlands_source_readiness.csv"
REPORT_PATH = ROOT / "docs" / "NETHERLANDS_LIVE_SOURCE_READINESS.md"

DEFAULT_MODEL = "gemini-2.5-flash"
PROJECT_OUTPUT_VALUE = "configured_via_GOOGLE_CLOUD_PROJECT"
DATA_STATUS = "research_needed_sample_demo_not_verified_live_coverage"

FIELDNAMES = [
    "source_name",
    "country_scope",
    "coverage_type",
    "likely_access_method",
    "integration_difficulty_1_5",
    "commercial_value_1_5",
    "legal_data_risk_1_5",
    "required_auth_or_credentials",
    "likely_fields_available",
    "likely_missing_fields",
    "recommended_first_test",
    "live_integration_priority",
    "caveat",
    "vertex_status",
    "vertex_reasoning_note",
    "generated_at",
    "model",
    "project",
]

BASE_SOURCES: list[dict[str, Any]] = [
    {
        "source_name": "TenderNed",
        "country_scope": "Netherlands",
        "coverage_type": "Dutch national public procurement notices and contracting authority publication workflows",
        "likely_access_method": "Public portal and RSS/dataset review first; production API likely needs TenderNed-issued username/password.",
        "integration_difficulty_1_5": 4,
        "commercial_value_1_5": 5,
        "legal_data_risk_1_5": 3,
        "required_auth_or_credentials": "Likely credentials for official XML/API access; no credentials for manual public portal review.",
        "likely_fields_available": "notice title; buyer; publication date; deadline; CPV; procedure; notice identifier; documents/links when published",
        "likely_missing_fields": "supplier fit score; English summary; normalized buyer category; downstream relationship/contact data; some document details without deeper parsing",
        "recommended_first_test": "Manually verify 20 current public works notices, then test RSS/dataset/API shape without storing credentials in Git.",
        "live_integration_priority": "1",
        "caveat": "research_needed sample_demo not_verified; official access terms and automated-use constraints must be checked before claiming live coverage.",
    },
    {
        "source_name": "TED/EU notices",
        "country_scope": "EU with Netherlands filtering",
        "coverage_type": "EU/TED published notices, especially above-threshold Dutch and cross-border infrastructure procurement",
        "likely_access_method": "Official TED API for published notices; anonymous access appears available for published notices, while unpublished/manipulation endpoints require API key.",
        "integration_difficulty_1_5": 3,
        "commercial_value_1_5": 5,
        "legal_data_risk_1_5": 2,
        "required_auth_or_credentials": "None expected for published-notice search/retrieval pilot; API key may be required for non-public or eSender workflows.",
        "likely_fields_available": "notice identifier; buyer; country; CPV; procedure; dates; values when disclosed; language; links; eForms fields",
        "likely_missing_fields": "buyer aliases; practical eligibility interpretation; translations; commercial fit score; local-lot nuance",
        "recommended_first_test": "Run a Netherlands CPV query for construction, roads, water, maintenance, and compare returned fields against the demo data model.",
        "live_integration_priority": "2",
        "caveat": "research_needed not_verified; API availability is a source-access assumption until a live query is executed and logged outside committed artifacts.",
    },
    {
        "source_name": "EU Public Procurement Data Space",
        "country_scope": "EU analytics with Netherlands slice",
        "coverage_type": "EU procurement analytics, dashboards, harmonized datasets, market sizing, and trend intelligence",
        "likely_access_method": "Public PPDS/data.europa.eu exploration first; confirm dataset download/API/registration options for production.",
        "integration_difficulty_1_5": 4,
        "commercial_value_1_5": 4,
        "legal_data_risk_1_5": 3,
        "required_auth_or_credentials": "Unknown until dataset-by-dataset review; may need account/API access for some services.",
        "likely_fields_available": "aggregated procurement indicators; buyer and notice dimensions; CPV/country/time filters; historical trend views",
        "likely_missing_fields": "active bid urgency; full notice detail; document attachments; local buyer aliases; sales-ready summaries",
        "recommended_first_test": "Map three Netherlands infrastructure CPV trends against TenderNed/TED sample notices for buyer prioritisation.",
        "live_integration_priority": "4",
        "caveat": "research_needed sample_demo not_verified; use as analytics layer until dataset licensing and freshness are verified.",
    },
    {
        "source_name": "Dutch public works / municipal procurement portals",
        "country_scope": "Netherlands municipalities",
        "coverage_type": "Municipal public realm, roads, buildings, drainage, and civil works opportunities that may appear on TenderNed plus local pages",
        "likely_access_method": "Start via TenderNed buyer filtering; add municipality portal watchlist only after source terms review.",
        "integration_difficulty_1_5": 4,
        "commercial_value_1_5": 5,
        "legal_data_risk_1_5": 3,
        "required_auth_or_credentials": "Usually none for manual public pages; credentials may be needed for tender document platforms.",
        "likely_fields_available": "buyer name; project title; procurement page link; deadline; document pointers; CPV when mirrored through TenderNed",
        "likely_missing_fields": "consistent API fields; complete document metadata; normalized region; English summary; duplicate detection across portals",
        "recommended_first_test": "Pick Rotterdam, Utrecht, Eindhoven, and Haarlemmermeer as manual validation buyers, then check whether TenderNed already covers each relevant notice.",
        "live_integration_priority": "3",
        "caveat": "research_needed sample_demo not_verified; do not scrape local portals at scale before legal and robots review.",
    },
    {
        "source_name": "Dutch water authority procurement",
        "country_scope": "Netherlands water authorities",
        "coverage_type": "Waterschap procurement for flood defence, pumping stations, drainage, treatment works, asset inspection, and maintenance",
        "likely_access_method": "TenderNed buyer/category filters first; maintain water authority buyer taxonomy and manually verify portal/document access.",
        "integration_difficulty_1_5": 3,
        "commercial_value_1_5": 5,
        "legal_data_risk_1_5": 2,
        "required_auth_or_credentials": "No credentials expected for notice discovery; tender-document access may vary by platform.",
        "likely_fields_available": "buyer; water/civil CPV; location; publication/deadline; procedure; title; notice link",
        "likely_missing_fields": "asset type classification; local consortium requirements; M&E/civils split; environmental permit nuance",
        "recommended_first_test": "Build a waterschap buyer alias list and test CPVs 4524, 452324, 452521, 7132 against TenderNed/TED records.",
        "live_integration_priority": "2",
        "caveat": "research_needed sample_demo not_verified; water authority scope is a strong hypothesis, not verified live coverage.",
    },
    {
        "source_name": "Dutch infrastructure/transport procurement",
        "country_scope": "Netherlands national and regional infrastructure buyers",
        "coverage_type": "Rijkswaterstaat, provinces, transport authorities, ports, roads, waterways, bridges, tunnels, and mobility projects",
        "likely_access_method": "TenderNed/TED first, then buyer-specific portals for document and framework nuance after access review.",
        "integration_difficulty_1_5": 4,
        "commercial_value_1_5": 5,
        "legal_data_risk_1_5": 3,
        "required_auth_or_credentials": "Notice discovery likely public; platform accounts may be needed for documents, Q&A, or bid participation.",
        "likely_fields_available": "buyer; project title; CPV; NUTS/region; value where disclosed; deadline; notice type; procedure",
        "likely_missing_fields": "framework call-off visibility; safety/certification requirements; local partner requirements; document-derived scoring criteria",
        "recommended_first_test": "Validate Rijkswaterstaat and two province buyer queries, then compare transport CPVs against existing demo categories.",
        "live_integration_priority": "2",
        "caveat": "research_needed sample_demo not_verified; high commercial relevance but heavier compliance and document parsing likely.",
    },
    {
        "source_name": "Dutch framework/maintenance procurement sources",
        "country_scope": "Netherlands multi-year frameworks and recurring maintenance",
        "coverage_type": "Maintenance frameworks, road resurfacing, drainage cleaning, bridge repair, inspections, and asset services",
        "likely_access_method": "TenderNed/TED CPV and notice-type filters, plus buyer framework pages if public and terms permit.",
        "integration_difficulty_1_5": 3,
        "commercial_value_1_5": 4,
        "legal_data_risk_1_5": 2,
        "required_auth_or_credentials": "Usually none for notice discovery; tender platform credentials may be needed for detailed documents.",
        "likely_fields_available": "framework title; buyer; CPV; duration; estimated value when disclosed; deadline; lot indicators",
        "likely_missing_fields": "call-off timing; incumbent supplier; renewal likelihood; granular lot geography; practical supplier fit",
        "recommended_first_test": "Search maintenance CPVs 50000000, 50230000, 71500000, and drainage CPVs, then classify recurring buyers.",
        "live_integration_priority": "3",
        "caveat": "research_needed sample_demo not_verified; frameworks can be commercially valuable but may hide call-off detail.",
    },
    {
        "source_name": "Dutch buyer categories",
        "country_scope": "Netherlands internal normalization layer",
        "coverage_type": "Internal taxonomy for municipalities, provinces, ministries, Rijkswaterstaat, ports, public transport, water authorities, and public estate bodies",
        "likely_access_method": "Derived from public buyer names in TenderNed/TED outputs and maintained in project-controlled mapping files.",
        "integration_difficulty_1_5": 2,
        "commercial_value_1_5": 5,
        "legal_data_risk_1_5": 1,
        "required_auth_or_credentials": "None for taxonomy maintenance; avoid private contact enrichment without privacy review.",
        "likely_fields_available": "buyer name; normalized category; likely sector; region; source provenance",
        "likely_missing_fields": "official entity identifiers; parent/child authority structure; buyer aliases; contact ownership",
        "recommended_first_test": "Create a 50-buyer alias table from sample/TenderNed/TED records and test dashboard grouping consistency.",
        "live_integration_priority": "1",
        "caveat": "sample_demo research_needed; this is not an external source and should not imply live procurement coverage.",
    },
    {
        "source_name": "CPV groups",
        "country_scope": "EU/Netherlands taxonomy",
        "coverage_type": "CPV filters for construction, roads, drainage, water, maintenance, engineering, and inspection services",
        "likely_access_method": "Use public CPV taxonomy and source-provided CPV fields; maintain ProcessEd-specific filter groups.",
        "integration_difficulty_1_5": 1,
        "commercial_value_1_5": 5,
        "legal_data_risk_1_5": 1,
        "required_auth_or_credentials": "None.",
        "likely_fields_available": "CPV code; label; parent prefix; ProcessEd category mapping; source-specific occurrence counts after live testing",
        "likely_missing_fields": "buyer intent; project scope nuance; false-positive control; language-specific title signals",
        "recommended_first_test": "Use the inventory CPV prefixes as a first ruleset, then measure false positives against 50 manually reviewed notices.",
        "live_integration_priority": "1",
        "caveat": "sample_demo research_needed; CPV is a filter/taxonomy layer, not a standalone live source.",
    },
]


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path, max_chars: int = 1400) -> str:
    if not path.exists():
        return ""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8")).strip()[:max_chars]


def clean_text(value: Any, max_length: int = 360) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text.replace("\r", " ").replace("\n", " ")[:max_length]


def clamp_1_5(value: Any, default: int) -> str:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = default
    return str(max(1, min(5, score)))


def context_summary() -> dict[str, Any]:
    opportunities = load_json(ENRICHED_OPPORTUNITIES_PATH) or load_json(DEMO_OPPORTUNITIES_PATH) or []
    sources = Counter(item.get("source", "unknown") for item in opportunities if isinstance(item, dict))
    categories = Counter(item.get("category", "unknown") for item in opportunities if isinstance(item, dict))
    return {
        "demo_opportunity_count": len(opportunities) if isinstance(opportunities, list) else 0,
        "demo_sources": dict(sources.most_common(8)),
        "demo_categories": dict(categories.most_common(8)),
        "source_inventory_excerpt": load_text(SOURCE_INVENTORY_PATH),
        "data_model_excerpt": load_text(DATA_MODEL_PATH),
        "market_brief_excerpt": load_text(MARKET_BRIEF_PATH),
    }


def build_prompt(source: dict[str, Any], summary: dict[str, Any]) -> str:
    payload = {
        "task": "Return JSON only: cautious Netherlands/EU procurement source readiness assessment for ProcessEd Intelligence.",
        "rules": [
            "Use only Gemini Flash/Flash-Lite style concise reasoning.",
            "Do not claim live source coverage, successful API access, or current data ingestion.",
            "Keep unverified source claims marked research_needed, sample_demo, or not_verified.",
            "Do not invent credentials, secrets, customer data, or concrete project IDs.",
            "Prioritize practical integration roadmap value for TenderNed, TED/EU, PPDS, Dutch public works, water, infrastructure, and maintenance sources.",
            "Return short strings suitable for CSV cells.",
        ],
        "required_keys": [
            "likely_access_method",
            "integration_difficulty_1_5",
            "commercial_value_1_5",
            "legal_data_risk_1_5",
            "required_auth_or_credentials",
            "likely_fields_available",
            "likely_missing_fields",
            "recommended_first_test",
            "live_integration_priority",
            "caveat",
            "reasoning_note",
        ],
        "source_seed": source,
        "project_context": {
            "demo_opportunity_count": summary["demo_opportunity_count"],
            "demo_sources": summary["demo_sources"],
            "demo_categories": summary["demo_categories"],
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


def dry_run_record(source: dict[str, Any], model: str, generated_at: str) -> dict[str, str]:
    record = {field: clean_text(source.get(field, "")) for field in FIELDNAMES if field not in {"vertex_status", "vertex_reasoning_note", "generated_at", "model"}}
    record["integration_difficulty_1_5"] = clamp_1_5(source.get("integration_difficulty_1_5"), 3)
    record["commercial_value_1_5"] = clamp_1_5(source.get("commercial_value_1_5"), 4)
    record["legal_data_risk_1_5"] = clamp_1_5(source.get("legal_data_risk_1_5"), 3)
    record["vertex_status"] = "dry_run"
    record["vertex_reasoning_note"] = "Dry-run heuristic only; no Vertex call was made and source access remains research_needed/not_verified."
    record["generated_at"] = generated_at
    record["model"] = model
    record["project"] = PROJECT_OUTPUT_VALUE
    return record


def vertex_record(source: dict[str, Any], model: str, generated_at: str, client: Any, types: Any, summary: dict[str, Any]) -> dict[str, str]:
    fallback = dry_run_record(source, model, generated_at)
    try:
        response = client.models.generate_content(
            model=model,
            contents=build_prompt(source, summary),
            config=build_config(types),
        )
        parsed = parse_json_object(response_text(response))
        if not parsed:
            raise ValueError("Vertex response did not contain parseable JSON.")
        record = dict(fallback)
        for key in [
            "likely_access_method",
            "required_auth_or_credentials",
            "likely_fields_available",
            "likely_missing_fields",
            "recommended_first_test",
            "live_integration_priority",
            "caveat",
        ]:
            record[key] = clean_text(parsed.get(key) or fallback[key])
        record["integration_difficulty_1_5"] = clamp_1_5(parsed.get("integration_difficulty_1_5"), int(fallback["integration_difficulty_1_5"]))
        record["commercial_value_1_5"] = clamp_1_5(parsed.get("commercial_value_1_5"), int(fallback["commercial_value_1_5"]))
        record["legal_data_risk_1_5"] = clamp_1_5(parsed.get("legal_data_risk_1_5"), int(fallback["legal_data_risk_1_5"]))
        record["vertex_status"] = "generated"
        record["vertex_reasoning_note"] = clean_text(parsed.get("reasoning_note") or "Generated by Vertex with conservative source-readiness caveats.")
        if not re.search(r"research_needed|sample_demo|not_verified", record["caveat"], re.IGNORECASE):
            record["caveat"] = clean_text(record["caveat"] + " research_needed sample_demo not_verified")
        return record
    except Exception as exc:  # Keep batch useful if one source fails.
        fallback["vertex_status"] = "error"
        fallback["vertex_reasoning_note"] = clean_text(f"Vertex enrichment failed; fallback used. {type(exc).__name__}")
        return fallback


def enrich_sources(args: argparse.Namespace) -> list[dict[str, str]]:
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    sources = BASE_SOURCES[: args.limit] if args.limit is not None else BASE_SOURCES
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

    rows = []
    for source in sources:
        if args.dry_run:
            rows.append(dry_run_record(source, args.model, generated_at))
        else:
            rows.append(vertex_record(source, args.model, generated_at, client, types, summary))
    return rows


def write_outputs(rows: list[dict[str, str]], output_json: Path, output_csv: Path, model: str) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "metadata": {
            "name": "Netherlands live source readiness",
            "data_status": DATA_STATUS,
            "model": model,
            "project": PROJECT_OUTPUT_VALUE,
            "record_count": len(rows),
            "source_inputs": [
                "docs/NETHERLANDS_SOURCE_INVENTORY.md",
                "docs/NETHERLANDS_DATA_MODEL.md",
                "docs/NETHERLANDS_MARKET_ENTRY_BRIEF.md",
                "data/dutch/demo/dutch_demo_opportunities.json",
                "data/dutch/demo/dutch_demo_opportunities_enriched.json",
            ],
        },
        "sources": rows,
    }
    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def score(row: dict[str, str], key: str) -> int:
    try:
        return int(float(row.get(key, "0") or 0))
    except ValueError:
        return 0


def integration_order(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            int(re.sub(r"\D", "", row.get("live_integration_priority", "")) or 99),
            -score(row, "commercial_value_1_5"),
            score(row, "integration_difficulty_1_5"),
            score(row, "legal_data_risk_1_5"),
        ),
    )


def write_report(rows: list[dict[str, str]], model: str, dry_run: bool, output_report: Path) -> None:
    status_counts = Counter(row.get("vertex_status", "unknown") for row in rows)
    ordered = integration_order(rows)
    mode = "dry-run heuristic" if dry_run else "Vertex AI Gemini Flash"
    no_credential_tests = [row for row in rows if re.search(r"none|manual|public|rss|taxonomy", row.get("required_auth_or_credentials", ""), re.IGNORECASE)]
    credential_tests = [row for row in rows if re.search(r"credential|username|password|api key|account|platform", row.get("required_auth_or_credentials", ""), re.IGNORECASE)]

    lines = [
        "# Netherlands Live Source Readiness",
        "",
        "Status: research_needed/sample_demo roadmap. This pack does not claim verified live TenderNed, TED/EU, PPDS, municipal, water authority, transport, or maintenance coverage.",
        "",
        "## Controlled Vertex Use",
        "",
        f"- Records assessed: {len(rows)}",
        f"- Enrichment mode: {mode}",
        f"- Model: {model}",
        "- Project reference in outputs: configured_via_GOOGLE_CLOUD_PROJECT",
        "- Cost control: `--dry-run` and `--limit N` supported; prompts are concise, low temperature, and request JSON.",
        "",
        "## Source-By-Source Assessment",
        "",
    ]
    for row in ordered:
        lines.extend(
            [
                f"### {row['source_name']}",
                "",
                f"- Scope: {row['country_scope']} | {row['coverage_type']}",
                f"- Likely access: {row['likely_access_method']}",
                f"- Difficulty/value/risk: {row['integration_difficulty_1_5']}/5, {row['commercial_value_1_5']}/5, {row['legal_data_risk_1_5']}/5",
                f"- Credentials: {row['required_auth_or_credentials']}",
                f"- Likely fields: {row['likely_fields_available']}",
                f"- Likely gaps: {row['likely_missing_fields']}",
                f"- First test: {row['recommended_first_test']}",
                f"- Caveat: {row['caveat']}",
                "",
            ]
        )

    lines.extend(["## Recommended Integration Order", ""])
    for index, row in enumerate(ordered, start=1):
        lines.append(f"{index}. {row['source_name']}: priority {row['live_integration_priority']}; value {row['commercial_value_1_5']}/5; start with `{row['recommended_first_test']}`")

    lines.extend(["", "## What Can Be Tested Without Credentials", ""])
    for row in no_credential_tests:
        lines.append(f"- {row['source_name']}: {row['recommended_first_test']}")

    lines.extend(["", "## What Needs Credentials Or API Keys", ""])
    for row in credential_tests:
        lines.append(f"- {row['source_name']}: {row['required_auth_or_credentials']}")

    lines.extend(
        [
            "",
            "## Data Model Gaps",
            "",
            "- Add source notice IDs, source publication version, attribution/licence fields, and retrieval timestamp before live ingestion.",
            "- Add buyer entity normalization, buyer category, aliases, official identifiers where available, and duplicate detection across TenderNed/TED/local portals.",
            "- Add language detection confidence, translation review status, document URL provenance, CPV parent/child expansion, and live-source freshness status.",
            "- Add `source_access_status` values such as `manual_verified`, `api_verified`, `credentials_required`, `terms_review_required`, and `not_verified`.",
            "",
            "## Legal And Data Caveats",
            "",
            "- Treat this as a roadmap, not a legal opinion or a verified live source integration.",
            "- Review source terms, robots guidance, attribution requirements, rate limits, and redistribution limits before scheduled collection.",
            "- Keep credentials, raw source payloads, platform accounts, service account files, and customer notes outside Git.",
            "- Avoid personal contact enrichment until a privacy review defines lawful basis, retention, and suppression handling.",
            "",
            "## Next 7-Day Implementation Plan",
            "",
            "1. Day 1: Run manual TenderNed and TED field checks for construction, water, roads, drainage, maintenance, engineering, and inspection CPVs.",
            "2. Day 2: Create a source field mapping table from the checked notices to the Netherlands data model.",
            "3. Day 3: Build a no-credentials TED published-notice prototype and record only normalized sample outputs.",
            "4. Day 4: Request/confirm TenderNed API access path and keep any credentials outside the repository.",
            "5. Day 5: Build buyer taxonomy for municipalities, provinces, water authorities, Rijkswaterstaat, ports, and transport authorities.",
            "6. Day 6: Run a 50-notice manual false-positive review for CPV groups and buyer categories.",
            "7. Day 7: Produce a founder-ready weekly digest mock with caveats and a go/no-go list for live ingestion.",
            "",
            "## Commercial Product Impact",
            "",
            "This moves ProcessEd Intelligence from a Netherlands demo pack toward a credible integration roadmap. The commercial upside is a clearer first wedge: verified TenderNed/TED discovery, Dutch buyer normalization, English summaries, source caveats, and CPV-led prioritisation for contractors and suppliers considering Netherlands or Benelux public works growth.",
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
    parser = argparse.ArgumentParser(description="Assess Netherlands/EU procurement source readiness with optional Vertex AI.")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic local readiness records without calling Vertex.")
    parser.add_argument("--limit", type=int, default=None, help="Limit sources processed for controlled Vertex batches.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini Flash or Flash-Lite model name.")
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON_PATH, help="Output readiness JSON path.")
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV_PATH, help="Output readiness CSV path.")
    parser.add_argument("--output-report", type=Path, default=REPORT_PATH, help="Output readiness Markdown report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be a positive integer.")
    if "pro" in args.model.lower():
        raise SystemExit("Use Gemini Flash or Flash-Lite only for this controlled enrichment workflow.")

    rows = enrich_sources(args)
    write_outputs(rows, args.output_json, args.output_csv, args.model)
    write_report(rows, args.model, args.dry_run, args.output_report)
    statuses = Counter(row.get("vertex_status", "unknown") for row in rows)
    print(
        "Netherlands source readiness complete: "
        f"{len(rows)} sources, statuses {dict(sorted(statuses.items()))}, "
        f"json {args.output_json}, csv {args.output_csv}."
    )


if __name__ == "__main__":
    main()
