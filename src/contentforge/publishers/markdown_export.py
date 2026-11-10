"""Write an article as Markdown with front matter for Hugo, Jekyll, Astro or GitHub Pages (free hosting)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..models import BlogArticle


def export_markdown(article: BlogArticle, out_dir: Path, video_url: str = "", image: str = "") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    seo = article.seo
    front = {
        "title": seo.title, "description": seo.meta_description, "slug": seo.slug,
        "date": date.today().isoformat(), "tags": seo.tags, "keywords": [seo.focus_keyword, *seo.keywords],
        **({"image": image} if image else {}), **({"video": video_url} if video_url else {}),
    }
    lines = ["---", *(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in front.items()), "---", "", article.markdown.strip()]
    if article.faq:
        lines += ["", "## שאלות נפוצות" if any("֐" <= c <= "׿" for c in seo.title) else "## FAQ"]
        for item in article.faq:
            lines += ["", f"### {item.question}", "", item.answer]
    path = out_dir / f"{date.today().isoformat()}-{seo.slug or 'article'}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
