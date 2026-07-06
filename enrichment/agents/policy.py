from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from enrichment.suppression import SuppressionList


GENERIC_INBOX_PREFIXES = {
    "admin",
    "contact",
    "enquiries",
    "hello",
    "info",
    "office",
    "sales",
    "support",
    "tenders",
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    status: str
    reasons: list[str]
    required_footer: str
    contact_route_type: str
    risk_score: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["policy_allowed"] = self.allowed
        return payload

    @property
    def policy_allowed(self) -> bool:
        return self.allowed


class OutreachPolicyGate:
    def __init__(
        self,
        suppression_list: SuppressionList | None = None,
        opt_out_address: str = "info@processedcivils.com",
        sender_company: str = "ProcessEd Ltd",
        registered_address: str | None = None,
    ) -> None:
        self.suppression_list = suppression_list or SuppressionList()
        self.opt_out_address = opt_out_address
        self.sender_company = sender_company
        self.registered_address = (
            registered_address
            or os.getenv("PROCESSED_REGISTERED_ADDRESS")
            or "registered address to be confirmed"
        )

    def evaluate(
        self,
        email: str | None,
        domain: str | None,
        evidence_score: float,
        quality_score: float,
    ) -> PolicyDecision:
        reasons: list[str] = []
        route_type = self._route_type(email)
        risk_score = 0.0

        if self.suppression_list.is_suppressed(email):
            return PolicyDecision(
                allowed=False,
                status="policy_blocked",
                reasons=["suppressed"],
                required_footer=self.footer(),
                contact_route_type=route_type,
                risk_score=1.0,
            )
        if not email:
            reasons.append("No email route available.")
            risk_score += 0.45
        if evidence_score < 0.55:
            reasons.append("Evidence support is below outreach threshold.")
            risk_score += 0.25
        if quality_score < 80:
            reasons.append("Lead quality score is below approval-ready threshold.")
            risk_score += 0.2
        if route_type == "guessed_personal":
            reasons.append("Contact route appears guessed rather than source-confirmed.")
            risk_score += 0.3

        allowed = bool(email) and risk_score < 0.6
        status = "policy_allowed" if allowed else "policy_blocked"
        if not reasons:
            reasons.append("Policy checks passed for draft creation.")

        return PolicyDecision(
            allowed=allowed,
            status=status,
            reasons=reasons,
            required_footer=self.footer(),
            contact_route_type=route_type,
            risk_score=round(min(risk_score, 1.0), 3),
        )

    def footer(self) -> str:
        return (
            f"{self.sender_company}, registered address: {self.registered_address}. "
            f"Reply STOP to opt out, or contact {self.opt_out_address}."
        )

    def _route_type(self, email: str | None) -> str:
        if not email or "@" not in email:
            return "missing"
        local = email.split("@", 1)[0].casefold()
        if local in GENERIC_INBOX_PREFIXES:
            return "generic_inbox"
        if "." in local or len(local) > 5:
            return "personal_or_role_inbox"
        return "guessed_personal"
