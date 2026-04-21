# ProcessEd External Review Prompt (Gemini)

Act as a principal engineer + delivery risk reviewer.

## Task
Perform a deep technical and operational review of the attached ProcessEd files.
Focus on production behavior, not style.

## Review goals
1. Detect bugs and edge-case failures.
2. Validate step ordering and data contracts across pipeline stages.
3. Validate decision logic consistency and dedupe correctness.
4. Validate notification safety and manifest truthfulness.
5. Validate outreach compliance gate logic quality and completeness.

## Files to review
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

## Output format (mandatory)
1. Findings (P1/P2/P3) with:
   - file
   - issue
   - impact
   - recommended patch
2. Coverage gaps in tests.
3. Highest-risk failure scenarios still unmitigated.
4. Green flags (what is already strong).
5. Final go-live recommendation:
   - Go
   - Go with conditions
   - No-go

## Standard
Assume this will be used for real revenue operations and external clients.
Feedback must be concrete, verifiable, and implementation-ready.

