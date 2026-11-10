"""Writing with the local model: SEO packages, social posts, blog articles and short-video scripts."""

from __future__ import annotations

from .models import BlogArticle, SEOPackage, SocialPost, SocialPosts, VideoScript
from .seo import MAX_HASHTAGS, PLATFORM_LIMITS, clean_hashtags, slugify, truncate
from .topics import StructuredLLM

LANG_NAMES = {"he": "Hebrew", "en": "English", "ar": "Arabic", "ru": "Russian", "es": "Spanish", "fr": "French"}


def _lang(code: str) -> str:
    return LANG_NAMES.get(code, code)


def _system(language: str) -> str:
    return (
        f"You are a senior content marketer and SEO specialist. Write natural, engaging {_lang(language)} "
        "for people, not for search engines: no keyword stuffing, no clickbait that the content doesn't "
        "deliver, no invented facts beyond the source material."
    )


def _tidy_seo(seo: SEOPackage) -> SEOPackage:
    seo.slug = slugify(seo.slug or seo.title)
    seo.meta_description = truncate(seo.meta_description, 160)
    seo.hashtags = clean_hashtags(seo.hashtags, 30)
    seo.keywords = list(dict.fromkeys(k.strip() for k in seo.keywords if k.strip()))
    return seo


def seo_package(llm: StructuredLLM, source_text: str, topic: str = "", language: str = "he",
                audience: str = "") -> SEOPackage:
    prompt = f"""Create an SEO package for the content below.
Topic: {topic or "(infer from the content)"}
Audience: {audience or "general audience"}
- title: up to 60 characters, focus keyword near the start
- alternative_titles: 3-5 options in different styles (question, number, benefit)
- meta_description: 140-160 characters with a reason to click
- slug: short, in {_lang(language)} or transliterated
- focus_keyword: the main search phrase people would type
- keywords: 8-15 secondary and long-tail phrases
- hashtags: 10-20, mixing broad and niche, without '#'
- tags: 10-15 tags for YouTube / WordPress

<content>
{source_text[:12000]}
</content>"""
    return _tidy_seo(llm.generate(_system(language), prompt, SEOPackage))


def social_posts(llm: StructuredLLM, source_text: str, platforms: list[str], seo: SEOPackage | None = None,
                 language: str = "he", link: str = "") -> list[SocialPost]:
    rules = "\n".join(
        f"- {p}: at most {PLATFORM_LIMITS.get(p, 2200) - 150} characters of text, up to {MAX_HASHTAGS.get(p, 5)} hashtags"
        for p in platforms
    )
    seo_hint = f"Focus keyword: {seo.focus_keyword}. Suggested hashtags: {', '.join(seo.hashtags[:15])}." if seo else ""
    prompt = f"""Write one post per platform for the content below, in {_lang(language)}.
Platforms and limits:
{rules}
Adapt tone and format to each platform (hook in the first line, short paragraphs, emojis only where
they fit the platform). {seo_hint} {"The post will include this link: " + link if link else ""}
Put hashtags only in the "hashtags" field, not in "text".

<content>
{source_text[:12000]}
</content>"""
    result = llm.generate(_system(language), prompt, SocialPosts)
    wanted = set(platforms)
    posts = [p for p in result.posts if p.platform in wanted]
    for p in posts:
        p.hashtags = clean_hashtags(p.hashtags, MAX_HASHTAGS.get(p.platform))
    return posts


def blog_article(llm: StructuredLLM, source_text: str, topic: str = "", language: str = "he",
                 words: int = 1200, video_url: str = "") -> BlogArticle:
    prompt = f"""Write a blog article of about {words} words in {_lang(language)} based on the material below.
Topic: {topic or "(infer from the material)"}
Structure: an opening paragraph that contains the focus keyword, H2/H3 sections, a short summary,
and 3-5 FAQ items that answer real search questions. Markdown only (no HTML).
{"Mention that the full video is available at " + video_url if video_url else ""}
Also fill the SEO package (title up to 60 characters, meta description 140-160 characters).

<material>
{source_text[:24000]}
</material>"""
    article = llm.generate(_system(language), prompt, BlogArticle)
    article.seo = _tidy_seo(article.seo)
    return article


def video_script(llm: StructuredLLM, idea: str, language: str = "he", seconds: int = 45) -> VideoScript:
    prompt = f"""Write a script for a {seconds}-second vertical video in {_lang(language)} about:
{idea}

Open with a hook in the first 3 seconds, then 4-8 scenes. Each scene has short on-screen text
(max 8 words), the narration line, and a duration; durations add up to about {seconds} seconds."""
    return llm.generate(_system(language), prompt, VideoScript)
