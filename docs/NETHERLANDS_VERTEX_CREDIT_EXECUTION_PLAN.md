# Netherlands Vertex Credit Execution Plan

Status: Phases 1, 2, and 3 completed and staged for manual approval. Do not push. Do not commit Phase 1, Phase 2, or Phase 3 automatically.

## Objective

Use Google Cloud / Vertex AI credits intelligently to turn the Netherlands expansion work into commercial, reusable procurement intelligence assets for ProcessEd Intelligence without claiming unverified live Dutch coverage.

## Global Guardrails

- `run_pipeline.py` must remain unchanged.
- No pushes, merges, force pushes, or branch deletion.
- No secrets, credentials, `.env` files, ADC files, service account JSON, API keys, or cloud credential files.
- No invented personal contacts, emails, phone numbers, or verified relationships.
- Unverified outputs must stay marked `research_needed`, `sample_demo`, or `not_verified`.
- Use Gemini Flash or Flash-Lite only; do not use Pro.
- Use dry-run first, then controlled `--limit` runs before full Vertex runs.
- Do not store the concrete Google project ID in outputs; use `configured_via_GOOGLE_CLOUD_PROJECT`.

## Phases

### Phase 0 - Target Intelligence Recovery

Status: complete before this tracker was created.

Evidence:

- Branch confirmed: `feature/netherlands-expansion-pack`.
- Existing HEAD commit: `3241ce5 Add Vertex-enriched Netherlands target intelligence`.
- Commit contains the intended target intelligence files:
  - `scripts/enrich_netherlands_targets_with_vertex.py`
  - `data/outreach/netherlands_company_targets_enriched.csv`
  - `data/outreach/netherlands_company_targets_enriched.json`
  - `docs/NETHERLANDS_TARGET_ENRICHMENT_REPORT.md`
  - `tests/test_netherlands_target_enrichment.py`
- Previous verification: `python -m pytest tests/test_dutch_demo_bundle.py tests/test_netherlands_outreach_pack.py tests/test_netherlands_target_enrichment.py -q` passed.
- No push was made.

### Phase 1 - Live Source Readiness Intelligence

Status: staged for manual approval.

Generated artifacts:

- `scripts/enrich_netherlands_sources_with_vertex.py`
- `data/dutch/source_readiness/netherlands_source_readiness.json`
- `data/dutch/source_readiness/netherlands_source_readiness.csv`
- `docs/NETHERLANDS_LIVE_SOURCE_READINESS.md`
- `tests/test_netherlands_source_readiness.py`

Completed checks:

- Dry-run completed without Vertex calls.
- Controlled Vertex run completed with `--limit 3 --model gemini-2.5-flash`.
- Full Vertex run completed with `--model gemini-2.5-flash`.
- Readiness records include source caveats and `project: configured_via_GOOGLE_CLOUD_PROJECT`.
- Report keeps live coverage claims caveated as `research_needed`, `sample_demo`, or `not_verified`.

Test results:

- `python -m pytest tests/test_netherlands_source_readiness.py -q`: passed.
- `python -m pytest tests/test_dutch_demo_bundle.py tests/test_netherlands_outreach_pack.py tests/test_netherlands_target_enrichment.py tests/test_netherlands_source_readiness.py -q`: passed.

Manual approval gate:

- Phase 1 approval was granted by the user with "proceed all".
- No commit or push was made.

### Phase 2 - Buyer Memory Intelligence

Status: complete and staged for manual approval.

Planned artifacts:

- `scripts/build_netherlands_buyer_memory.py`
- `scripts/enrich_netherlands_buyer_memory_with_vertex.py`
- `data/dutch/buyer_memory/netherlands_buyer_memory.json`
- `data/dutch/buyer_memory/netherlands_buyer_memory_enriched.json`
- `docs/NETHERLANDS_BUYER_MEMORY_BRIEF.md`
- `tests/test_netherlands_buyer_memory.py`

Completed checks:

- Built buyer memory from sample/demo Netherlands opportunities.
- Dry-run enrichment completed without Vertex calls.
- Controlled Vertex run initially exposed parse/network fragility; prompt was reduced and controlled `--limit 5 --model gemini-2.5-flash` then generated all 5 records.
- Full Vertex run completed with 12 generated buyer-memory records.
- Outputs retain `sample_demo`, `research_needed`, `not_verified`, and `configured_via_GOOGLE_CLOUD_PROJECT`.

Test results:

- `python -m pytest tests/test_netherlands_buyer_memory.py -q`: passed.
- Included in final Netherlands suite: passed.

### Phase 3 - Account-Level Outreach Personalization

Status: complete and staged for manual approval.

Planned artifacts:

- `scripts/generate_netherlands_account_outreach_with_vertex.py`
- `data/outreach/netherlands_account_outreach_enriched.csv`
- `data/outreach/netherlands_account_outreach_enriched.json`
- `docs/NETHERLANDS_OUTREACH_PERSONALIZATION_REPORT.md`
- `tests/test_netherlands_account_outreach.py`

Completed checks:

- Dry-run generated 100 account-level outreach rows without Vertex calls.
- Controlled Vertex run completed with `--limit 10 --model gemini-2.5-flash` and generated all 10 records.
- Full Vertex run completed with 100 generated account outreach records.
- Outputs use generic salutations and do not include personal names, private inboxes, call numbers, or verified relationships.
- Every row keeps the `sample_demo research_needed not_verified` disclaimer and `configured_via_GOOGLE_CLOUD_PROJECT`.

Test results:

- `python -m pytest tests/test_netherlands_account_outreach.py -q`: passed.
- Included in final Netherlands suite: passed.

## Cost-Control Notes

- Default model: `gemini-2.5-flash`.
- Dry-run mode must not call Vertex.
- Controlled `--limit` runs precede full Vertex runs.
- Prompts are concise, low temperature, and request structured JSON where possible.
- VM remains stopped unless strictly needed.

## Current Status

Phases 1, 2, and 3 are complete and staged for manual approval. No commit or push has been made for Phase 1, Phase 2, or Phase 3.

Final test command:

`python -m pytest tests/test_dutch_demo_bundle.py tests/test_netherlands_outreach_pack.py tests/test_netherlands_target_enrichment.py tests/test_netherlands_source_readiness.py tests/test_netherlands_buyer_memory.py tests/test_netherlands_account_outreach.py -q`

Final test result: `35 passed`.

Known issue resolved:

- A Phase 2 controlled Vertex attempt briefly failed because of DNS/name resolution and JSON parse drift. The process exited, no secrets were written, and the prompt was tightened. The successful controlled and full reruns generated all buyer-memory records.
