"""Find the parts of a long video that talk about given topics and merge them into one clip per topic."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

from .models import ClipPlan, ClipSegment, TopicClip, Transcript

T = TypeVar("T", bound=BaseModel)


class StructuredLLM(Protocol):
    def generate(self, system: str, prompt: str, output: type[T]) -> T: ...


SYSTEM = (
    "You are a video editor who cuts long recordings into short, self-contained clips. "
    "You only use timestamps that appear in the transcript, start each part at the beginning "
    "of a sentence and end it after a complete thought, so the joined clip makes sense to a "
    "viewer who never saw the full video."
)

PROMPT = """Below is part of a timestamped transcript of a long video (times in seconds).

Topics:
{topics}

For each topic, list the parts of this transcript that discuss it. A topic may use several
separate parts; they will be joined in the order you list them. Use each topic name exactly as
written above. Skip a topic this part does not really cover. Write titles in language "{language}".

<transcript>
{transcript}
</transcript>"""

AUTO_TOPICS = "(choose the 3-5 strongest topics of the video yourself and name them briefly)"


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def plan_clips(llm: StructuredLLM, transcript: Transcript, topics: list[str], max_clip_seconds: float = 90,
               language: str = "he", chunk_seconds: float = 1200) -> ClipPlan:
    """Ask the model chunk by chunk, then combine every topic's parts across chunks."""
    topic_lines = "\n".join(f"- {t}" for t in topics) if topics else AUTO_TOPICS
    by_topic: dict[str, TopicClip] = {}
    for chunk in transcript.chunks(size=chunk_seconds):
        plan = llm.generate(SYSTEM, PROMPT.format(topics=topic_lines, language=language,
                                                  transcript=chunk.to_prompt_text()), ClipPlan)
        for clip in plan.clips:
            # Map the model's topic name back to the requested one when it paraphrased it.
            name = next((t for t in topics if _norm(t) == _norm(clip.topic)), None) or \
                next((t for t in topics if _norm(t) in _norm(clip.topic) or _norm(clip.topic) in _norm(t)), clip.topic)
            if topics and name not in topics:
                continue
            if name in by_topic:
                by_topic[name].segments.extend(clip.segments)
            else:
                by_topic[name] = TopicClip(topic=name, title=clip.title, segments=list(clip.segments))
    cleaned = [clean_clip(c, transcript.duration, max_clip_seconds) for c in by_topic.values()]
    return ClipPlan(clips=[c for c in cleaned if c.segments])


def clean_clip(clip: TopicClip, video_duration: float, max_seconds: float, min_part: float = 1.5) -> TopicClip:
    """Clamp to the video, drop tiny parts, merge overlapping ones and trim to the length budget.

    Parts keep the order the model chose; only parts that overlap or touch are merged.
    """
    parts: list[ClipSegment] = []
    for seg in clip.segments:
        start = max(0.0, seg.start)
        end = min(seg.end, video_duration) if video_duration else seg.end
        if end - start < min_part:
            continue
        merged = False
        for i, p in enumerate(parts):
            if start <= p.end + 0.5 and end >= p.start - 0.5:
                parts[i] = ClipSegment(start=min(p.start, start), end=max(p.end, end), reason=p.reason)
                merged = True
                break
        if not merged:
            parts.append(ClipSegment(start=start, end=end, reason=seg.reason))

    kept: list[ClipSegment] = []
    total = 0.0
    for p in parts:
        room = max_seconds - total
        if room < min_part:
            break
        end = min(p.end, p.start + room)
        kept.append(ClipSegment(start=p.start, end=end, reason=p.reason))
        total += end - p.start
    return TopicClip(topic=clip.topic, title=clip.title, segments=kept)
