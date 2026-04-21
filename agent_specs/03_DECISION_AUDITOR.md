# Agent Spec: decision_auditor

## Mission
Ensure decision outputs are useful, consistent, and defensible.

## Owns
- `src/decision.py`
- decision-related notifier formatting in `src/notify/discord.py`
- tests: `tests/test_decision.py`

## Inputs
- shortlist records with score + breakdown

## Outputs
- `decision_all.json`
- `decision_shortlist.json`
- fields: verdict, confidence, reasons, risk flags

## Hard rules
1. Verdict logic must be deterministic.
2. Confidence must stay bounded (0-100).
3. No hidden randomness.
4. Decision summaries must be human-readable in alerts.

## Done criteria
1. Decision tests pass.
2. Manifest includes decision counters.

