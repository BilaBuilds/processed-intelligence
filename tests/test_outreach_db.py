import tempfile
import unittest
from pathlib import Path

from outreach.contacts import filter_contacts
from outreach.db import connect, init_db


class OutreachDbTests(unittest.TestCase):
    def test_db_bootstrap_creates_required_tables(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_file = Path(td) / "outreach.sqlite"
            conn = connect(db_file)
            try:
                init_db(conn)
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'outreach_%' ORDER BY name"
                ).fetchall()
                self.assertEqual(
                    [row[0] for row in rows],
                    [
                        "outreach_campaigns",
                        "outreach_contacts",
                        "outreach_messages",
                        "outreach_samples",
                        "outreach_send_log",
                    ],
                )
            finally:
                conn.close()

    def test_contact_filtering_works(self) -> None:
        contacts = [
            {
                "id": 1,
                "company_name": "North Build",
                "preferred_channel": "email",
                "email": "north@example.com",
                "region": "North East",
                "sectors": "construction, maintenance",
                "is_active": 1,
            },
            {
                "id": 2,
                "company_name": "Inactive Ltd",
                "preferred_channel": "email",
                "email": "inactive@example.com",
                "region": "North East",
                "sectors": "construction",
                "is_active": 0,
            },
            {
                "id": 3,
                "company_name": "No Destination",
                "preferred_channel": "email",
                "email": "",
                "region": "North East",
                "sectors": "construction",
                "is_active": 1,
            },
        ]
        filtered = filter_contacts(
            contacts,
            active_only=True,
            sector="construction",
            region="north east",
            preferred_channel="email",
        )
        self.assertEqual([contact["id"] for contact in filtered], [1])


if __name__ == "__main__":
    unittest.main()
