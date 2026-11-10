"""Telegram Bot API (free). Create a bot with @BotFather and add it as an admin of your channel."""

from __future__ import annotations

from pathlib import Path

import requests

from .base import PublishResult, check


class TelegramPublisher:
    def __init__(self, bot_token: str, chat_id: str, session: requests.Session | None = None):
        self.api = f"https://api.telegram.org/bot{bot_token}"
        self.chat_id = chat_id
        self.session = session or requests.Session()

    def publish(self, text: str, video: Path | None = None, thumbnail: Path | None = None) -> PublishResult:
        try:
            if video:
                files = {"video": video.open("rb")}
                if thumbnail:
                    files["thumbnail"] = thumbnail.open("rb")
                try:
                    resp = self.session.post(f"{self.api}/sendVideo", timeout=600, files=files, data={
                        "chat_id": self.chat_id, "caption": text[:1024], "supports_streaming": "true"})
                finally:
                    for f in files.values():
                        f.close()
            else:
                resp = self.session.post(f"{self.api}/sendMessage", timeout=60,
                                         data={"chat_id": self.chat_id, "text": text[:4096]})
            msg = check(resp, "Telegram")["result"]
            return PublishResult("telegram", True, id=str(msg["message_id"]))
        except Exception as exc:
            return PublishResult("telegram", False, error=str(exc))
