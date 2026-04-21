"""
src/leads_compliance.py
=======================
Compliance gate for outbound lead activation.

Purpose:
    Classify whether a lead can be contacted for direct marketing in a
    compliance-first UK workflow (GDPR + PECR aware).

Important:
    This module is an engineering control, not legal advice.
    Keep rules aligned with your legal counsel and latest ICO guidance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SubscriberType(str, Enum):
    CORPORATE = "corporate"
    INDIVIDUAL = "individual"
    UNKNOWN = "unknown"


class DecisionStatus(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


@dataclass(frozen=True)
class LeadRecord:
    lead_id: str
    email: str
    subscriber_type: SubscriberType
    source: str
    campaign_type: str = "b2b_tender_intel"
    has_consent: bool = False
    soft_opt_in_eligible: bool = False
    has_opt_out_link: bool = True
    sender_identity_clear: bool = True
    on_suppression_list: bool = False
    lia_completed: bool = False
    privacy_notice_ready: bool = False


@dataclass(frozen=True)
class ComplianceDecision:
    status: DecisionStatus
    reasons: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)


def evaluate_lead(record: LeadRecord) -> ComplianceDecision:
    reasons: list[str] = []
    required: list[str] = []

    if record.on_suppression_list:
        return ComplianceDecision(
            status=DecisionStatus.BLOCK,
            reasons=["suppression_list_match"],
            required_actions=[],
        )

    if not record.email or "@" not in record.email:
        return ComplianceDecision(
            status=DecisionStatus.BLOCK,
            reasons=["invalid_email"],
            required_actions=[],
        )

    if not record.sender_identity_clear:
        return ComplianceDecision(
            status=DecisionStatus.BLOCK,
            reasons=["sender_identity_not_clear"],
            required_actions=["ensure_sender_identity_clear"],
        )

    if not record.has_opt_out_link:
        return ComplianceDecision(
            status=DecisionStatus.BLOCK,
            reasons=["missing_opt_out_mechanism"],
            required_actions=["add_opt_out_address_or_link"],
        )

    if not record.privacy_notice_ready:
        required.append("provide_privacy_notice_at_or_before_first_contact")

    if not record.lia_completed:
        required.append("complete_legitimate_interest_assessment")

    if record.subscriber_type == SubscriberType.CORPORATE:
        # PECR consent/soft-opt-in requirement does not apply in the same way as
        # individual subscribers, but GDPR still applies if personal data is used.
        if required:
            return ComplianceDecision(
                status=DecisionStatus.REVIEW,
                reasons=["corporate_subscriber_but_governance_incomplete"],
                required_actions=required,
            )
        return ComplianceDecision(
            status=DecisionStatus.ALLOW,
            reasons=["corporate_subscriber_path"],
            required_actions=[],
        )

    # Individual or unknown subscriber:
    # require consent OR soft-opt-in controls.
    if record.has_consent or record.soft_opt_in_eligible:
        if required:
            return ComplianceDecision(
                status=DecisionStatus.REVIEW,
                reasons=["individual_path_with_marketing_basis_but_governance_incomplete"],
                required_actions=required,
            )
        return ComplianceDecision(
            status=DecisionStatus.ALLOW,
            reasons=["individual_path_with_valid_marketing_basis"],
            required_actions=[],
        )

    return ComplianceDecision(
        status=DecisionStatus.BLOCK,
        reasons=["individual_or_unknown_without_consent_or_soft_opt_in"],
        required_actions=["collect_consent_or_establish_soft_opt_in_eligibility"],
    )

