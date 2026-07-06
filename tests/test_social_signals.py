from __future__ import annotations

import unittest

from enrichment.agents.social_signals import SocialSignalScout


class FakeResponse:
    def __init__(self, status_code: int, text: str, content_type: str = "text/html") -> None:
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def get(self, url, headers, timeout):
        if url.endswith("/robots.txt"):
            return FakeResponse(404, "")
        return FakeResponse(
            200,
            """
            <html>
              <body>
                <a href="https://www.linkedin.com/company/acme-ltd/">LinkedIn</a>
                <a href="https://x.com/acme">X</a>
                <a href="/contact">Contact</a>
              </body>
            </html>
            """,
        )


class SocialSignalsTest(unittest.TestCase):
    def test_discovers_public_social_links_from_company_site(self) -> None:
        report = SocialSignalScout(session=FakeSession()).discover("example.com")

        platforms = {signal.platform for signal in report.signals}
        urls = {signal.url for signal in report.signals}

        self.assertEqual(platforms, {"linkedin", "x"})
        self.assertIn("https://www.linkedin.com/company/acme-ltd", urls)
        self.assertIn("https://x.com/acme", urls)


if __name__ == "__main__":
    unittest.main()
