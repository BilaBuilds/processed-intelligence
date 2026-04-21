# Agent Handoff Contract

Use this contract between agents to avoid drift.

## Required handoff payload
```json
{
  "task_id": "TASK-YYYYMMDD-###",
  "agent": "ingest_guardian|signal_qa|decision_auditor|compliance_guard|revenue_ops",
  "status": "ok|review|blocked",
  "changed_files": ["path1", "path2"],
  "tests_ran": ["command1", "command2"],
  "evidence": ["artifact path or log line"],
  "risks": ["risk1", "risk2"],
  "next_actions": ["next1", "next2"]
}
```

## Merge rules
1. No merge without evidence.
2. No merge on `blocked`.
3. `review` requires explicit sign-off note in `reviews/`.

