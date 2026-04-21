# Agent Spec: ingest_guardian

## Mission
Maintain reliable intake from FTS + Contracts Finder without breaking downstream steps.

## Owns
- `src/ingest.py`
- `src/fts_scraper.py`
- `data/last_fts_run.txt` behavior

## Inputs
- API responses
- env settings for limits/timeouts/lookback

## Outputs
- `raw_tenders.jsonl`
- `source_health` summary in pipeline context

## Hard rules
1. Never silently drop source failures.
2. Keep pagination safe (loop protection, max request cap).
3. Advance FTS watermark only on successful fetch flow.

## Done criteria
1. Ingest step stable across 2 consecutive runs.
2. Manifest shows truthful source health.

