from __future__ import annotations

import csv
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

DOCS = [
    "docs/PILOT_VALIDATION_FRAMEWORK.md",
    "docs/DEMO_SCRIPT.md",
    "docs/PILOT_SUCCESS_METRICS.md",
    "docs/PILOT_CONVERSION_EMAILS.md",
    "docs/LINKEDIN_OUTREACH_PLAYBOOK.md",
]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_all_pilot_docs_exist() -> None:
    for path in DOCS:
        assert (REPO_ROOT / path).exists(), path


def test_pilot_csv_template_has_required_columns() -> None:
    path = REPO_ROOT / "data" / "pilot" / "pilot_tracker_TEMPLATE.csv"

    with path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = set(reader.fieldnames or [])

    required = {
        "pilot_id",
        "company",
        "contact_name",
        "persona",
        "demo_completed",
        "tenders_reviewed",
        "relevant_tenders",
        "buyers_tracked",
        "timing_ready_reviewed",
        "time_saved_hours",
        "buyer_insight_score",
        "opportunity_quality_score",
        "demo_to_pilot_status",
        "pilot_to_paid_status",
        "next_action",
    }
    assert required.issubset(fieldnames)


def test_linkedin_templates_exist() -> None:
    path = REPO_ROOT / "data" / "outreach" / "linkedin_sequence_templates.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["mode"] == "manual_copy_paste_only"
    assert {
        "connection_message",
        "follow_up_1",
        "follow_up_2",
        "demo_ask",
        "soft_close",
    }.issubset(payload["templates"])


def test_docs_mention_hostinger_live_and_vps_unverified() -> None:
    combined = "\n".join(read(path) for path in DOCS).casefold()

    assert "hostinger" in combined
    assert "dashboard is live" in combined
    assert "vps production pipeline is still unverified" in combined


def test_docs_do_not_claim_paying_clients_exist() -> None:
    combined = "\n".join(read(path) for path in DOCS).casefold()

    forbidden_positive_claims = [
        "we have paying clients",
        "existing paying clients",
        "current paying clients",
        "our paying clients",
        "paid customers already",
    ]
    for claim in forbidden_positive_claims:
        assert claim not in combined


def test_docs_do_not_claim_guaranteed_wins() -> None:
    combined = "\n".join(read(path) for path in DOCS).casefold()

    forbidden_positive_claims = [
        "we guarantee tender wins",
        "processed guarantees tender wins",
        "this guarantees tender wins",
        "will win tenders",
        "will win contracts",
    ]
    for claim in forbidden_positive_claims:
        assert claim not in combined
