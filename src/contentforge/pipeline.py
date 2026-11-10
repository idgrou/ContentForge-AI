"""End to end: link -> transcript -> topic clips -> videos -> SEO and posts -> manifest -> publish."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import content, highlights, ingest, reframe, transcribe, video
from .config import Settings
from .llm import LocalLLM
from .models import ClipSegment, Manifest, RenderedClip, TopicClip, Transcript
from .publishers import (FacebookPublisher, InstagramPublisher, PublishResult, TelegramPublisher,
                         WebhookPublisher, WordPressPublisher, YouTubePublisher, export_markdown)
from .seo import compose_post, slugify
from .topics import plan_clips

log = logging.getLogger("contentforge")

DEFAULT_PLATFORMS = ["youtube_shorts", "tiktok", "instagram", "facebook", "telegram", "x", "linkedin"]


def make_llm(s: Settings) -> LocalLLM:
    return LocalLLM(model=s.llm_model, host=s.llm_host, num_ctx=s.llm_num_ctx, think=s.llm_think)


def get_source(source: str, out_dir: Path) -> tuple[Path, str, Path | None]:
    """Local file, or anything yt-dlp can download. Returns (video, title, subtitles)."""
    p = Path(source).expanduser()
    if p.is_file():
        return p, p.stem, None
    d = ingest.download(source, out_dir / "source")
    return d.path, d.title, d.subtitles_path


def get_transcript(video_path: Path, subtitles: Path | None, s: Settings, use_whisper: bool) -> Transcript:
    if subtitles and not use_whisper:
        t = transcribe.load_subtitles(subtitles)
        if t.segments:
            return t
    return transcribe.whisper_transcribe(video_path, s.whisper_model, s.language or None, s.whisper_device,
                                         cache_dir=s.output_dir / "cache")


def _highlight_clips(llm: LocalLLM, transcript: Transcript, num_clips: int, language: str) -> list[TopicClip]:
    found = highlights.find_highlights(transcript, llm.complete, num_clips=num_clips, language=language)
    return [TopicClip(topic=h["title"], title=h["title"],
                      segments=[ClipSegment(start=h["start_time"], end=h["end_time"], reason=h["virality_reason"])])
            for h in found[:num_clips]]


def render_clip(src: Path, transcript: Transcript, clip: TopicClip, out_dir: Path, vertical: bool = True,
                reframe_mode: str = "auto") -> RenderedClip:
    """reframe_mode: auto (face tracking if OpenCV is installed, else blur), face, blur, crop."""
    folder = out_dir / (slugify(clip.title) or "clip")
    folder.mkdir(parents=True, exist_ok=True)
    parts = [(s.start, s.end) for s in clip.segments]

    horizontal = video.cut_and_join(src, parts, folder / "clip.mp4")
    srt = folder / "clip.srt"
    srt.write_text(transcribe.to_srt(transcribe.remap_for_clip(transcript, parts)), encoding="utf-8")

    vertical_path = None
    if vertical:
        vertical_path = folder / "vertical.mp4"
        use_face = reframe_mode == "face" or (reframe_mode == "auto" and reframe.available())
        if use_face:
            tracked = reframe.face_track_vertical(horizontal, folder / "vertical_nosubs.mp4")
            video.burn_subtitles(tracked, srt, vertical_path)
        else:
            video.make_vertical(horizontal, vertical_path, subtitles=srt,
                                mode="crop" if reframe_mode == "crop" else "blur")
    thumb = video.thumbnail(horizontal, folder / "thumbnail.jpg", at=min(1.0, sum(e - s for s, e in parts) / 2))
    return RenderedClip(
        topic=clip.topic, video_path=str(horizontal), vertical_path=str(vertical_path) if vertical_path else None,
        thumbnail_path=str(thumb), subtitles_path=str(srt), duration=sum(e - s for s, e in parts),
        transcript_text=" ".join(transcript.text_between(s, e) for s, e in parts),
    )


def run(source: str, topics: list[str], s: Settings | None = None, platforms: list[str] | None = None,
        num_clips: int = 3, max_clip_seconds: float = 90, vertical: bool = True, reframe_mode: str = "auto",
        with_article: bool = False, use_whisper: bool = False, llm: LocalLLM | None = None) -> Manifest:
    s = s or Settings()
    llm = llm or make_llm(s)
    platforms = platforms or DEFAULT_PLATFORMS
    s.output_dir.mkdir(parents=True, exist_ok=True)

    src, title, subs = get_source(source, s.output_dir)
    log.info("source: %s", src)
    transcript = get_transcript(src, subs, s, use_whisper)
    log.info("transcript: %d segments, %.0fs", len(transcript.segments), transcript.duration)

    if topics or num_clips == 0:
        clips = plan_clips(llm, transcript, topics, max_clip_seconds, s.language).clips
    else:
        clips = _highlight_clips(llm, transcript, num_clips, s.language)
    log.info("clips planned: %d", len(clips))

    manifest = Manifest(source_url=source, source_title=title, source_path=str(src))
    for clip in clips:
        log.info("rendering: %s", clip.title)
        rc = render_clip(src, transcript, clip, s.output_dir / "clips", vertical, reframe_mode)
        rc.seo = content.seo_package(llm, rc.transcript_text, clip.topic, s.language)
        rc.posts = content.social_posts(llm, rc.transcript_text, platforms, rc.seo, s.language)
        manifest.clips.append(rc)

    if with_article:
        manifest.article = content.blog_article(llm, transcript.text_between(0, transcript.duration),
                                                ", ".join(topics), s.language,
                                                video_url=source if source.startswith("http") else "")
    save_manifest(manifest, s.output_dir / "manifest.json")
    return manifest


def save_manifest(m: Manifest, path: Path) -> Path:
    path.write_text(m.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_manifest(path: Path) -> Manifest:
    return Manifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def publish(m: Manifest, targets: list[str], s: Settings | None = None) -> list[PublishResult]:
    """targets: any of wordpress, markdown, telegram, youtube, facebook, instagram, webhook.

    Everything is created as draft / private / unpublished where the platform allows it.
    """
    s = s or Settings()
    results: list[PublishResult] = []
    wp = WordPressPublisher(s.wordpress_url, s.wordpress_user, s.wordpress_app_password) \
        if {"wordpress", "instagram"} & set(targets) and s.wordpress_url else None

    for clip in m.clips:
        vid = Path(clip.vertical_path or clip.video_path)
        posts = {p.platform: p for p in clip.posts}
        seo = clip.seo

        def text_for(platform: str) -> str:
            p = posts.get(platform)
            if p:
                return compose_post(platform, p.text, p.hashtags, p.call_to_action)
            return compose_post(platform, seo.meta_description if seo else clip.topic, seo.hashtags if seo else [])

        if "telegram" in targets:
            results.append(TelegramPublisher(s.telegram_bot_token, s.telegram_chat_id).publish(
                text_for("telegram"), vid, Path(clip.thumbnail_path) if clip.thumbnail_path else None))
        if "youtube" in targets and seo:
            p = posts.get("youtube_shorts")
            results.append(YouTubePublisher(s.youtube_client_secrets).upload(
                vid, seo.title, (p.text if p else seo.meta_description) + "\n\n" + " ".join(f"#{h}" for h in seo.hashtags[:5]),
                seo.tags, shorts=clip.vertical_path is not None, language=s.language))
        if "facebook" in targets:
            results.append(FacebookPublisher(s.meta_page_id, s.meta_page_token).publish(
                text_for("facebook"), vid, title=seo.title if seo else clip.topic))
        if "instagram" in targets:
            if wp is None:
                results.append(PublishResult("instagram", False, error="Instagram needs a public video URL: configure WordPress"))
            else:
                url = wp.upload_media(vid, title=clip.topic)["source_url"]
                results.append(InstagramPublisher(s.instagram_user_id, s.meta_page_token).publish_reel(url, text_for("instagram")))
        if "webhook" in targets:
            results.append(WebhookPublisher(s.webhook_url).publish({
                "topic": clip.topic, "video_path": str(vid), "seo": seo.model_dump() if seo else None,
                "posts": {k: text_for(k) for k in posts}}))

    a = m.article
    if a and "wordpress" in targets and wp:
        results.append(wp.publish_article(a.seo.title, a.markdown, a.seo.meta_description, a.seo.slug,
                                          tags=a.seo.tags, faq=[(f.question, f.answer) for f in a.faq],
                                          keywords=[a.seo.focus_keyword, *a.seo.keywords]))
    if a and "markdown" in targets:
        path = export_markdown(a, s.output_dir / "blog")
        results.append(PublishResult("markdown", True, url=str(path)))
    return results
