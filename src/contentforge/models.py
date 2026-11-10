"""Data models shared by every stage of the pipeline.

Models that Claude fills in (structured outputs) forbid extra fields so their JSON
schema carries ``additionalProperties: false``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["youtube", "youtube_shorts", "tiktok", "instagram", "facebook", "x", "linkedin", "telegram", "threads"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- transcript -----------------------------------------------------------------

class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    language: str | None = None
    segments: list[TranscriptSegment]

    def to_prompt_text(self) -> str:
        """Timestamped lines, compact enough to send a long video to Claude."""
        return "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.text.strip()}" for s in self.segments)

    def text_between(self, start: float, end: float) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.end > start and s.start < end)


# --- topic clips (Claude output) -----------------------------------------------

class ClipSegment(_Strict):
    start: float = Field(description="Start time in seconds, taken from the transcript timestamps")
    end: float = Field(description="End time in seconds")
    reason: str = Field(description="Why this part belongs to the topic")


class TopicClip(_Strict):
    topic: str
    title: str = Field(description="Working title for the merged clip")
    segments: list[ClipSegment]


class ClipPlan(_Strict):
    clips: list[TopicClip]


# --- SEO and posts (Claude output) ---------------------------------------------

class SEOPackage(_Strict):
    title: str = Field(description="Main SEO title, about 50-60 characters")
    alternative_titles: list[str] = Field(description="3-5 alternative titles for A/B testing")
    meta_description: str = Field(description="Meta description, about 140-160 characters")
    slug: str
    focus_keyword: str
    keywords: list[str] = Field(description="Secondary and long-tail keywords")
    hashtags: list[str] = Field(description="Hashtags without the # sign")
    tags: list[str] = Field(description="Tags for YouTube / WordPress")


class SocialPost(_Strict):
    platform: Platform
    text: str = Field(description="Post body, within the platform's length limit, hashtags not included")
    hashtags: list[str] = Field(description="Hashtags for this platform, without the # sign")
    call_to_action: str


class SocialPosts(_Strict):
    posts: list[SocialPost]


class FAQItem(_Strict):
    question: str
    answer: str


class BlogArticle(_Strict):
    seo: SEOPackage
    markdown: str = Field(description="Full article in Markdown with H2/H3 headings")
    excerpt: str
    faq: list[FAQItem]


class VideoScene(_Strict):
    text: str = Field(description="On-screen text for the scene, one short sentence")
    narration: str = Field(description="What a voice-over would say")
    duration: float = Field(description="Scene length in seconds")


class VideoScript(_Strict):
    title: str
    hook: str
    scenes: list[VideoScene]


# --- pipeline manifest ---------------------------------------------------------

class RenderedClip(BaseModel):
    topic: str
    video_path: str
    vertical_path: str | None = None
    thumbnail_path: str | None = None
    subtitles_path: str | None = None
    duration: float
    transcript_text: str
    seo: SEOPackage | None = None
    posts: list[SocialPost] = []


class Manifest(BaseModel):
    source_url: str
    source_title: str | None = None
    source_path: str
    clips: list[RenderedClip] = []
    article: BlogArticle | None = None
