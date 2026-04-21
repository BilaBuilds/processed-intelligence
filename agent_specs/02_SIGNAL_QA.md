# Agent Spec: signal_qa

## Mission
Keep feed quality high by removing stale, closed, duplicate, and low-value noise.

## Owns
- `src/normalize.py`
- `src/match.py`
- `src/select.py`
- `src/dedupe.py`
- tests: `tests/test_select_filters.py`, `tests/test_dedupe.py`

## Inputs
- normalized/scored records

## Outputs
- shortlist with high signal-to-noise ratio
- deduped `new_tenders.json`

## Hard rules
1. Stale deadlines must be filtered.
2. Excluded statuses/tags must not leak.
3. Duplicate same-run variants must not appear in outbound set.
4. Determinism: same input + same config = same shortlist.

## Done criteria
1. Select and dedupe tests pass.
2. Audit shows reduced stale/closed leakage.

