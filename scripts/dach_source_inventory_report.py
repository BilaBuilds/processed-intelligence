from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "data" / "dach" / "source_inventory_TEMPLATE.json"
REPORT_PATH = ROOT / "data" / "dach" / "source_inventory_report.md"

REQUIRED_SOURCE_FIELDS = {
    "country",
    "source_name",
    "source_type",
    "base_url",
    "status",
    "auth_required",
    "fields_expected",
    "scraper_difficulty",
    "commercial_priority",
    "notes",
}

REQUIRED_EXPECTED_FIELDS = {
    "title",
    "buyer",
    "country",
    "region",
    "deadline",
    "value",
    "currency",
    "cpv",
    "url",
    "source",
    "notice_id",
    "published_at",
    "description",
}

COUNTRY_ORDER = ["Germany", "Austria", "Switzerland"]


def load_inventory() -> dict:
    with INVENTORY_PATH.open(encoding="utf-8") as inventory_file:
        return json.load(inventory_file)


def validate_inventory(inventory: dict) -> list[dict]:
    sources = inventory.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Inventory must contain a non-empty 'sources' list.")

    for index, source in enumerate(sources, start=1):
        missing = REQUIRED_SOURCE_FIELDS - source.keys()
        if missing:
            raise ValueError(
                f"Source #{index} is missing required fields: {sorted(missing)}"
            )

        expected_fields = set(source["fields_expected"])
        missing_expected = REQUIRED_EXPECTED_FIELDS - expected_fields
        if missing_expected:
            raise ValueError(
                f"{source['source_name']} is missing expected fields: "
                f"{sorted(missing_expected)}"
            )

    return sources


def next_actions_for(source: dict) -> list[str]:
    return [
        f"Verify terms and usage permissions for {source['source_name']}.",
        f"Confirm access mode, authentication, rate limits, and useful fields for {source['source_name']}.",
        f"Check duplicate risk and stale notice behavior for {source['source_name']}.",
    ]


def build_report(sources: list[dict]) -> str:
    counts = Counter(source["country"] for source in sources)
    grouped = defaultdict(list)
    for source in sources:
        grouped[source["country"]].append(source)

    high_priority = [
        source for source in sources if source["commercial_priority"] == "high"
    ]
    unverified = [source for source in sources if source["status"] == "unverified"]

    lines = [
        "# DACH Source Inventory Report",
        "",
        "Generated from `data/dach/source_inventory_TEMPLATE.json`.",
        "",
        "No scraping was performed. This report is generated from local static inventory data only.",
        "",
        "## Source Count By Country",
        "",
    ]

    for country in COUNTRY_ORDER:
        lines.append(f"- {country}: {counts[country]}")

    lines.extend(["", "## High-Priority Sources", ""])
    for source in high_priority:
        lines.append(f"- {source['country']}: {source['source_name']}")

    lines.extend(["", "## Unverified Sources", ""])
    for source in unverified:
        lines.append(f"- {source['country']}: {source['source_name']}")

    lines.extend(["", "## Next Verification Actions", ""])
    for source in sources:
        lines.append(f"### {source['country']} - {source['source_name']}")
        for action in next_actions_for(source):
            lines.append(f"- {action}")
        lines.append("")

    lines.append("## Sources By Country")
    lines.append("")
    for country in COUNTRY_ORDER:
        lines.append(f"### {country}")
        for source in grouped[country]:
            lines.extend(
                [
                    f"- Source: {source['source_name']}",
                    f"  - Type: {source['source_type']}",
                    f"  - Status: {source['status']}",
                    f"  - Auth required: {source['auth_required']}",
                    f"  - Scraper difficulty: {source['scraper_difficulty']}",
                    f"  - Commercial priority: {source['commercial_priority']}",
                    f"  - Base URL: {source['base_url'] or 'TBD'}",
                    f"  - Notes: {source['notes']}",
                ]
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    inventory = load_inventory()
    sources = validate_inventory(inventory)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(sources), encoding="utf-8")
    print(f"Generated {REPORT_PATH}")


if __name__ == "__main__":
    main()
