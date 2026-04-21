import os
import unittest
from unittest.mock import patch

from src.notify.discord import COLOR_BID, COLOR_REVIEW, DiscordNotifier


class TestDiscordNotifier(unittest.TestCase):
    def setUp(self) -> None:
        self.notifier = DiscordNotifier()
        self.run_id = "2026-04-17_000003"
        self.opportunity = {
            "title": "Drainage and civils package",
            "buyer_name": "Example Council",
            "region": "North East",
            "deadline_at": "2026-05-12T12:00:00+00:00",
            "value_amount": 250000,
            "value_currency": "GBP",
            "score": 47,
            "decision_confidence": 81,
            "decision_verdict": "BID",
            "decision_reasons": ["high_match_score", "value_band_strong"],
            "risk_flags": ["tight_deadline"],
            "source_url": "https://example.com/tender",
        }

    def test_validate_webhook_rejects_placeholders_and_bad_shape(self) -> None:
        with self.assertRaises(ValueError):
            self.notifier._validate_webhook_url("https://discord.com/api/webhooks/YOUR_ROTATED_URL")
        with self.assertRaises(ValueError):
            self.notifier._validate_webhook_url("https://example.com/api/webhooks/123/abc")
        with self.assertRaises(ValueError):
            self.notifier._validate_webhook_url("https://discord.com/api/webhooks/123")

    def test_validate_webhook_accepts_well_formed_url(self) -> None:
        self.notifier._validate_webhook_url("https://discord.com/api/webhooks/123456789/abc_DEF-ghi")

    def test_build_run_summary_counts_verdicts(self) -> None:
        payload = self.notifier.build_run_summary(
            [
                {"decision_verdict": "BID"},
                {"decision_verdict": "REVIEW"},
                {"decision_verdict": "BID"},
            ],
            self.run_id,
            evaluated_count=5,
        )
        self.assertIn("Tender pipeline | Run 2026-04-17_000003", payload["content"])
        self.assertIn("Evaluated: 5 | Actionable: 3", payload["content"])
        self.assertIn("BID: 2 | REVIEW: 1 | Not posted: 2", payload["content"])

    def test_build_tender_embed_contains_client_ready_fields(self) -> None:
        payload = self.notifier.build_tender_embed(self.opportunity, self.run_id)
        embed = payload["embeds"][0]
        self.assertEqual(embed["title"], "Drainage and civils package")
        self.assertEqual(embed["url"], "https://example.com/tender")
        self.assertEqual(embed["color"], COLOR_BID)
        field_names = [field["name"] for field in embed["fields"]]
        self.assertEqual(
            field_names,
            ["Decision", "Confidence", "Score", "Buyer", "Region", "Deadline", "Value"],
        )
        self.assertIn("Why:", embed["description"])
        self.assertIn("Risks:", embed["description"])

    def test_build_tender_embed_uses_review_colour(self) -> None:
        review = dict(self.opportunity)
        review["decision_verdict"] = "REVIEW"
        payload = self.notifier.build_tender_embed(review, self.run_id)
        self.assertEqual(payload["embeds"][0]["color"], COLOR_REVIEW)

    def test_send_posts_summary_then_one_message_per_tender(self) -> None:
        opportunities = [
            dict(self.opportunity),
            dict(self.opportunity, title="Second tender", decision_verdict="REVIEW"),
            dict(self.opportunity, title="Pass tender", decision_verdict="NO_BID"),
        ]
        posted = []

        with patch.object(self.notifier, "_get_webhook_url", return_value="https://discord.com/api/webhooks/123/abc"), patch.object(
            self.notifier, "_post_payload", side_effect=lambda payload, webhook: (posted.append(payload), (True, ""))[1]
        ), patch("src.notify.discord.time.sleep", return_value=None), patch.dict(
            os.environ, {"TENDER_NOTIFY_N": "5"}, clear=False
        ):
            success = self.notifier.send(opportunities, self.run_id)

        self.assertTrue(success)
        self.assertEqual(len(posted), 3)
        self.assertIn("content", posted[0])
        self.assertIn("Evaluated: 3 | Actionable: 2", posted[0]["content"])
        self.assertIn("embeds", posted[1])
        self.assertIn("embeds", posted[2])

    def test_send_falls_back_to_text_when_embed_build_fails(self) -> None:
        posted = []

        with patch.object(self.notifier, "_get_webhook_url", return_value="https://discord.com/api/webhooks/123/abc"), patch.object(
            self.notifier, "_post_payload", side_effect=lambda payload, webhook: (posted.append(payload), (True, ""))[1]
        ), patch.object(
            self.notifier, "build_tender_embed", side_effect=RuntimeError("boom")
        ), patch("src.notify.discord.time.sleep", return_value=None):
            success = self.notifier.send([self.opportunity], self.run_id)

        self.assertTrue(success)
        self.assertEqual(len(posted), 2)
        self.assertIn("content", posted[1])

    def test_send_returns_false_when_summary_post_fails(self) -> None:
        with patch.object(self.notifier, "_get_webhook_url", return_value="https://discord.com/api/webhooks/123/abc"), patch.object(
            self.notifier, "_post_payload", return_value=(False, "HTTP 404: Unknown Webhook")
        ), patch("src.notify.discord.time.sleep", return_value=None):
            success = self.notifier.send([self.opportunity], self.run_id)

        self.assertFalse(success)

    def test_send_returns_false_on_partial_tender_failure(self) -> None:
        posted = []

        def fake_post(payload, webhook):
            posted.append(payload)
            # Second call (first tender embed) fails
            return (True, "") if len(posted) != 2 else (False, "HTTP 500: server error")

        with patch.object(self.notifier, "_get_webhook_url", return_value="https://discord.com/api/webhooks/123/abc"), patch.object(
            self.notifier, "_post_payload", side_effect=fake_post
        ), patch("src.notify.discord.time.sleep", return_value=None):
            success = self.notifier.send([self.opportunity], self.run_id)

        self.assertFalse(success)

    def test_send_returns_false_for_invalid_webhook_without_raising(self) -> None:
        with patch.object(self.notifier, "_get_webhook_url", return_value="https://discord.com/api/webhooks/YOUR_ROTATED_URL"):
            success = self.notifier.send([self.opportunity], self.run_id)

        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()
