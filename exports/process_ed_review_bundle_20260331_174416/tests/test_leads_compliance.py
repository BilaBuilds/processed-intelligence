import unittest

from src.leads_compliance import (
    ComplianceDecision,
    DecisionStatus,
    LeadRecord,
    SubscriberType,
    evaluate_lead,
)


class TestLeadsCompliance(unittest.TestCase):
    def test_block_if_suppressed(self) -> None:
        rec = LeadRecord(
            lead_id="1",
            email="ops@example.com",
            subscriber_type=SubscriberType.CORPORATE,
            source="companies_house_api",
            on_suppression_list=True,
        )
        out: ComplianceDecision = evaluate_lead(rec)
        self.assertEqual(out.status, DecisionStatus.BLOCK)
        self.assertIn("suppression_list_match", out.reasons)

    def test_corporate_requires_governance_controls(self) -> None:
        rec = LeadRecord(
            lead_id="2",
            email="info@example.com",
            subscriber_type=SubscriberType.CORPORATE,
            source="manual",
            lia_completed=False,
            privacy_notice_ready=False,
        )
        out = evaluate_lead(rec)
        self.assertEqual(out.status, DecisionStatus.REVIEW)
        self.assertIn("complete_legitimate_interest_assessment", out.required_actions)

    def test_corporate_allow_when_controls_present(self) -> None:
        rec = LeadRecord(
            lead_id="3",
            email="procurement@example.com",
            subscriber_type=SubscriberType.CORPORATE,
            source="manual",
            lia_completed=True,
            privacy_notice_ready=True,
        )
        out = evaluate_lead(rec)
        self.assertEqual(out.status, DecisionStatus.ALLOW)

    def test_individual_block_without_basis(self) -> None:
        rec = LeadRecord(
            lead_id="4",
            email="person@example.com",
            subscriber_type=SubscriberType.INDIVIDUAL,
            source="manual",
            has_consent=False,
            soft_opt_in_eligible=False,
            lia_completed=True,
            privacy_notice_ready=True,
        )
        out = evaluate_lead(rec)
        self.assertEqual(out.status, DecisionStatus.BLOCK)
        self.assertIn("collect_consent_or_establish_soft_opt_in_eligibility", out.required_actions)

    def test_individual_allow_with_consent(self) -> None:
        rec = LeadRecord(
            lead_id="5",
            email="person@example.com",
            subscriber_type=SubscriberType.INDIVIDUAL,
            source="manual",
            has_consent=True,
            lia_completed=True,
            privacy_notice_ready=True,
        )
        out = evaluate_lead(rec)
        self.assertEqual(out.status, DecisionStatus.ALLOW)


if __name__ == "__main__":
    unittest.main()

