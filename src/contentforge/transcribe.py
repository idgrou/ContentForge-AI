"""Transcripts: parse subtitle files (VTT/SRT) or run Whisper locally, and write SRT files."""

from __future__ import annotations

import re
from pathlib import Path

from .models import Transcript, TranscriptSegment

_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_TAG = re.compile(r"<[^>]+>")


def _seconds(ts: str) -> float:
    m = _TS.search(ts)
    if not m:
        raise ValueError(f"bad timestamp: {ts!r}")
    h, mnt, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mnt) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_subtitles(text: str) -> Transcript:
    """Parse WebVTT or SRT. Removes inline tags and the rolling duplicates of YouTube auto-captions."""
    segments: list[TranscriptSegment] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [ln for ln in block.strip().split("\n") if ln.strip()]
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if idx is None:
            continue
        start_s, end_s = lines[idx].split("-->")
        body = " ".join(_TAG.sub("", ln).strip() for ln in lines[idx + 1:]).strip()
        if not body:
            continue
        if segments and body == segments[-1].text:
            segments[-1].end = _seconds(end_s)
            continue
        if segments and body.startswith(segments[-1].text):
            body = body[len(segments[-1].text):].strip() or body
        segments.append(TranscriptSegment(start=_seconds(start_s), end=_seconds(end_s), text=body))
    return Transcript(segments=segments)


def load_subtitles(path: Path) -> Transcript:
    return parse_subtitles(path.read_text(encoding="utf-8", errors="replace"))


def whisper_transcribe(video: Path, model_size: str = "medium", language: str | None = None) -> Transcript:
    """Local speech-to-text with faster-whisper (pip install 'contentforge-ai[transcribe]')."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed: pip install 'contentforge-ai[transcribe]'") from exc
    model = WhisperModel(model_size, compute_type="auto")
    segments, info = model.transcribe(str(video), language=language, vad_filter=True)
    return Transcript(
        language=info.language,
        segments=[TranscriptSegment(start=s.start, end=s.end, text=s.text.strip()) for s in segments],
    )


def _srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def to_srt(segments: list[TranscriptSegment]) -> str:
    return "\n".join(
        f"{i}\n{_srt_time(s.start)} --> {_srt_time(s.end)}\n{s.text}\n" for i, s in enumerate(segments, 1)
    )


def remap_for_clip(transcript: Transcript, parts: list[tuple[float, float]]) -> list[TranscriptSegment]:
    """Shift subtitle times onto the timeline of a clip made by joining ``parts`` in order."""
    out: list[TranscriptSegment] = []
    offset = 0.0
    for start, end in parts:
        for s in transcript.segments:
            if s.end <= start or s.start >= end:
                continue
            out.append(TranscriptSegment(
                start=max(s.start, start) - start + offset,
                end=min(s.end, end) - start + offset,
                text=s.text,
            ))
        offset += end - start
    return out
