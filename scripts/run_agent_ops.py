import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from enrichment.agents.hermes import HermesAgent


TASKS_ROOT = REPO_ROOT / "agent_ops" / "tasks"
PENDING_DIR = TASKS_ROOT / "pending"
IN_PROGRESS_DIR = TASKS_ROOT / "in_progress"
DONE_DIR = TASKS_ROOT / "done"
FAILED_DIR = TASKS_ROOT / "failed"

LOGS_DIR = REPO_ROOT / "agent_ops" / "logs"
EVENT_LOG = LOGS_DIR / "agent_events.jsonl"

MEMORY_DIR = REPO_ROOT / "agent_ops" / "memory"
BUYER_PROFILE_STUBS_DIR = MEMORY_DIR / "buyer_profile_stubs"
OUTREACH_APPROVALS_DIR = MEMORY_DIR / "outreach_approvals"
HERMES_RUNS_DIR = REPO_ROOT / "data" / "hermes" / "runs"
ENRICHMENT_CONFIG = REPO_ROOT / "enrichment" / "config.yaml"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _append_event(event: Dict[str, Any]) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
        f.write("\n")


def _move_task(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists():
        # deterministic: overwrite is not allowed; keep the original and treat as no-op
        return dst
    shutil.move(str(src), str(dst))
    return dst


def _process_buyer_profile_missing(task: Dict[str, Any]) -> str:
    BUYER_PROFILE_STUBS_DIR.mkdir(parents=True, exist_ok=True)
    inputs = task.get("input") or []
    first = inputs[0] if isinstance(inputs, list) and inputs else {}
    buyer_name = first.get("buyer_name", "")
    buyer_key = first.get("buyer_key", "")
    stub_path = BUYER_PROFILE_STUBS_DIR / f"{buyer_key or task['task_id']}.json"
    stub = {
        "buyer_name": buyer_name,
        "buyer_key": buyer_key,
        "requested_at": _now(),
        "template": {
            "full_name": "",
            "frequency": "",
            "avg_value": "",
            "style": "",
            "contact_pattern": "",
        },
        "notes": "",
    }
    _atomic_write_json(stub_path, stub)
    return stub_path.as_posix()


def _process_outreach_approval(task: Dict[str, Any]) -> str:
    OUTREACH_APPROVALS_DIR.mkdir(parents=True, exist_ok=True)
    inputs = task.get("input") or []
    first = inputs[0] if isinstance(inputs, list) and inputs else {}
    md_path = OUTREACH_APPROVALS_DIR / f"{task['task_id']}.md"

    buyer = str(first.get("buyer_name", "")).strip()
    title = str(first.get("tender_title", "")).strip()
    ref = str(first.get("tender_reference", "")).strip()
    deadline = str(first.get("deadline", "")).strip()
    value = str(first.get("value", "")).strip()
    verdict = str(first.get("verdict", "")).strip()
    risks = first.get("risks", [])
    if not isinstance(risks, list):
        risks = [str(risks)]
    suggested_subject = str(first.get("suggested_subject", "")).strip()
    suggested_email = str(first.get("suggested_email", "")).strip()
    source_run_id = str(first.get("source_run_id", "")).strip()

    lines: List[str] = []
    lines.append(f"# Outreach Approval: {task['task_id']}")
    lines.append("")
    lines.append(f"- Buyer: {buyer or '(missing)'}")
    lines.append(f"- Tender: {title or '(missing)'}")
    lines.append(f"- Reference: {ref or '(missing)'}")
    lines.append(f"- Deadline: {deadline or '(missing)'}")
    lines.append(f"- Value: {value or '(missing)'}")
    lines.append(f"- Verdict: {verdict or '(missing)'}")
    lines.append(f"- Source run: {source_run_id or '(missing)'}")
    lines.append(f"- Risks: {', '.join([str(r) for r in risks]) if risks else '(none)'}")
    lines.append("")
    lines.append("## Suggested Subject")
    lines.append("")
    lines.append(suggested_subject or "(missing)")
    lines.append("")
    lines.append("## Suggested Email")
    lines.append("")
    if suggested_email:
        lines.append("```")
        lines.append(suggested_email.rstrip())
        lines.append("```")
    else:
        lines.append("(missing)")
    lines.append("")
    lines.append("## Approval Checklist")
    lines.append("")
    lines.append("- No fake bidding language")
    lines.append("- No invented named contacts")
    lines.append("- Appropriate route (portal-only risk?)")
    lines.append("- Buyer fit is credible")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path.as_posix()


def _process_hermes_enrichment_batch(task: Dict[str, Any]) -> str:
    inputs = task.get("input") or []
    first = inputs[0] if isinstance(inputs, list) and inputs else {}
    input_csv = str(first.get("input_csv", "")).strip()
    if not input_csv:
        raise ValueError("Hermes task missing input_csv.")

    input_path = REPO_ROOT / input_csv
    if not input_path.exists():
        raise FileNotFoundError(f"Hermes input CSV not found: {input_csv}")

    run_id = f"{task['task_id']}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run_dir = HERMES_RUNS_DIR / run_id
    output_path = run_dir / "enriched_output.csv"
    summary_path = run_dir / "summary.json"

    agent = HermesAgent.from_config(ENRICHMENT_CONFIG)
    try:
        agent.enrich_csv(input_path, output_path, summary_path, run_id=run_id)
    finally:
        agent.close()

    return summary_path.relative_to(REPO_ROOT).as_posix()


def _process_task(task: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
    task_type = task.get("type")
    if task_type == "buyer_profile_missing":
        return True, "ok", _process_buyer_profile_missing(task)
    if task_type == "outreach_approval":
        return True, "ok", _process_outreach_approval(task)
    if task_type == "hermes_enrichment_batch":
        return True, "ok", _process_hermes_enrichment_batch(task)
    return False, "unknown_task_type", None


def main() -> int:
    for d in (PENDING_DIR, IN_PROGRESS_DIR, DONE_DIR, FAILED_DIR):
        d.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    # 1) pending -> in_progress
    pending_files = sorted(PENDING_DIR.glob("*.json"), key=lambda p: p.name)
    for src in pending_files:
        dst = _move_task(src, IN_PROGRESS_DIR)
        _append_event(
            {
                "ts": _now(),
                "event": "task_moved",
                "task_id": dst.stem,
                "from": "pending",
                "to": "in_progress",
            }
        )

    # 2) process in_progress -> done/failed
    in_progress_files = sorted(IN_PROGRESS_DIR.glob("*.json"), key=lambda p: p.name)
    for path in in_progress_files:
        task_id = path.stem
        try:
            task = _load_json(path)
            if not isinstance(task, dict):
                raise ValueError("Task JSON is not an object.")
        except Exception as e:
            failed_path = _move_task(path, FAILED_DIR)
            _append_event(
                {
                    "ts": _now(),
                    "event": "task_failed",
                    "task_id": task_id,
                    "reason": "parse_error",
                    "error": str(e),
                    "path": failed_path.as_posix(),
                }
            )
            continue

        ok, result, output_path = _process_task(task)
        task["status"] = "done" if ok else "failed"
        task["completed_at"] = _now()
        task["output"] = output_path or ""
        _atomic_write_json(path, task)

        dst_dir = DONE_DIR if ok else FAILED_DIR
        final_path = _move_task(path, dst_dir)
        _append_event(
            {
                "ts": _now(),
                "event": "task_processed",
                "task_id": task_id,
                "agent": task.get("agent", ""),
                "type": task.get("type", ""),
                "result": result,
                "status": task["status"],
                "output": task["output"],
                "path": final_path.as_posix(),
            }
        )

    # Ensure log file exists even if there were no tasks.
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    EVENT_LOG.touch(exist_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
