import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "agent_ops" / "state" / "current_state.json"

TASKS_ROOT = REPO_ROOT / "agent_ops" / "tasks"
PENDING_DIR = TASKS_ROOT / "pending"
IN_PROGRESS_DIR = TASKS_ROOT / "in_progress"
DONE_DIR = TASKS_ROOT / "done"
FAILED_DIR = TASKS_ROOT / "failed"

RISKS_DIR = REPO_ROOT / "agent_ops" / "risks"

REPORTS_DIR = REPO_ROOT / "agent_ops" / "reports" / "daily"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = _load_json(STATE_PATH)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _list_tasks(dir_path: Path) -> List[Dict[str, Any]]:
    if not dir_path.exists():
        return []
    tasks: List[Dict[str, Any]] = []
    for path in sorted(dir_path.glob("*.json"), key=lambda p: p.name):
        try:
            t = _load_json(path)
        except Exception:
            continue
        if isinstance(t, dict):
            tasks.append(t)
    return tasks


def _task_counts() -> Dict[str, int]:
    return {
        "pending": len(list(PENDING_DIR.glob("*.json"))) if PENDING_DIR.exists() else 0,
        "in_progress": len(list(IN_PROGRESS_DIR.glob("*.json"))) if IN_PROGRESS_DIR.exists() else 0,
        "done": len(list(DONE_DIR.glob("*.json"))) if DONE_DIR.exists() else 0,
        "failed": len(list(FAILED_DIR.glob("*.json"))) if FAILED_DIR.exists() else 0,
    }


def _read_risks() -> List[str]:
    if not RISKS_DIR.exists():
        return []
    risks: List[str] = []
    for path in sorted(RISKS_DIR.glob("*.md"), key=lambda p: p.name):
        risks.append(path.name)
    for path in sorted(RISKS_DIR.glob("*.json"), key=lambda p: p.name):
        risks.append(path.name)
    return risks


def _suggest_next_actions(pending: List[Dict[str, Any]]) -> List[str]:
    types = {str(t.get("type", "")).strip() for t in pending}
    actions: List[str] = []
    if "outreach_approval" in types:
        actions.append("Review P1 outreach approvals (operator).")
    if "buyer_profile_missing" in types:
        actions.append("Fill missing buyer profile stubs (research).")
    if "hermes_enrichment_batch" in types:
        actions.append("Run Hermes enrichment batch for new lead CSVs.")
    if not actions and pending:
        actions.append("Work down pending tasks by priority.")
    if not actions:
        actions.append("No pending tasks detected.")
    return actions


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    state = _read_state()
    counts = _task_counts()
    pending_tasks = _list_tasks(PENDING_DIR)

    run_id = state.get("run_id", "(unknown)")
    pipeline_status = state.get("pipeline_status", "(unknown)")
    shortlist_count = state.get("shortlist_count")
    decision_counts = state.get("decision_counts") or {}
    outreach_count = state.get("outreach_count")
    hermes = state.get("hermes") or {}
    warnings = state.get("warnings") or []

    report_date = date.today().isoformat()
    path = REPORTS_DIR / f"daily_sync_{report_date}.md"

    lines: List[str] = []
    lines.append(f"# Daily Sync ({report_date})")
    lines.append("")
    lines.append("## Run Summary")
    lines.append("")
    lines.append(f"- Run ID: {run_id}")
    lines.append(f"- Pipeline status: {pipeline_status}")
    lines.append(f"- Shortlist count: {shortlist_count if shortlist_count is not None else '(unknown)'}")
    lines.append(f"- Decision counts: {json.dumps(decision_counts, ensure_ascii=False, sort_keys=True)}")
    lines.append(f"- Outreach count: {outreach_count if outreach_count is not None else '(unknown)'}")
    if isinstance(hermes, dict) and hermes:
        lines.append(
            "- Hermes: "
            f"{hermes.get('enriched', 0)}/{hermes.get('total', 0)} enriched, "
            f"{hermes.get('with_email', 0)} with email, "
            f"{hermes.get('with_phone', 0)} with phone, "
            f"{hermes.get('drafts_created', 0)} drafts, "
            f"{hermes.get('approval_ready', 0)} approval-ready"
        )
    else:
        lines.append("- Hermes: no enrichment run recorded")
    lines.append("")
    lines.append("## Key Findings")
    lines.append("")
    if warnings:
        for w in warnings[:10]:
            lines.append(f"- {w}")
    else:
        lines.append("- No warnings recorded in current_state.json.")
    lines.append("")
    lines.append("## Risks")
    lines.append("")
    risk_files = _read_risks()
    if risk_files:
        for r in risk_files[:10]:
            lines.append(f"- {r}")
    else:
        # Treat state warnings as operational risks to scan.
        if warnings:
            lines.append("- See warnings in Key Findings.")
        else:
            lines.append("- None logged.")
    lines.append("")
    lines.append("## Tasks")
    lines.append("")
    lines.append(f"- Counts: {json.dumps(counts, ensure_ascii=False, sort_keys=True)}")
    if pending_tasks:
        for t in pending_tasks[:10]:
            lines.append(
                f"- {t.get('priority','P?')} {t.get('type','(missing type)')} ({t.get('agent','(missing agent)')}): {t.get('task_id','(missing id)')}"
            )
    else:
        lines.append("- No pending tasks.")
    lines.append("")
    lines.append("## Next Actions")
    lines.append("")
    for a in _suggest_next_actions(pending_tasks):
        lines.append(f"- {a}")
    lines.append("")
    lines.append(f"_Generated at {datetime.now(timezone.utc).isoformat()}_")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
