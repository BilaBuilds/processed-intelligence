# ProcessEd Execution Scoreboard
Date: 2026-04-01  
Cadence: Weekly (with daily operational checks)  
Purpose: Single source of truth for reliability, decision quality, revenue, and compliance performance.

## 1) KPI Definitions and Red Lines

| Category | KPI | Definition | Source | Weekly target | Red line | Owner | Action if red line hit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Product reliability | Pipeline success rate | Successful pipeline runs / total scheduled runs | `data/runs/*/run_manifest.json` | >= 99.0% | < 97.0% | Data engineering lead | Freeze feature changes, run incident RCA in 24h |
| Product reliability | Freshness lag (CF) | Median hours from source update to ingest completion | Ingest timestamps | <= 6h | > 12h | Data engineering lead | Trigger connector health audit and retry policy review |
| Product reliability | Freshness lag (FTS) | Median hours from source update to ingest completion | Ingest timestamps | <= 6h | > 12h | Data engineering lead | Check watermark logic and pagination path |
| Product reliability | Dedupe precision | 1 - (duplicate alerts sent / total alerts sent) | `state/sent_log.sqlite`, run manifests | >= 99.5% | < 98.5% | Decision systems lead | Block outbound for dedupe patch verification |
| Decision quality | Decision explainability coverage | Decision events with reason codes / total decision events | Decision logs | 100% | < 99.0% | Decision systems lead | Reject release until reason code path fixed |
| Decision quality | Shortlist-to-positive-response rate | Positive replies / opportunities sent | Outreach tracker + notify logs | >= 8% | < 4% | Growth ops lead | Recalibrate targeting and decision thresholds |
| Decision quality | Bid recommendation acceptance rate | Opportunities marked BID/REVIEW and accepted by operator / total BID/REVIEW | Internal operator review log | >= 70% | < 55% | Decision systems lead | Run scoring drift review and reason audit |
| Revenue | Outreach volume | New outbound sends per week | Outreach tracker | 100 to 150 | < 70 | Growth ops lead | Increase list build capacity and message throughput |
| Revenue | Reply rate | Replies / total outbound sends | Outreach tracker | >= 10% | < 6% | Growth ops lead | Rewrite Day 1/Day 2 copy and tighten ICP |
| Revenue | Calls booked | Qualified calls booked per week | CRM / tracker | >= 5 | < 2 | Sales owner | Escalate to direct-call and referral motion |
| Revenue | Pilot conversion | Pilot starts / qualified calls | CRM / tracker | >= 25% | < 15% | Sales owner | Update offer framing and qualification script |
| Revenue | Paid retention (30-day) | Paid accounts retained at day 30 / paid starts | Billing + CRM | >= 80% | < 65% | Product + growth | Add onboarding intervention and value checkpoint |
| Compliance | Suppression violations | Sends to opted-out/suppressed contacts | Outreach + suppression logs | 0 | >= 1 | Compliance ops lead | Immediate send halt + incident review |
| Compliance | Opt-out SLA compliance | Opt-outs processed inside SLA / total opt-outs | Suppression system logs | 100% in <= 24h | < 100% | Compliance ops lead | Hotfix suppression workflow within same day |
| Compliance | Provenance completeness | Records with valid source references / total records used in decisions | Data quality checks | >= 98% | < 95% | Data governance owner | Block institutional output generation |

## 2) Weekly Review Operating Loop

### Monday (Reliability + pipeline quality)

1. Review reliability KPIs and freshness lag.
2. Check dedupe precision and decision explainability coverage.
3. Assign technical fixes before outbound week starts.

### Wednesday (Decision quality + GTM tuning)

1. Review shortlist-to-positive-response and bid acceptance rates.
2. Calibrate thresholds and reason codes from real responses.
3. Approve or reject scoring adjustments using evidence only.

### Friday (Commercial + compliance closeout)

1. Review outreach, calls, pilots, and retention indicators.
2. Review compliance KPIs (suppression, opt-out SLA, provenance).
3. Publish weekly scorecard with green/yellow/red by track.

## 3) Weekly Scorecard Template

Use this format every Friday:

| Track | Status (G/Y/R) | What changed this week | KPI evidence | Next week focus |
| --- | --- | --- | --- | --- |
| Track A: Data and graph foundation |  |  |  |  |
| Track B: Decision and explainability |  |  |  |  |
| Track C: SME revenue workflow |  |  |  |  |
| Track D: Compliance and governance |  |  |  |  |
| Track E: GTM and conversion ops |  |  |  |  |

Status rules:
- Green: all critical KPIs above target and no red-line events.
- Yellow: one or more KPIs below target but above red line.
- Red: any red-line breach or unresolved incident.

## 4) Acceptance Gates (Execution Readiness)

### Gate 1: Operational trust

- Pipeline success rate >= 99% for 4 consecutive weeks.
- No unresolved red-line reliability incidents.

### Gate 2: Decision trust

- Explainability coverage at 100% for 4 consecutive weeks.
- Bid recommendation acceptance rate >= 70% rolling 4 weeks.

### Gate 3: Commercial repeatability

- Reply rate >= 10% and calls booked >= 5 weekly for 3 consecutive weeks.
- Pilot conversion >= 25% over rolling 30 days.

### Gate 4: Compliance integrity

- Zero suppression violations.
- 100% opt-out SLA compliance.
- Provenance completeness >= 98% for all decision-driving records.

## 5) Scenario Drill Matrix

| Scenario | Trigger | Expected behavior | Pass condition |
| --- | --- | --- | --- |
| No-new-tenders day | `new_count = 0` | Pipeline succeeds, status explicit, no false alerting | Manifest state trustworthy and dashboard remains green/yellow based on KPIs |
| High-volume burst | Ingest volume > 3x baseline | Select/decision/dedupe remain stable and timely | Processing time within SLO and dedupe precision >= 99.5% |
| Compliance objection | Contact opts out | Suppression state flips and outreach blocks immediately | No subsequent sends to that contact/account |

## 6) Escalation Rules

1. Any compliance red-line breach triggers immediate outbound pause.
2. Any two reliability red-line events in one week trigger change freeze until RCA closed.
3. Any three consecutive weeks of revenue red-line underperformance trigger offer/ICP reset workshop.

## 7) Ownership Matrix

| Function | Primary owner | Backup owner |
| --- | --- | --- |
| Data reliability and freshness | Data engineering lead | Platform engineer |
| Decision quality and calibration | Decision systems lead | Product lead |
| Outreach and conversion execution | Growth ops lead | Sales owner |
| Compliance operations | Compliance ops lead | Legal/commercial advisor |
| Weekly scorecard publication | Program owner (Bilal) | Operations analyst |
