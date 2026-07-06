import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_RUNS_DIR = REPO_ROOT / "data" / "runs"
DATA_OUTREACH_DIR = REPO_ROOT / "data" / "outreach"
DATA_LEADS_DIR = REPO_ROOT / "data" / "leads"
DATA_HERMES_RUNS_DIR = REPO_ROOT / "data" / "hermes" / "runs"
BUYER_PROFILES_PATH = REPO_ROOT / "state" / "buyer_profiles.json"

TASKS_ROOT = REPO_ROOT / "agent_ops" / "tasks"
PENDING_DIR = TASKS_ROOT / "pending"
IN_PROGRESS_DIR = TASKS_ROOT / "in_progress"
DONE_DIR = TASKS_ROOT / "done"
FAILED_DIR = TASKS_ROOT / "failed"


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
        if (DATA_RUNS_DIR / run_id / filename).exists():
            return run_id
    return None


def _normalize_buyer_key(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*\\(.*?\\)\s*", " ", s)  # drop parenthetical noise
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _existing_task_ids() -> Set[str]:
    task_ids: Set[str] = set()
    for base in (PENDING_DIR, IN_PROGRESS_DIR, DONE_DIR, FAILED_DIR):
        if not base.exists():
            continue
        for path in base.glob("*.json"):
            task_ids.add(path.stem)
    return task_ids


def _make_task_id(task_type: str, key: str) -> str:
    h = hashlib.sha1(f"{task_type}:{key}".encode("utf-8")).hexdigest()
    return f"task_{h[:12]}"


def _buyer_profiles_keys() -> Set[str]:
    if not BUYER_PROFILES_PATH.exists():
        return set()
    try:
        data = _load_json(BUYER_PROFILES_PATH)
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    return {_normalize_buyer_key(k) for k in data.keys() if isinstance(k, str)}


def _iter_decision_buyers() -> Iterable[Tuple[str, str, str]]:
    """
    Yields (buyer_key, buyer_name, source_run_id) from latest decision_shortlist.json.
    """
    run_id = _find_latest_run_with_file("decision_shortlist.json")
    if not run_id:
        return []
    path = DATA_RUNS_DIR / run_id / "decision_shortlist.json"
    try:
        data = _load_json(path)
    except Exception:
        return []
    if not isinstance(data, dict) or not isinstance(data.get("opportunities"), list):
        return []
    out: List[Tuple[str, str, str]] = []
    for opp in data["opportunities"]:
        if not isinstance(opp, dict):
            continue
        buyer_name = opp.get("buyer_name") or opp.get("buyer")
        if not isinstance(buyer_name, str) or not buyer_name.strip():
            continue
        out.append((_normalize_buyer_key(buyer_name), buyer_name.strip(), run_id))
    return out


def _read_latest_outreach_queue() -> Tuple[Optional[Any], Optional[Path]]:
    latest = DATA_OUTREACH_DIR / "outreach_queue_latest.json"
    if latest.exists():
        try:
            return _load_json(latest), latest
        except Exception:
            return None, latest
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


def _iter_outreach_ready_items() -> Iterable[Dict[str, Any]]:
    data, _path = _read_latest_outreach_queue()
    items: List[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data["items"]

    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        send_ready = item.get("send_ready")
        status = item.get("status")
        is_ready = False
        if send_ready is True:
            is_ready = True
        elif isinstance(status, str) and status.strip().lower() == "ready":
            is_ready = True
        elif isinstance(item.get("suggested_email"), str) and item.get("suggested_email").strip():
            # In the current pipeline, suggested_email usually implies a draft exists.
            is_ready = True
        if is_ready:
            out.append(item)
    return out


def _completed_hermes_input_paths() -> Set[str]:
    completed: Set[str] = set()
    if not DATA_HERMES_RUNS_DIR.exists():
        return completed
    for summary_path in DATA_HERMES_RUNS_DIR.glob("*/summary.json"):
        try:
            data = _load_json(summary_path)
        except Exception:
            continue
        input_path = data.get("input_path") if isinstance(data, dict) else None
        if isinstance(input_path, str) and input_path:
            completed.add(input_path)
    return completed


def _iter_hermes_lead_csvs() -> Iterable[Path]:
    if not DATA_LEADS_DIR.exists():
        return []
    return sorted(DATA_LEADS_DIR.glob("*.csv"), key=lambda path: path.name)


def _write_task(task: Dict[str, Any]) -> Path:
    task_id = task["task_id"]
    path = PENDING_DIR / f"{task_id}.json"
    _atomic_write_json(path, task)
    return path


def main() -> int:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    existing = _existing_task_ids()
    created: List[str] = []
    now = datetime.now(timezone.utc).isoformat()

    buyer_profile_keys = _buyer_profiles_keys()
    seen_missing_buyers: Set[str] = set()
    for buyer_key, buyer_name, source_run_id in sorted(set(_iter_decision_buyers())):
        if not buyer_key or buyer_key in buyer_profile_keys:
            continue
        if buyer_key in seen_missing_buyers:
            continue
        seen_missing_buyers.add(buyer_key)
        task_id = _make_task_id("buyer_profile_missing", buyer_key)
        if task_id in existing:
            continue
        task = {
            "task_id": task_id,
            "agent": "research",
            "type": "buyer_profile_missing",
            "priority": "P2",
            "status": "pending",
            "created_at": now,
            "input": [
                {
                    "buyer_name": buyer_name,
                    "buyer_key": buyer_key,
                    "source_run_id": source_run_id,
                }
            ],
            "output": "",
        }
        _write_task(task)
        created.append(task_id)
        existing.add(task_id)

    for item in _iter_outreach_ready_items():
        outreach_id = item.get("outreach_id") or item.get("notice_id") or item.get("tender_reference") or ""
        outreach_key = str(outreach_id).strip() or (item.get("buyer_name") or item.get("buyer") or "")
        outreach_key = str(outreach_key)
        task_id = _make_task_id("outreach_approval", outreach_key)
        if task_id in existing:
            continue
        task = {
            "task_id": task_id,
            "agent": "operator",
            "type": "outreach_approval",
            "priority": "P1",
            "status": "pending",
            "created_at": now,
            "input": [
                {
                    "outreach_id": item.get("outreach_id", ""),
                    "buyer_name": item.get("buyer_name", ""),
                    "tender_title": item.get("tender_title", ""),
                    "tender_reference": item.get("tender_reference", ""),
                    "deadline": item.get("deadline", ""),
                    "value": item.get("value", ""),
                    "verdict": item.get("verdict", ""),
                    "risks": item.get("risks", []),
                    "suggested_subject": item.get("suggested_subject", ""),
                    "suggested_email": item.get("suggested_email", ""),
                    "source_run_id": item.get("source_run_id", ""),
                }
            ],
            "output": "",
        }
        _write_task(task)
        created.append(task_id)
        existing.add(task_id)

    completed_hermes_inputs = _completed_hermes_input_paths()
    for lead_csv in _iter_hermes_lead_csvs():
        rel_input = lead_csv.relative_to(REPO_ROOT).as_posix()
        if rel_input in completed_hermes_inputs:
            continue
        task_id = _make_task_id("hermes_enrichment_batch", rel_input)
        if task_id in existing:
            continue
        task = {
            "task_id": task_id,
            "agent": "hermes",
            "type": "hermes_enrichment_batch",
            "priority": "P1",
            "status": "pending",
            "created_at": now,
            "input": [
                {
                    "input_csv": rel_input,
                }
            ],
            "output": "",
        }
        _write_task(task)
        created.append(task_id)
        existing.add(task_id)

    summary = {
        "generated_at": now,
        "created_task_ids": created,
        "created_count": len(created),
    }
    summary_path = REPO_ROOT / "agent_ops" / "state" / "task_generation_summary.json"
    _atomic_write_json(summary_path, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
