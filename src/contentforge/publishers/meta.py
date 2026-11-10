"""Facebook Page and Instagram (Reels) through the free Meta Graph API.

You need a Page access token with pages_manage_posts (and instagram_content_publish for
Instagram, with an Instagram business/creator account linked to the Page).
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

from .base import PublishError, PublishResult, check

GRAPH_VERSION = "v21.0"


class FacebookPublisher:
    def __init__(self, page_id: str, page_token: str, session: requests.Session | None = None,
                 version: str = GRAPH_VERSION):
        self.page_id, self.token, self.version = page_id, page_token, version
        self.session = session or requests.Session()

    def publish(self, text: str, video: Path | None = None, title: str = "", link: str = "",
                published: bool = False) -> PublishResult:
        """``published=False`` keeps video posts unpublished until you approve them on the Page."""
        try:
            if video:
                with video.open("rb") as f:
                    resp = self.session.post(
                        f"https://graph-video.facebook.com/{self.version}/{self.page_id}/videos", timeout=900,
                        files={"source": f},
                        data={"access_token": self.token, "description": text, "title": title,
                              "published": str(published).lower()})
            else:
                data = {"access_token": self.token, "message": text, "published": str(published).lower()}
                if link:
                    data["link"] = link
                resp = self.session.post(f"https://graph.facebook.com/{self.version}/{self.page_id}/feed",
                                         data=data, timeout=60)
            out = check(resp, "Facebook")
            return PublishResult("facebook", True, id=str(out.get("id", "")))
        except Exception as exc:
            return PublishResult("facebook", False, error=str(exc))


class InstagramPublisher:
    """Instagram fetches the video itself, so it needs a public URL (for example the WordPress media URL)."""

    def __init__(self, ig_user_id: str, token: str, session: requests.Session | None = None,
                 version: str = GRAPH_VERSION, poll_seconds: float = 5, max_wait: float = 600):
        self.base = f"https://graph.facebook.com/{version}"
        self.user, self.token = ig_user_id, token
        self.session = session or requests.Session()
        self.poll_seconds, self.max_wait = poll_seconds, max_wait

    def publish_reel(self, video_url: str, caption: str, share_to_feed: bool = True) -> PublishResult:
        try:
            container = check(self.session.post(f"{self.base}/{self.user}/media", timeout=60, data={
                "media_type": "REELS", "video_url": video_url, "caption": caption[:2200],
                "share_to_feed": str(share_to_feed).lower(), "access_token": self.token}), "Instagram container")
            cid = container["id"]
            waited = 0.0
            while True:
                status = check(self.session.get(f"{self.base}/{cid}", timeout=30, params={
                    "fields": "status_code", "access_token": self.token}), "Instagram status").get("status_code")
                if status == "FINISHED":
                    break
                if status in ("ERROR", "EXPIRED") or waited >= self.max_wait:
                    raise PublishError(f"Instagram processing ended with status {status}")
                time.sleep(self.poll_seconds)
                waited += self.poll_seconds
            media = check(self.session.post(f"{self.base}/{self.user}/media_publish", timeout=60, data={
                "creation_id": cid, "access_token": self.token}), "Instagram publish")
            return PublishResult("instagram", True, id=str(media["id"]))
        except Exception as exc:
            return PublishResult("instagram", False, error=str(exc))
