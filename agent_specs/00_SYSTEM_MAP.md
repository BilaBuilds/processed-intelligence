# ProcessEd Agent System Map

This project uses **5 logical agents** (roles), even if your host tool has 1 runtime identity.

## Why
Use clear ownership boundaries so work is parallelizable, testable, and low-risk.

## Agents
1. `ingest_guardian` -> data intake reliability
2. `signal_qa` -> filtering, scoring quality, stale/duplicate controls
3. `decision_auditor` -> BID/REVIEW/NO_BID quality and explainability
4. `compliance_guard` -> outbound eligibility and governance checks
5. `revenue_ops` -> outreach queue quality and conversion operations

## Canonical directories
- Specs: `agent_specs/`
- Work tickets: `tasks/`
- Reviews: `reviews/`
- Run artifacts: `runs/`

## Core pipeline files (current)
- `run_pipeline.py`
- `src/ingest.py`
- `src/normalize.py`
- `src/match.py`
- `src/select.py`
- `src/decision.py`
- `src/dedupe.py`
- `src/notify/discord.py`
- `src/leads_compliance.py`

