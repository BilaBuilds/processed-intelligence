# ProcessEd External Review Pack

Use this pack to have another reviewer (Claude/GPT/human engineer) verify the work independently.

## Files to review
1. `run_pipeline.py`
2. `src/select.py`
3. `src/decision.py`
4. `src/dedupe.py`
5. `src/notify/discord.py`
6. `src/leads_compliance.py`
7. `tests/test_select_filters.py`
8. `tests/test_decision.py`
9. `tests/test_dedupe.py`
10. `tests/test_leads_compliance.py`
11. `docs/PROCESS_ED_EXECUTION_PLAN_V1.md`
12. `docs/PROCESS_ED_COMPLIANCE_AUDIT_2026-03-31.md`

## External reviewer prompt (copy/paste)
Please perform a production-readiness and compliance-oriented code review of this project.

Focus on:
1. Correctness of pipeline flow and failure behavior.
2. Determinism and idempotency (select, decision, dedupe, notify).
3. Data-quality guards (stale deadlines, excluded statuses, duplicate suppression).
4. Compliance gate behavior for outbound lead activation (`src/leads_compliance.py`).
5. Test coverage gaps and high-risk edge cases.

Output format:
1. Findings first, ordered by severity (P1 to P3).
2. For each finding: file path, issue, impact, concrete fix.
3. Then list "what is strong."
4. Then list "must-fix before go-live."
5. Then provide a final verdict: Ready / Conditionally Ready / Not Ready.

## Acceptance criteria for sign-off
1. No P1 findings open.
2. Test suite passes.
3. Compliance gate path is reviewable and documented.
4. Manifest output remains truthful under notify success/failure.
5. No duplicate alerts from same-run duplicates.

## Verification commands
1. Unit tests:
   - `python -m unittest discover -s tests -p "test_*.py"`
2. Pipeline audit:
   - `powershell -ExecutionPolicy Bypass -File .\audit.ps1`
3. Forced notify:
   - `powershell -ExecutionPolicy Bypass -File .\audit.ps1 -ForceNotify`

