import json
import tempfile
import unittest
from pathlib import Path

from outreach.db import connect, init_db
from outreach.repositories import create_contact
from outreach.senders import build_default_sender_map
from outreach.service import preview_sample_for_contact, send_sample_to_contact


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class OutreachServiceTests(unittest.TestCase):
    def make_runs_dir(self, root: Path) -> Path:
        runs_dir = root / "runs"
        run_dir = runs_dir / "2026-04-11_165252"
        run_dir.mkdir(parents=True, exist_ok=True)
        write_json(run_dir / "run_manifest.json", {"run_id": run_dir.name, "status": "success"})
        write_json(
            run_dir / "shortlist.json",
            {
                "opportunities": [
                    {"id": "s1", "title": "North East Retrofit", "region": "North East", "buyer_name": "Buyer A", "score": 40, "source_url": "https://example.com/s1"},
                ]
            },
        )
        write_jsonl(
            run_dir / "review_candidates.jsonl",
            [
                {"id": "r1", "title": "North East Maintenance", "region": "North East", "buyer_name": "Buyer C", "score": 18, "source_url": "https://example.com/r1"},
            ],
        )
        write_jsonl(
            run_dir / "market_intelligence.jsonl",
            [
                {"id": "m1", "title": "Awarded North East Retrofit", "region": "North East", "buyer_name": "Buyer E", "rejection_reasons": ["award"], "source_url": "https://example.com/m1"},
            ],
        )
        write_jsonl(
            run_dir / "rejected_tenders.jsonl",
            [
                {"id": "x1", "title": "Rejected", "rejection_reasons": ["inactive_status"]},
            ],
        )
        return runs_dir

    def test_preview_mode_does_not_send(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = connect(root / "outreach.sqlite")
            init_db(conn)
            contact_id = create_contact(
                conn,
                {
                    "company_name": "North Build",
                    "contact_name": "Sam",
                    "preferred_channel": "email",
                    "email": "sam@example.com",
                    "region": "North East",
                    "sectors": "retrofit",
                },
            )
            runs_dir = self.make_runs_dir(root)

            result = preview_sample_for_contact(contact_id=contact_id, conn=conn, runs_dir=runs_dir)

            self.assertEqual(result["status"], "preview")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outreach_messages").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outreach_send_log").fetchone()[0], 0)
            conn.close()

    def test_send_sample_writes_rows_and_duplicate_protection_works(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = connect(root / "outreach.sqlite")
            init_db(conn)
            contact_id = create_contact(
                conn,
                {
                    "company_name": "North Build",
                    "contact_name": "Sam",
                    "preferred_channel": "discord",
                    "discord_webhook_url": "https://discord.example/webhook",
                    "region": "North East",
                    "sectors": "retrofit",
                },
            )
            runs_dir = self.make_runs_dir(root)
            sender_map = build_default_sender_map(
                discord_transport=lambda destination, payload: {"status": "sent", "provider_response": {"destination": destination}, "error_message": None}
            )

            first = send_sample_to_contact(contact_id, conn=conn, runs_dir=runs_dir, sender_map=sender_map)
            second = send_sample_to_contact(contact_id, conn=conn, runs_dir=runs_dir, sender_map=sender_map)

            self.assertEqual(first["status"], "sent")
            self.assertEqual(second["status"], "duplicate_skipped")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outreach_samples").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outreach_messages").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM outreach_send_log").fetchone()[0], 1)
            conn.close()

    def test_missing_destination_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = connect(root / "outreach.sqlite")
            init_db(conn)
            contact_id = create_contact(
                conn,
                {
                    "company_name": "North Build",
                    "contact_name": "Sam",
                    "preferred_channel": "email",
                    "region": "North East",
                    "sectors": "retrofit",
                },
            )
            runs_dir = self.make_runs_dir(root)
            result = send_sample_to_contact(contact_id, conn=conn, runs_dir=runs_dir)
            self.assertEqual(result["status"], "failed")
            self.assertIn("No usable destination", result["error"])
            conn.close()

    def test_email_and_whatsapp_stubs_behave(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            conn = connect(root / "outreach.sqlite")
            init_db(conn)
            email_contact_id = create_contact(
                conn,
                {
                    "company_name": "North Build",
                    "contact_name": "Sam",
                    "preferred_channel": "email",
                    "email": "sam@example.com",
                    "region": "North East",
                    "sectors": "retrofit",
                },
            )
            whatsapp_contact_id = create_contact(
                conn,
                {
                    "company_name": "North Build",
                    "contact_name": "Sam",
                    "preferred_channel": "whatsapp",
                    "whatsapp_number": "+447700900123",
                    "region": "North East",
                    "sectors": "retrofit",
                },
            )
            runs_dir = self.make_runs_dir(root)
            sender_map = build_default_sender_map(
                email_transport=lambda destination, message: {"status": "sent", "provider_response": {"destination": destination}, "error_message": None},
                whatsapp_transport=lambda destination, message: {"status": "sent", "provider_response": {"destination": destination}, "error_message": None},
            )
            email_result = send_sample_to_contact(email_contact_id, conn=conn, runs_dir=runs_dir, sender_map=sender_map)
            whatsapp_result = send_sample_to_contact(whatsapp_contact_id, conn=conn, runs_dir=runs_dir, sender_map=sender_map)

            self.assertEqual(email_result["status"], "sent")
            self.assertEqual(whatsapp_result["status"], "sent")
            conn.close()


if __name__ == "__main__":
    unittest.main()
