import json
import shutil
import subprocess
from pathlib import Path

import pytest

from contentforge.models import Transcript, TranscriptSegment


class FakeLLM:
    """Stands in for LocalLLM: returns canned objects per output model, records prompts."""

    def __init__(self, answers: dict | None = None, raw: list[str] | None = None):
        self.answers = answers or {}
        self.raw = list(raw or [])
        self.prompts: list[str] = []

    def generate(self, system, prompt, output):
        self.prompts.append(prompt)
        value = self.answers[output.__name__]
        value = value(prompt) if callable(value) else value
        return output.model_validate(value)

    def complete(self, prompt, json_mode=True):
        self.prompts.append(prompt)
        return self.raw.pop(0) if self.raw else json.dumps({"content_type": "talk", "density": "high"})


@pytest.fixture
def transcript():
    lines = ["שלום וברוכים הבאים", "היום נדבר על שיווק", "טיפ ראשון על SEO", "עכשיו על וידאו קצר",
             "עוד על SEO ומילות מפתח", "סיכום ותודה"]
    return Transcript(segments=[TranscriptSegment(start=i * 5.0, end=i * 5.0 + 5.0, text=t) for i, t in enumerate(lines)])


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    out = tmp_path / "sample.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=30",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=30", "-shortest", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
    return out
