"""Settings read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, without overriding variables already set."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    model: str = field(default_factory=lambda: _env("CONTENTFORGE_MODEL", "claude-opus-5-5"))
    language: str = field(default_factory=lambda: _env("CONTENTFORGE_LANGUAGE", "he"))
    output_dir: Path = field(default_factory=lambda: Path(_env("CONTENTFORGE_OUTPUT", "output")))

    wordpress_url: str = field(default_factory=lambda: _env("WORDPRESS_URL"))
    wordpress_user: str = field(default_factory=lambda: _env("WORDPRESS_USER"))
    wordpress_app_password: str = field(default_factory=lambda: _env("WORDPRESS_APP_PASSWORD"))

    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))

    meta_page_id: str = field(default_factory=lambda: _env("META_PAGE_ID"))
    meta_page_token: str = field(default_factory=lambda: _env("META_PAGE_TOKEN"))
    instagram_user_id: str = field(default_factory=lambda: _env("INSTAGRAM_USER_ID"))

    youtube_client_secrets: str = field(default_factory=lambda: _env("YOUTUBE_CLIENT_SECRETS", "client_secret.json"))

    webhook_url: str = field(default_factory=lambda: _env("WEBHOOK_URL"))
