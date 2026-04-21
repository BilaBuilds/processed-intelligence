"""
SQLite bootstrap and connection helpers for outreach persistence.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(os.getenv("TENDER_BASE_DIR", str(Path(__file__).resolve().parent.parent))).expanduser().resolve()
STATE_DIR = BASE_DIR / "state"
DEFAULT_DB_PATH = STATE_DIR / "outreach.sqlite"

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS outreach_contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        contact_name TEXT,
        role TEXT,
        email TEXT,
        whatsapp_number TEXT,
        discord_webhook_url TEXT,
        preferred_channel TEXT NOT NULL,
        region TEXT,
        sectors TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS outreach_campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        campaign_type TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS outreach_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contact_id INTEGER NOT NULL,
        campaign_id INTEGER,
        channel TEXT NOT NULL,
        template_key TEXT NOT NULL,
        subject TEXT,
        body_text TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        send_status TEXT NOT NULL,
        sent_at TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS outreach_samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contact_id INTEGER NOT NULL,
        run_id TEXT NOT NULL,
        shortlist_count INTEGER NOT NULL,
        review_count INTEGER NOT NULL,
        intelligence_count INTEGER NOT NULL,
        sample_payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS outreach_send_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contact_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        channel TEXT NOT NULL,
        result TEXT NOT NULL,
        provider_response_json TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_outreach_contacts_active ON outreach_contacts(is_active, preferred_channel)",
    "CREATE INDEX IF NOT EXISTS idx_outreach_samples_contact_run ON outreach_samples(contact_id, run_id)",
    "CREATE INDEX IF NOT EXISTS idx_outreach_messages_contact_channel ON outreach_messages(contact_id, channel, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_outreach_send_log_message ON outreach_send_log(message_id, created_at)",
    # --- Action layer (Phase 1) ---
    """
    CREATE TABLE IF NOT EXISTS buyer_actions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        buyer_key   TEXT    NOT NULL,
        buyer_name  TEXT    NOT NULL,
        action_type TEXT    NOT NULL,
        action_status TEXT  NOT NULL DEFAULT 'pending',
        run_id      TEXT,
        notes       TEXT,
        actor       TEXT    NOT NULL DEFAULT 'operator',
        source      TEXT    NOT NULL DEFAULT 'cli',
        created_at  TEXT    NOT NULL,
        updated_at  TEXT    NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_buyer_actions_buyer ON buyer_actions(buyer_key, action_type, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_buyer_actions_status ON buyer_actions(action_status, created_at)",
]

# Valid enumerations — enforced in repositories, not just DB
ACTION_TYPES = frozenset({
    "preview_outreach",
    "mark_drafted",
    "mark_sent",
    "mark_ignored",
    "mark_follow_up",
    "open_dossier",
    "open_latest_tenders",
    "export_contact_brief",
})

ACTION_STATUSES = frozenset({
    "pending",
    "drafted",
    "sent",
    "ignored",
    "follow_up",
    "completed",
    "failed",
})


def db_path() -> Path:
    override = os.getenv("OUTREACH_DB_PATH")
    return Path(override).expanduser().resolve() if override else DEFAULT_DB_PATH


def connect(path: Path | None = None) -> sqlite3.Connection:
    resolved = path or db_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
    conn.commit()
