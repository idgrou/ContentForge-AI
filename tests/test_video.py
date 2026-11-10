import json
import subprocess
from pathlib import Path

from contentforge import video
from contentforge.models import ClipSegment, TopicClip
from contentforge.pipeline import render_clip


def test_cut_and_join_cmd_builds_concat_graph():
    cmd = video.cut_and_join_cmd(Path("in.mp4"), [(1, 2), (5, 7.5)], Path("out.mp4"))
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "trim=start=1.000:end=2.000" in graph and "atrim=start=5.000:end=7.500" in graph
    assert graph.endswith("concat=n=2:v=1:a=1[v][a]")


def test_vertical_cmd_escapes_subtitle_path():
    cmd = video.vertical_cmd(Path("in.mp4"), Path("o.mp4"), Path("C:/x/it's.srt"), mode="crop")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert r"C\:/x/it\'s.srt" in graph and "crop=1080:1920" in graph


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_render_clip_end_to_end(sample_video, transcript, tmp_path):
    clip = TopicClip(topic="SEO", title="SEO tips", segments=[ClipSegment(start=10, end=15, reason=""),
                                                             ClipSegment(start=20, end=25, reason="")])
    rc = render_clip(sample_video, transcript, clip, tmp_path / "out", vertical=True, reframe_mode="blur")
    info = _probe(Path(rc.video_path))
    assert abs(float(info["format"]["duration"]) - 10) < 0.3
    assert {s["codec_type"] for s in info["streams"]} == {"video", "audio"}
    v = next(s for s in _probe(Path(rc.vertical_path))["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert Path(rc.thumbnail_path).stat().st_size > 0
    assert "עוד על SEO" in Path(rc.subtitles_path).read_text(encoding="utf-8")
    assert rc.duration == 10


def test_render_text_video(tmp_path):
    out = video.render_text_video([("Hello", 1.0), ("World", 1.5)], tmp_path / "v.mp4", tmp_path / "w")
    assert abs(float(_probe(out)["format"]["duration"]) - 2.5) < 0.3
