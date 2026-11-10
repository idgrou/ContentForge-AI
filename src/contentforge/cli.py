"""Command line: contentforge clips | article | script | publish | doctor"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

import typer

from . import content, pipeline, video
from .config import Settings, load_dotenv
from .models import Manifest

app = typer.Typer(add_completion=False, help="Clips, posts and articles from long videos, with a local AI model.")


def _settings(output: Optional[Path], language: Optional[str]) -> Settings:
    load_dotenv()
    s = Settings()
    if output:
        s.output_dir = output
    if language:
        s.language = language
    return s


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@app.command()
def clips(
    source: str = typer.Argument(..., help="Video link (YouTube, Vimeo, Facebook...) or a local file"),
    topic: list[str] = typer.Option([], "--topic", "-t", help="Topic to extract; repeat for several. Omit for best moments"),
    num_clips: int = typer.Option(3, help="How many best-moment clips when no topic is given"),
    max_seconds: float = typer.Option(90, help="Maximum length of each merged clip"),
    platforms: str = typer.Option(",".join(pipeline.DEFAULT_PLATFORMS), help="Platforms to write posts for"),
    reframe: str = typer.Option("auto", help="Vertical framing: auto, face, blur, crop"),
    no_vertical: bool = typer.Option(False, help="Skip the 9:16 version"),
    article: bool = typer.Option(False, help="Also write a blog article from the whole video"),
    whisper: bool = typer.Option(False, help="Transcribe with Whisper even if the site has subtitles"),
    language: Optional[str] = typer.Option(None, help="Content language code, e.g. he or en"),
    output: Optional[Path] = typer.Option(None, help="Output folder"),
    verbose: bool = typer.Option(True),
):
    """Cut a long video into clips (by topic or best moments) and write SEO + posts for each."""
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(message)s")
    s = _settings(output, language)
    m = pipeline.run(source, topic, s, _split(platforms), num_clips, max_seconds, not no_vertical, reframe,
                     article, whisper)
    for c in m.clips:
        typer.echo(f"\n■ {c.topic}  ({c.duration:.0f}s)\n  {c.vertical_path or c.video_path}")
        if c.seo:
            typer.echo(f"  title: {c.seo.title}\n  hashtags: {' '.join('#' + h for h in c.seo.hashtags[:10])}")
    typer.echo(f"\nmanifest: {s.output_dir / 'manifest.json'}")


@app.command()
def article(
    source: str = typer.Argument(..., help="Video link, local video, or a .txt/.md file with source text"),
    topic: str = typer.Option("", help="Article topic / focus"),
    words: int = typer.Option(1200),
    language: Optional[str] = typer.Option(None),
    output: Optional[Path] = typer.Option(None),
):
    """Write an SEO blog article (Markdown with front matter) from a video or a text file."""
    s = _settings(output, language)
    llm = pipeline.make_llm(s)
    p = Path(source)
    if p.suffix.lower() in (".txt", ".md") and p.is_file():
        text, link = p.read_text(encoding="utf-8"), ""
    else:
        src, _, subs = pipeline.get_source(source, s.output_dir)
        t = pipeline.get_transcript(src, subs, s, use_whisper=False)
        text, link = t.text_between(0, t.duration), source if source.startswith("http") else ""
    art = content.blog_article(llm, text, topic, s.language, words, link)
    m = Manifest(source_url=source, source_path=source, article=art)
    pipeline.save_manifest(m, s.output_dir / "manifest.json")
    path = pipeline.export_markdown(art, s.output_dir / "blog")
    typer.echo(f"{art.seo.title}\n{path}")


@app.command()
def script(
    idea: str = typer.Argument(..., help="What the video is about"),
    seconds: int = typer.Option(45),
    render: bool = typer.Option(True, help="Render a text-on-screen 9:16 video from the script"),
    font: Optional[Path] = typer.Option(None, help="TTF font (needed for Hebrew glyphs)"),
    language: Optional[str] = typer.Option(None),
    output: Optional[Path] = typer.Option(None),
):
    """Write a short-video script and optionally render it as a text video."""
    s = _settings(output, language)
    sc = content.video_script(pipeline.make_llm(s), idea, s.language, seconds)
    folder = s.output_dir / "scripts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "script.json").write_text(sc.model_dump_json(indent=2), encoding="utf-8")
    typer.echo(f"{sc.title}\nhook: {sc.hook}")
    for i, scene in enumerate(sc.scenes, 1):
        typer.echo(f"{i}. [{scene.duration:.0f}s] {scene.text} — {scene.narration}")
    if render:
        out = video.render_text_video([(sc.hook, 3.0)] + [(x.text, x.duration) for x in sc.scenes],
                                      folder / "video.mp4", folder / "scenes", font)
        typer.echo(f"video: {out}")


@app.command()
def publish(
    manifest: Path = typer.Argument(..., help="manifest.json from `clips` or `article`"),
    to: str = typer.Option("markdown", help="Comma list: wordpress, markdown, telegram, youtube, facebook, instagram, webhook"),
    output: Optional[Path] = typer.Option(None),
):
    """Publish a manifest. Posts are created as drafts / private where the platform supports it."""
    s = _settings(output, None)
    m = pipeline.load_manifest(manifest)
    for r in pipeline.publish(m, _split(to), s):
        typer.echo(f"{'✓' if r.ok else '✗'} {r.platform} {r.url or r.id} {r.error}")


@app.command()
def doctor():
    """Check that FFmpeg, Ollama, Whisper and OpenCV are available."""
    load_dotenv()
    s = Settings()
    import requests
    typer.echo(f"ffmpeg:  {'ok' if shutil.which('ffmpeg') else 'MISSING (install ffmpeg)'}")
    try:
        tags = requests.get(f"{s.llm_host}/api/tags", timeout=5).json().get("models", [])
        names = [t["name"] for t in tags]
        state = "ok" if any(n.startswith(s.llm_model) for n in names) else f"model missing: ollama pull {s.llm_model}"
        typer.echo(f"ollama:  {state} (installed: {', '.join(names) or 'none'})")
    except Exception:
        typer.echo(f"ollama:  not reachable at {s.llm_host} (install from ollama.com, then `ollama serve`)")
    for mod, extra in (("faster_whisper", "transcribe"), ("cv2", "facetrack"), ("googleapiclient", "youtube")):
        try:
            __import__(mod)
            typer.echo(f"{mod}: ok")
        except ImportError:
            typer.echo(f"{mod}: not installed (pip install 'contentforge-ai[{extra}]')")


if __name__ == "__main__":
    app()
