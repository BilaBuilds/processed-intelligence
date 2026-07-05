from __future__ import annotations

import json
from pathlib import Path

import scripts.build_hostinger_dashboard_export as exporter


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def tender(index: int, **overrides) -> dict:
    payload = {
        "source_id": f"nl-{index}",
        "source": "tenderned",
        "country": "NL",
        "title": f"Renovatie en onderhoud wegen {index}",
        "buyer": f"Gemeente Test {index % 7}",
        "deadline": "2026-09-11T14:00:00",
        "publication_date": f"2026-07-{(index % 9) + 1:02d}",
        "procedure_code": "OPE",
        "type_code": "W",
        "url": f"https://example.test/{index}",
    }
    payload.update(overrides)
    return payload


def payload_with(count: int) -> dict:
    records = [tender(index) for index in range(count)]
    return {
        "generated_at": "2026-07-06T00:00:00Z",
        "source": "tenderned",
        "country": "NL",
        "latestRun": {"tenders": records, "opportunities": records},
        "tenders": records,
        "opportunities": records,
    }


def build_tmp(tmp_path: Path, payload: dict) -> dict:
    input_path = tmp_path / "dutch_tenders.json"
    write_json(input_path, payload)
    built, _ = exporter.build_export(input_path, tmp_path / "export", tmp_path / "dashboard")
    return built


def test_dashboard_data_json_has_total_tenders_for_50_input(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(50))

    assert built["status"] == "ready"
    assert built["dashboard_version"] == "hostinger_static_v2"
    assert built["total_tenders"] == 50
    assert built["total_opportunities"] == 50
    assert built["pipeline_runs"] == 1
    assert built["latestRun"]["manifest"]["shortlist_count"] == built["shortlist_count"]


def test_latest_run_summary_tenders_equals_50(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(50))

    assert built["latestRun"]["summary"]["tenders"] == 50
    assert built["latestRun"]["summary"]["opportunities"] == 50
    assert built["latestRun"]["summary"]["buyers"] == built["buyer_count"]


def test_kpis_unique_buyers_is_greater_than_zero(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(50))

    assert built["kpis"]["unique_buyers"] > 0
    assert built["kpis"]["buyer_count"] == built["buyer_count"]
    assert built["kpis"]["pipeline_runs"] == 1
    assert built["kpis"]["avg_fit_score"] > 0


def test_buyers_and_buyer_cards_are_non_empty(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(5))

    assert built["buyers"]
    assert built["buyerCards"]
    assert built["latestRun"]["buyers"] == built["buyers"]
    assert built["latestRun"]["buyerCards"] == built["buyerCards"]


def test_at_least_some_tenders_have_score_above_zero(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(5))

    assert any((item["score"] or 0) > 0 for item in built["tenders"])


def test_shortlist_is_non_empty_when_construction_keywords_exist(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(3))

    assert built["shortlist"]
    assert built["shortlist_count"] == len(built["shortlist"])
    assert all(item["score"] >= 20 for item in built["shortlist"])


def test_richer_dashboard_intelligence_fields_are_populated(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(10))

    assert built["avg_fit_score"] > 0
    assert built["kpis"]["hot_outreach_count"] > 0
    assert built["kpis"]["warm_buyers"] > 0
    assert built["kpis"]["timing_ready"] > 0
    assert built["kpis"]["products"] > 0
    assert built["hot_outreach"]
    assert built["outreach_queue"] == built["hot_outreach"]
    assert built["warm_buyers"]
    assert built["timing_ready"]
    assert built["products"]
    assert built["product_rails"]
    assert built["latestRun"]["summary"]["avg_fit_score"] == built["avg_fit_score"]
    assert built["latestRun"]["summary"]["hot_outreach"] == len(built["hot_outreach"])
    assert built["latestRun"]["summary"]["warm_buyers"] == len(built["warm_buyers"])
    assert built["latestRun"]["summary"]["timing_ready"] == len(built["timing_ready"])


def test_summaries_exist_on_top_opportunities(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(5))
    top = sorted(built["opportunities"], key=lambda item: item["score"], reverse=True)[0]

    assert top["summary"]
    assert "Dutch public-sector opportunity" in top["summary"]
    assert top["description"]
    assert top["rationale"]
    assert top["next_step"]


def test_pipeline_model_fields_exist(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(1))

    assert built["pipeline_model"]["supplier_source"] == "tenderned_json"
    assert built["pipeline_model"]["notifier_channels"] == ["hostinger_static"]
    assert built["pipeline_model"]["loop_steps"] == 1
    assert built["loop_steps"] == 1
    assert built["post_run_steps"] == 1
    assert built["fatal_steps"] == 0
    assert built["supplier_source"] == "tenderned_json"
    assert built["notifier_channels"] == ["hostinger_static"]


def test_every_opportunity_has_derived_table_fields(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(5))

    for opportunity in built["opportunities"]:
        assert "decision" in opportunity
        assert "verdict" in opportunity
        assert "confidence" in opportunity
        assert "score" in opportunity
        assert "region" in opportunity
        assert "value" in opportunity


def test_dashboard_data_js_contains_all_three_global_variables(tmp_path: Path) -> None:
    input_path = tmp_path / "dutch_tenders.json"
    output_dir = tmp_path / "export"
    dashboard_dir = tmp_path / "dashboard"
    write_json(input_path, payload_with(1))

    exporter.build_export(input_path, output_dir, dashboard_dir)

    js = (output_dir / "dashboard_data.js").read_text(encoding="utf-8")
    assert "window.PROCESSED_DASHBOARD_DATA =" in js
    assert "window.dashboardData = window.PROCESSED_DASHBOARD_DATA;" in js
    assert "window.DASHBOARD_DATA = window.PROCESSED_DASHBOARD_DATA;" in js


def test_dashboard_does_not_go_blank_if_input_exists(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, payload_with(1))

    assert built["latestRun"]["tenders"]
    assert built["latestRun"]["opportunities"]
    assert built["system_health"]["hostinger_ready"] is True
    assert built["system_health"]["status"] == "ready"


def test_missing_input_uses_previous_dashboard_fallback(tmp_path: Path) -> None:
    output_dir = tmp_path / "export"
    dashboard_dir = tmp_path / "dashboard"
    write_json(output_dir / "dashboard_data.json", payload_with(1))

    payload, _ = exporter.build_export(tmp_path / "missing.json", output_dir, dashboard_dir)

    assert payload["system_health"]["hostinger_ready"] is True
    assert payload["latestRun"]["tenders"]


def test_no_crash_when_fields_are_missing(tmp_path: Path) -> None:
    built = build_tmp(tmp_path, {"tenders": [{"source_id": "minimal"}]})

    opportunity = built["opportunities"][0]
    assert opportunity["source_id"] == "minimal"
    assert opportunity["title"] == ""
    assert opportunity["buyer"] == ""
    assert opportunity["deadline"] is None
    assert opportunity["region"] == "Netherlands"
    assert opportunity["decision"] == "Low fit"
