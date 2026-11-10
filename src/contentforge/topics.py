"""Find the parts of a long video that talk about given topics, and tidy the result."""

from __future__ import annotations

from .llm import ClaudeWriter
from .models import ClipPlan, ClipSegment, TopicClip, Transcript

SYSTEM = (
    "You are a video editor who cuts long recordings into short, self-contained clips. "
    "You only use timestamps that appear in the transcript, start each part at the beginning "
    "of a sentence and end it after a complete thought, so the joined clip makes sense to a "
    "viewer who never saw the full video."
)


def plan_clips(
    writer: ClaudeWriter,
    transcript: Transcript,
    topics: list[str],
    max_clip_seconds: float = 90,
    language: str = "he",
) -> ClipPlan:
    topic_lines = "\n".join(f"- {t}" for t in topics) if topics else "- (choose the 3-5 strongest topics yourself)"
    prompt = f"""Below is a timestamped transcript of a long video (times in seconds).

Topics to extract:
{topic_lines}

For each topic, choose the parts of the video that discuss it. A topic may draw on several
separate parts from anywhere in the video; they will be joined in the order you list them.
Keep each topic's total length under {max_clip_seconds:.0f} seconds. Leave out a topic if the
video does not really cover it. Write titles in language code "{language}".

<transcript>
{transcript.to_prompt_text()}
</transcript>"""
    plan = writer.generate(SYSTEM, prompt, ClipPlan)
    duration = transcript.segments[-1].end if transcript.segments else 0.0
    return ClipPlan(clips=[c for c in (clean_clip(c, duration, max_clip_seconds) for c in plan.clips) if c.segments])


def clean_clip(clip: TopicClip, video_duration: float, max_seconds: float, min_part: float = 1.5) -> TopicClip:
    """Clamp to the video, drop tiny parts, merge overlapping ones and trim to the length budget.

    Parts keep the order Claude chose; only parts that overlap or touch are merged.
    """
    parts: list[ClipSegment] = []
    for seg in clip.segments:
        start = max(0.0, seg.start)
        end = min(seg.end, video_duration) if video_duration else seg.end
        if end - start < min_part:
            continue
        if parts and start <= parts[-1].end + 0.5 and end >= parts[-1].start:
            prev = parts[-1]
            parts[-1] = ClipSegment(start=min(prev.start, start), end=max(prev.end, end), reason=prev.reason)
            continue
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
