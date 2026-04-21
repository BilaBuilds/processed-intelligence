"""
Low-level SQL helpers for outreach data.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def create_contact(conn: sqlite3.Connection, contact: dict[str, Any]) -> int:
    now = utc_now_iso()
    values = {
        "company_name": contact["company_name"],
        "contact_name": contact.get("contact_name"),
        "role": contact.get("role"),
        "email": contact.get("email"),
        "whatsapp_number": contact.get("whatsapp_number"),
        "discord_webhook_url": contact.get("discord_webhook_url"),
        "preferred_channel": contact.get("preferred_channel", "email"),
        "region": contact.get("region"),
        "sectors": contact.get("sectors"),
        "is_active": 1 if contact.get("is_active", True) else 0,
        "created_at": now,
        "updated_at": now,
    }
    cursor = conn.execute(
        """
        INSERT INTO outreach_contacts (
            company_name, contact_name, role, email, whatsapp_number,
            discord_webhook_url, preferred_channel, region, sectors,
            is_active, created_at, updated_at
        ) VALUES (
            :company_name, :contact_name, :role, :email, :whatsapp_number,
            :discord_webhook_url, :preferred_channel, :region, :sectors,
            :is_active, :created_at, :updated_at
        )
        """,
        values,
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_contacts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM outreach_contacts
        ORDER BY company_name ASC, contact_name ASC, id ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_contact(conn: sqlite3.Connection, contact_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM outreach_contacts WHERE id = ?",
        (contact_id,),
    ).fetchone()
    return row_to_dict(row)


def insert_sample(
    conn: sqlite3.Connection,
    *,
    contact_id: int,
    run_id: str,
    shortlist_count: int,
    review_count: int,
    intelligence_count: int,
    sample_payload: dict[str, Any],
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO outreach_samples (
            contact_id, run_id, shortlist_count, review_count,
            intelligence_count, sample_payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contact_id,
            run_id,
            shortlist_count,
            review_count,
            intelligence_count,
            json.dumps(sample_payload, sort_keys=True, separators=(",", ":")),
            utc_now_iso(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def insert_message(
    conn: sqlite3.Connection,
    *,
    contact_id: int,
    campaign_id: int | None,
    channel: str,
    template_key: str,
    subject: str | None,
    body_text: str,
    payload: dict[str, Any],
    send_status: str,
    sent_at: str | None = None,
    error_message: str | None = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO outreach_messages (
            contact_id, campaign_id, channel, template_key, subject,
            body_text, payload_json, send_status, sent_at,
            error_message, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contact_id,
            campaign_id,
            channel,
            template_key,
            subject,
            body_text,
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            send_status,
            sent_at,
            error_message,
            utc_now_iso(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def update_message_status(
    conn: sqlite3.Connection,
    *,
    message_id: int,
    send_status: str,
    sent_at: str | None,
    error_message: str | None,
) -> None:
    conn.execute(
        """
        UPDATE outreach_messages
        SET send_status = ?, sent_at = ?, error_message = ?
        WHERE id = ?
        """,
        (send_status, sent_at, error_message, message_id),
    )
    conn.commit()


def insert_send_log(
    conn: sqlite3.Connection,
    *,
    contact_id: int,
    message_id: int,
    channel: str,
    result: str,
    provider_response: dict[str, Any] | None,
    error_message: str | None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO outreach_send_log (
            contact_id, message_id, channel, result,
            provider_response_json, error_message, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contact_id,
            message_id,
            channel,
            result,
            json.dumps(provider_response, sort_keys=True, separators=(",", ":"))
            if provider_response is not None
            else None,
            error_message,
            utc_now_iso(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


# ---------------------------------------------------------------------------
# buyer_actions — Phase 1 action layer
# ---------------------------------------------------------------------------

def create_action(
    conn: sqlite3.Connection,
    *,
    buyer_key: str,
    buyer_name: str,
    action_type: str,
    run_id: str | None = None,
    notes: str | None = None,
    actor: str = "operator",
    source: str = "cli",
    action_status: str = "pending",
) -> int:
    """Insert a new buyer action row.  Returns the new action_id."""
    from outreach.db import ACTION_TYPES, ACTION_STATUSES
    if action_type not in ACTION_TYPES:
        raise ValueError(f"Unknown action_type '{action_type}'. Valid: {sorted(ACTION_TYPES)}")
    if action_status not in ACTION_STATUSES:
        raise ValueError(f"Unknown action_status '{action_status}'. Valid: {sorted(ACTION_STATUSES)}")
    now = utc_now_iso()
    cursor = conn.execute(
        """
        INSERT INTO buyer_actions
            (buyer_key, buyer_name, action_type, action_status,
             run_id, notes, actor, source, created_at, updated_at)
        VALUES
            (:buyer_key, :buyer_name, :action_type, :action_status,
             :run_id, :notes, :actor, :source, :created_at, :updated_at)
        """,
        {
            "buyer_key": buyer_key,
            "buyer_name": buyer_name,
            "action_type": action_type,
            "action_status": action_status,
            "run_id": run_id,
            "notes": notes,
            "actor": actor,
            "source": source,
            "created_at": now,
            "updated_at": now,
        },
    )
    conn.commit()
    return int(cursor.lastrowid)


def update_action_status(
    conn: sqlite3.Connection,
    *,
    action_id: int,
    action_status: str,
    notes: str | None = None,
) -> bool:
    """Update status (and optionally notes) on an existing action.
    Returns True if a row was updated, False if action_id not found."""
    from outreach.db import ACTION_STATUSES
    if action_status not in ACTION_STATUSES:
        raise ValueError(f"Unknown action_status '{action_status}'. Valid: {sorted(ACTION_STATUSES)}")
    result = conn.execute(
        """
        UPDATE buyer_actions
        SET action_status = ?,
            notes = COALESCE(?, notes),
            updated_at = ?
        WHERE id = ?
        """,
        (action_status, notes, utc_now_iso(), action_id),
    )
    conn.commit()
    return result.rowcount > 0


def get_action(conn: sqlite3.Connection, action_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM buyer_actions WHERE id = ?", (action_id,)
    ).fetchone()
    return row_to_dict(row)


def list_actions(
    conn: sqlite3.Connection,
    *,
    buyer_key: str | None = None,
    action_type: str | None = None,
    action_status: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return actions filtered by any combination of buyer/type/status."""
    clauses: list[str] = []
    params: list[Any] = []
    if buyer_key is not None:
        clauses.append("buyer_key = ?")
        params.append(buyer_key)
    if action_type is not None:
        clauses.append("action_type = ?")
        params.append(action_type)
    if action_status is not None:
        clauses.append("action_status = ?")
        params.append(action_status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM buyer_actions {where} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def buyer_current_state(
    conn: sqlite3.Connection,
    buyer_key: str,
) -> dict[str, Any]:
    """Derive the single most-informative current state for a buyer.

    Rules (in priority order):
    1. Any 'sent' action  → overall_status = sent
    2. Any 'drafted' action → overall_status = drafted
    3. Any 'follow_up' action → overall_status = follow_up
    4. Any 'ignored' action → overall_status = ignored
    5. Any 'pending' action → overall_status = pending
    6. Nothing              → overall_status = not_started
    """
    rows = conn.execute(
        """
        SELECT id, action_type, action_status, run_id, notes, actor, source, created_at, updated_at
        FROM buyer_actions
        WHERE buyer_key = ?
        ORDER BY updated_at DESC
        """,
        (buyer_key,),
    ).fetchall()
    actions = [dict(r) for r in rows]

    STATUS_PRIORITY = {"sent": 0, "drafted": 1, "follow_up": 2, "ignored": 3, "completed": 4, "pending": 5, "failed": 6}
    overall = "not_started"
    latest_action: dict[str, Any] | None = None
    for action in actions:
        s = action["action_status"]
        if STATUS_PRIORITY.get(s, 99) < STATUS_PRIORITY.get(overall, 99):
            overall = s
            latest_action = action

    return {
        "buyer_key": buyer_key,
        "overall_status": overall,
        "action_count": len(actions),
        "latest_action": latest_action,
        "all_actions": actions,
    }


def has_open_action_of_type(
    conn: sqlite3.Connection,
    buyer_key: str,
    action_type: str,
) -> bool:
    """True if there is already a pending/drafted action of this type for the buyer.
    Used to prevent accidental duplicate creation."""
    row = conn.execute(
        """
        SELECT id FROM buyer_actions
        WHERE buyer_key = ?
          AND action_type = ?
          AND action_status IN ('pending', 'drafted', 'follow_up')
        LIMIT 1
        """,
        (buyer_key, action_type),
    ).fetchone()
    return row is not None


def has_successful_send_for_run(
    conn: sqlite3.Connection,
    *,
    contact_id: int,
    run_id: str,
    channel: str,
) -> bool:
    pattern = f'"run_id":"{run_id}"'
    row = conn.execute(
        """
        SELECT m.id
        FROM outreach_messages m
        JOIN outreach_send_log l ON l.message_id = m.id
        WHERE m.contact_id = ?
          AND m.channel = ?
          AND m.payload_json LIKE ?
          AND l.result = 'sent'
        ORDER BY m.id DESC
        LIMIT 1
        """,
        (contact_id, channel, f"%{pattern}%"),
    ).fetchone()
    return row is not None
