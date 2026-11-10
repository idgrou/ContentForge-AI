"""Download a video (YouTube, Vimeo, Facebook, TikTok and ~1000 other sites) with yt-dlp."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DownloadedVideo:
    path: Path
    title: str
    duration: float | None
    subtitles_path: Path | None
    info: dict


def download(url: str, out_dir: Path, sub_langs: tuple[str, ...] = ("he", "iw", "en")) -> DownloadedVideo:
    """Download the video as MP4 plus any available subtitles (manual or auto) as VTT.

    Only download content you own or have the rights to reuse.
    """
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": list(sub_langs),
        "subtitlesformat": "vtt",
        "quiet": True,
        "noprogress": True,
    }
    cookies = os.environ.get("YTDLP_COOKIES", "").strip()
    if cookies and os.path.isfile(cookies):  # exported browser cookies, for sites that block servers
        opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")

    subtitles = sorted(out_dir.glob(f"{info['id']}*.vtt"))
    preferred = next((s for lang in sub_langs for s in subtitles if f".{lang}" in s.name), None)
    return DownloadedVideo(
        path=video_path,
        title=info.get("title") or video_path.stem,
        duration=info.get("duration"),
        subtitles_path=preferred or (subtitles[0] if subtitles else None),
        info={k: info.get(k) for k in ("id", "title", "uploader", "webpage_url", "duration", "description")},
    )
