# ProcessEd External Review Prompt (Claude)

You are reviewing a production-oriented UK tender intelligence codebase.

## Objectives
1. Identify only meaningful findings (bugs, risks, regressions, compliance/control gaps).
2. Prioritize findings by severity (P1, P2, P3).
3. Propose concrete code-level fixes with file paths.
4. Validate whether the architecture is ready for the next scale phase (API-first lead engine + compliant outreach).

## Scope
Review these files:
- `run_pipeline.py`
- `src/select.py`
- `src/decision.py`
- `src/dedupe.py`
- `src/notify/discord.py`
- `src/leads_compliance.py`
- `tests/test_select_filters.py`
- `tests/test_decision.py`
- `tests/test_dedupe.py`
- `tests/test_leads_compliance.py`
- `docs/PROCESS_ED_EXECUTION_PLAN_V1.md`
- `docs/PROCESS_ED_COMPLIANCE_AUDIT_2026-03-31.md`

## Required output format
1. Findings first, ordered P1 -> P3.
2. For each finding:
   - Title
   - Severity
   - File path
   - Why it matters
   - Exact fix
3. "What is strong" section.
4. "Must-fix before go-live" section.
5. Final verdict:
   - Ready
   - Conditionally Ready
   - Not Ready

## Review constraints
1. Be strict about correctness, determinism, idempotency, and operational reliability.
2. Check for hidden duplication paths and stale data paths.
3. Treat compliance controls as first-class engineering requirements.
4. Avoid generic advice; provide implementation-grade feedback.

