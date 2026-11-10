"""SEO helpers that don't need a model: slugs, hashtags, length limits, JSON-LD."""

from __future__ import annotations

import json
import re
import unicodedata

PLATFORM_LIMITS = {
    "x": 280, "threads": 500, "instagram": 2200, "tiktok": 2200, "facebook": 5000,
    "linkedin": 3000, "telegram": 1024, "youtube": 5000, "youtube_shorts": 5000,
}  # telegram: caption limit when the post carries a video
MAX_HASHTAGS = {"instagram": 30, "tiktok": 8, "x": 3, "threads": 3, "linkedin": 5, "facebook": 5,
                "youtube": 15, "youtube_shorts": 5, "telegram": 5}
YOUTUBE_TITLE_LIMIT = 100
YOUTUBE_TAGS_CHAR_LIMIT = 500


def slugify(text: str, max_len: int = 70) -> str:
    """URL slug that keeps letters of any script (Hebrew slugs stay in Hebrew)."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).replace("_", " ")
    slug = re.sub(r"[\s-]+", "-", text).strip("-")
    return slug[:max_len].rstrip("-")


def normalize_hashtag(tag: str) -> str:
    """'#Digital Marketing!' -> 'DigitalMarketing'; Hebrew letters are kept."""
    words = re.sub(r"[^\w\s]", " ", tag.lstrip("#"), flags=re.UNICODE).split()
    if len(words) > 1:  # CamelCase multi-word tags; leave single words as written
        words = [w[:1].upper() + w[1:] if w.isascii() else w for w in words]
    return "".join(words).replace("_", "")


def clean_hashtags(tags: list[str], limit: int | None = None) -> list[str]:
    seen, out = set(), []
    for t in tags:
        n = normalize_hashtag(t)
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out[:limit] if limit else out


def truncate(text: str, limit: int, ellipsis: str = "…") -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - len(ellipsis)]
    space = cut.rfind(" ")
    return (cut[:space] if space >= limit * 0.5 else cut).rstrip(" ,.;:-") + ellipsis


def compose_post(platform: str, text: str, hashtags: list[str], call_to_action: str = "", link: str = "") -> str:
    """Final post text within the platform limit: body, call to action, link, hashtags."""
    limit = PLATFORM_LIMITS.get(platform, 2200)
    tags = " ".join(f"#{h}" for h in clean_hashtags(hashtags, MAX_HASHTAGS.get(platform)))
    tail = "\n\n".join(p for p in (call_to_action.strip(), link.strip(), tags) if p)
    room = limit - len(tail) - (2 if tail else 0)
    if room < 20 and tags:  # drop hashtags before cutting the message itself
        tail = "\n\n".join(p for p in (call_to_action.strip(), link.strip()) if p)
        room = limit - len(tail) - (2 if tail else 0)
    body = truncate(text, max(room, 0))
    return f"{body}\n\n{tail}".strip() if tail else body


def youtube_tags(tags: list[str]) -> list[str]:
    out, total = [], 0
    for t in dict.fromkeys(x.strip() for x in tags if x.strip()):
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
        if total + cost > YOUTUBE_TAGS_CHAR_LIMIT:
            break
        out.append(t)
        total += cost
    return out


def keyword_report(text: str, focus_keyword: str, keywords: list[str]) -> dict:
    """Simple on-page check: where the focus keyword appears and how often each keyword is used."""
    low = text.lower()
    words = max(len(re.findall(r"\w+", low, flags=re.UNICODE)), 1)
    first_para = low.strip().split("\n\n", 1)[0]
    headings = " ".join(re.findall(r"^#{1,3}\s+(.+)$", text, flags=re.MULTILINE)).lower()
    fk = focus_keyword.lower()
    return {
        "word_count": words,
        "focus_in_first_paragraph": fk in first_para,
        "focus_in_headings": fk in headings,
        "focus_density_percent": round(100 * low.count(fk) * max(len(fk.split()), 1) / words, 2),
        "keyword_counts": {k: low.count(k.lower()) for k in keywords},
    }


def article_jsonld(title: str, description: str, url: str = "", image: str = "", author: str = "",
                   keywords: list[str] | None = None, faq: list[tuple[str, str]] | None = None) -> str:
    graph: list[dict] = [{
        "@type": "Article", "headline": title[:110], "description": description,
        **({"url": url} if url else {}), **({"image": image} if image else {}),
        **({"author": {"@type": "Person", "name": author}} if author else {}),
        **({"keywords": ", ".join(keywords)} if keywords else {}),
    }]
    if faq:
        graph.append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2)


def video_jsonld(name: str, description: str, duration_seconds: float, thumbnail_url: str = "",
                 content_url: str = "", upload_date: str = "") -> str:
    secs = int(round(duration_seconds))
    data = {
        "@context": "https://schema.org", "@type": "VideoObject", "name": name, "description": description,
        "duration": f"PT{secs // 60}M{secs % 60}S",
        **({"thumbnailUrl": thumbnail_url} if thumbnail_url else {}),
        **({"contentUrl": content_url} if content_url else {}),
        **({"uploadDate": upload_date} if upload_date else {}),
    }
    return json.dumps(data, ensure_ascii=False, indent=2)
