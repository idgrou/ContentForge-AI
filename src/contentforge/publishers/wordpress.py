"""WordPress REST API with an Application Password (Users > Profile > Application Passwords)."""

from __future__ import annotations

import mimetypes
from pathlib import Path

import requests

from ..seo import article_jsonld
from .base import PublishResult, check


def markdown_to_html(md: str) -> str:
    try:
        import markdown
    except ImportError:  # minimal fallback: paragraphs and headings
        import html
        import re
        out = []
        for block in md.strip().split("\n\n"):
            m = re.match(r"^(#{1,6})\s+(.*)", block)
            out.append(f"<h{len(m.group(1))}>{html.escape(m.group(2))}</h{len(m.group(1))}>" if m
                       else f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>")
        return "\n".join(out)
    return markdown.markdown(md, extensions=["extra", "sane_lists"])


class WordPressPublisher:
    def __init__(self, site_url: str, user: str, app_password: str, session: requests.Session | None = None):
        self.api = site_url.rstrip("/") + "/wp-json/wp/v2"
        self.session = session or requests.Session()
        self.session.auth = (user, app_password)

    def upload_media(self, path: Path, title: str = "", alt_text: str = "") -> dict:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as f:
            resp = self.session.post(f"{self.api}/media", data=f, timeout=600, headers={
                "Content-Type": mime,
                "Content-Disposition": f'attachment; filename="{path.name}"',
            })
        media = check(resp, "WordPress media upload")
        if title or alt_text:
            self.session.post(f"{self.api}/media/{media['id']}", json={"title": title, "alt_text": alt_text}, timeout=60)
        return media

    def _term_ids(self, taxonomy: str, names: list[str]) -> list[int]:
        ids = []
        for name in names:
            found = check(self.session.get(f"{self.api}/{taxonomy}", params={"search": name}, timeout=30), "term lookup")
            match = next((t for t in found if t.get("name", "").lower() == name.lower()), None)
            if match is None:
                match = check(self.session.post(f"{self.api}/{taxonomy}", json={"name": name}, timeout=30), "term create")
            ids.append(match["id"])
        return ids

    def publish_article(self, title: str, markdown_body: str, excerpt: str = "", slug: str = "",
                        tags: list[str] | None = None, categories: list[str] | None = None,
                        featured_image: Path | None = None, video: Path | None = None,
                        faq: list[tuple[str, str]] | None = None, keywords: list[str] | None = None,
                        status: str = "draft") -> PublishResult:
        """Create a post. ``status="draft"`` by default so you can review before it goes live."""
        try:
            html = markdown_to_html(markdown_body)
            media_id = None
            if featured_image:
                media_id = self.upload_media(featured_image, title=title, alt_text=title)["id"]
            if video:
                v = self.upload_media(video, title=title)
                html = f'<figure class="wp-block-video"><video controls src="{v["source_url"]}"></video></figure>\n' + html
            html += f'\n<script type="application/ld+json">{article_jsonld(title, excerpt, keywords=keywords, faq=faq)}</script>'
            body = {"title": title, "content": html, "excerpt": excerpt, "status": status}
            if slug:
                body["slug"] = slug
            if tags:
                body["tags"] = self._term_ids("tags", tags)
            if categories:
                body["categories"] = self._term_ids("categories", categories)
            if media_id:
                body["featured_media"] = media_id
            post = check(self.session.post(f"{self.api}/posts", json=body, timeout=120), "WordPress post")
            return PublishResult("wordpress", True, id=str(post["id"]), url=post.get("link", ""))
        except Exception as exc:
            return PublishResult("wordpress", False, error=str(exc))
