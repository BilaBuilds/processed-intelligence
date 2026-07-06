# Netherlands Target Enrichment Report

Status: sample/demo target-account intelligence. All unverified account rows remain research_needed and are not verified live coverage.

## What Was Enriched

- Records enriched: 100
- Enrichment mode: dry-run heuristic
- Model: gemini-2.5-flash
- Project reference in outputs: configured_via_GOOGLE_CLOUD_PROJECT
- Source file: `data/outreach/netherlands_company_targets.csv`

## Controlled-Cost Approach

- The script supports `--dry-run` for no-cost validation.
- The script supports `--limit N` for small controlled Vertex batches.
- Prompts are concise, low temperature, and request structured JSON.
- Gemini Flash is the default model; Pro is not required.

## Priority Distribution

- High 80-100: 30
- Medium 60-79: 58
- Lower 0-59: 12
- Blank/error: 0

## Vertex Status Distribution

- dry_run: 100

## Segment Mix

- DACH contractors with possible Netherlands/EU interest: 13
- Dutch civils contractors: 15
- Dutch infrastructure contractors: 15
- UK contractors with possible Netherlands/EU interest: 12
- engineering consultancies: 15
- maintenance/framework contractors: 15
- water/public works suppliers: 15

## Top 10 Target Categories/Accounts After Enrichment

- NL-TGT-031: Water public works supplier target 031 | water/public works suppliers | score 90 | Lead with water authority resilience pilot
- NL-TGT-032: Water public works supplier target 032 | water/public works suppliers | score 90 | Ask for waterschap source coverage feedback
- NL-TGT-033: Water public works supplier target 033 | water/public works suppliers | score 90 | Validate flood resilience opportunity ranking
- NL-TGT-034: Water public works supplier target 034 | water/public works suppliers | score 90 | Ask for drainage maintenance pilot input
- NL-TGT-042: Water public works supplier target 042 | water/public works suppliers | score 90 | Ask about CPV groups for public works suppliers
- NL-TGT-016: Dutch infrastructure contractor target 016 | Dutch infrastructure contractors | score 89 | Discuss Rijkswaterstaat style source validation
- NL-TGT-017: Dutch infrastructure contractor target 017 | Dutch infrastructure contractors | score 89 | Validate port and logistics infrastructure segment
- NL-TGT-018: Dutch infrastructure contractor target 018 | Dutch infrastructure contractors | score 89 | Ask for bridge maintenance opportunity ranking feedback
- NL-TGT-025: Dutch infrastructure contractor target 025 | Dutch infrastructure contractors | score 89 | Validate higher-value opportunity scoring
- NL-TGT-028: Dutch infrastructure contractor target 028 | Dutch infrastructure contractors | score 89 | Ask for pilot conversation around selected CPVs

## Commercial Interpretation

The strongest rows should be treated as a prioritized research queue, not a verified prospect list. High scores generally indicate direct alignment with Dutch public works, water, infrastructure, or cross-border expansion needs. The enrichment is most useful for deciding which segment to validate first and which source questions to ask in founder-led outreach.

## Warnings And Caveats

- Company target rows are placeholders/categories unless separately researched.
- Do not treat any row as evidence of live procurement activity.
- Do not infer personal contacts, relationships, or buyer intent from this pack.
- Validate TenderNed, TED/EU notices, and source terms before making coverage claims.

## Next Manual Validation Steps

1. Replace placeholder account names with researched company accounts only after manual verification.
2. Validate source coverage for the top two segments with a small live source review.
3. Confirm whether the suggested outreach angles match real buyer/supplier pain points.
4. Run five founder feedback calls before scaling the list.

## Recommended Outreach Sequence

1. Start with a blunt feedback ask using the sample/demo disclaimer.
2. Offer the dashboard and one relevant source-validation question.
3. Follow up with a narrow four-week pilot proposal only if source relevance is confirmed.
4. Keep all claims grounded in sample/demo workflow until live coverage is verified.
