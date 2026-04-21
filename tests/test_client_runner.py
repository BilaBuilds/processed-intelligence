from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import client_runner
from scripts import build_dashboard_bundle


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            rows.append(json.loads(text))
    return rows


def _client_config(
    *,
    client_id: str = "client_a",
    display_name: str = "Client A",
    active: bool = True,
    subscribed_products: list[str] | None = None,
    filters: dict | None = None,
    notify: dict | None = None,
) -> dict:
    return {
        "client_id": client_id,
        "display_name": display_name,
        "active": active,
        "subscribed_products": subscribed_products or ["prod_alpha"],
        "filters": filters or {"min_score": 0, "regions": [], "buyer_whitelist": []},
        "notify": notify or {"channel": "discord", "webhook_env_var": "TEST_WEBHOOK"},
    }


def _tender(
    *,
    notice_id: str,
    score: float = 10.0,
    region: str = "London",
    buyer_name: str = "Buyer One",
    product_rank: float = 1.0,
) -> dict:
    return {
        "id": notice_id,
        "title": f"Tender {notice_id}",
        "score": score,
        "region": region,
        "buyer_name": buyer_name,
        "product_rank": product_rank,
    }


def _make_run_dir(tmp_path: Path, run_id: str = "2026-04-19_120000") -> Path:
    run_dir = tmp_path / "data" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "run_manifest.json",
        {"run_id": run_id, "status": "success", "finished_at": "2026-04-19T12:00:00+00:00"},
    )
    return run_dir


def _write_product_shortlist(run_dir: Path, product_id: str, tenders: list[dict]) -> None:
    _write_json(run_dir / "products" / product_id / "product_shortlist.json", tenders)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def test_valid_client_config_loads_without_error(tmp_path: Path) -> None:
    cfg_path = tmp_path / "clients" / "ok.json"
    _write_json(cfg_path, _client_config())
    loaded = client_runner.load_client_config(cfg_path)
    assert loaded["client_id"] == "client_a"


def test_run_clients_skips_inactive_client(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    _write_product_shortlist(run_dir, "prod_alpha", [_tender(notice_id="n1")])

    cfg_dir = tmp_path / "config" / "clients"
    _write_json(cfg_dir / "inactive.json", _client_config(client_id="inactive_c", active=False))

    result = client_runner.run_clients(run_dir, cfg_dir)
    assert result["status"] == "no_clients"
    assert result["enabled_count"] == 0
    assert result["outputs"] == {}


def test_missing_subscribed_product_is_handled_gracefully(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    cfg_dir = tmp_path / "config" / "clients"
    _write_json(
        cfg_dir / "missing_product.json",
        _client_config(client_id="c_missing", subscribed_products=["does_not_exist"]),
    )

    result = client_runner.run_clients(run_dir, cfg_dir)
    assert result["status"] == "ok"
    assert result["outputs"]["c_missing"]["status"] == "empty"
    assert result["outputs"]["c_missing"]["item_count"] == 0


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def test_min_score_filter_excludes_below_threshold() -> None:
    tenders = [_tender(notice_id="a", score=49), _tender(notice_id="b", score=50)]
    out = client_runner.apply_client_filters(tenders, {"min_score": 50, "regions": [], "buyer_whitelist": []})
    assert [t["id"] for t in out] == ["b"]


def test_region_filter_excludes_outside_regions_and_empty_list_means_no_filter() -> None:
    tenders = [_tender(notice_id="a", region="London"), _tender(notice_id="b", region="Bristol")]
    filtered = client_runner.apply_client_filters(
        tenders, {"min_score": 0, "regions": ["London"], "buyer_whitelist": []}
    )
    assert [t["id"] for t in filtered] == ["a"]
    no_filter = client_runner.apply_client_filters(
        tenders, {"min_score": 0, "regions": [], "buyer_whitelist": []}
    )
    assert [t["id"] for t in no_filter] == ["a", "b"]


def test_buyer_whitelist_filter_excludes_non_matching_and_empty_list_means_no_filter() -> None:
    tenders = [_tender(notice_id="a", buyer_name="Alpha Council"), _tender(notice_id="b", buyer_name="Beta Council")]
    filtered = client_runner.apply_client_filters(
        tenders, {"min_score": 0, "regions": [], "buyer_whitelist": ["alpha"]}
    )
    assert [t["id"] for t in filtered] == ["a"]
    no_filter = client_runner.apply_client_filters(
        tenders, {"min_score": 0, "regions": [], "buyer_whitelist": []}
    )
    assert [t["id"] for t in no_filter] == ["a", "b"]


def test_merge_and_deduplicate_keeps_same_notice_once_across_products() -> None:
    by_product = {
        "p1": [_tender(notice_id="same", score=80), _tender(notice_id="x1", score=70)],
        "p2": [_tender(notice_id="same", score=60), _tender(notice_id="x2", score=50)],
    }
    merged = client_runner.merge_and_deduplicate(by_product)
    ids = [t["id"] for t in merged]
    assert ids.count("same") == 1
    assert set(ids) == {"same", "x1", "x2"}


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


def test_notify_status_skipped_when_new_count_zero() -> None:
    client = _client_config()
    status = client_runner.send_discord_notification(client, "run_1", [])
    assert status == "skipped"


def test_notify_status_error_when_webhook_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_config(notify={"channel": "discord", "webhook_env_var": "MISSING_WEBHOOK_VAR"})
    monkeypatch.delenv("MISSING_WEBHOOK_VAR", raising=False)
    status = client_runner.send_discord_notification(client, "run_1", [_tender(notice_id="n1")])
    assert status == "error"


def test_notify_status_sent_when_webhook_set_and_http_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    class Resp:
        status_code = 204

    calls: list[dict] = []

    def fake_post(url: str, json: dict, timeout: int) -> Resp:
        calls.append({"url": url, "json": json, "timeout": timeout})
        return Resp()

    client = _client_config(notify={"channel": "discord", "webhook_env_var": "TEST_WEBHOOK"})
    monkeypatch.setenv("TEST_WEBHOOK", "https://discord.com/api/webhooks/123456789/token_abc")

    status = client_runner.send_discord_notification(
        client, "run_1", [_tender(notice_id="n1")], _requests_post=fake_post
    )
    assert status == "sent"
    assert len(calls) == 1


def test_discord_message_is_capped_at_10_tenders() -> None:
    client = _client_config(display_name="Cap Test")
    tenders = [_tender(notice_id=f"n{i}") for i in range(12)]
    message = client_runner._build_discord_message(client, "run_1", tenders)
    bullet_lines = [line for line in message.splitlines() if line.startswith("• ")]
    assert len(bullet_lines) == 10
    assert "_…and 2 more" in message


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_clients_top_level_status_is_valid_enum(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    cfg_dir = tmp_path / "config" / "clients"
    _write_json(cfg_dir / "a.json", _client_config(client_id="a"))
    _write_product_shortlist(run_dir, "prod_alpha", [])
    result = client_runner.run_clients(run_dir, cfg_dir)
    assert result["status"] in {"ok", "skipped", "error", "no_clients"}


def test_per_client_status_is_valid_enum(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    cfg_dir = tmp_path / "config" / "clients"
    _write_json(cfg_dir / "a.json", _client_config(client_id="a"))
    _write_product_shortlist(run_dir, "prod_alpha", [])
    result = client_runner.run_clients(run_dir, cfg_dir)
    assert result["outputs"]["a"]["status"] in {"ok", "empty", "error"}


def test_all_empty_case_top_level_ok_each_client_empty(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    cfg_dir = tmp_path / "config" / "clients"
    _write_json(cfg_dir / "a.json", _client_config(client_id="a"))
    _write_json(cfg_dir / "b.json", _client_config(client_id="b"))
    _write_product_shortlist(run_dir, "prod_alpha", [])
    result = client_runner.run_clients(run_dir, cfg_dir)
    assert result["status"] == "ok"
    assert result["outputs"]["a"]["status"] == "empty"
    assert result["outputs"]["b"]["status"] == "empty"


def test_enabled_count_reflects_active_configs(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    cfg_dir = tmp_path / "config" / "clients"
    _write_json(cfg_dir / "a.json", _client_config(client_id="a", active=True))
    _write_json(cfg_dir / "b.json", _client_config(client_id="b", active=False))
    _write_product_shortlist(run_dir, "prod_alpha", [])
    result = client_runner.run_clients(run_dir, cfg_dir)
    assert result["enabled_count"] == 1


def test_notified_count_reflects_clients_that_sent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Resp:
        status_code = 204

    def fake_post(_url: str, json: dict, timeout: int) -> Resp:  # noqa: ARG001
        return Resp()

    run_dir = _make_run_dir(tmp_path)
    cfg_dir = tmp_path / "config" / "clients"
    _write_json(
        cfg_dir / "a.json",
        _client_config(client_id="a", notify={"channel": "discord", "webhook_env_var": "TEST_WEBHOOK"}),
    )
    _write_json(
        cfg_dir / "b.json",
        _client_config(client_id="b", notify={"channel": "discord", "webhook_env_var": "MISSING_WEBHOOK"}),
    )
    _write_product_shortlist(run_dir, "prod_alpha", [_tender(notice_id="n1")])
    monkeypatch.setenv("TEST_WEBHOOK", "https://discord.com/api/webhooks/123456789/token_abc")
    monkeypatch.delenv("MISSING_WEBHOOK", raising=False)

    result = client_runner.run_clients(run_dir, cfg_dir, _requests_post=fake_post)
    assert result["notified_count"] == 1
    assert result["outputs"]["a"]["notify_status"] == "sent"
    assert result["outputs"]["b"]["notify_status"] == "error"


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


def test_client_shortlist_is_written_to_correct_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = _make_run_dir(tmp_path)
    cfg_dir = tmp_path / "config" / "clients"
    _write_json(cfg_dir / "a.json", _client_config(client_id="a"))
    _write_product_shortlist(run_dir, "prod_alpha", [_tender(notice_id="n1")])
    monkeypatch.setenv("TEST_WEBHOOK", "https://discord.com/api/webhooks/123456789/token_abc")

    class Resp:
        status_code = 204

    result = client_runner.run_clients(run_dir, cfg_dir, _requests_post=lambda *_args, **_kwargs: Resp())
    assert result["outputs"]["a"]["status"] == "ok"
    shortlist_path = run_dir / "clients" / "a" / "client_shortlist.json"
    assert shortlist_path.exists()


def test_client_summary_contains_required_fields(tmp_path: Path) -> None:
    out_dir = tmp_path / "clients" / "abc"
    client = _client_config(client_id="abc", display_name="ABC Ltd")
    shortlist = [_tender(notice_id="n1")]
    client_runner._write_client_artifacts(
        out_dir,
        client,
        "run_123",
        shortlist,
        "sent",
        "2026-04-19T12:00:00+00:00",
    )
    summary = json.loads((out_dir / "client_summary.json").read_text(encoding="utf-8"))
    required = {
        "client_id",
        "display_name",
        "run_id",
        "generated_at",
        "subscribed_products",
        "item_count",
        "new_count",
        "notified",
        "notify_status",
    }
    assert required.issubset(summary.keys())


# ---------------------------------------------------------------------------
# Dashboard bundle integration
# ---------------------------------------------------------------------------


def test_build_client_data_returns_correct_structure(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    _write_json(
        run_dir / "clients" / "client_a" / "client_summary.json",
        {
            "client_id": "client_a",
            "display_name": "Client A",
            "item_count": 3,
            "new_count": 2,
            "notified": True,
            "notify_status": "sent",
        },
    )

    data = build_dashboard_bundle.build_client_data(run_dir)
    assert "clients" in data
    assert len(data["clients"]) == 1
    row = data["clients"][0]
    required_keys = {"id", "display_name", "status", "item_count", "new_count", "notified", "notify_status"}
    assert required_keys.issubset(set(row.keys()))
    assert row["id"] == "client_a"


def test_build_client_data_returns_empty_when_no_client_files(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    data = build_dashboard_bundle.build_client_data(run_dir)
    assert data == {"clients": []}


def test_latest_run_clients_present_in_bundle_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_dir = _make_run_dir(tmp_path, run_id="2026-04-19_130000")
    _write_json(run_dir / "decision_shortlist.json", {"opportunities": []})
    (run_dir / "context_tenders.jsonl").write_text("", encoding="utf-8")
    _write_json(
        run_dir / "clients" / "client_a" / "client_summary.json",
        {
            "client_id": "client_a",
            "display_name": "Client A",
            "item_count": 1,
            "new_count": 1,
            "notified": False,
            "notify_status": "skipped",
        },
    )

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    _write_json(state_dir / "buyer_profiles.json", {})

    monkeypatch.setattr(build_dashboard_bundle, "BASE_DIR", tmp_path)
    monkeypatch.setattr(build_dashboard_bundle, "RUNS_DIR", tmp_path / "data" / "runs")
    monkeypatch.setattr(build_dashboard_bundle, "STATE_DIR", state_dir)
    monkeypatch.setattr(build_dashboard_bundle, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(build_dashboard_bundle, "OUTPUT_FILE", tmp_path / "dashboard_data.js")

    build_dashboard_bundle.main()

    output_text = (tmp_path / "dashboard_data.js").read_text(encoding="utf-8")
    assert "window.DASHBOARD_DATA" in output_text
    data = json.loads(output_text.split(" = ", 1)[1].rstrip(";\n"))
    assert "clients" in data["latestRun"]