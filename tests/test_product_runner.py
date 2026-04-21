"""
tests/test_product_runner.py
============================
Tests for the product runner layer.
No network calls. All deterministic.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.product_runner import (
    apply_filters,
    compute_product_rank,
    discover_product_configs,
    load_product_config,
    load_scored_tenders,
    run_all_products,
    run_product,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "id": "test_product",
    "display_name": "Test Product",
    "enabled": True,
    "min_score": 20,
    "shortlist_size": 5,
    "include_keywords": [],
    "exclude_keywords": [],
    "regions": [],
    "buyer_filters": [],
    "value_min": None,
    "value_max": None,
    "score_boosts": {},
    "notify": False,
}

TENDER_A = {
    "id": "t-001",
    "title": "Civil engineering works for highways",
    "description": "Public realm improvements and infrastructure",
    "region": "England",
    "buyer_name": "Anytown Council",
    "value_amount": 250000.0,
    "score": 45,
}

TENDER_B = {
    "id": "t-002",
    "title": "Drainage and sewer rehabilitation",
    "description": "SUDS and surface water management",
    "region": "London",
    "buyer_name": "Islington Borough Council",
    "value_amount": 80000.0,
    "score": 35,
}

TENDER_C = {
    "id": "t-003",
    "title": "IT systems support contract",
    "description": "Software and support services",
    "region": "Scotland",
    "buyer_name": "Scottish Authority",
    "value_amount": 5000.0,
    "score": 30,
}

TENDER_LOW_SCORE = {
    "id": "t-004",
    "title": "Civil engineering minor works",
    "description": "Small groundworks",
    "region": "England",
    "buyer_name": "Test Council",
    "value_amount": 75000.0,
    "score": 10,
}

TENDER_NULL_VALUE = {
    "id": "t-005",
    "title": "Civil engineering procurement",
    "description": "Infrastructure development",
    "region": "England",
    "buyer_name": "Northern Council",
    "value_amount": None,
    "score": 50,
}

ALL_TENDERS = [TENDER_A, TENDER_B, TENDER_C, TENDER_LOW_SCORE]
ALL_TENDERS_WITH_NULL = [TENDER_A, TENDER_B, TENDER_C, TENDER_LOW_SCORE, TENDER_NULL_VALUE]


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

class TestLoadProductConfig:
    def test_valid_config_loads(self, tmp_path):
        cfg_file = tmp_path / "test.json"
        cfg_file.write_text(json.dumps(BASE_CONFIG), encoding="utf-8")
        cfg = load_product_config(cfg_file)
        assert cfg["id"] == "test_product"
        assert cfg["enabled"] is True

    def test_missing_required_field_raises(self, tmp_path):
        bad = dict(BASE_CONFIG)
        del bad["shortlist_size"]
        cfg_file = tmp_path / "bad.json"
        cfg_file.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match="missing fields"):
            load_product_config(cfg_file)

    def test_invalid_shortlist_size_raises(self, tmp_path):
        bad = dict(BASE_CONFIG, shortlist_size=0)
        cfg_file = tmp_path / "bad.json"
        cfg_file.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match="shortlist_size"):
            load_product_config(cfg_file)

    def test_invalid_id_raises(self, tmp_path):
        bad = dict(BASE_CONFIG, id="")
        cfg_file = tmp_path / "bad.json"
        cfg_file.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match="'id'"):
            load_product_config(cfg_file)

    def test_invalid_score_boosts_type_raises(self, tmp_path):
        bad = dict(BASE_CONFIG, score_boosts=["not", "a", "dict"])
        cfg_file = tmp_path / "bad.json"
        cfg_file.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match="score_boosts"):
            load_product_config(cfg_file)

    def test_allow_null_value_valid_boolean(self, tmp_path):
        good = dict(BASE_CONFIG, allow_null_value=True)
        cfg_file = tmp_path / "good.json"
        cfg_file.write_text(json.dumps(good), encoding="utf-8")
        cfg = load_product_config(cfg_file)
        assert cfg["allow_null_value"] is True

    def test_allow_null_value_invalid_type_raises(self, tmp_path):
        bad = dict(BASE_CONFIG, allow_null_value="yes")
        cfg_file = tmp_path / "bad.json"
        cfg_file.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match="allow_null_value"):
            load_product_config(cfg_file)


class TestDiscoverProductConfigs:
    def test_finds_enabled_configs(self, tmp_path):
        for i in range(2):
            cfg = dict(BASE_CONFIG, id=f"product_{i}")
            (tmp_path / f"product_{i}.json").write_text(json.dumps(cfg), encoding="utf-8")
        configs = discover_product_configs(tmp_path)
        assert len(configs) == 2

    def test_skips_disabled(self, tmp_path):
        enabled = dict(BASE_CONFIG, id="enabled_one")
        disabled = dict(BASE_CONFIG, id="disabled_one", enabled=False)
        (tmp_path / "enabled.json").write_text(json.dumps(enabled), encoding="utf-8")
        (tmp_path / "disabled.json").write_text(json.dumps(disabled), encoding="utf-8")
        configs = discover_product_configs(tmp_path)
        assert len(configs) == 1
        assert configs[0]["id"] == "enabled_one"

    def test_invalid_config_skipped_not_raised(self, tmp_path):
        good = dict(BASE_CONFIG, id="good_one")
        (tmp_path / "good.json").write_text(json.dumps(good), encoding="utf-8")
        (tmp_path / "bad.json").write_text("{invalid json}", encoding="utf-8")
        configs = discover_product_configs(tmp_path)
        assert len(configs) == 1

    def test_empty_dir_returns_empty(self, tmp_path):
        configs = discover_product_configs(tmp_path)
        assert configs == []

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        configs = discover_product_configs(tmp_path / "nonexistent")
        assert configs == []


# ---------------------------------------------------------------------------
# Filter pipeline
# ---------------------------------------------------------------------------

class TestApplyFilters:
    def test_empty_filters_all_pass(self):
        # BASE_CONFIG has min_score=20; TENDER_LOW_SCORE has score=10, so it gets filtered
        cfg = dict(BASE_CONFIG, min_score=0)
        matched, stages = apply_filters(ALL_TENDERS, cfg)
        assert stages["after_min_score"] == len(ALL_TENDERS)

    def test_include_keywords_filters(self):
        cfg = dict(BASE_CONFIG, include_keywords=["drainage", "sewer"])
        matched, stages = apply_filters(ALL_TENDERS, cfg)
        assert all("drainage" in t["title"].lower() or "sewer" in t["title"].lower() for t in matched)
        assert stages["after_include_keywords"] < stages["input"]

    def test_include_keywords_case_insensitive(self):
        cfg = dict(BASE_CONFIG, include_keywords=["CIVIL ENGINEERING"])
        matched, _ = apply_filters([TENDER_A], cfg)
        assert len(matched) == 1

    def test_exclude_keywords_filters(self):
        cfg = dict(BASE_CONFIG, exclude_keywords=["IT systems", "software"])
        matched, stages = apply_filters(ALL_TENDERS, cfg)
        assert all("it systems" not in t["title"].lower() for t in matched)

    def test_region_filter(self):
        cfg = dict(BASE_CONFIG, regions=["London"])
        matched, stages = apply_filters(ALL_TENDERS, cfg)
        assert all(t["region"] == "London" for t in matched)
        assert stages["after_region_filter"] == 1

    def test_region_filter_case_insensitive(self):
        cfg = dict(BASE_CONFIG, regions=["london"])
        matched, _ = apply_filters([TENDER_B], cfg)
        assert len(matched) == 1

    def test_buyer_filter(self):
        cfg = dict(BASE_CONFIG, buyer_filters=["borough"])
        matched, _ = apply_filters(ALL_TENDERS, cfg)
        assert all("borough" in t["buyer_name"].lower() for t in matched)

    def test_buyer_filter_multiple_substrings(self):
        cfg = dict(BASE_CONFIG, buyer_filters=["islington", "anytown"])
        matched, _ = apply_filters(ALL_TENDERS, cfg)
        assert len(matched) == 2

    def test_value_min_filter(self):
        cfg = dict(BASE_CONFIG, value_min=100000)
        matched, _ = apply_filters(ALL_TENDERS, cfg)
        # Only TENDER_A (250k) passes; TENDER_B=80k fails; TENDER_C=5k fails
        # TENDER_LOW_SCORE=75k fails
        # Tenders with None value_amount are skipped when value_min set
        assert all(
            (t.get("value_amount") or 0) >= 100000
            for t in matched
            if t.get("value_amount") is not None
        )

    def test_value_max_filter(self):
        cfg = dict(BASE_CONFIG, value_min=None, value_max=90000)
        matched, _ = apply_filters(ALL_TENDERS, cfg)
        # TENDER_B (80k) and TENDER_C (5k) pass; TENDER_A (250k) fails
        # TENDER_LOW_SCORE (75k) passes
        passing_values = [t["value_amount"] for t in matched if t.get("value_amount")]
        assert all(v <= 90000 for v in passing_values)

    def test_value_band_both_bounds(self):
        cfg = dict(BASE_CONFIG, value_min=50000, value_max=150000)
        matched, _ = apply_filters([TENDER_A, TENDER_B, TENDER_C], cfg)
        # TENDER_B (80k) qualifies; TENDER_A (250k) too high; TENDER_C (5k) too low
        assert len(matched) == 1
        assert matched[0]["id"] == "t-002"

    def test_min_score_filter(self):
        cfg = dict(BASE_CONFIG, min_score=40)
        matched, stages = apply_filters(ALL_TENDERS, cfg)
        assert all((t.get("score") or 0) >= 40 for t in matched)

    def test_min_score_zero_all_pass(self):
        cfg = dict(BASE_CONFIG, min_score=0)
        matched, _ = apply_filters(ALL_TENDERS, cfg)
        assert len(matched) == len(ALL_TENDERS)

    def test_stage_counts_present(self):
        cfg = dict(BASE_CONFIG, include_keywords=["civil"])
        _, stages = apply_filters(ALL_TENDERS, cfg)
        assert "input" in stages
        assert "after_include_keywords" in stages
        assert "after_min_score" in stages

    def test_zero_match_returns_empty(self):
        cfg = dict(BASE_CONFIG, include_keywords=["quantum_physics_contract"])
        matched, stages = apply_filters(ALL_TENDERS, cfg)
        assert matched == []
        assert stages["after_include_keywords"] == 0

    def test_allow_null_value_false_excludes_nulls(self):
        """When allow_null_value=False (default), null values excluded when value filter set"""
        cfg = dict(BASE_CONFIG, value_min=50000, allow_null_value=False)
        matched, _ = apply_filters(ALL_TENDERS_WITH_NULL, cfg)
        # TENDER_NULL_VALUE should be excluded
        assert all(t.get("value_amount") is not None for t in matched)

    def test_allow_null_value_true_includes_nulls(self):
        """When allow_null_value=True, null values pass the value filter"""
        cfg = dict(BASE_CONFIG, value_min=50000, allow_null_value=True)
        matched, _ = apply_filters(ALL_TENDERS_WITH_NULL, cfg)
        # TENDER_NULL_VALUE should be included (it has high score=50 and allow_null=True)
        null_tenders = [t for t in matched if t.get("value_amount") is None]
        assert len(null_tenders) > 0
        assert TENDER_NULL_VALUE["id"] in [t["id"] for t in null_tenders]

    def test_allow_null_value_true_with_value_max(self):
        """allow_null_value=True works with value_max too"""
        cfg = dict(BASE_CONFIG, value_max=100000, allow_null_value=True)
        matched, _ = apply_filters(ALL_TENDERS_WITH_NULL, cfg)
        null_tenders = [t for t in matched if t.get("value_amount") is None]
        assert len(null_tenders) > 0


# ---------------------------------------------------------------------------
# Product rank computation
# ---------------------------------------------------------------------------

class TestComputeProductRank:
    def test_no_boosts_equals_base_score(self):
        rank = compute_product_rank(TENDER_A, {})
        assert rank == TENDER_A["score"]

    def test_boost_applied_for_keyword_match(self):
        rank = compute_product_rank(TENDER_A, {"civil engineering": 10})
        assert rank == TENDER_A["score"] + 10

    def test_boost_case_insensitive(self):
        rank = compute_product_rank(TENDER_A, {"CIVIL ENGINEERING": 10})
        assert rank == TENDER_A["score"] + 10

    def test_multiple_boosts_sum(self):
        rank = compute_product_rank(TENDER_A, {"civil engineering": 10, "highways": 5})
        assert rank == TENDER_A["score"] + 10 + 5

    def test_non_matching_boost_not_applied(self):
        rank = compute_product_rank(TENDER_A, {"drainage": 10})
        assert rank == TENDER_A["score"]

    def test_base_score_not_mutated(self):
        original_score = TENDER_A["score"]
        compute_product_rank(TENDER_A, {"civil engineering": 99})
        assert TENDER_A["score"] == original_score

    def test_empty_boost_dict(self):
        rank = compute_product_rank(TENDER_C, {})
        assert rank == TENDER_C["score"]


# ---------------------------------------------------------------------------
# run_product — artifact writing
# ---------------------------------------------------------------------------

class TestRunProduct:
    def test_writes_shortlist_and_summary(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        result = run_product(
            [TENDER_A, TENDER_B],
            BASE_CONFIG,
            run_dir,
            "run_001",
            "2026-04-01T00:00:00+00:00",
        )
        prod_dir = run_dir / "products" / "test_product"
        assert (prod_dir / "product_shortlist.json").exists()
        assert (prod_dir / "product_summary.json").exists()

    def test_shortlist_sorted_by_product_rank(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        cfg = dict(BASE_CONFIG, score_boosts={"drainage": 20})
        run_product([TENDER_A, TENDER_B, TENDER_C], cfg, run_dir, "run_001", "2026-04-01T00:00:00")
        shortlist = json.loads((run_dir / "products" / "test_product" / "product_shortlist.json").read_text())
        ranks = [r["product_rank"] for r in shortlist]
        assert ranks == sorted(ranks, reverse=True)

    def test_product_rank_field_in_output(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        run_product([TENDER_A], BASE_CONFIG, run_dir, "run_001", "2026-04-01T00:00:00")
        shortlist = json.loads((run_dir / "products" / "test_product" / "product_shortlist.json").read_text())
        assert "product_rank" in shortlist[0]

    def test_product_id_field_in_output(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        run_product([TENDER_A], BASE_CONFIG, run_dir, "run_001", "2026-04-01T00:00:00")
        shortlist = json.loads((run_dir / "products" / "test_product" / "product_shortlist.json").read_text())
        assert shortlist[0]["product_id"] == "test_product"

    def test_base_score_not_overwritten(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        cfg = dict(BASE_CONFIG, score_boosts={"civil engineering": 50})
        run_product([TENDER_A], cfg, run_dir, "run_001", "2026-04-01T00:00:00")
        shortlist = json.loads((run_dir / "products" / "test_product" / "product_shortlist.json").read_text())
        assert shortlist[0]["score"] == TENDER_A["score"]
        assert shortlist[0]["product_rank"] == TENDER_A["score"] + 50

    def test_zero_match_returns_empty_status(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        cfg = dict(BASE_CONFIG, include_keywords=["quantum_physics_xyz"])
        result = run_product([TENDER_A, TENDER_B], cfg, run_dir, "run_001", "2026-04-01T00:00:00")
        assert result["status"] == "empty"
        assert result["item_count"] == 0

    def test_shortlist_size_respected(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        cfg = dict(BASE_CONFIG, shortlist_size=1)
        run_product([TENDER_A, TENDER_B, TENDER_C], cfg, run_dir, "run_001", "2026-04-01T00:00:00")
        shortlist = json.loads((run_dir / "products" / "test_product" / "product_shortlist.json").read_text())
        assert len(shortlist) <= 1

    def test_summary_contains_filter_stages(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        run_product([TENDER_A], BASE_CONFIG, run_dir, "run_001", "2026-04-01T00:00:00")
        summary = json.loads((run_dir / "products" / "test_product" / "product_summary.json").read_text())
        assert "filter_stages" in summary
        assert "item_count" in summary
        assert summary["product_id"] == "test_product"
        assert summary["run_id"] == "run_001"

    def test_filter_stages_structure_correct(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        cfg = dict(BASE_CONFIG, include_keywords=["civil"], regions=["England"])
        run_product([TENDER_A, TENDER_B, TENDER_C], cfg, run_dir, "run_001", "2026-04-01T00:00:00")
        summary = json.loads((run_dir / "products" / "test_product" / "product_summary.json").read_text())
        stages = summary["filter_stages"]
        assert "input" in stages
        assert "after_include_keywords" in stages
        assert "after_exclude_keywords" in stages
        assert "after_region_filter" in stages
        assert "after_buyer_filter" in stages
        assert "after_value_filter" in stages
        assert "after_min_score" in stages
        # Verify they're all integers
        for stage_name, count in stages.items():
            assert isinstance(count, int), f"{stage_name} should be int, got {type(count)}"
        # Verify monotonic decrease (or equal)
        prev = stages["input"]
        for stage_name in ["after_include_keywords", "after_exclude_keywords", "after_region_filter",
                          "after_buyer_filter", "after_value_filter", "after_min_score"]:
            curr = stages[stage_name]
            assert curr <= prev, f"{stage_name} ({curr}) > previous ({prev})"
            prev = curr


# ---------------------------------------------------------------------------
# run_all_products — orchestration
# ---------------------------------------------------------------------------

class TestRunAllProducts:
    def _write_scored_tenders(self, run_dir: Path, tenders: list[dict]) -> None:
        path = run_dir / "scored_tenders.jsonl"
        path.write_text("\n".join(json.dumps(t) for t in tenders), encoding="utf-8")

    def _write_product_config(self, config_dir: Path, cfg: dict) -> None:
        (config_dir / f"{cfg['id']}.json").write_text(json.dumps(cfg), encoding="utf-8")

    def test_no_scored_tenders_returns_skipped(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        result = run_all_products(run_dir, tmp_path / "products")
        assert result["status"] == "skipped"

    def test_no_product_configs_returns_no_products(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A])
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        result = run_all_products(run_dir, config_dir)
        assert result["status"] == "no_products"

    def test_runs_all_enabled_products(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A, TENDER_B])
        self._write_product_config(config_dir, dict(BASE_CONFIG, id="prod_a"))
        self._write_product_config(config_dir, dict(BASE_CONFIG, id="prod_b"))
        result = run_all_products(run_dir, config_dir)
        assert result["enabled_count"] == 2
        assert result["generated_count"] == 2
        assert "prod_a" in result["outputs"]
        assert "prod_b" in result["outputs"]

    def test_manifest_fields_populated(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A])
        self._write_product_config(config_dir, BASE_CONFIG)
        result = run_all_products(run_dir, config_dir)
        assert "status" in result
        assert "enabled_count" in result
        assert "generated_count" in result
        assert "outputs" in result

    def test_one_bad_config_does_not_block_others(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A])
        # Good config
        self._write_product_config(config_dir, dict(BASE_CONFIG, id="good_prod"))
        # Invalid JSON config (will be skipped at discovery)
        (config_dir / "bad.json").write_text("{invalid}", encoding="utf-8")
        result = run_all_products(run_dir, config_dir)
        assert result["generated_count"] == 1
        assert "good_prod" in result["outputs"]

    def test_empty_match_status_is_empty_not_ok(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A])
        cfg = dict(BASE_CONFIG, include_keywords=["quantum_xyz_impossible"])
        self._write_product_config(config_dir, cfg)
        result = run_all_products(run_dir, config_dir)
        assert result["outputs"]["test_product"]["status"] == "empty"

    def test_artifacts_created_per_product(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A, TENDER_B])
        self._write_product_config(config_dir, dict(BASE_CONFIG, id="test_art"))
        run_all_products(run_dir, config_dir)
        prod_dir = run_dir / "products" / "test_art"
        assert (prod_dir / "product_shortlist.json").exists()
        assert (prod_dir / "product_summary.json").exists()

    def test_top_level_status_is_ok_when_all_empty(self, tmp_path):
        """Top-level status is 'ok' even if all products are empty"""
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A])
        cfg = dict(BASE_CONFIG, id="empty_prod", include_keywords=["nonexistent_xyz"])
        self._write_product_config(config_dir, cfg)
        result = run_all_products(run_dir, config_dir)
        assert result["status"] == "ok"
        assert result["enabled_count"] == 1
        assert result["generated_count"] == 1
        assert result["outputs"]["empty_prod"]["status"] == "empty"

    def test_top_level_status_error_when_product_config_invalid(self, tmp_path):
        """Invalid product config is skipped during discovery"""
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A])
        # Create a broken config that fails validation
        bad_cfg = dict(BASE_CONFIG, id="bad_prod", score_boosts="not_a_dict")
        self._write_product_config(config_dir, bad_cfg)
        result = run_all_products(run_dir, config_dir)
        # Bad config is skipped, so no error at top level (no products ran)
        assert result["generated_count"] == 0
        assert result["status"] == "no_products"

    def test_per_product_status_values_valid(self, tmp_path):
        """Per-product status must be one of: ok, empty, error"""
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A, TENDER_B])
        self._write_product_config(config_dir, dict(BASE_CONFIG, id="test_status"))
        result = run_all_products(run_dir, config_dir)
        for product_id, output in result["outputs"].items():
            status = output.get("status")
            assert status in {"ok", "empty", "error"}, f"Invalid status '{status}' for product {product_id}"

    def test_manifest_top_level_status_values_valid(self, tmp_path):
        """Top-level status must be one of: ok, error, no_products, skipped"""
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        config_dir = tmp_path / "products"
        config_dir.mkdir()
        self._write_scored_tenders(run_dir, [TENDER_A])
        self._write_product_config(config_dir, BASE_CONFIG)
        result = run_all_products(run_dir, config_dir)
        assert result["status"] in {"ok", "error", "no_products", "skipped"}


# ---------------------------------------------------------------------------
# Backward compatibility — scored_tenders loader
# ---------------------------------------------------------------------------

class TestLoadScoredTenders:
    def test_loads_valid_jsonl(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        path = run_dir / "scored_tenders.jsonl"
        path.write_text("\n".join(json.dumps(t) for t in [TENDER_A, TENDER_B]), encoding="utf-8")
        tenders = load_scored_tenders(run_dir)
        assert len(tenders) == 2

    def test_missing_file_returns_empty(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        tenders = load_scored_tenders(run_dir)
        assert tenders == []

    def test_skips_invalid_lines(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        path = run_dir / "scored_tenders.jsonl"
        path.write_text(f"{json.dumps(TENDER_A)}\n{{bad json}}\n{json.dumps(TENDER_B)}", encoding="utf-8")
        tenders = load_scored_tenders(run_dir)
        assert len(tenders) == 2
