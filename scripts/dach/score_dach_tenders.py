from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


INPUT_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_tenders.json"
SCORED_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_scored.json"
SUMMARY_PATH = ROOT / "data" / "dach" / "demo" / "dach_demo_score_summary.json"

SCORING_VERSION = "dach_fixture_scoring_v0_2"
DISCLAIMER = (
    "DACH scoring demo generated from fixture data. No live scraping performed. "
    "Not bid advice."
)

MAJOR_CIVILS_SIGNALS = [
    "drainage",
    "road",
    "bridge",
    "groundworks",
    "civil engineering",
    "utilities",
    "wastewater",
    "infrastructure",
]

CONSTRUCTION_WORKS_SIGNALS = [
    "concrete",
    "maintenance",
    "refurbishment",
    "public building",
    "school",
    "school refurbishment",
    "framework",
    "term contract",
    "repair",
    "construction",
    "building works",
]

NEGATIVE_SIGNALS = [
    "pure it",
    "software only",
    "office supplies",
    "consulting only",
    "vehicles only",
    "medical equipment",
    "legal services",
    "catering",
    "cleaning only",
]

PRIORITIES = {"HIGH", "MEDIUM", "LOW", "MONITOR"}


def load_tenders() -> list[dict[str, Any]]:
    with INPUT_PATH.open(encoding="utf-8") as tender_file:
        return json.load(tender_file)


def combined_text(tender: dict[str, Any]) -> str:
    fields = [
        tender.get("title", ""),
        tender.get("description", ""),
        " ".join(tender.get("cpv_codes", []) or []),
    ]
    return " ".join(str(field) for field in fields).lower()


def parse_deadline(value: Any) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def score_value(value: Any, reasons: list[str]) -> int:
    if value is None:
        reasons.append("Value not published")
        return 0

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        reasons.append("Value not published")
        return 0

    if numeric_value >= 1_000_000:
        reasons.append("High-value opportunity")
        return 10

    if numeric_value >= 250_000:
        reasons.append("Material contract value")
        return 6

    reasons.append("Relevant smaller works")
    return 5


def deadline_reasons(deadline: Any, now: datetime, reasons: list[str]) -> tuple[int, bool]:
    parsed_deadline = parse_deadline(deadline)
    if parsed_deadline is None:
        reasons.append("Watchlist timing")
        return 0, False

    days_until_deadline = (parsed_deadline.date() - now.date()).days
    if days_until_deadline < 0:
        reasons.append("Expired/stale notice")
        return 0, True

    if days_until_deadline <= 14:
        reasons.append("Urgent deadline")
        return 8, False

    if days_until_deadline <= 45:
        reasons.append("Timing-ready review window")
        return 10, False

    reasons.append("Watchlist timing")
    return 5, False


def signal_score(tender: dict[str, Any], reasons: list[str]) -> int:
    text = combined_text(tender)
    major_signals = [signal for signal in MAJOR_CIVILS_SIGNALS if signal in text]
    works_signals = [signal for signal in CONSTRUCTION_WORKS_SIGNALS if signal in text]
    negatives = [signal for signal in NEGATIVE_SIGNALS if signal in text]

    if major_signals:
        reasons.append(
            "Infrastructure/civils signal: "
            + ", ".join(sorted(set(major_signals))[:4])
        )

    if "drainage" in major_signals or "wastewater" in major_signals:
        reasons.append("Drainage or wastewater works")

    recurring_signals = {"framework", "term contract", "maintenance"} & set(works_signals)
    if recurring_signals:
        reasons.append("Framework or recurring maintenance signal")

    if works_signals:
        reasons.append(
            "Construction/building works signal: "
            + ", ".join(sorted(set(works_signals))[:4])
        )

    if negatives:
        reasons.append("Non-core signal: " + ", ".join(sorted(set(negatives))[:3]))

    score = min(70, len(set(major_signals)) * 20 + len(set(works_signals)) * 12)
    score -= min(50, len(set(negatives)) * 20)
    return max(0, score)


def priority_for(score: int, expired: bool) -> str:
    if expired or score == 0:
        return "MONITOR"
    if score >= 70:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


def next_action_for(priority: str) -> str:
    if priority == "HIGH":
        return "Review for pilot shortlist"
    if priority == "MEDIUM":
        return "Review if geography and capacity fit"
    if priority == "LOW":
        return "Keep on watchlist"
    return "Monitor only"


def score_tender(tender: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = ["Fixture-only demo record"]

    score = signal_score(tender, reasons)
    score += score_value(tender.get("value"), reasons)
    timing_score, expired = deadline_reasons(tender.get("deadline"), now, reasons)
    score += timing_score
    score = max(0, min(100, int(score)))

    priority = priority_for(score, expired)

    scored = dict(tender)
    scored.update(
        {
            "fit_score": score,
            "priority": priority,
            "reasons": reasons,
            "next_action": next_action_for(priority),
            "scoring_version": SCORING_VERSION,
        }
    )
    return scored


def build_summary(scored_tenders: list[dict[str, Any]]) -> dict[str, Any]:
    count_by_country = dict(
        sorted(Counter(tender["country"] for tender in scored_tenders).items())
    )
    count_by_priority = {
        priority: sum(1 for tender in scored_tenders if tender["priority"] == priority)
        for priority in sorted(PRIORITIES)
    }
    total_score = sum(tender["fit_score"] for tender in scored_tenders)
    total_tenders = len(scored_tenders)

    return {
        "total_tenders": total_tenders,
        "count_by_country": count_by_country,
        "count_by_priority": count_by_priority,
        "average_fit_score": round(total_score / total_tenders, 2) if total_tenders else 0,
        "high_signal_count": sum(
            1 for tender in scored_tenders if tender["fit_score"] >= 70
        ),
        "timing_ready_count": sum(
            1
            for tender in scored_tenders
            if "Timing-ready review window" in tender["reasons"]
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scoring_version": SCORING_VERSION,
        "disclaimer": DISCLAIMER,
    }


def export_scored_demo() -> dict[str, Any]:
    tenders = load_tenders()
    scored_tenders = [score_tender(tender) for tender in tenders]
    summary = build_summary(scored_tenders)

    SCORED_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCORED_PATH.write_text(
        json.dumps(scored_tenders, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "scored_path": str(SCORED_PATH),
        "summary_path": str(SUMMARY_PATH),
        "summary": summary,
    }


def main() -> None:
    result = export_scored_demo()
    print(f"Scored {result['summary']['total_tenders']} DACH demo tenders")
    print(f"Scored JSON: {result['scored_path']}")
    print(f"Summary: {result['summary_path']}")


if __name__ == "__main__":
    main()
