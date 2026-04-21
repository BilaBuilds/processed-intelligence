"""
High-level outreach service operations.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from outreach.contacts import channel_destination
from outreach.db import connect, init_db
from outreach.renderers import render_message
from outreach.repositories import (
    get_contact,
    has_successful_send_for_run,
    insert_message,
    insert_sample,
    insert_send_log,
    update_message_status,
    utc_now_iso,
)
from outreach.samples import build_sample_bundle, latest_successful_run_id
from outreach.senders import build_default_sender_map, send_message


def preview_sample_for_contact(
    *,
    contact_id: int,
    run_id: str | None = None,
    conn: sqlite3.Connection | None = None,
    runs_dir: Path | None = None,
) -> dict[str, Any]:
    owns_connection = conn is None
    if conn is None:
        conn = connect()
    try:
        init_db(conn)
        contact = get_contact(conn, contact_id)
        if contact is None:
            return {"status": "failed", "error": f"Contact {contact_id} not found."}
        resolved_runs_dir = runs_dir or (Path.cwd() / "data" / "runs")
        resolved_run_id = run_id or latest_successful_run_id(resolved_runs_dir)
        sample = build_sample_bundle(
            run_id=resolved_run_id,
            contact=contact,
            runs_dir=resolved_runs_dir,
        )
        rendered = render_message(str(contact.get("preferred_channel") or "email"), contact, sample)
        return {
            "status": "preview",
            "contact": contact,
            "run_id": resolved_run_id,
            "sample_payload": sample,
            "rendered_message": rendered,
        }
    finally:
        if owns_connection:
            conn.close()


def send_sample_to_contact(
    contact_id: int,
    run_id: str | None = None,
    force: bool = False,
    *,
    conn: sqlite3.Connection | None = None,
    runs_dir: Path | None = None,
    sender_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    owns_connection = conn is None
    if conn is None:
        conn = connect()
    try:
        init_db(conn)
        contact = get_contact(conn, contact_id)
        if contact is None:
            return {"status": "failed", "error": f"Contact {contact_id} not found."}

        channel = str(contact.get("preferred_channel") or "email").strip().lower()
        destination = channel_destination(contact, channel)
        if not destination:
            return {
                "status": "failed",
                "error": f"No usable destination for preferred channel '{channel}'.",
                "channel": channel,
            }

        resolved_runs_dir = runs_dir or (Path.cwd() / "data" / "runs")
        resolved_run_id = run_id or latest_successful_run_id(resolved_runs_dir)

        if not force and has_successful_send_for_run(conn, contact_id=contact_id, run_id=resolved_run_id, channel=channel):
            return {
                "status": "duplicate_skipped",
                "contact_id": contact_id,
                "run_id": resolved_run_id,
                "channel": channel,
            }

        sample = build_sample_bundle(run_id=resolved_run_id, contact=contact, runs_dir=resolved_runs_dir)
        rendered = render_message(channel, contact, sample)

        sample_id = insert_sample(
            conn,
            contact_id=contact_id,
            run_id=resolved_run_id,
            shortlist_count=sample["counts"]["shortlist"],
            review_count=sample["counts"]["review"],
            intelligence_count=sample["counts"]["market_intelligence"],
            sample_payload=sample,
        )
        message_payload = {
            "run_id": resolved_run_id,
            "sample_id": sample_id,
            "contact_id": contact_id,
            "channel": channel,
            "sample_payload": sample,
            "rendered_message": rendered,
        }
        message_id = insert_message(
            conn,
            contact_id=contact_id,
            campaign_id=None,
            channel=channel,
            template_key=rendered["template_key"],
            subject=rendered.get("subject"),
            body_text=rendered["body_text"],
            payload=message_payload,
            send_status="pending",
        )

        result = send_message(
            channel,
            destination,
            rendered,
            {"contact_id": contact_id, "run_id": resolved_run_id, "sample_id": sample_id},
            sender_map=sender_map or build_default_sender_map(),
        )
        sent_at = utc_now_iso() if result["status"] == "sent" else None
        update_message_status(
            conn,
            message_id=message_id,
            send_status=result["status"],
            sent_at=sent_at,
            error_message=result.get("error_message"),
        )
        send_log_id = insert_send_log(
            conn,
            contact_id=contact_id,
            message_id=message_id,
            channel=channel,
            result=result["status"],
            provider_response=result.get("provider_response"),
            error_message=result.get("error_message"),
        )
        return {
            "status": result["status"],
            "contact_id": contact_id,
            "run_id": resolved_run_id,
            "channel": channel,
            "sample_id": sample_id,
            "message_id": message_id,
            "send_log_id": send_log_id,
            "error": result.get("error_message"),
        }
    finally:
        if owns_connection:
            conn.close()
