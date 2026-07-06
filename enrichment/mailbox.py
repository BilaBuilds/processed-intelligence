from __future__ import annotations

import imaplib
import os
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv


class ImapClient(Protocol):
    def login(self, user: str, password: str) -> tuple[str, list[bytes]]: ...

    def append(
        self,
        mailbox: str,
        flags: str | None,
        date_time: str | None,
        message: bytes,
    ) -> tuple[str, list[bytes]]: ...

    def logout(self) -> tuple[str, list[bytes]]: ...


@dataclass(frozen=True)
class MailboxDraftConfig:
    email_address: str
    password: str
    imap_host: str = "imap.hostinger.com"
    imap_port: int = 993
    drafts_folder: str = "Drafts"

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> "MailboxDraftConfig":
        load_dotenv(env_path)
        email_address = os.getenv("HOSTINGER_EMAIL", "").strip()
        password = os.getenv("HOSTINGER_EMAIL_PASSWORD", "").strip()
        if not email_address:
            raise ValueError("HOSTINGER_EMAIL is required")
        if not password:
            raise ValueError("HOSTINGER_EMAIL_PASSWORD is required")

        return cls(
            email_address=email_address,
            password=password,
            imap_host=os.getenv("HOSTINGER_IMAP_HOST", "imap.hostinger.com").strip(),
            imap_port=int(os.getenv("HOSTINGER_IMAP_PORT", "993")),
            drafts_folder=os.getenv("HOSTINGER_DRAFTS_FOLDER", "Drafts").strip()
            or "Drafts",
        )


class ImapDraftClient:
    def __init__(
        self,
        config: MailboxDraftConfig,
        imap_factory=imaplib.IMAP4_SSL,
    ) -> None:
        self.config = config
        self.imap_factory = imap_factory

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to: str | None = None,
    ) -> None:
        message = self._message(to, subject, body, reply_to)
        client = self.imap_factory(self.config.imap_host, self.config.imap_port)
        try:
            client.login(self.config.email_address, self.config.password)
            self._append_to_drafts(client, message)
        finally:
            client.logout()

    def _append_to_drafts(
        self,
        client: ImapClient,
        message: EmailMessage,
    ) -> None:
        folders = [
            self.config.drafts_folder,
            f"INBOX.{self.config.drafts_folder}",
            f"INBOX/{self.config.drafts_folder}",
        ]
        responses: list[tuple[str, list[bytes]]] = []
        for folder in dict.fromkeys(folders):
            status, response = client.append(
                folder,
                "\\Draft",
                None,
                message.as_bytes(),
            )
            if status == "OK":
                return
            responses.append((status, response))

        raise RuntimeError(f"IMAP append failed: {responses!r}")

    def _message(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to: str | None = None,
    ) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self.config.email_address
        message["To"] = to
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid(domain=self.config.email_address.split("@")[-1])
        message["X-Hermes-Approval-Required"] = "true"
        message["X-Hermes-Mode"] = "draft-only"
        if reply_to:
            message["Reply-To"] = reply_to
        message.set_content(body)
        return message
