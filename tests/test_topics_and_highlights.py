import json

from contentforge.highlights import dedupe, find_highlights, sanitize
from contentforge.models import ClipSegment, TopicClip
from contentforge.topics import clean_clip, plan_clips

from conftest import FakeLLM


def test_clean_clip_merges_overlaps_drops_tiny_and_trims():
    clip = TopicClip(topic="SEO", title="t", segments=[
        ClipSegment(start=10, end=20, reason="a"),
        ClipSegment(start=19, end=25, reason="b"),   # overlaps the first
        ClipSegment(start=40, end=40.5, reason="tiny"),
        ClipSegment(start=50, end=200, reason="long"),
    ])
    out = clean_clip(clip, video_duration=100, max_seconds=40)
    assert [(s.start, s.end) for s in out.segments] == [(10, 25), (50, 75)]


def test_plan_clips_combines_topic_parts_across_chunks_and_maps_names(transcript):
    def answer(prompt):
        return {"clips": [
            {"topic": "seo", "title": "SEO", "segments": [{"start": 10, "end": 15, "reason": "r"},
                                                        {"start": 20, "end": 25, "reason": "r"}]},
            {"topic": "unrelated", "title": "x", "segments": [{"start": 0, "end": 5, "reason": "r"}]},
        ]}
    llm = FakeLLM({"ClipPlan": answer})
    plan = plan_clips(llm, transcript, ["SEO"], max_clip_seconds=60, language="he")
    assert len(plan.clips) == 1
    assert plan.clips[0].topic == "SEO"
    assert [(s.start, s.end) for s in plan.clips[0].segments] == [(10, 15), (20, 25)]
    assert "- SEO" in llm.prompts[0] and "[10.0-15.0]" in llm.prompts[0]


def test_highlights_sanitize_dedupe_and_retry(transcript):
    good = json.dumps({"highlights": [
        {"title": "a", "start_time": 0, "end_time": 20, "score": 90},
        {"title": "b", "start_time": 2, "end_time": 18, "score": 50},   # mostly inside a
        {"title": "c", "start_time": 20, "end_time": 30, "score": 70},
        {"title": "bad", "start_time": 10, "end_time": 5, "score": 99},
    ]})
    llm = FakeLLM(raw=['{"content_type":"talk","density":"high"}', "not json", good])
    found = find_highlights(transcript, llm.complete, num_clips=2)
    assert [h["title"] for h in found] == ["a", "c"]
    assert sanitize([{"start_time": "5", "end_time": 999, "score": 150}], 30)[0] == {
        "title": "Untitled", "start_time": 5.0, "end_time": 30, "score": 100, "hook_sentence": "", "virality_reason": ""}
    assert dedupe([]) == []
