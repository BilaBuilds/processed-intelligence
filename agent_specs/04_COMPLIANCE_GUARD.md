# Agent Spec: compliance_guard

## Mission
Block non-compliant outbound activation before outreach starts.

## Owns
- `src/leads_compliance.py`
- tests: `tests/test_leads_compliance.py`
- compliance docs under `docs/`

## Inputs
- lead records (email, subscriber type, consent flags, suppression flags)

## Outputs
- `ALLOW / REVIEW / BLOCK` decision with reasons and required actions

## Hard rules
1. Suppression-list matches are always blocked.
2. Missing identity/opt-out controls are blocked.
3. Individual/unknown subscribers require consent or soft-opt-in path.
4. Governance gaps produce REVIEW, not silent allow.

## Done criteria
1. Compliance tests pass.
2. Rules documented and externally reviewable.

