"""
src/notify/discord.py
=====================
Discord webhook notifier.

Config (environment variables):
    TENDER_WEBHOOK_URL   - Discord webhook URL (required)
    TENDER_NOTIFY_N      - Max opportunities per notification (default 5)

Features:
    - Single rich embed per run (not N separate messages)
    - Rate-limit aware with exponential backoff
    - Never fails the core pipeline
"""

import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from src.notify.base import BaseNotifier

log = logging.getLogger("notify.discord")

MAX_RETRIES = 3
RETRY_BACKOFF = 2
POST_DELAY = 1.2
EMBED_COLOR = 0x2F6BFF


class DiscordNotifier(BaseNotifier):

    @property
    def name(self) -> str:
        return "discord"

    def _get_webhook_url(self) -> str:
        return os.getenv("TENDER_WEBHOOK_URL", "").strip()

    def _validate_webhook_url(self, webhook_url: str) -> None:
        if not webhook_url:
            raise ValueError("TENDER_WEBHOOK_URL is missing.")
        if "<" in webhook_url or ">" in webhook_url:
            raise ValueError("TENDER_WEBHOOK_URL contains placeholder angle brackets.")
        if "REAL_ROTATED_WEBHOOK" in webhook_url or "PASTE" in webhook_url.upper():
            raise ValueError("TENDER_WEBHOOK_URL still contains placeholder text.")

        parsed = urlparse(webhook_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("TENDER_WEBHOOK_URL is not a valid URL.")
        if "/api/webhooks/" not in parsed.path:
            raise ValueError("TENDER_WEBHOOK_URL must contain /api/webhooks/.")

    def is_configured(self) -> bool:
        try:
            self._validate_webhook_url(self._get_webhook_url())
            return True
        except ValueError:
            return False

    def _safe_value(self, raw) -> str:
        if raw is None or raw == "":
            return "N/A"
        try:
            return "GBP {:,}".format(int(float(raw)))
        except (ValueError, TypeError):
            return "N/A"

    def _format_opportunity(self, opp: dict, idx: int) -> str:
        title = opp.get("title") or "Untitled Opportunity"
        score = opp.get("score") or "-"
        region = opp.get("region") or "Unknown"
        deadline_raw = opp.get("deadline")
        deadline = f"{deadline_raw[:10]}" if deadline_raw else "N/A"
        decision = str(opp.get("decision_verdict") or "REVIEW").upper()
        confidence = opp.get("decision_confidence")
        value = self._safe_value(opp.get("value") or opp.get("estimated_value"))
        buyer = opp.get("buyer") or opp.get("buyer_name") or "Unknown"
        url = opp.get("url") or opp.get("source_url") or ""
        reasons = opp.get("decision_reasons") or []
        risks = opp.get("risk_flags") or []

        lines = [
            f"**{idx}. {title}**",
            f"Score: **{score}**  |  Region: {region}",
            f"Buyer: {buyer}",
            f"Deadline: {deadline}  |  Value: {value}",
        ]
        if confidence is not None:
            lines.append(f"Decision: **{decision}**  |  Confidence: {confidence}%")
        else:
            lines.append(f"Decision: **{decision}**")
        if reasons:
            lines.append(f"Why: {', '.join(str(r) for r in reasons[:3])}")
        if risks:
            lines.append(f"Risk: {', '.join(str(r) for r in risks[:3])}")
        if url:
            lines.append(f"[View tender]({url})")
        return "\n".join(lines)

    def _build_payload(self, opportunities: list[dict], run_id: str) -> dict:
        top_n = int(os.getenv("TENDER_NOTIFY_N", os.getenv("TENDER_TOP_N", "5")))
        top = opportunities[:top_n]

        description = "\n\n".join(
            self._format_opportunity(opp, i) for i, opp in enumerate(top, start=1)
        )

        if len(description) > 4000:
            description = description[:3997] + "..."

        return {
            "embeds": [
                {
                    "title": f"Tender Matches  |  {len(top)} New  |  Run {run_id}",
                    "description": description,
                    "color": EMBED_COLOR,
                    "footer": {
                        "text": "Project BigBoi  |  {} UTC".format(
                            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                        )
                    },
                }
            ]
        }

    def _post(self, payload: dict, webhook_url: str) -> bool:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(webhook_url, json=payload, timeout=10)

                if resp.status_code == 429:
                    retry_after = POST_DELAY
                    try:
                        retry_after = float(resp.json().get("retry_after", POST_DELAY))
                    except Exception:
                        pass

                    log.warning(
                        "Rate-limited - retrying in %.1fs (attempt %d/%d)",
                        retry_after,
                        attempt,
                        MAX_RETRIES,
                    )
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                return True

            except requests.RequestException as exc:
                wait = RETRY_BACKOFF ** attempt
                log.error(
                    "POST failed (attempt %d/%d): %s - retrying in %.1fs",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)

        log.error("All %d attempts failed.", MAX_RETRIES)
        return False

    def send(self, opportunities: list[dict], run_id: str) -> bool:
        if not opportunities:
            log.info("Discord: no new opportunities to send.")
            return True

        webhook_url = self._get_webhook_url()
        self._validate_webhook_url(webhook_url)

        payload = self._build_payload(opportunities, run_id)
        success = self._post(payload, webhook_url)

        if success:
            sent_n = min(
                len(opportunities),
                int(os.getenv("TENDER_NOTIFY_N", os.getenv("TENDER_TOP_N", "5"))),
            )
            log.info("Discord: sent %d opportunities.", sent_n)
        else:
            log.error("Discord: failed to send.")

        return success
