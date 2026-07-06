# ProcessEd Current State

## Canonical Status

ProcessEd is a UK civils buyer intelligence and direct opportunity engine running on a VPS.

The system ingests public tender data, filters for civils relevance, scores fit, classifies action, generates buyer intelligence, and produces safe outreach/approval outputs.

## Business Model

Current model:
Direct buyer acquisition.

ProcessEd Civils is not currently prioritising:
- portal registration
- heavy supplier onboarding
- formal tender submission admin

Primary objective:
Find high-fit civils buyers and opportunities, then contact buyers directly where appropriate.

## Core Pipeline

Sources:
- Find a Tender, primary
- Contracts Finder, secondary

Pipeline principles:
- deterministic matching
- weighted scoring
- stale/deadline filtering
- excluded status filtering
- no duplicate alerts
- notifier failures non-fatal
- AI optional, never blocking

## Outreach Rules

All outreach must be classified as:

DIRECT_CONTACT:
High civils fit, usable contact, safe direct introduction.

POSITIONING:
Medium fit or buyer relationship opportunity.

PORTAL_ONLY_SKIP:
Portal-bound opportunity, no tender-specific send-ready email.

SKIP_LOW_FIT:
Irrelevant or weak opportunity, no email.

Portal-only opportunities must never produce tender-specific send-ready outreach.

Weak-fit facilities, consultancy, software, HR, legal, cleaning, catering, security, or professional-services contracts must not become DIRECT_CONTACT unless strong civils/external works evidence exists.

## Agent Operating System

Agents communicate through repo files, not chat.

Agent OS location:
agent_ops/

Agents:
- strategy
- implementation
- qa
- research
- operator
- orchestrator

The Agent OS owns:
- shared state
- task queue
- daily reports
- memory
- decisions
- risks
- ideas
- backups

## VPS And Model Security

Production runs on the VPS.

VPS-local files are not automatically exposed to external models.

Data becomes exposed only when:
- pasted into a prompt
- read by Codex or another model tool
- attached/uploaded manually

Never expose:
- .env
- webhook URLs
- API keys
- tokens
- private credentials
- state/sent_log.sqlite

Codex must not read or modify secrets.

## Current Priority

Phase 2:
Connect Agent OS to outreach quality control.

Required next work:
- enforce outreach classification
- remove weak outreach copy
- prevent portal-only send-ready emails
- add validation
- keep pipeline deterministic

## Do Not Change

- run_pipeline.py orchestration unless necessary
- notifier failure behaviour
- secrets
- .env files
- core deterministic pipeline behaviour

## Next Operator Command

powershell -ExecutionPolicy Bypass -File scripts/run_agent_system.ps1

After writing this file:
- all future implementation must follow 02_current_state.md
- do not override it unless explicitly instructed

