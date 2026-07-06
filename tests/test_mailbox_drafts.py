from __future__ import annotations

import unittest

from enrichment.mailbox import ImapDraftClient, MailboxDraftConfig


class FakeImap:
    instances = []

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.logged_in = False
        self.appended = []
        self.logged_out = False
        FakeImap.instances.append(self)

    def login(self, user: str, password: str):
        self.logged_in = True
        self.user = user
        self.password = password
        return "OK", []

    def append(self, mailbox: str, flags: str | None, date_time: str | None, message: bytes):
        self.appended.append((mailbox, flags, date_time, message))
        return "OK", []

    def logout(self):
        self.logged_out = True
        return "OK", []


class MailboxDraftTest(unittest.TestCase):
    def test_create_draft_appends_rfc822_message_to_drafts(self) -> None:
        FakeImap.instances = []
        config = MailboxDraftConfig(
            email_address="info@processedcivils.com",
            password="secret",
        )
        client = ImapDraftClient(config, imap_factory=FakeImap)

        client.create_draft(
            to="lead@example.com",
            subject="Relevant civils opportunities",
            body="Hello from Hermes",
        )

        instance = FakeImap.instances[0]
        self.assertEqual(instance.host, "imap.hostinger.com")
        self.assertEqual(instance.port, 993)
        self.assertTrue(instance.logged_in)
        self.assertTrue(instance.logged_out)
        mailbox, flags, _date_time, message = instance.appended[0]
        self.assertEqual(mailbox, "Drafts")
        self.assertEqual(flags, "\\Draft")
        self.assertIn(b"To: lead@example.com", message)
        self.assertIn(b"Subject: Relevant civils opportunities", message)
        self.assertIn(b"X-Hermes-Approval-Required: true", message)
        self.assertIn(b"X-Hermes-Mode: draft-only", message)
        self.assertIn(b"Hello from Hermes", message)

    def test_create_draft_falls_back_to_inbox_drafts_namespace(self) -> None:
        class NamespaceFakeImap(FakeImap):
            def append(self, mailbox, flags, date_time, message):
                self.appended.append((mailbox, flags, date_time, message))
                if mailbox == "INBOX.Drafts":
                    return "OK", []
                return "NO", [b"Client tried to access nonexistent namespace"]

        FakeImap.instances = []
        config = MailboxDraftConfig(
            email_address="info@processedcivils.com",
            password="secret",
        )
        client = ImapDraftClient(config, imap_factory=NamespaceFakeImap)

        client.create_draft(
            to="lead@example.com",
            subject="Subject",
            body="Body",
        )

        instance = FakeImap.instances[0]
        self.assertEqual(instance.appended[0][0], "Drafts")
        self.assertEqual(instance.appended[1][0], "INBOX.Drafts")


if __name__ == "__main__":
    unittest.main()
