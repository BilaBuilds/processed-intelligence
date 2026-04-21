from __future__ import annotations

import json
from pathlib import Path

import scripts.build_dashboard_bundle as bundle


def test_dashboard_bundle_ingests_timing_artifacts(tmp_path: Path, monkeypatch) -> None:
    base_dir = tmp_path
    runs_dir = base_dir / "data" / "runs"
    state_dir = base_dir / "state"
    config_dir = base_dir / "config"
    buyers_dir = base_dir / "openclaw_workspace" / "buyers"
    run_dir = runs_dir / "2026-04-18_120000"
    run_dir.mkdir(parents=True)
    state_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    buyers_dir.mkdir(parents=True)

    (run_dir / "run_manifest.json").write_text(
        json.dumps({"run_id": run_dir.name, "status": "success", "finished_at": "2026-04-18T12:00:00+00:00"}),
        encoding="utf-8",
    )
    (run_dir / "decision_shortlist.json").write_text(json.dumps({"opportunities": []}), encoding="utf-8")
    (run_dir / "context_tenders.jsonl").write_text("", encoding="utf-8")
    (run_dir / "buyer_watchlist.json").write_text(
        json.dumps(
            [
                {
                    "buyer_name": "Environment Agency",
                    "activity_30d": 1,
                    "activity_90d": 2,
                    "total_notices": 5,
                    "typical_value": 450000,
                    "typical_value_label": "£250k – £500k",
                    "top_categories": ["drainage"],
                    "top_regions": ["South East"],
                    "recent_match_count": 2,
                    "fit_to_client": 74,
                    "outreach_priority": "hot",
                    "action_note": "Reach out now.",
                    "latest_notice_date": "2026-04-01",
                    "latest_notice_title": "Flood works",
                    "frequency": "monthly",
                    "contact_pattern": "procurement",
                    "style": "civils",
                }
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "buyer_timing_signals.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-04-18T12:00:00+00:00",
                "buyer_count": 1,
                "signals": [
                        {
                            "buyer_key": "environment agency",
                            "buyer_name": "Environment Agency",
                            "timing_status": "due_soon",
                            "timing_label": "Actionable",
                            "timing_visibility": "visible",
                            "timing_confidence": "High",
                            "timing_reason": "Median gap 30d.",
                        "action_note": "Prepare outreach now.",
                        "days_until_window_open": 5,
                        "days_until_central": 10,
                        "predicted_next_start": "2026-04-23",
                        "predicted_next_central": "2026-04-28",
                        "predicted_next_end": "2026-05-04",
                        "median_gap_days": 30,
                        "gap_stddev": 4,
                        "category_repeat_strength": 0.75,
                        "quarter_distribution": {"Q1": 3, "Q2": 1, "Q3": 0, "Q4": 0},
                        "month_distribution": {"1": 1, "2": 1, "3": 1, "4": 1},
                        "timing_score": 71,
                        "fit_to_client": 74,
                        "buyer_due_rank": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "buyer_timing_backtest.json").write_text(
        json.dumps({"sample_count": 1, "window_hit_rate": 1.0, "results": []}),
        encoding="utf-8",
    )
    (run_dir / "tender_forecast.json").write_text(
        json.dumps({"forecasts": [{"buyer_key": "environment agency", "status": "due_soon", "confidence": "high"}]}),
        encoding="utf-8",
    )
    (state_dir / "buyer_profiles.json").write_text(json.dumps({}), encoding="utf-8")
    (config_dir / "client_tiers.json").write_text(json.dumps({"tiers": {}, "clients": []}), encoding="utf-8")
    (buyers_dir / "environment_agency.md").write_text("# Environment Agency\n", encoding="utf-8")

    monkeypatch.setattr(bundle, "BASE_DIR", base_dir)
    monkeypatch.setattr(bundle, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(bundle, "STATE_DIR", state_dir)
    monkeypatch.setattr(bundle, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(bundle, "OUTPUT_FILE", base_dir / "dashboard_data.js")
    monkeypatch.setattr(bundle, "OPENCLAW_BUYERS_DIR", buyers_dir)

    built = bundle.build_bundle()

    card = built["latestRun"]["buyerCards"][0]
    assert built["latestRun"]["buyerTiming"]["signals"][0]["timing_status"] == "due_soon"
    assert built["latestRun"]["buyerTimingBacktest"]["sample_count"] == 1
    assert card["timing_status"] == "due_soon"
    assert card["predicted_next_start"] == "2026-04-23"
    assert card["predicted_next_central"] == "2026-04-28"
    assert card["buyer_due_rank"] == 1
    assert card["action_state"] == "not_started"
    assert card["next_action"] == "Draft outreach"
    assert card["dossier_exists"] is True
    assert card["dossier_path"].replace("\\", "/").endswith("openclaw_workspace/buyers/environment_agency.md")
    assert card["dossier_uri"].startswith("file:///")
    assert card["cli_mark_drafted"] == 'python scripts/generate_outreach.py --buyer "Environment Agency" --mode email --save'
    assert card["cli_mark_sent"] == 'python -m outreach.cli create-action --buyer "Environment Agency" --type mark_sent --status sent'
    assert card["cli_mark_ignored"] == 'python -m outreach.cli create-action --buyer "Environment Agency" --type mark_ignored --status ignored'
