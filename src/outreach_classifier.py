"""
src/outreach_classifier.py
=========================
Deterministic outreach quality control (QC) and action classification.

This module is intentionally "dumb-but-safe":
- No network calls
- No LLM calls
- No randomness
- Same input text -> same classification output

Action types:
    DIRECT_CONTACT
    POSITIONING
    PORTAL_ONLY_SKIP
    SKIP_LOW_FIT

Key safety rules enforced here:
- Portal-route opportunities are never send-ready and never get an email body.
- Facilities/consultancy/software/professional-services-only items are never DIRECT_CONTACT.
- High-fit civils keywords can qualify for DIRECT_CONTACT (buyer-introduction, not tender submission).
- Medium-fit items can qualify for POSITIONING (relationship-building, not tender-specific).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


ACTION_DIRECT = "DIRECT_CONTACT"
ACTION_POSITIONING = "POSITIONING"
ACTION_PORTAL_SKIP = "PORTAL_ONLY_SKIP"
ACTION_LOW_FIT = "SKIP_LOW_FIT"


_POSITIVE_KEYWORDS = [
    # Core civils / external works signals
    "civils",
    "civil engineering",
    "groundworks",
    "drainage",
    "resurfacing",
    "surfacing",
    "car park",
    "highway",
    "highways",
    "footpath",
    "footpaths",
    "pavement",
    "kerb",
    "kerbing",
    "external works",
    "enabling works",
    "landscaping",
    "public realm",
    "site clearance",
    "foundations",
    "retaining wall",
    "retaining walls",
    "earthworks",
    "excavation",
    "roadworks",
    "street works",
    "streetworks",
    "section 278",
    "s278",
    "section 38",
    "s38",
]

_NEGATIVE_KEYWORDS = [
    "facilities management",
    "management agreement",
    "consultancy",
    "consultant",
    "software",
    "saas",
    "it services",
    "legal",
    "audit",
    "recruitment",
    "training",
    "cleaning",
    "catering",
    "security",
    "insurance",
    "hr",
    "payroll",
    "professional services",
    "strategy",
    "assessment only",
    "design only",
    "survey only",
]

_PORTAL_KEYWORDS = [
    "multiquote",
    "supplying the south west",
    "procontract",
    "delta",
    "esourcing portal",
    "e-sourcing portal",
    "procurement portal",
    "tender portal",
    "contracts finder",
    "find a tender",
    "fts",
    "submit via portal",
    "portal only",
    "register on",
    "supplier portal",
]

_BANNED_PHRASES = [
    "i am getting in touch",
    "i hope you are well",
    "synergy",
    "best-in-class",
    "uniquely positioned",
]


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    # best-effort for dict/list without dumping huge payloads
    try:
        return str(value)
    except Exception:
        return ""


def _norm(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _keyword_hits(text: str, keywords: List[str]) -> List[str]:
    """
    Return the list of keywords that appear in text (case-insensitive).
    Uses substring matching, which is good enough for controlled keyword sets.
    """
    t = _norm(text)
    hits: List[str] = []
    for kw in keywords:
        if kw.lower() in t:
            hits.append(kw)
    return hits


def _has_email(candidate: Dict[str, Any]) -> bool:
    """
    Best-effort check for any email-like value in common fields.
    We do NOT validate deliverability. We just detect presence.
    """
    possible_keys = (
        "recipient_email",
        "contact_email",
        "buyer_email",
        "email",
        "emails",
        "contact_emails",
    )
    for key in possible_keys:
        value = candidate.get(key)
        if isinstance(value, str):
            if "@" in value and "." in value.split("@")[-1]:
                return True
        if isinstance(value, list):
            for v in value:
                if isinstance(v, str) and "@" in v and "." in v.split("@")[-1]:
                    return True
    return False


def extract_classification_evidence(candidate: Dict[str, Any]) -> Dict[str, Any]:
    title = _as_text(candidate.get("tender_title") or candidate.get("title"))
    desc = _as_text(candidate.get("description") or candidate.get("summary") or candidate.get("buyer_signal"))
    category = _as_text(candidate.get("procurement_category") or candidate.get("category"))

    combined = " ".join([title, desc, category]).strip()

    pos = _keyword_hits(combined, _POSITIVE_KEYWORDS)
    neg = _keyword_hits(combined, _NEGATIVE_KEYWORDS)
    portal = _keyword_hits(combined, _PORTAL_KEYWORDS)

    # Fit score: bounded integer for downstream consumers.
    # - positives push it up
    # - negatives push it down harder
    # - "works" provides a small lift, "services" a small drop
    score = 0
    score += min(len(pos) * 12, 72)
    score -= min(len(neg) * 18, 72)

    cat = category.strip().lower()
    if cat == "works":
        score += 8
    elif cat == "services":
        score -= 8

    score = max(0, min(score, 100))

    route_risk = "none"
    if portal:
        route_risk = "high"

    return {
        "positive_keywords": sorted(set(pos)),
        "negative_keywords": sorted(set(neg)),
        "portal_keywords": sorted(set(portal)),
        "has_contact_email": _has_email(candidate),
        "fit_score": int(score),
        "route_risk": route_risk,
    }


def _confidence_from_score(score: int) -> str:
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _buyer_team_name(candidate: Dict[str, Any]) -> str:
    """
    Never invent named contacts. Default to Procurement Team unless an
    explicit safe hint suggests Estates.
    """
    text = _norm(" ".join([
        _as_text(candidate.get("tender_title") or candidate.get("title")),
        _as_text(candidate.get("description") or ""),
        _as_text(candidate.get("procurement_category") or ""),
    ]))
    if any(k in text for k in ("estates", "housing repairs", "building maintenance")):
        return "Estates Team"
    return "Procurement Team"


def build_outreach_email(candidate: Dict[str, Any], action_type: str) -> Tuple[str, str]:
    """
    Return (subject, body). For skip actions, both are empty.
    """
    if action_type in {ACTION_PORTAL_SKIP, ACTION_LOW_FIT}:
        return "", ""

    team = _buyer_team_name(candidate)

    subject = "Civils and external works support"

    if action_type == ACTION_DIRECT:
        body = (
            f"Dear {team},\n\n"
            "We work with councils and public sector estates teams on groundworks, drainage, resurfacing, "
            "enabling works, and external civils packages.\n\n"
            "I wanted to check the best route to introduce ProcessEd Civils for upcoming works where external "
            "civils support is required.\n\n"
            "Kind regards,\n"
            "Bilali\n"
            "ProcessEd Civils\n"
            "info@processedcivils.com\n"
            "07853 505 322"
        )
        return subject, body

    # POSITIONING (relationship-building, non-tender-specific)
    body = (
        f"Dear {team},\n\n"
        "We support councils and public sector estates teams with groundworks, drainage, enabling works, "
        "resurfacing, and external works.\n\n"
        "Could you point me to the best contact or route for introducing ProcessEd Civils for upcoming "
        "civils-related packages?\n\n"
        "Kind regards,\n"
        "Bilali\n"
        "ProcessEd Civils\n"
        "info@processedcivils.com\n"
        "07853 505 322"
    )
    return subject, body


def classify_outreach_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministically classify an outreach candidate and produce QC fields.

    Output keys (stable):
        action_type, send_ready, confidence, reason, risk_flags,
        recommended_next_action, classification_evidence, subject, body
    """
    evidence = extract_classification_evidence(candidate)
    score = int(evidence.get("fit_score") or 0)
    conf = _confidence_from_score(score)

    title = _as_text(candidate.get("tender_title") or candidate.get("title") or "").strip()
    has_portal = bool(evidence.get("portal_keywords"))
    pos = evidence.get("positive_keywords") or []
    neg = evidence.get("negative_keywords") or []

    risk_flags: List[str] = []

    # Hard rule: portal-route items are internal notes only.
    if has_portal:
        action_type = ACTION_PORTAL_SKIP
        send_ready = False
        if title:
            reason = f"Portal-only route detected for '{title}'. Do not send tender-specific outreach."
        else:
            reason = "Portal-only route detected. Do not send tender-specific outreach."
        risk_flags.append("portal_only_route_detected")
        recommended_next_action = (
            "Add buyer to watchlist. Do not send tender-specific email unless formal portal registration is pursued later."
        )
        subject, body = build_outreach_email(candidate, action_type)
        return {
            "action_type": action_type,
            "send_ready": send_ready,
            "confidence": "High" if conf in {"High", "Medium"} else conf,
            "reason": reason,
            "risk_flags": risk_flags,
            "recommended_next_action": recommended_next_action,
            "classification_evidence": evidence,
            "subject": subject,
            "body": body,
        }

    # Hard rule: negative-only services cannot be direct outreach.
    strong_positive = score >= 70 or len(pos) >= 3
    negative_heavy = len(neg) >= 1 and not strong_positive

    if negative_heavy and score < 40:
        action_type = ACTION_LOW_FIT
        send_ready = False
        reason = "Low civils fit based on services/professional-services signals; skip outreach."
        risk_flags.append("low_fit_services_only")
        recommended_next_action = "Skip outreach. Keep only as pipeline intelligence."
        subject, body = build_outreach_email(candidate, action_type)
        return {
            "action_type": action_type,
            "send_ready": send_ready,
            "confidence": conf,
            "reason": reason,
            "risk_flags": risk_flags,
            "recommended_next_action": recommended_next_action,
            "classification_evidence": evidence,
            "subject": subject,
            "body": body,
        }

    # Main: decide between DIRECT_CONTACT, POSITIONING, SKIP_LOW_FIT.
    if score >= 70:
        action_type = ACTION_DIRECT
        confidence = conf  # High
    elif score >= 40:
        action_type = ACTION_POSITIONING
        confidence = conf  # Medium
    else:
        action_type = ACTION_LOW_FIT
        confidence = conf  # Low

    if action_type == ACTION_LOW_FIT:
        send_ready = False
        reason = "Weak civils/external works signal; skip outreach."
        recommended_next_action = "Skip outreach. Keep only as pipeline intelligence."
        subject, body = build_outreach_email(candidate, action_type)
        return {
            "action_type": action_type,
            "send_ready": send_ready,
            "confidence": confidence,
            "reason": reason,
            "risk_flags": risk_flags,
            "recommended_next_action": recommended_next_action,
            "classification_evidence": evidence,
            "subject": subject,
            "body": body,
        }

    # Send-ready gating:
    # - DIRECT_CONTACT: High/Medium confidence only (by construction)
    # - POSITIONING: Medium confidence only
    send_ready = True if confidence in {"High", "Medium"} else False

    if not evidence.get("has_contact_email"):
        risk_flags.append("missing_direct_contact_email")

    if action_type == ACTION_DIRECT:
        reason = "High civils fit signals detected; safe for a buyer-introduction message."
        recommended_next_action = "Prepare approval to send a short buyer-introduction email (non-tender-specific) and confirm best contact route."
    else:
        reason = "Medium civils relevance; use relationship-building positioning outreach."
        recommended_next_action = "Prepare approval to send a short positioning email and identify the correct buyer contact for future civils packages."

    subject, body = build_outreach_email(candidate, action_type)

    # Safety: ensure our own deterministic templates never contain banned phrases.
    combined = _norm(subject + " " + body)
    for phrase in _BANNED_PHRASES:
        if phrase in combined:
            # If this ever triggers, it's a bug in this module: fail closed.
            action_type = ACTION_LOW_FIT
            send_ready = False
            subject, body = "", ""
            risk_flags.append("qc_template_contains_banned_phrase")
            reason = "QC template safety failure; skip outreach."
            recommended_next_action = "Skip outreach until QC templates are fixed."
            break

    return {
        "action_type": action_type,
        "send_ready": send_ready,
        "confidence": confidence,
        "reason": reason,
        "risk_flags": risk_flags,
        "recommended_next_action": recommended_next_action,
        "classification_evidence": evidence,
        "subject": subject,
        "body": body,
    }

