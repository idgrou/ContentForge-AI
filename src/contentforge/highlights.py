"""Find the most share-worthy single moments in a transcript (used when no topics are given).

Adapted from Anil-matcha/AI-Youtube-Shorts-Generator (MIT, see NOTICE.md): virality criteria,
content-type detection, long-video chunking and score-based dedupe. The paid MuAPI, OpenAI and
Gemini backends were removed; ``llm_fn`` is any ``prompt -> text`` callable, by default the
local Ollama model.
"""

from __future__ import annotations

from typing import Callable

from .llm import parse_json_loose
from .models import Transcript

LLMFn = Callable[[str], str]

CONTENT_TYPE_PROMPT = """Analyze this video transcript sample and classify the content type.
Choose one: podcast, interview, tutorial, lecture, commentary, debate, vlog, other.
Also estimate content density: low (mostly filler/chit-chat), medium, or high (dense info/stories).
Respond with JSON only: {"content_type": "...", "density": "..."}"""

VIRALITY_CRITERIA = """
Virality signals to prioritize (ranked by impact):
1. HOOK MOMENTS - statements that create immediate curiosity ("The secret is...", "Nobody talks about...")
2. EMOTIONAL PEAKS - genuine surprise, laughter, anger, vulnerability, excitement
3. OPINION BOMBS - strong, polarizing or counter-intuitive statements
4. REVELATION MOMENTS - surprising facts, stats, or confessions
5. CONFLICT/TENSION - disagreement, pushback, or a problem confronted head-on
6. QUOTABLE ONE-LINERS - a sentence that works as a standalone quote card
7. STORY PEAKS - the climax or twist of an anecdote
8. PRACTICAL VALUE - a concrete tip the viewer can apply immediately
"""

HIGHLIGHT_PROMPT = """You are an elite short-form video editor who knows what makes viewers stop scrolling.
{criteria}
Content type: {content_type} | Density: {density}

Identify the most viral-worthy highlights in the transcript below (times are in seconds).
Rules:
- Each highlight opens with a strong hook in its first 3 seconds
- Duration 45-90 seconds; 20-44s only for a perfect one-liner; up to 180s for a story that needs it
- Never cut mid-sentence; each clip must be self-contained
- Clips must not overlap much
- Score 0-100 on viral potential
- Return at least {min_clips} highlights
- Write "title" and "hook_sentence" in language code "{language}"

Respond ONLY with JSON:
{{"highlights":[{{"title":"string","start_time":float,"end_time":float,"score":int,"hook_sentence":"string","virality_reason":"string"}}]}}

Transcript:
{transcript}"""


def _float(v: object, default: float = -1.0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def sanitize(raw: object, duration: float) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        start, end = _float(item.get("start_time")), _float(item.get("end_time"))
        if duration > 0:
            start, end = min(start, duration), min(end, duration)
        if start < 0 or end <= start:
            continue
        out.append({
            "title": str(item.get("title") or "Untitled").strip(),
            "start_time": start,
            "end_time": end,
            "score": max(0, min(100, int(_float(item.get("score"), 0)))),
            "hook_sentence": str(item.get("hook_sentence") or "").strip(),
            "virality_reason": str(item.get("virality_reason") or "").strip(),
        })
    return out


def dedupe(highlights: list[dict]) -> list[dict]:
    """Drop a highlight that overlaps more than half of itself with a higher-scoring one."""
    kept: list[dict] = []
    for h in sorted(highlights, key=lambda x: x["score"], reverse=True):
        dur = h["end_time"] - h["start_time"]
        if not any(min(h["end_time"], k["end_time"]) - max(h["start_time"], k["start_time"]) > 0.5 * dur for k in kept):
            kept.append(h)
    return kept


def detect_content_type(transcript: Transcript, llm_fn: LLMFn) -> dict:
    sample = " ".join(s.text for s in transcript.segments[:25])[:3000]
    try:
        info = parse_json_loose(llm_fn(f"{CONTENT_TYPE_PROMPT}\n\nTranscript sample:\n{sample}"))
        return info if isinstance(info, dict) else {}
    except Exception:
        return {"content_type": "other", "density": "medium"}


def find_highlights(transcript: Transcript, llm_fn: LLMFn, num_clips: int = 3, language: str = "he",
                    attempts: int = 3) -> list[dict]:
    """Return candidates sorted by score (best first). Long videos are processed in chunks."""
    info = detect_content_type(transcript, llm_fn)
    found: list[dict] = []
    for chunk in transcript.chunks():
        span = chunk.duration - chunk.segments[0].start
        prompt = HIGHLIGHT_PROMPT.format(
            criteria=VIRALITY_CRITERIA,
            content_type=info.get("content_type", "other"),
            density=info.get("density", "medium"),
            min_clips=min(max(num_clips * 2, 5), max(2, int(span / 90)), 8),
            language=language,
            transcript=chunk.to_prompt_text(),
        )
        for _ in range(attempts):
            try:
                items = sanitize(parse_json_loose(llm_fn(prompt)).get("highlights"), transcript.duration)
            except Exception:
                items = []
            if items:
                found.extend(items)
                break
            prompt += "\n\nIMPORTANT: return ONLY valid JSON with a top-level 'highlights' array."
    return dedupe(found)
