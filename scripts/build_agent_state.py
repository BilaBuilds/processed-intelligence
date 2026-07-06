import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_RUNS_DIR = REPO_ROOT / "data" / "runs"
DATA_OUTREACH_DIR = REPO_ROOT / "data" / "outreach"
DATA_HERMES_RUNS_DIR = REPO_ROOT / "data" / "hermes" / "runs"
BUYER_PROFILES_PATH = REPO_ROOT / "state" / "buyer_profiles.json"
CURRENT_STATE_PATH = REPO_ROOT / "agent_ops" / "state" / "current_state.json"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    tmp_path.replace(path)


def _list_run_ids() -> List[str]:
    if not DATA_RUNS_DIR.exists():
        return []
    run_ids = [p.name for p in DATA_RUNS_DIR.iterdir() if p.is_dir()]
    run_ids.sort()
    return run_ids


def _find_latest_run_with_file(filename: str) -> Optional[str]:
    for run_id in reversed(_list_run_ids()):
        candidate = DATA_RUNS_DIR / run_id / filename
        if candidate.exists():
            return run_id
    return None


def _read_latest_run_manifest() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    run_id = _find_latest_run_with_file("run_manifest.json")
    if not run_id:
        return None, None
    path = DATA_RUNS_DIR / run_id / "run_manifest.json"
    try:
        return _load_json(path), run_id
    except Exception:
        return None, run_id


def _safe_opportunity_count(obj: Any) -> Optional[int]:
    if isinstance(obj, dict) and isinstance(obj.get("opportunities"), list):
        return len(obj["opportunities"])
    if isinstance(obj, list):
        return len(obj)
    return None


def _read_latest_shortlist_like(filename: str) -> Tuple[Optional[Any], Optional[str]]:
    run_id = _find_latest_run_with_file(filename)
    if not run_id:
        return None, None
    path = DATA_RUNS_DIR / run_id / filename
    try:
        return _load_json(path), run_id
    except Exception:
        return None, run_id


def _compute_decision_counts(decision_shortlist: Any) -> Dict[str, int]:
    if not isinstance(decision_shortlist, dict):
        return {}
    opps = decision_shortlist.get("opportunities")
    if not isinstance(opps, list):
        return {}
    counts = Counter()
    for opp in opps:
        if not isinstance(opp, dict):
            continue
        verdict = opp.get("decision_verdict")
        if isinstance(verdict, str) and verdict.strip():
            counts[verdict.strip()] += 1
    return dict(sorted(counts.items(), key=lambda kv: kv[0]))


def _find_latest_outreach_queue() -> Tuple[Optional[Any], Optional[Path]]:
    # Prefer the stable "latest" pointer if present.
    latest_path = DATA_OUTREACH_DIR / "outreach_queue_latest.json"
    if latest_path.exists():
        try:
            return _load_json(latest_path), latest_path
        except Exception:
            return None, latest_path

    if not DATA_OUTREACH_DIR.exists():
        return None, None

    candidates = sorted(DATA_OUTREACH_DIR.glob("outreach_queue_*.json"), key=lambda p: p.name)
    if not candidates:
        return None, None
    path = candidates[-1]
    try:
        return _load_json(path), path
    except Exception:
        return None, path


def _outreach_count(obj: Any) -> Optional[int]:
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        if isinstance(obj.get("items"), list):
            return len(obj["items"])
        if isinstance(obj.get("count"), int):
            return obj["count"]
    return None


def _read_latest_hermes_summary() -> Optional[Dict[str, Any]]:
    if not DATA_HERMES_RUNS_DIR.exists():
        return None
    summaries = sorted(
        DATA_HERMES_RUNS_DIR.glob("*/summary.json"),
        key=lambda path: path.as_posix(),
    )
    if not summaries:
        return None
    try:
        data = _load_json(summaries[-1])
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def main() -> int:
    warnings: List[str] = []

    manifest, manifest_run_id = _read_latest_run_manifest()
    if manifest is None:
        if manifest_run_id:
            warnings.append(f"Failed to parse run manifest for run_id={manifest_run_id}.")
        else:
            warnings.append("No run manifest found under data/runs/.")

    shortlist, shortlist_run_id = _read_latest_shortlist_like("shortlist.json")
    if shortlist is None and shortlist_run_id:
        warnings.append(f"Failed to parse shortlist.json for run_id={shortlist_run_id}.")
    if shortlist is None and shortlist_run_id is None:
        warnings.append("No shortlist.json found under data/runs/.")

    decision_shortlist, decision_run_id = _read_latest_shortlist_like("decision_shortlist.json")
    if decision_shortlist is None and decision_run_id:
        warnings.append(f"Failed to parse decision_shortlist.json for run_id={decision_run_id}.")
    if decision_shortlist is None and decision_run_id is None:
        warnings.append("No decision_shortlist.json found under data/runs/.")

    buyer_profiles_exists = BUYER_PROFILES_PATH.exists()
    if not buyer_profiles_exists:
        warnings.append("Missing state/buyer_profiles.json.")
    else:
        try:
            _load_json(BUYER_PROFILES_PATH)
        except Exception:
            warnings.append("Failed to parse state/buyer_profiles.json.")

    outreach, outreach_path = _find_latest_outreach_queue()
    if outreach is None and outreach_path is not None:
        warnings.append(f"Failed to parse outreach queue: {outreach_path.as_posix()}.")
    if outreach is None and outreach_path is None:
        warnings.append("No outreach queue found under data/outreach/.")

    run_id = None
    pipeline_status = None
    if isinstance(manifest, dict):
        run_id = manifest.get("run_id") if isinstance(manifest.get("run_id"), str) else None
        pipeline_status = manifest.get("status") if isinstance(manifest.get("status"), str) else None

    shortlist_count = _safe_opportunity_count(shortlist)
    decision_counts = _compute_decision_counts(decision_shortlist)
    outreach_count = _outreach_count(outreach)
    hermes_summary = _read_latest_hermes_summary()

    # Flag mismatched sources to make state interpretation safer.
    if run_id and shortlist_run_id and shortlist_run_id != run_id:
        warnings.append(f"shortlist.json sourced from run_id={shortlist_run_id} (manifest run_id={run_id}).")
    if run_id and decision_run_id and decision_run_id != run_id:
        warnings.append(
            f"decision_shortlist.json sourced from run_id={decision_run_id} (manifest run_id={run_id})."
        )

    state: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id or manifest_run_id,
        "pipeline_status": pipeline_status or (manifest.get("status") if isinstance(manifest, dict) else None),
        "shortlist_count": shortlist_count,
        "decision_counts": decision_counts,
        "outreach_count": outreach_count,
        "hermes": hermes_summary,
        "warnings": warnings,
    }

    _atomic_write_json(CURRENT_STATE_PATH, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
