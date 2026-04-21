from __future__ import annotations

import json
from pathlib import Path

from src.buyer_intel import _load_shortlist_opportunities, attach_briefs


def test_shortlist_parsing_uses_canonical_opportunities_key(tmp_path: Path) -> None:
    shortlist_file = tmp_path / "decision_shortlist.json"
    shortlist_file.write_text(
        json.dumps(
            {
                "opportunities": [
                    {"buyer_name": "Environment Agency", "title": "Flood package"}
                ],
                "tenders": [
                    {"buyer_name": "Wrong Buyer", "title": "Should not be read"}
                ],
            }
        ),
        encoding="utf-8",
    )

    opportunities = _load_shortlist_opportunities(shortlist_file)

    assert len(opportunities) == 1
    assert opportunities[0]["buyer_name"] == "Environment Agency"


def test_brief_attachment_works_in_normal_post_dedupe_flow(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    run_dir = tmp_path / "data" / "runs" / "2026-04-18_120000"
    state_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)

    (state_dir / "buyer_briefs.json").write_text(
        json.dumps(
            {
                "environment agency": {
                    "buyer_name": "Environment Agency",
                    "brief": "Regular flood and civils commissioning buyer.",
                    "record_count": 4,
                    "synthesised_at": "2026-04-18T00:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    deduped_file = run_dir / "new_tenders.json"
    deduped_file.write_text(
        json.dumps(
            {
                "opportunities": [
                    {"buyer_name": "Environment Agency", "title": "Flood alleviation works"}
                ]
            }
        ),
        encoding="utf-8",
    )

    result = attach_briefs({"state_dir": state_dir, "deduped_file": deduped_file})
    payload = json.loads(deduped_file.read_text(encoding="utf-8"))

    assert result["buyer_intel_briefs_attached"] == 1
    assert payload["opportunities"][0]["buyer_intel_summary"] == "Regular flood and civils commissioning buyer."
