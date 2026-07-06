from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dach.dach_demo_fixtures import DACH_DEMO_FIXTURES, DEMO_SOURCE
from scripts.dach.normalize_dach_tender import normalize_dach_tender


OUTPUT_DIR = ROOT / "data" / "dach" / "demo"
JSON_PATH = OUTPUT_DIR / "dach_demo_tenders.json"
JSONL_PATH = OUTPUT_DIR / "dach_demo_tenders.jsonl"
SUMMARY_PATH = OUTPUT_DIR / "dach_demo_summary.json"

DISCLAIMER = "DACH demo generated from fixture data. No live scraping performed."


def build_demo_tenders() -> list[dict]:
    return [
        normalize_dach_tender(raw, DEMO_SOURCE, raw["country"])
        for raw in DACH_DEMO_FIXTURES
    ]


def build_summary(tenders: list[dict]) -> dict:
    count_by_country = dict(sorted(Counter(tender["country"] for tender in tenders).items()))
    return {
        "total_tenders": len(tenders),
        "countries": sorted(count_by_country),
        "count_by_country": count_by_country,
        "source": DEMO_SOURCE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": DISCLAIMER,
    }


def export_demo() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tenders = build_demo_tenders()
    summary = build_summary(tenders)

    JSON_PATH.write_text(
        json.dumps(tenders, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    JSONL_PATH.write_text(
        "".join(json.dumps(tender, ensure_ascii=False) + "\n" for tender in tenders),
        encoding="utf-8",
    )
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "json": str(JSON_PATH),
        "jsonl": str(JSONL_PATH),
        "summary": str(SUMMARY_PATH),
        "summary_data": summary,
    }


def main() -> None:
    result = export_demo()
    print(f"Exported {result['summary_data']['total_tenders']} DACH demo tenders")
    print(f"JSON: {result['json']}")
    print(f"JSONL: {result['jsonl']}")
    print(f"Summary: {result['summary']}")


if __name__ == "__main__":
    main()
