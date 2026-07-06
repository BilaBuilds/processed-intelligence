from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from enrichment.agents.account_intelligence import AccountIntelligenceAgent
from enrichment.agents.evidence import graph_from_dict, graph_from_enriched_row
from enrichment.agents.policy import OutreachPolicyGate
from enrichment.agents.social_signals import SocialSignalReport, SocialSignalScout
from enrichment.agents.strategy import CommercialStrategyAgent


@dataclass(frozen=True)
class ResearchProfile:
    company_name: str
    contact_name: str
    title: str
    email: str
    phone: str
    evidence: list[str]
    raw_highlights: dict[str, Any]
    social_signals: dict[str, Any]
    evidence_graph: dict[str, Any]
    strategic_brief: dict[str, Any] | None = None
    policy_decision: dict[str, Any] | None = None
    account_intelligence: dict[str, Any] | None = None


@dataclass(frozen=True)
class PersonaMap:
    likely_persona: str
    likely_priorities: list[str]
    outreach_angle: str
    tone: str


@dataclass(frozen=True)
class OutreachDraft:
    subject: str
    body: str


@dataclass(frozen=True)
class TruthQAResult:
    passed: bool
    checks: list[str]
    risks: list[str]


@dataclass(frozen=True)
class OperatorReview:
    status: str
    checklist: list[str]
    next_action: str


@dataclass(frozen=True)
class OutreachArtifact:
    lead_id: str
    research_profile: ResearchProfile
    persona_map: PersonaMap
    draft: OutreachDraft
    truth_qa: TruthQAResult
    operator_review: OperatorReview
    artifact_path: str


class DraftPolicyError(RuntimeError):
    pass


class ResearchScout:
    def build(
        self,
        row: dict[str, str],
        social_report: SocialSignalReport | None = None,
    ) -> ResearchProfile:
        raw = _parse_raw(row.get("raw", ""))
        evidence_graph = graph_from_enriched_row(row, raw)
        company_profile = _dict_or_empty(raw.get("company_profile"))
        officer = _dict_or_empty(raw.get("officer"))
        appointments = _dict_or_empty(raw.get("officer_appointments"))
        supplements = raw.get("supplements") if isinstance(raw, dict) else []

        evidence = [
            f"Companies House status: {company_profile.get('company_status', 'unknown')}",
            f"SIC codes: {', '.join(company_profile.get('sic_codes', []) or ['unknown'])}",
            f"Officer role: {officer.get('officer_role', row.get('title') or 'unknown')}",
            f"Officer appointed: {officer.get('appointed_on', 'unknown')}",
        ]
        if isinstance(appointments, dict) and appointments.get("active_count") is not None:
            evidence.append(f"Active appointments: {appointments.get('active_count')}")
        for supplement in supplements if isinstance(supplements, list) else []:
            if isinstance(supplement, dict) and supplement.get("filled_fields"):
                evidence.append(
                    "Supplemented by "
                    f"{supplement.get('provider')}: "
                    f"{', '.join(supplement.get('filled_fields', []))}"
                )
        social_payload = social_report.to_dict() if social_report else {}
        social_signals = social_payload.get("signals", [])
        if social_signals:
            platforms = sorted({signal["platform"] for signal in social_signals})
            evidence.append(f"Public social links found: {', '.join(platforms)}")

        return ResearchProfile(
            company_name=row.get("company") or row.get("company_name") or "",
            contact_name=row.get("name") or "",
            title=row.get("title") or "",
            email=row.get("email") or "",
            phone=row.get("phone") or "",
            evidence=evidence,
            raw_highlights={
                "company_number": company_profile.get("company_number"),
                "registered_office": company_profile.get("registered_office_address"),
                "sic_codes": company_profile.get("sic_codes") or [],
                "source": row.get("source"),
                "quality_score": row.get("quality_score"),
            },
            social_signals=social_payload,
            evidence_graph=evidence_graph.to_dict(),
        )


class PersonaMapper:
    def build(self, profile: ResearchProfile) -> PersonaMap:
        sic_codes = profile.raw_highlights.get("sic_codes") or []
        title = profile.title.casefold()
        if "director" in title:
            persona = "Senior decision maker"
            priorities = [
                "qualified pipeline",
                "early visibility of relevant opportunities",
                "reducing wasted bid effort",
            ]
            angle = (
                "position ProcessEd as a practical way to surface relevant civils "
                "and construction opportunities before bid effort is committed"
            )
        elif "preconstruction" in title or "bid" in title:
            persona = "Preconstruction / bid leader"
            priorities = [
                "bid/no-bid clarity",
                "framework relevance",
                "faster opportunity triage",
            ]
            angle = (
                "lead with better opportunity qualification and less manual tender scanning"
            )
        else:
            persona = "Commercial construction stakeholder"
            priorities = [
                "relevant project intelligence",
                "timely lead discovery",
                "clear next steps",
            ]
            angle = (
                "connect ProcessEd to targeted lead discovery for specialist construction teams"
            )

        if sic_codes:
            priorities.append(f"context from SIC {', '.join(sic_codes)}")

        return PersonaMap(
            likely_persona=persona,
            likely_priorities=priorities,
            outreach_angle=angle,
            tone="direct, commercially useful, specific, and not over-familiar",
        )


class CreativeCopywriter:
    def __init__(self, policy_gate: OutreachPolicyGate | None = None) -> None:
        self.policy_gate = policy_gate or OutreachPolicyGate()

    def build(self, profile: ResearchProfile, persona: PersonaMap) -> OutreachDraft:
        policy = self._require_policy_allowed(profile)
        first_name = _first_name(profile.contact_name)
        company = _display_company(profile.company_name) or "your team"
        contact_name = _display_person(profile.contact_name)
        subject = f"Relevant civils opportunities for {company}"
        social_sentence = self._social_sentence(profile)
        strategy = profile.strategic_brief or {}
        opt_out = str(policy.get("required_footer") or "").strip()
        angle = str(strategy.get("commercial_angle") or persona.outreach_angle)
        graph = graph_from_dict(profile.evidence_graph)
        has_sector_evidence = graph.support_score("sic_code") > 0

        greeting = f"Hi {first_name}," if first_name else "Hello,"
        if has_sector_evidence:
            opening = (
                f"I noticed {company} is active in specialist civil engineering "
                "and ground engineering work. Companies House also lists "
                f"{contact_name or 'your team'} as {profile.title or 'a senior contact'}."
            )
        else:
            opening = (
                f"I noticed {company} in our lead research. Companies House also lists "
                f"{contact_name or 'your team'} as {profile.title or 'a senior contact'}."
            )
        lines = [
            greeting,
            "",
            opening,
        ]
        if social_sentence:
            lines.extend(["", social_sentence])
        lines.extend(
            [
                "",
                (
                    "ProcessEd helps construction teams spot and qualify public-sector "
                    "and framework opportunities earlier, so bid effort goes toward "
                    "work that actually fits."
                ),
                "",
                (
                    f"For {company}, the useful angle may be to {persona.outreach_angle}. "
                    if not angle
                    else f"For {company}, the useful angle may be to {angle}. "
                )
                + (
                    "If useful, I can send over a short example of the kind of opportunities "
                    "we would flag for your team."
                ),
            ]
        )
        lines.extend(["", "Best,", "Bilal"])
        if opt_out:
            lines.extend(["", opt_out])
        body = "\n".join(lines)
        return OutreachDraft(subject=subject, body=body)

    def _require_policy_allowed(self, profile: ResearchProfile) -> dict[str, Any]:
        policy = profile.policy_decision
        if not policy:
            policy_decision = self.policy_gate.evaluate(
                profile.email,
                self._profile_domain(profile),
                _safe_float(str((profile.strategic_brief or {}).get("evidence_score", 1.0))),
                _safe_float(str(profile.raw_highlights.get("quality_score") or 100)),
            )
            policy = policy_decision.to_dict()

        if not policy.get("allowed"):
            reasons = policy.get("reasons") or []
            reason_text = ",".join(str(reason) for reason in reasons) or str(policy.get("status"))
            raise DraftPolicyError(f"draft blocked by outreach policy: {reason_text}")

        if not str(policy.get("required_footer") or "").strip():
            policy = {**policy, "required_footer": self.policy_gate.footer()}
        return policy

    def _profile_domain(self, profile: ResearchProfile) -> str | None:
        if profile.social_signals and profile.social_signals.get("domain"):
            return str(profile.social_signals.get("domain"))
        return None

    def _social_sentence(self, profile: ResearchProfile) -> str:
        signals = profile.social_signals.get("signals", []) if profile.social_signals else []
        if not signals:
            return ""
        meaningful_labels: list[str] = []
        for signal in signals:
            platform = str(signal.get("platform") or "").casefold()
            label = str(signal.get("label") or "").strip()
            if label and label.casefold() != platform and len(label) > 8:
                meaningful_labels.append(label)
        if not meaningful_labels:
            return ""
        readable = "; ".join(meaningful_labels[:2])
        return (
            f"I also noticed this public signal from your website: {readable}. "
            "That is why I have kept this note focused on practical business context."
        )


class TruthQA:
    FORBIDDEN_PATTERNS = (
        "we spoke",
        "as discussed",
        "i saw your post",
        "congratulations on",
    )

    def check(self, profile: ResearchProfile, draft: OutreachDraft) -> TruthQAResult:
        risks: list[str] = []
        body_lower = draft.body.casefold()
        policy = profile.policy_decision or {}

        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern in body_lower:
                risks.append(f"Unsupported familiarity phrase: {pattern}")

        display_name = _display_person(profile.contact_name)
        if (
            profile.contact_name
            and profile.contact_name not in draft.body
            and display_name not in draft.body
        ):
            risks.append("Named contact is not referenced in draft body.")
        if "Companies House" in draft.body and not profile.contact_name:
            risks.append("Companies House claim needs a named officer.")
        if len(draft.body) > 1500:
            risks.append("Draft is too long for first-touch outreach.")
        if policy and not (policy.get("allowed") or policy.get("policy_allowed")):
            risks.append(f"Policy gate blocked draft: {policy.get('status')}")
        if policy and policy.get("required_footer") not in draft.body:
            risks.append("Required opt-out footer is missing.")
        if not self._has_claim_support(profile, "contact_name"):
            risks.append("Contact name lacks claim-ledger support.")
        if "specialist civil engineering" in body_lower and not self._has_claim_support(profile, "sic_code"):
            risks.append("Sector claim lacks SIC evidence.")

        checks = [
            "No invented direct relationship",
            "No unsupported personal claim",
            "Company/person facts are sourced from enrichment evidence",
            "Human approval required before sending",
        ]
        return TruthQAResult(passed=not risks, checks=checks, risks=risks)

    def _has_claim_support(self, profile: ResearchProfile, predicate: str) -> bool:
        return graph_from_dict(profile.evidence_graph).support_score(predicate) > 0


class OperatorReviewAgent:
    def build(self, row: dict[str, str], qa: TruthQAResult) -> OperatorReview:
        score = _safe_float(row.get("quality_score"))
        policy = row.get("_policy_decision")
        policy_allowed = True
        if isinstance(policy, dict):
            policy_allowed = bool(policy.get("allowed") or policy.get("policy_allowed"))

        if qa.passed and policy_allowed and score >= 80 and row.get("email"):
            status = "approval_ready"
            next_action = "Review draft, confirm fit, then approve for sending."
        elif qa.passed:
            status = "needs_review"
            next_action = "Review evidence and add a stronger contact route before sending."
        else:
            status = "qa_blocked"
            next_action = "Fix QA risks before approval."

        return OperatorReview(
            status=status,
            checklist=[
                "Evidence supports every personalized claim",
                "Contact route is appropriate",
                "Tone is useful rather than pushy",
                "No send without human approval",
            ],
            next_action=next_action,
        )


class HermesOutreachOrchestrator:
    def __init__(self) -> None:
        self.research = ResearchScout()
        self.social = SocialSignalScout()
        self.strategy = CommercialStrategyAgent()
        self.policy = OutreachPolicyGate()
        self.account_intelligence = AccountIntelligenceAgent()
        self.persona = PersonaMapper()
        self.copywriter = CreativeCopywriter(self.policy)
        self.qa = TruthQA()
        self.operator = OperatorReviewAgent()

    def build_from_csv(
        self,
        enriched_csv: Path,
        outreach_dir: Path,
    ) -> list[OutreachArtifact]:
        if self.copywriter.policy_gate is not self.policy:
            self.copywriter = CreativeCopywriter(self.policy)
        rows = self._read_rows(enriched_csv)
        artifacts: list[OutreachArtifact] = []
        outreach_dir.mkdir(parents=True, exist_ok=True)

        for index, row in enumerate(rows, start=1):
            if row.get("status") != "enriched":
                continue
            if row.get("recommended_action") not in {
                "ready_for_outreach",
                "review_then_outreach",
            }:
                continue

            lead_id = self._lead_id(index, row)
            pre_policy = self.policy.evaluate(
                row.get("email"),
                row.get("domain"),
                evidence_score=1.0,
                quality_score=100,
            )
            if "suppressed" in pre_policy.reasons:
                continue
            social_report = self.social.discover(row.get("domain"))
            profile = self.research.build(row, social_report)
            graph = graph_from_dict(profile.evidence_graph)
            social_platforms = [
                str(signal.get("platform"))
                for signal in profile.social_signals.get("signals", [])
                if isinstance(signal, dict) and signal.get("platform")
            ]
            strategic_brief = self.strategy.build(
                graph,
                _safe_float(row.get("quality_score")),
                social_platforms,
            )
            policy_decision = self.policy.evaluate(
                row.get("email"),
                row.get("domain"),
                strategic_brief.evidence_score,
                _safe_float(row.get("quality_score")),
            )
            intelligence = self.account_intelligence.build(
                graph,
                strategic_brief,
                policy_decision,
            )
            profile = ResearchProfile(
                **{
                    **asdict(profile),
                    "strategic_brief": strategic_brief.to_dict(),
                    "policy_decision": policy_decision.to_dict(),
                    "account_intelligence": intelligence.to_dict(),
                }
            )
            persona = self.persona.build(profile)
            draft = self.copywriter.build(profile, persona)
            qa = self.qa.check(profile, draft)
            review = self.operator.build({**row, "_policy_decision": policy_decision.to_dict()}, qa)
            artifact_path = outreach_dir / f"{lead_id}.json"
            artifact = OutreachArtifact(
                lead_id=lead_id,
                research_profile=profile,
                persona_map=persona,
                draft=draft,
                truth_qa=qa,
                operator_review=review,
                artifact_path=artifact_path.as_posix(),
            )
            self._write_artifact(artifact_path, artifact)
            self._write_markdown(outreach_dir / f"{lead_id}.md", artifact)
            artifacts.append(artifact)

        return artifacts

    def _read_rows(self, enriched_csv: Path) -> list[dict[str, str]]:
        with enriched_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
            return [dict(row) for row in csv.DictReader(csv_file)]

    def _lead_id(self, index: int, row: dict[str, str]) -> str:
        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            (row.get("company_name") or f"lead-{index}").casefold(),
        ).strip("-")
        return f"{index:03d}-{slug or 'lead'}"

    def _write_artifact(self, path: Path, artifact: OutreachArtifact) -> None:
        with path.open("w", encoding="utf-8") as artifact_file:
            json.dump(asdict(artifact), artifact_file, indent=2, sort_keys=True)
            artifact_file.write("\n")

    def _write_markdown(self, path: Path, artifact: OutreachArtifact) -> None:
        profile = artifact.research_profile
        persona = artifact.persona_map
        draft = artifact.draft
        qa = artifact.truth_qa
        review = artifact.operator_review
        lines = [
            f"# Hermes Outreach Review: {profile.company_name}",
            "",
            "## Contact",
            "",
            f"- Name: {profile.contact_name or '(missing)'}",
            f"- Title: {profile.title or '(missing)'}",
            f"- Email: {profile.email or '(missing)'}",
            f"- Phone: {profile.phone or '(missing)'}",
            "",
            "## Evidence",
            "",
            *[f"- {item}" for item in profile.evidence],
            "",
            "## Public Social Signals",
            "",
            *self._social_lines(profile),
            "",
            "## Persona Map",
            "",
            f"- Persona: {persona.likely_persona}",
            f"- Angle: {persona.outreach_angle}",
            f"- Tone: {persona.tone}",
            "",
            "## Strategic Brief",
            "",
            *self._strategic_lines(profile),
            "",
            "## Policy Gate",
            "",
            *self._policy_lines(profile),
            "",
            "## Account Intelligence",
            "",
            *self._intelligence_lines(profile),
            "",
            "## Draft",
            "",
            f"Subject: {draft.subject}",
            "",
            "```text",
            draft.body,
            "```",
            "",
            "## Truth QA",
            "",
            f"- Passed: {qa.passed}",
            *[f"- Check: {check}" for check in qa.checks],
            *[f"- Risk: {risk}" for risk in qa.risks],
            "",
            "## Operator Review",
            "",
            f"- Status: {review.status}",
            f"- Next action: {review.next_action}",
            *[f"- Checklist: {item}" for item in review.checklist],
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")

    def _social_lines(self, profile: ResearchProfile) -> list[str]:
        signals = profile.social_signals.get("signals", []) if profile.social_signals else []
        if not signals:
            return ["- None found on checked website pages."]
        return [
            f"- {signal.get('platform')}: {signal.get('url')} (source: {signal.get('source_url')})"
            for signal in signals[:10]
        ]

    def _strategic_lines(self, profile: ResearchProfile) -> list[str]:
        brief = profile.strategic_brief or {}
        if not brief:
            return ["- Missing strategic brief."]
        lines = [
            f"- ICP score: {brief.get('icp_score')}",
            f"- Evidence score: {brief.get('evidence_score')}",
            f"- Expected value: {brief.get('expected_value')}",
            f"- Next best step: {brief.get('next_best_step')}",
            f"- Commercial angle: {brief.get('commercial_angle')}",
        ]
        for reason in brief.get("reasons") or []:
            lines.append(f"- Reason: {reason}")
        return lines

    def _policy_lines(self, profile: ResearchProfile) -> list[str]:
        policy = profile.policy_decision or {}
        if not policy:
            return ["- Missing policy decision."]
        lines = [
            f"- Status: {policy.get('status')}",
            f"- Allowed: {policy.get('allowed')}",
            f"- Contact route type: {policy.get('contact_route_type')}",
            f"- Risk score: {policy.get('risk_score')}",
        ]
        for reason in policy.get("reasons") or []:
            lines.append(f"- Reason: {reason}")
        return lines

    def _intelligence_lines(self, profile: ResearchProfile) -> list[str]:
        intelligence = profile.account_intelligence or {}
        if not intelligence:
            return ["- Missing account intelligence profile."]
        lines = [
            f"- Tier: {intelligence.get('account_tier')}",
            f"- Priority score: {intelligence.get('priority_score')}",
            f"- Next best action: {intelligence.get('next_best_action')}",
        ]
        for strength in intelligence.get("strengths") or []:
            lines.append(f"- Strength: {strength}")
        for gap in intelligence.get("gaps") or []:
            lines.append(f"- Gap: {gap}")
        for action in intelligence.get("recommended_research") or []:
            lines.append(f"- Research: {action}")
        return lines


def build_hermes_dashboard(
    enriched_csv: Path,
    outreach_artifacts: list[OutreachArtifact],
    summary: dict[str, Any],
    output_path: Path,
) -> None:
    rows = []
    with enriched_csv.open("r", encoding="utf-8-sig", newline="") as csv_file:
        rows = [dict(row) for row in csv.DictReader(csv_file)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_text = _dashboard_html(rows, outreach_artifacts, summary)
    output_path.write_text(html_text, encoding="utf-8")


def _dashboard_html(
    rows: list[dict[str, str]],
    artifacts: list[OutreachArtifact],
    summary: dict[str, Any],
) -> str:
    artifact_by_company = {
        artifact.research_profile.company_name: artifact for artifact in artifacts
    }
    total = len(rows)
    enriched = sum(1 for row in rows if row.get("status") == "enriched")
    with_email = sum(1 for row in rows if row.get("email"))
    with_phone = sum(1 for row in rows if row.get("phone"))
    ready = sum(1 for row in rows if row.get("recommended_action") == "ready_for_outreach")
    cards = [
        ("Processed", total),
        ("Enriched", enriched),
        ("With email", with_email),
        ("With phone", with_phone),
        ("Ready", ready),
    ]
    card_html = "\n".join(
        f"<section class='metric'><span>{html.escape(label)}</span><strong>{value}</strong></section>"
        for label, value in cards
    )
    rows_html = "\n".join(_lead_row_html(row, artifact_by_company) for row in rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hermes Lead Report</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #182026;
      --muted: #5c6b73;
      --line: #d9e1e5;
      --paper: #f8faf9;
      --accent: #0f766e;
      --good: #166534;
      --warn: #9a3412;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--paper);
    }}
    header {{
      padding: 28px 36px 18px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }}
    h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    .meta {{ color: var(--muted); font-size: 14px; }}
    main {{ padding: 24px 36px 42px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }}
    .metric {{
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 8px; font-size: 28px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    tr:last-child td {{ border-bottom: 0; }}
    .score {{ font-weight: 700; color: var(--accent); }}
    .action-ready_for_outreach {{ color: var(--good); font-weight: 700; }}
    .action-review_then_outreach {{ color: var(--warn); font-weight: 700; }}
    details {{ max-width: 520px; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 700; }}
    pre {{
      white-space: pre-wrap;
      font-family: Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
      background: #f1f5f4;
      padding: 10px;
      border-radius: 6px;
      border: 1px solid var(--line);
    }}
  </style>
</head>
<body>
  <header>
    <h1>Hermes Lead Report</h1>
    <div class="meta">Run {html.escape(str(summary.get("run_id", "unknown")))} | Human approval required before sending</div>
  </header>
  <main>
    <section class="metrics">{card_html}</section>
    <table>
      <thead>
        <tr>
          <th>Company</th>
          <th>Contact</th>
          <th>Contact Route</th>
          <th>Score</th>
          <th>Action</th>
          <th>Draft</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </main>
</body>
</html>
"""


def _lead_row_html(
    row: dict[str, str],
    artifact_by_company: dict[str, OutreachArtifact],
) -> str:
    company = row.get("company") or row.get("company_name") or ""
    artifact = artifact_by_company.get(company)
    draft_html = "No draft"
    if artifact:
        draft_html = (
            "<details><summary>View draft</summary>"
            f"<pre>Subject: {html.escape(artifact.draft.subject)}\n\n"
            f"{html.escape(artifact.draft.body)}</pre></details>"
        )
    action = row.get("recommended_action", "")
    return f"""
        <tr>
          <td>{html.escape(company)}</td>
          <td>{html.escape(row.get("name", ""))}<br>{html.escape(row.get("title", ""))}</td>
          <td>{html.escape(row.get("email", ""))}<br>{html.escape(row.get("phone", ""))}</td>
          <td class="score">{html.escape(row.get("quality_score", "0"))}</td>
          <td class="action-{html.escape(action)}">{html.escape(action)}</td>
          <td>{draft_html}</td>
        </tr>
"""


def _parse_raw(raw_text: str) -> dict[str, Any]:
    if not raw_text:
        return {}
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_name(name: str) -> str:
    if not name:
        return ""
    if "," in name:
        _, remainder = name.split(",", maxsplit=1)
        parts = remainder.strip().split()
        return parts[0].title() if parts else ""
    return name.split()[0].title()


def _display_company(company_name: str) -> str:
    if not company_name:
        return ""
    if company_name.isupper():
        return company_name.title().replace(" Limited", " Limited")
    return company_name


def _display_person(name: str) -> str:
    if not name:
        return ""
    if "," not in name:
        return " ".join(part.title() for part in name.split())
    surname, remainder = name.split(",", maxsplit=1)
    return f"{remainder.strip().title()} {surname.strip().title()}".strip()


def _safe_float(value: str | None) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0
