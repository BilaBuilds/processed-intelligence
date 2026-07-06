from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "linkedin_outreach_prep.py"


def test_script_creates_ranked_buyers_template_if_input_missing(tmp_path: Path) -> None:
    missing_input = tmp_path / "missing_ranked_buyers.csv"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(missing_input)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    template = REPO_ROOT / "data" / "outreach" / "ranked_buyers_TEMPLATE.csv"
    assert template.exists()
    assert "Created template" in result.stdout or "Input CSV not found" in result.stdout

    with template.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = set(reader.fieldnames or [])

    assert {
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
    }.issubset(fieldnames)


def test_script_generates_manual_queue_without_blocked_claims(tmp_path: Path) -> None:
    input_path = tmp_path / "ranked_buyers.csv"
    output_path = tmp_path / "linkedin_manual_queue.csv"
    input_path.write_text(
        "\n".join(
            [
                "name,first_name,last_name,company,title,linkedin_url,email,sector,region,buyer_score,notes",
                "Jane Smith,Jane,Smith,Example Civils Ltd,Bid Manager,https://linkedin.test/jane,jane@example.com,civils,NL,85,Good fit",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    with output_path.open("r", encoding="utf-8", newline="") as output_file:
        rows = list(csv.DictReader(output_file))

    assert len(rows) == 1
    row = rows[0]
    assert row["priority"] == "P1"
    assert row["connection_message"]
    assert row["follow_up_1"]
    assert row["follow_up_2"]
    assert row["demo_ask"]
    assert row["soft_close"]

    generated = " ".join(
        row[column]
        for column in [
            "connection_message",
            "follow_up_1",
            "follow_up_2",
            "demo_ask",
            "soft_close",
        ]
    ).casefold()
    assert "guaranteed win" not in generated
    assert "guaranteed wins" not in generated
    assert "guaranteed tender wins" not in generated
    assert "paying clients" not in generated
    assert "no messages were sent" not in generated


def test_script_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "manual LinkedIn outreach queue" in result.stdout
