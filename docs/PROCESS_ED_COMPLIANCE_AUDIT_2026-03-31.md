# ProcessEd Compliance + Readiness Audit
Date: 2026-03-31
Scope: Tender intelligence stack + planned lead activation expansion

## Executive summary
The core tender engine is production-functional. The next risk frontier is outbound lead generation compliance and governance, not scraping capability. This audit recommends an API-first lead pipeline and a hard compliance gate before any outbound marketing workflow.

## What is strong now
1. Deterministic pipeline and run manifests.
2. Decision layer and explainable output.
3. Dedupe and notification controls.
4. Stale/closed filtering already reducing noise.
5. Test suite now includes selection, dedupe, decision, and compliance gate tests.

## Key risks to address before scaling outreach
P1:
1. No complete outreach compliance workflow yet (suppression + objection SLA + privacy delivery workflow).
2. No canonical lead store with provenance and activation status.

P2:
1. No campaign governance metrics tied to compliance status.
2. No formal review cadence with legal/compliance owner.

P3:
1. Limited role/contact enrichment capabilities if only tender-side data is used.

## Controls implemented in code (new)
1. `src/leads_compliance.py`
2. `tests/test_leads_compliance.py`

Control behavior:
1. blocks suppression list contacts
2. blocks invalid sender/opt-out controls
3. requires consent/soft-opt-in path for individual or unknown subscriber type
4. forces governance review when lawful-basis artifacts are incomplete

## Compliance policy baseline (engineering interpretation)
1. Corporate-subscriber marketing and individual-subscriber marketing are not treated the same.
2. GDPR still applies where personal data is used.
3. Right to object for direct marketing must be honored absolutely.
4. Suppression is mandatory and should be retained to prevent re-contact.
5. Transparency obligations apply at or before first marketing communication.

## Evidence and verification checklist
Pass/fail checks:
1. Lead record includes subscriber classification.
2. Suppression check executes before queueing.
3. Every send includes sender identity and unsubscribe route.
4. Objection event immediately updates suppression store.
5. Audit log records message id, legal path, and decision status.

## Recommendations for reviewers
1. Validate lawful basis assumptions with qualified UK counsel.
2. Review PECR-specific path differences by subscriber type.
3. Confirm retention policy and DSAR handling process.
4. Confirm provider contracts (DPA, SCC/IDTA where relevant).

## Sources used for this audit baseline
1. ICO direct marketing guidance:
   - https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/direct-marketing-guidance/plan-direct-marketing/
2. ICO right to object (Article 21):
   - https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/right-to-object/

Note:
This audit is an engineering/compliance implementation view, not legal advice.

