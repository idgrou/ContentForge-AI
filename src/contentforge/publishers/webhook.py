"""Send a post to your own automation (for example a self-hosted n8n workflow, which is free)
to reach networks without a simple free API, such as TikTok, X or LinkedIn."""

from __future__ import annotations

import requests

from .base import PublishResult, check


class WebhookPublisher:
    def __init__(self, url: str, session: requests.Session | None = None):
        self.url = url
        self.session = session or requests.Session()

    def publish(self, payload: dict) -> PublishResult:
        try:
            out = check(self.session.post(self.url, json=payload, timeout=60), "Webhook")
            return PublishResult("webhook", True, id=str(out.get("id", "")) if isinstance(out, dict) else "")
        except Exception as exc:
            return PublishResult("webhook", False, error=str(exc))
