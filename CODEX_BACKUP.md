# CODEX HARD BACKUP: Tender Engine

Follow these rules exactly.

## Repo
The only valid repo root is:

C:\Users\bilal\tender_engine

Do not assume C:\Dev is the repo.
Do not assume relative paths are correct.

## First steps
Always do this first:

1. Run:
   Get-Location

2. Verify:
   Test-Path C:\Users\bilal\tender_engine
   Test-Path C:\Users\bilal\tender_engine\run_pipeline.py

3. Use the repo at:
   C:\Users\bilal\tender_engine

## Canonical run method
Primary:
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\bilal\tender_engine\run_tenders.ps1

Optional alias:
run-tenders

Fallback:
python C:\Users\bilal\tender_engine\run_pipeline.py

## What to report after running
Return these exact items:

- run_id
- ingest counts by source
- shortlist count
- new count
- notify status
- full manifest path

## Network interpretation
If tender API calls fail only inside the assistant runtime or sandbox, say exactly:

This failure is sandbox/network constrained, not a repo regression.

Do not misdiagnose sandbox egress restrictions as code breakage.

## Discord
Canonical webhook variable:
TENDER_WEBHOOK_URL

Setup/test command:
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\bilal\tender_engine\set_webhook.ps1

If Discord webhook fails with 401/403/404, treat it as webhook/configuration failure, not core pipeline failure.

## Behavior rules
- Prefer absolute paths.
- Prefer wrapper-first execution.
- Never assume the current shell directory is the repo.
- Report what changed before destructive edits.
- Do not claim the pipeline is broken if the only issue is sandbox network policy.
- A run with `new_count = 0` and `Notify: skipped` is valid and healthy.

## Success pattern
Healthy run may look like:
- Contracts Finder returns records
- FTS may return 0 releases in the current window
- pipeline status = success
- new_count = 0
- notify = skipped

That is not a failure.
