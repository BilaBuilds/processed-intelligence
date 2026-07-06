from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities.json"
OUTPUT_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities_enriched.json"


def load_opportunities(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as input_file:
        data = json.load(input_file)
    if not isinstance(data, list):
        raise ValueError("Dutch demo opportunities input must be a list.")
    return data


def dry_run_enrich(opportunities: list[dict]) -> list[dict]:
    enriched = []
    for item in opportunities:
        updated = dict(item)
        updated["vertex_enrichment"] = {
            "status": "dry_run_not_called",
            "note": "No Vertex request was made. Demo data remains unverified live coverage.",
        }
        enriched.append(updated)
    return enriched


def vertex_enrich(opportunities: list[dict], project: str, location: str, model: str) -> list[dict]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "Vertex enrichment requires the google-genai package. Use --dry-run for offline validation."
        ) from exc

    client = genai.Client(vertexai=True, project=project, location=location)
    enriched = []
    for item in opportunities:
        prompt = (
            "You are enriching a sample Netherlands procurement demo record for ProcessEd Intelligence. "
            "Write one concise English qualification note for a sales or bid team. Ground the note only "
            "in the JSON fields provided, mention the likely capability or partner angle, and do not "
            "claim live verification, eligibility facts, or requirements that are not in the data.\n\n"
            + json.dumps(
                {
                    "title": item["title"],
                    "buyer": item["buyer"],
                    "category": item["category"],
                    "cpv_codes": item["cpv_codes"],
                    "summary_en": item["summary_en"],
                    "recommended_action": item["recommended_action"],
                    "buyer_signal": item["buyer_signal"],
                    "expansion_relevance": item["expansion_relevance"],
                    "data_status": item["data_status"],
                },
                ensure_ascii=True,
            )
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=192,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        note = (response.text or "").strip()
        if not note and response.candidates:
            parts = response.candidates[0].content.parts if response.candidates[0].content else []
            note = " ".join((part.text or "").strip() for part in parts if getattr(part, "text", None)).strip()
        updated = dict(item)
        updated["vertex_enrichment"] = {
            "status": "generated",
            "model": model,
            "project": "configured_via_GOOGLE_CLOUD_PROJECT",
            "location": location,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "qualification_note": note,
            "data_status": "sample_demo_not_verified_live_coverage",
        }
        enriched.append(updated)
    return enriched


def write_output(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optionally enrich the Dutch demo fixture with Vertex AI.")
    parser.add_argument("--dry-run", action="store_true", help="Write an offline preview without calling Vertex.")
    parser.add_argument("--limit", type=int, default=None, help="Limit records processed for controlled Vertex runs.")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Vertex model name to use when not in dry-run mode.")
    parser.add_argument("--input", type=Path, default=INPUT_PATH, help="Input opportunity fixture path.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output enriched fixture path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    opportunities = load_opportunities(args.input)
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be a positive integer.")
        opportunities = opportunities[: args.limit]
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION")

    if args.dry_run:
        enriched = dry_run_enrich(opportunities)
        mode = "dry run"
    else:
        if not project or not location:
            raise SystemExit("GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are required unless --dry-run is used.")
        enriched = vertex_enrich(opportunities, project=project, location=location, model=args.model)
        mode = "vertex"

    write_output(args.output, enriched)
    print(f"Dutch demo Vertex enrichment {mode}: wrote {len(enriched)} records to {args.output}")


if __name__ == "__main__":
    main()
