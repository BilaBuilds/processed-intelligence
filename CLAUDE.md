# Tender Engine Operating Instructions

## Project root
Always treat this as the only repo root:

`C:\Users\bilal\tender_engine`

Never assume the project is in `C:\Dev` or any other folder.

## Canonical run command
Preferred command from any directory:

`powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\bilal\tender_engine\run_tenders.ps1`

PowerShell profile alias may also exist:

`run-tenders`

## Direct fallback
If the wrapper cannot be used:

`python C:\Users\bilal\tender_engine\run_pipeline.py`

## Required behavior before acting
Before running, editing, or making assumptions:

1. Show current directory:
   - `Get-Location`

2. Confirm the repo exists:
   - `Test-Path C:\Users\bilal\tender_engine`
   - `Test-Path C:\Users\bilal\tender_engine\run_pipeline.py`

3. If work depends on the repo, use:
   - `C:\Users\bilal\tender_engine`

## Runtime rules
- Prefer local machine execution for live API pulls.
- Treat sandbox/API/network failures as environment constraints unless proven otherwise.
- If UK tender endpoints fail only inside the assistant runtime, state clearly:
  - `This failure is sandbox/network constrained, not a repo regression.`

## What to report after a run
After running the pipeline, report:

- `run_id`
- ingest counts by source
- shortlist count
- new count
- notify status
- full manifest path

## Manifest location
Runs are saved under:

`C:\Users\bilal\tender_engine\data\runs\`

Latest manifest pattern:

`C:\Users\bilal\tender_engine\data\runs\<run_id>\run_manifest.json`

## Discord
Canonical environment variable:

`TENDER_WEBHOOK_URL`

Set/test with:

`powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\bilal\tender_engine\set_webhook.ps1`

If notify fails due to webhook/auth errors, treat that as config/runtime diagnosis work, not pipeline-core failure.

## Path discipline
- Never assume relative execution from the current shell is safe.
- Prefer absolute paths.
- Wrapper-first, direct-python second.

## Interpretation rules
- `Notify: skipped` with `new_count = 0` is normal.
- `FTS: 0 releases fetched` is not automatically an error.
- A successful run with no new opportunities is still a healthy run.
