from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class HermesSkill:
    name: str
    purpose: str
    agents: tuple[str, ...]
    permissions: tuple[str, ...]
    guardrails: tuple[str, ...]


HERMES_SKILLS: tuple[HermesSkill, ...] = (
    HermesSkill(
        name="signal_based_research",
        purpose="Find concrete company, role, sector, appointment, and website signals before drafting.",
        agents=("hermes_research_scout", "hermes_social_signal_scout", "hermes_persona_mapper"),
        permissions=("read_enrichment_evidence", "read_website_evidence", "read_companies_house_evidence"),
        guardrails=("do_not_invent_personal_events", "cite_evidence_in_artifacts"),
    ),
    HermesSkill(
        name="public_social_signal_discovery",
        purpose="Discover public company social links from the company website without login or private scraping.",
        agents=("hermes_social_signal_scout", "hermes_truth_qa"),
        permissions=("read_public_company_site_links", "record_public_social_urls"),
        guardrails=("no_authenticated_scraping", "no_private_profile_scraping", "no_unsupported_social_claims"),
    ),
    HermesSkill(
        name="claim_level_evidence_graph",
        purpose="Compile every usable source fact into machine-readable claims before strategy or copy is produced.",
        agents=("hermes_evidence_graph_builder", "hermes_truth_qa", "hermes_commercial_strategy_agent"),
        permissions=("write_claim_ledger", "score_claim_support", "export_machine_trace"),
        guardrails=("no_claim_without_source", "dedupe_equivalent_claims", "preserve_source_confidence"),
    ),
    HermesSkill(
        name="entity_resolution",
        purpose="Normalize company names and domains so duplicate rows and trading-name variants do not waste provider calls.",
        agents=("hermes_entity_resolver", "hermes", "orchestrator"),
        permissions=("normalize_company_identity", "dedupe_batch_entities", "write_entity_keys"),
        guardrails=("do_not_merge_without_domain_or_name_signal", "preserve_original_input", "record_resolution_key"),
    ),
    HermesSkill(
        name="commercial_expected_value_scoring",
        purpose="Prioritize leads by ICP fit, evidence strength, route quality, and likely commercial value.",
        agents=("hermes_commercial_strategy_agent", "hermes", "orchestrator"),
        permissions=("score_icp_fit", "choose_next_best_step", "rank_outreach_priority"),
        guardrails=("do_not_draft_low_value_leads", "record_score_reasons", "separate_score_from_evidence"),
    ),
    HermesSkill(
        name="account_intelligence_profile",
        purpose="Compress evidence, strategy, and policy into account tier, strengths, gaps, and recommended research actions.",
        agents=("hermes_account_intelligence_agent", "hermes_operator_review", "orchestrator"),
        permissions=("rank_account_tier", "identify_research_gaps", "write_priority_reasoning"),
        guardrails=("separate_strengths_from_gaps", "do_not_hide_policy_blocks", "prefer_machine_readable_outputs"),
    ),
    HermesSkill(
        name="suppression_aware_policy_gate",
        purpose="Block risky or non-compliant drafts before mailbox sync and require opt-out language.",
        agents=("hermes_policy_gate", "hermes_truth_qa", "hermes_operator_review"),
        permissions=("read_suppression_memory", "block_policy_risks", "require_opt_out_footer"),
        guardrails=("no_suppression_override", "drafts_only", "policy_blocks_sync"),
    ),
    HermesSkill(
        name="evidence_backed_personalization",
        purpose="Personalize around verified business context rather than fake familiarity.",
        agents=("hermes_commercial_strategy_agent", "hermes_persona_mapper", "hermes_copywriter", "hermes_truth_qa"),
        permissions=("use_company_context", "use_role_context", "use_sector_context"),
        guardrails=("no_fake_relationship", "no_unsupported_claims", "no_creepy_personalization"),
    ),
    HermesSkill(
        name="deliverability_plain_text",
        purpose="Prefer short, plain-text, human-sounding first-touch drafts suitable for mailbox drafts.",
        agents=("hermes_copywriter", "hermes_operator_review"),
        permissions=("draft_plain_text_email", "create_mailbox_draft_after_qa"),
        guardrails=("no_tracking_pixels", "no_html_heavy_email", "no_auto_send"),
    ),
    HermesSkill(
        name="human_in_the_loop_approval",
        purpose="Keep humans in charge of any external communication.",
        agents=("hermes_truth_qa", "hermes_operator_review"),
        permissions=("block_bad_drafts", "mark_approval_ready", "write_review_artifacts"),
        guardrails=("drafts_only", "human_must_send", "record_qa_reasoning"),
    ),
    HermesSkill(
        name="multi_agent_orchestration",
        purpose="Route leads through research, persona mapping, drafting, QA, operator review, and draft sync.",
        agents=("hermes", "orchestrator"),
        permissions=("create_hermes_tasks", "read_task_state", "write_agent_events"),
        guardrails=("one_owner_per_stage", "idempotent_outputs", "non_destructive_runs"),
    ),
    HermesSkill(
        name="neural_memory",
        purpose="Persist lead outcomes, source quality, contact routes, and campaign learnings for future runs.",
        agents=("hermes", "hermes_operator_review", "orchestrator"),
        permissions=("write_memory", "read_memory", "score_with_prior_context"),
        guardrails=("no_secret_storage", "append_only_events", "do_not_store_passwords"),
    ),
    HermesSkill(
        name="visual_reporting",
        purpose="Produce executive-readable reports showing quality, coverage, drafts, QA, and approval readiness.",
        agents=("hermes", "operator"),
        permissions=("write_html_reports", "write_summary_json", "read_hermes_runs"),
        guardrails=("local_reports_only", "no_public_upload"),
    ),
)


def hermes_skills_payload() -> list[dict[str, Any]]:
    return [asdict(skill) for skill in HERMES_SKILLS]
