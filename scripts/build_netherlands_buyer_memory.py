from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OPPORTUNITIES_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities.json"
ENRICHED_OPPORTUNITIES_PATH = ROOT / "data" / "dutch" / "demo" / "dutch_demo_opportunities_enriched.json"
TARGETS_PATH = ROOT / "data" / "outreach" / "netherlands_company_targets_enriched.json"
OUTPUT_PATH = ROOT / "data" / "dutch" / "buyer_memory" / "netherlands_buyer_memory.json"

DATA_STATUS = "sample_demo_research_needed_not_verified_live_coverage"
CAVEAT = "sample_demo research_needed not_verified; derived from demo opportunities, not verified live buyer coverage"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: Any, max_length: int = 260) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()[:max_length]


def buyer_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"nl-buyer-{slug[:54]}"


def buyer_type(name: str, country: str, source: str) -> str:
    lowered = name.lower()
    if "gemeente" in lowered:
        return "municipality"
    if "provincie" in lowered:
        return "province"
    if "waterschap" in lowered:
        return "water_authority"
    if "rijkswaterstaat" in lowered:
        return "national_infrastructure_agency"
    if "port" in lowered:
        return "port_or_logistics_authority_sample"
    if "eu" in country.lower() or "ted" in source.lower():
        return "eu_or_cross_border_sample"
    return "public_buyer_sample"


def procurement_theme(categories: list[str], titles: list[str]) -> str:
    category_set = set(categories)
    if "water" in category_set or any("drain" in title.lower() or "flood" in title.lower() for title in titles):
        return "water, drainage, flood resilience, and civil infrastructure"
    if "roads" in category_set or "maintenance" in category_set:
        return "roads, maintenance frameworks, surfacing, and asset repair"
    if "infrastructure" in category_set:
        return "major infrastructure, ports, utilities, and transport works"
    if "public works" in category_set or "civils" in category_set:
        return "municipal public works, civils, and public realm delivery"
    return "public procurement opportunity monitoring"


def likely_supplier_fit(categories: list[str], target_segments: list[str]) -> str:
    fits = []
    category_set = set(categories)
    if "water" in category_set or "drainage" in category_set:
        fits.append("water/public works suppliers")
    if "roads" in category_set or "maintenance" in category_set:
        fits.append("maintenance/framework contractors")
    if "public works" in category_set or "civils" in category_set:
        fits.append("Dutch civils contractors")
    if "infrastructure" in category_set:
        fits.append("Dutch infrastructure contractors")
    if any("EU" in segment or "DACH" in segment or "UK" in segment for segment in target_segments):
        fits.append("UK/DACH contractors with possible Netherlands/EU interest")
    return "; ".join(dict.fromkeys(fits or ["engineering consultancies"]))


def timing_signal(deadlines: list[str], urgencies: list[str]) -> str:
    urgency_counts = Counter(urgencies)
    if urgency_counts.get("high", 0):
        return "near-term sample opportunity pressure; manually verify dates before action"
    if deadlines:
        return f"sample deadlines range around {min(deadlines)} to {max(deadlines)}; not live verified"
    return "no live timing verified"


def relationship_angle(buyer_name: str, buyer_kind: str) -> str:
    if buyer_kind == "municipality":
        return f"Track {buyer_name} as a municipal public works buyer and validate recurring CPV patterns."
    if buyer_kind == "water_authority":
        return f"Use {buyer_name} as a water-resilience validation buyer for drainage, pumping, and treatment works."
    if buyer_kind == "national_infrastructure_agency":
        return f"Treat {buyer_name} as a strategic infrastructure buyer requiring source and compliance validation."
    if buyer_kind == "province":
        return f"Watch {buyer_name} for roads, structures, and maintenance framework patterns."
    return f"Use {buyer_name} as a sample buyer pattern until live source coverage is verified."


def load_target_segments(path: Path) -> list[str]:
    if not path.exists():
        return []
    data = load_json(path)
    targets = data.get("targets", []) if isinstance(data, dict) else []
    return sorted({clean_text(target.get("segment")) for target in targets if isinstance(target, dict) and target.get("segment")})


def build_memory(opportunities: list[dict[str, Any]], target_segments: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in opportunities:
        grouped[clean_text(item.get("buyer", "Unknown buyer"))].append(item)

    records = []
    for name, items in sorted(grouped.items()):
        categories = sorted({clean_text(item.get("category")) for item in items if item.get("category")})
        sources = sorted({clean_text(item.get("source")) for item in items if item.get("source")})
        titles = [clean_text(item.get("title")) for item in items]
        deadlines = sorted(clean_text(item.get("deadline")) for item in items if item.get("deadline"))
        urgencies = [clean_text(item.get("urgency")).lower() for item in items if item.get("urgency")]
        country = clean_text(items[0].get("country", "Netherlands"))
        source = clean_text(items[0].get("source", "sample"))
        kind = buyer_type(name, country, source)
        record = {
            "buyer_id": buyer_id(name),
            "buyer_name": name,
            "country": country,
            "region": clean_text(items[0].get("region", "")),
            "buyer_type": kind,
            "categories": categories,
            "observed_opportunity_count": len(items),
            "sample_sources": sources,
            "procurement_theme": procurement_theme(categories, titles),
            "likely_supplier_fit": likely_supplier_fit(categories, target_segments),
            "timing_signal": timing_signal(deadlines, urgencies),
            "relationship_angle": relationship_angle(name, kind),
            "recommended_watch_action": "Use as a buyer-memory seed, then validate via TenderNed/TED before commercial claims.",
            "data_status": DATA_STATUS,
            "caveat": CAVEAT,
        }
        records.append(record)
    return records


def write_output(records: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "name": "Netherlands buyer memory",
            "data_status": DATA_STATUS,
            "project": "configured_via_GOOGLE_CLOUD_PROJECT",
            "record_count": len(records),
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "source_inputs": [
                "data/dutch/demo/dutch_demo_opportunities.json",
                "data/dutch/demo/dutch_demo_opportunities_enriched.json",
                "data/outreach/netherlands_company_targets_enriched.json",
            ],
        },
        "buyers": records,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Netherlands buyer-memory records from sample/demo opportunities.")
    parser.add_argument("--input", type=Path, default=OPPORTUNITIES_PATH, help="Input Dutch demo opportunities JSON path.")
    parser.add_argument("--targets", type=Path, default=TARGETS_PATH, help="Input enriched target-account JSON path.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output buyer-memory JSON path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    opportunities = load_json(args.input)
    if not isinstance(opportunities, list):
        raise SystemExit("Input opportunities must be a JSON list.")
    target_segments = load_target_segments(args.targets)
    records = build_memory(opportunities, target_segments)
    write_output(records, args.output)
    print(f"Netherlands buyer memory built: {len(records)} buyers, output {args.output}.")


if __name__ == "__main__":
    main()
