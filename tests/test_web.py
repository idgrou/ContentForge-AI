import importlib
import time

import pytest
from fastapi.testclient import TestClient

from contentforge.models import Manifest, RenderedClip, SEOPackage, SocialPost


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENTFORGE_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("APP_PASSWORD", "secret-pass")
    import contentforge.web as web
    web = importlib.reload(web)
    monkeypatch.setattr(web, "ensure_model", lambda: None)

    def fake_run(source, topics, s, *args, **kwargs):
        clip_dir = s.output_dir / "clips" / "seo"
        clip_dir.mkdir(parents=True)
        (clip_dir / "vertical.mp4").write_bytes(b"video")
        m = Manifest(source_url=source, source_path=source, clips=[RenderedClip(
            topic="SEO", video_path=str(clip_dir / "vertical.mp4"), vertical_path=str(clip_dir / "vertical.mp4"),
            duration=10, transcript_text="t",
            seo=SEOPackage(title="כותרת", alternative_titles=["b"], meta_description="תיאור", slug="s",
                           focus_keyword="SEO", keywords=["k"], hashtags=["SEO"], tags=["t"]),
            posts=[SocialPost(platform="x", text="פוסט", hashtags=["SEO"], call_to_action="")])])
        (s.output_dir / "manifest.json").write_text(m.model_dump_json(), encoding="utf-8")
        return m

    monkeypatch.setattr(web.pipeline, "run", fake_run)
    with TestClient(web.app) as client:
        yield web, client


AUTH = ("admin", "secret-pass")


def test_requires_password(web):
    _, client = web
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("admin", "wrong")).status_code == 401
    assert client.get("/healthz").json() == {"ok": True}


def test_job_runs_and_shows_results(web):
    mod, client = web
    r = client.post("/jobs", auth=AUTH, data={"source": "https://example.com/v", "topics": "SEO\n\nוידאו",
                                              "platforms": ["x"], "article": "1"}, follow_redirects=False)
    assert r.status_code == 303
    job_id = r.headers["location"].rsplit("/", 1)[1]
    for _ in range(50):
        if mod.read_job(job_id)["status"] == "done":
            break
        time.sleep(0.05)
    job = mod.read_job(job_id)
    assert job["status"] == "done" and job["params"]["topics"] == ["SEO", "וידאו"] and job["params"]["article"]
    html = client.get(f"/jobs/{job_id}", auth=AUTH).text
    assert "כותרת" in html and "#SEO" in html and f"/files/{job_id}/output/clips/seo/vertical.mp4" in html
    assert client.get(f"/files/{job_id}/output/clips/seo/vertical.mp4", auth=AUTH).content == b"video"
    assert client.get(f"/files/{job_id}/../../etc/passwd", auth=AUTH).status_code == 404
    assert job_id in client.get("/", auth=AUTH).text


def test_upload_and_validation(web):
    mod, client = web
    assert client.post("/jobs", auth=AUTH, data={"source": ""}).status_code == 400
    r = client.post("/jobs", auth=AUTH, data={"source": ""}, files={"upload": ("my video.mp4", b"abc", "video/mp4")},
                    follow_redirects=False)
    job = mod.read_job(r.headers["location"].rsplit("/", 1)[1])
    assert job["params"]["source"].endswith("upload/my_video.mp4")
    assert client.get("/jobs/notreal!", auth=AUTH).status_code == 404
