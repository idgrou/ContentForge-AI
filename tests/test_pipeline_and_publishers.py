import json
from pathlib import Path

from contentforge import pipeline
from contentforge.config import Settings
from contentforge.models import BlogArticle
from contentforge.publishers import TelegramPublisher, WordPressPublisher, export_markdown

from conftest import FakeLLM

SEO = {"title": "טיפים ל-SEO", "alternative_titles": ["a"], "meta_description": "x" * 200, "slug": "SEO Tips!",
       "focus_keyword": "SEO", "keywords": ["seo", "seo", "מילות מפתח"], "hashtags": ["#SEO", "seo", "שיווק"],
       "tags": ["seo"]}


def fake_llm():
    return FakeLLM({
        "ClipPlan": {"clips": [{"topic": "SEO", "title": "SEO", "segments": [
            {"start": 10, "end": 15, "reason": ""}, {"start": 20, "end": 25, "reason": ""}]}]},
        "SEOPackage": SEO,
        "SocialPosts": {"posts": [
            {"platform": "x", "text": "פוסט", "hashtags": ["a", "b", "c", "d"], "call_to_action": "צפו"},
            {"platform": "telegram", "text": "טלגרם", "hashtags": ["a"], "call_to_action": ""},
            {"platform": "linkedin", "text": "not requested", "hashtags": [], "call_to_action": ""}]},
        "BlogArticle": {"seo": SEO, "markdown": "## כותרת\nתוכן", "excerpt": "e",
                        "faq": [{"question": "מה?", "answer": "זה."}]},
    })


def test_run_pipeline_with_fake_llm(sample_video, transcript, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "get_transcript", lambda *a, **k: transcript)
    s = Settings(output_dir=tmp_path / "out", language="he")
    m = pipeline.run(str(sample_video), ["SEO"], s, platforms=["x", "telegram"], vertical=False,
                     with_article=True, llm=fake_llm())
    clip = m.clips[0]
    assert clip.duration == 10 and Path(clip.video_path).exists()
    assert clip.seo.slug == "seo-tips" and len(clip.seo.meta_description) <= 160
    assert clip.seo.hashtags == ["SEO", "שיווק"] and clip.seo.keywords == ["seo", "מילות מפתח"]
    assert [p.platform for p in clip.posts] == ["x", "telegram"] and clip.posts[0].hashtags == ["a", "b", "c"]
    assert m.article and pipeline.load_manifest(s.output_dir / "manifest.json").clips[0].topic == "SEO"

    results = pipeline.publish(m, ["markdown"], s)
    md = Path(results[0].url).read_text(encoding="utf-8")
    assert results[0].ok and 'title: "טיפים ל-SEO"' in md and "## שאלות נפוצות" in md


class Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data


class Session:
    def __init__(self, routes):
        self.routes, self.calls, self.auth = routes, [], None

    def _hit(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for key, value in self.routes.items():
            if key in url:
                return value(kw) if callable(value) else value
        return Resp({"error": "no route"}, 404)

    def post(self, url, **kw):
        return self._hit("POST", url, **kw)

    def get(self, url, **kw):
        return self._hit("GET", url, **kw)


def test_wordpress_creates_draft_with_tags_and_jsonld():
    s = Session({"/tags": lambda kw: Resp([] if "params" in kw else {"id": 7}),
                 "/posts": Resp({"id": 42, "link": "https://site/p/42"})})
    r = WordPressPublisher("https://site", "u", "p", session=s).publish_article(
        "כותרת", "## חלק\nטקסט", excerpt="תיאור", slug="slug", tags=["seo"], faq=[("q", "a")])
    assert r.ok and r.id == "42"
    body = s.calls[-1][2]["json"]
    assert body["status"] == "draft" and body["tags"] == [7] and "<h2>חלק</h2>" in body["content"]
    assert "application/ld+json" in body["content"] and s.auth == ("u", "p")


def test_telegram_reports_errors_instead_of_raising():
    s = Session({"sendMessage": Resp({"ok": False, "description": "chat not found"}, 400)})
    r = TelegramPublisher("t", "c", session=s).publish("hi")
    assert not r.ok and "chat not found" in r.error


def test_markdown_export_front_matter(tmp_path):
    art = BlogArticle.model_validate({"seo": {**SEO, "title": "English title", "slug": "english"},
                                      "markdown": "Body", "excerpt": "", "faq": []})
    text = export_markdown(art, tmp_path).read_text(encoding="utf-8")
    assert text.startswith("---\ntitle: \"English title\"") and text.rstrip().endswith("Body")
