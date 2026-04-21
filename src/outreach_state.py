"""
src/outreach_state.py
=====================
Runtime outreach/compliance state bootstrap.

Creates an explicit lead activation state file so outreach and compliance
workflow state is never implicit or memory-only.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.entities import LeadActivationRecord, utc_now_iso


def default_lead_activation_state() -> dict:
    template = LeadActivationRecord(
        lead_id="example-lead-id",
        account_name="Example Account Ltd",
        contact_name="Example Contact",
        contact_channel="email",
        lawful_basis_path="lia_b2b_corporate_v1",
        outreach_stage="D1",
        suppression_state="active",
        response_status="none",
        call_booked=False,
        pilot_started=False,
        last_contacted_at=None,
    )
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now_iso(),
        "description": "Lead activation and outreach compliance runtime state.",
        "record_template": template.to_dict(),
        "records": [],
    }


def ensure_lead_activation_state(path: Path) -> bool:
    """
    Ensure an explicit outreach state file exists.
    Returns True when a file was created, False when already present.
    """
    if path.exists():
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = default_lead_activation_state()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return True

