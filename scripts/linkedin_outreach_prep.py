from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "data" / "outreach" / "ranked_buyers.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "outreach" / "linkedin_manual_queue.csv"
DEFAULT_TEMPLATE = REPO_ROOT / "data" / "outreach" / "ranked_buyers_TEMPLATE.csv"
TEMPLATE_JSON = REPO_ROOT / "data" / "outreach" / "linkedin_sequence_templates.json"

INPUT_COLUMNS = [
    "name",
    "first_name",
    "last_name",
    "company",
    "title",
    "linkedin_url",
    "email",
    "sector",
    "region",
    "buyer_score",
    "notes",
]

OUTPUT_COLUMNS = [
    *INPUT_COLUMNS,
    "priority",
    "connection_message",
    "follow_up_1",
    "follow_up_2",
    "demo_ask",
    "soft_close",
]

BLOCKED_CLAIMS = (
    "guaranteed win",
    "guaranteed wins",
    "guarantee tender wins",
    "guaranteed tender wins",
    "paying clients",
    "automated sending",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a manual LinkedIn outreach queue. This script does not send "
            "messages, does not use Apollo, and does not require internet access."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Ranked buyer CSV. If missing, a ranked_buyers_TEMPLATE.csv is created.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Manual LinkedIn queue CSV to write when input exists.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)

    if not input_path.exists():
        template_path = DEFAULT_TEMPLATE
        write_ranked_buyers_template(template_path)
        print(f"Input CSV not found. Created template: {template_path}")
        return 0

    rows = read_rows(input_path)
    templates = load_templates(TEMPLATE_JSON)
    output_rows = [build_queue_row(row, templates) for row in rows]
    assert_no_blocked_claims(output_rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote manual LinkedIn queue: {output_path}")
    print("Manual copy-paste only. No messages were sent.")
    return 0


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def write_ranked_buyers_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", encoding="utf-8", newline="") as template_file:
        writer = csv.DictWriter(template_file, fieldnames=INPUT_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "name": "Alex Morgan",
                "first_name": "Alex",
                "last_name": "Morgan",
                "company": "Example Civils Ltd",
                "title": "Bid Manager",
                "linkedin_url": "https://www.linkedin.com/in/example",
                "email": "alex@example.com",
                "sector": "civils",
                "region": "UK",
                "buyer_score": "75",
                "notes": "Template row only; replace before outreach.",
            }
        )


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as input_file:
        reader = csv.DictReader(input_file)
        return [{column: (row.get(column) or "").strip() for column in INPUT_COLUMNS} for row in reader]


def load_templates(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8") as template_file:
        payload = json.load(template_file)
    templates = payload.get("templates", {})
    if not isinstance(templates, dict):
        raise ValueError("linkedin_sequence_templates.json missing templates object")
    required = {"connection_message", "follow_up_1", "follow_up_2", "demo_ask", "soft_close"}
    missing = required - set(templates)
    if missing:
        raise ValueError(f"LinkedIn templates missing: {', '.join(sorted(missing))}")
    return {key: str(value) for key, value in templates.items()}


def build_queue_row(row: dict[str, str], templates: dict[str, str]) -> dict[str, str]:
    first_name = first_name_for(row)
    values: dict[str, Any] = {
        **row,
        "first_name": first_name,
        "company": row.get("company") or "your team",
        "title": row.get("title") or "your role",
        "sector": row.get("sector") or "construction",
        "region": row.get("region") or "UK/NL",
    }
    return {
        **row,
        "first_name": first_name,
        "priority": priority_for(row.get("buyer_score", "")),
        "connection_message": templates["connection_message"].format(**values),
        "follow_up_1": templates["follow_up_1"].format(**values),
        "follow_up_2": templates["follow_up_2"].format(**values),
        "demo_ask": templates["demo_ask"].format(**values),
        "soft_close": templates["soft_close"].format(**values),
    }


def first_name_for(row: dict[str, str]) -> str:
    if row.get("first_name"):
        return row["first_name"]
    name = row.get("name", "").strip()
    if name:
        return name.split()[0]
    email = row.get("email", "")
    if "@" in email:
        return email.split("@", maxsplit=1)[0].split(".", maxsplit=1)[0].title()
    return "there"


def priority_for(value: str) -> str:
    try:
        score = float(value)
    except ValueError:
        return "P3"
    if score >= 80:
        return "P1"
    if score >= 60:
        return "P2"
    return "P3"


def assert_no_blocked_claims(rows: list[dict[str, str]]) -> None:
    text = "\n".join(
        str(value).casefold()
        for row in rows
        for key, value in row.items()
        if key in {"connection_message", "follow_up_1", "follow_up_2", "demo_ask", "soft_close"}
    )
    blocked = [claim for claim in BLOCKED_CLAIMS if claim in text]
    if blocked:
        raise ValueError(f"Generated messages include blocked claims: {', '.join(blocked)}")


if __name__ == "__main__":
    raise SystemExit(main())
