import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRS = [
    REPO_ROOT / "agent_ops",
    REPO_ROOT / "agent_ops" / "state",
    REPO_ROOT / "agent_ops" / "memory",
    REPO_ROOT / "agent_ops" / "logs",
    REPO_ROOT / "agent_ops" / "decisions",
    REPO_ROOT / "agent_ops" / "risks",
    REPO_ROOT / "agent_ops" / "ideas",
    REPO_ROOT / "agent_ops" / "tasks" / "pending",
    REPO_ROOT / "agent_ops" / "tasks" / "in_progress",
    REPO_ROOT / "agent_ops" / "tasks" / "done",
    REPO_ROOT / "agent_ops" / "tasks" / "failed",
    REPO_ROOT / "agent_ops" / "reports" / "daily",
    REPO_ROOT / "agent_ops" / "backups",
]

CURRENT_STATE = REPO_ROOT / "agent_ops" / "state" / "current_state.json"
EVENT_LOG = REPO_ROOT / "agent_ops" / "logs" / "agent_events.jsonl"


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _check_dirs() -> List[str]:
    errors: List[str] = []
    for d in REQUIRED_DIRS:
        if not d.exists() or not d.is_dir():
            errors.append(f"Missing required directory: {d.relative_to(REPO_ROOT).as_posix()}")
    return errors


def _check_current_state() -> List[str]:
    if not CURRENT_STATE.exists():
        return ["Missing agent_ops/state/current_state.json"]
    try:
        obj = _load_json(CURRENT_STATE)
    except Exception as e:
        return [f"Failed to parse current_state.json: {e}"]
    if not isinstance(obj, dict):
        return ["current_state.json is not a JSON object"]
    return []


def _check_task_duplicates() -> List[str]:
    tasks_root = REPO_ROOT / "agent_ops" / "tasks"
    ids: Dict[str, List[str]] = {}
    for path in tasks_root.rglob("*.json"):
        if not path.is_file():
            continue
        task_id = path.stem
        rel = path.relative_to(REPO_ROOT).as_posix()
        ids.setdefault(task_id, []).append(rel)
    dups = {k: v for k, v in ids.items() if len(v) > 1}
    errors: List[str] = []
    for task_id, locations in sorted(dups.items(), key=lambda kv: kv[0]):
        errors.append(f"Duplicate task_id {task_id} in: {', '.join(sorted(locations))}")
    return errors


def _check_logs() -> List[str]:
    if not EVENT_LOG.exists():
        return ["Missing agent_ops/logs/agent_events.jsonl"]
    return []


def _check_daily_report() -> List[str]:
    report = REPO_ROOT / "agent_ops" / "reports" / "daily" / f"daily_sync_{date.today().isoformat()}.md"
    if not report.exists():
        return [f"Missing daily report: {report.relative_to(REPO_ROOT).as_posix()}"]
    return []


def main() -> int:
    errors: List[str] = []
    errors.extend(_check_dirs())
    errors.extend(_check_current_state())
    errors.extend(_check_task_duplicates())
    errors.extend(_check_logs())
    errors.extend(_check_daily_report())

    if errors:
        print("FAIL")
        for e in errors:
            print(f"- {e}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

