from contentforge.models import Transcript, TranscriptSegment
from contentforge.transcribe import parse_subtitles, remap_for_clip, to_srt

VTT = """WEBVTT

00:00:01.000 --> 00:00:03.500
<c>שלום</c> לכולם

00:00:03.500 --> 00:00:05.000
שלום לכולם

00:00:05.000 --> 00:00:07.000
שלום לכולם היום נדבר
"""


def test_parse_vtt_strips_tags_and_rolling_duplicates():
    t = parse_subtitles(VTT)
    assert [s.text for s in t.segments] == ["שלום לכולם", "היום נדבר"]
    assert t.segments[0].start == 1.0 and t.segments[0].end == 5.0


def test_srt_roundtrip():
    segs = [TranscriptSegment(start=0, end=1.25, text="a"), TranscriptSegment(start=3661.5, end=3662, text="b")]
    srt = to_srt(segs)
    assert "01:01:01,500 --> 01:01:02,000" in srt
    assert [s.text for s in parse_subtitles(srt).segments] == ["a", "b"]


def test_remap_puts_parts_back_to_back(transcript):
    out = remap_for_clip(transcript, [(10, 15), (20, 25)])
    assert [(s.start, s.end, s.text) for s in out] == [(0, 5, "טיפ ראשון על SEO"), (5, 10, "עוד על SEO ומילות מפתח")]


def test_chunks_overlap_and_cover_everything():
    t = Transcript(segments=[TranscriptSegment(start=i * 10, end=i * 10 + 10, text=str(i)) for i in range(300)])
    chunks = t.chunks(size=1200, overlap=60)
    assert len(chunks) == 3
    covered = {s.text for c in chunks for s in c.segments}
    assert covered == {str(i) for i in range(300)}
