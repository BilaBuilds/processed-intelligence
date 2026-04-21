# ProcessEd Runbook

## Daily
1. `python run_pipeline.py`
2. Check latest `data/runs/<run_id>/run_manifest.json`
3. Confirm notify status and new_count

## Weekly
1. `powershell -ExecutionPolicy Bypass -File .\audit.ps1`
2. Review stale/status filter counts and decision distribution
3. Archive review notes in `reviews/`

## Forced notify test (only for validation)
1. `powershell -ExecutionPolicy Bypass -File .\audit.ps1 -ForceNotify`
2. Verify Discord formatting and decision fields

## Quality gates before release
1. `python -m unittest discover -s tests -p "test_*.py"`
2. No open P1 findings in `reviews/`
3. Manifest truthfulness verified

