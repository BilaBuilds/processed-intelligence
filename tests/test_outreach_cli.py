import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from outreach.cli import build_parser, run_cli
from outreach.db import connect, init_db
from outreach.repositories import create_contact


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class OutreachCliTests(unittest.TestCase):
    def test_cli_argument_parsing(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["send-sample", "--contact-id", "123", "--force"])
        self.assertEqual(args.command, "send-sample")
        self.assertEqual(args.contact_id, 123)
        self.assertTrue(args.force)

    def test_cli_preview_outputs_deterministic_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_file = root / "outreach.sqlite"
            runs_dir = root / "runs"
            run_dir = runs_dir / "2026-04-11_165252"
            run_dir.mkdir(parents=True, exist_ok=True)
            write_json(run_dir / "run_manifest.json", {"run_id": run_dir.name, "status": "success"})
            write_json(
                run_dir / "shortlist.json",
                {"opportunities": [{"id": "s1", "title": "North East Retrofit", "region": "North East"}]},
            )
            (run_dir / "review_candidates.jsonl").write_text("", encoding="utf-8")
            (run_dir / "market_intelligence.jsonl").write_text("", encoding="utf-8")
            (run_dir / "rejected_tenders.jsonl").write_text("", encoding="utf-8")

            conn = connect(db_file)
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
            conn.close()

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_cli(
                    [
                        "preview-sample",
                        "--contact-id",
                        str(contact_id),
                        "--db-path",
                        str(db_file),
                        "--runs-dir",
                        str(runs_dir),
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["status"], "preview")
            self.assertEqual(payload["run_id"], "2026-04-11_165252")

    def test_create_action_accepts_explicit_status(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db_file = root / "outreach.sqlite"

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                exit_code = run_cli(
                    [
                        "create-action",
                        "--buyer",
                        "Environment Agency",
                        "--type",
                        "mark_sent",
                        "--status",
                        "sent",
                        "--db-path",
                        str(db_file),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("sent", buffer.getvalue())

            conn = connect(db_file)
            init_db(conn)
            row = conn.execute(
                "SELECT buyer_name, action_type, action_status FROM buyer_actions"
            ).fetchone()
            self.assertEqual(dict(row), {
                "buyer_name": "Environment Agency",
                "action_type": "mark_sent",
                "action_status": "sent",
            })
            conn.close()


if __name__ == "__main__":
    unittest.main()
