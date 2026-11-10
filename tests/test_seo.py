from contentforge import seo


def test_slugify_keeps_hebrew_and_strips_punctuation():
    assert seo.slugify("איך לבנות אתר? מדריך 2026!") == "איך-לבנות-אתר-מדריך-2026"
    assert seo.slugify("Hello,  World -- Again") == "hello-world-again"


def test_hashtags_are_normalized_and_deduplicated():
    assert seo.clean_hashtags(["#digital marketing", "DigitalMarketing", "שיווק דיגיטלי", "#SEO!"]) == [
        "DigitalMarketing", "שיווקדיגיטלי", "SEO"]
    assert len(seo.clean_hashtags([f"tag{i}" for i in range(50)], 30)) == 30


def test_compose_post_respects_platform_limit():
    long_text = "מילה " * 200
    post = seo.compose_post("x", long_text, ["one", "two", "three", "four"], "קישור בתגובה")
    assert len(post) <= 280
    assert "#one #two #three" in post and "#four" not in post
    assert post.endswith("#three")


def test_truncate_cuts_on_word_boundary():
    assert seo.truncate("one two three four", 12) == "one two…"
    assert seo.truncate("short", 10) == "short"


def test_youtube_tags_stay_under_500_chars():
    tags = seo.youtube_tags([f"keyword number {i}" for i in range(100)])
    assert sum(len(t) + 3 for t in tags) <= 520 and len(tags) < 100


def test_keyword_report_and_jsonld():
    text = "SEO מדריך\n\n## מה זה SEO\nתוכן על SEO"
    r = seo.keyword_report(text, "SEO", ["מדריך"])
    assert r["focus_in_first_paragraph"] and r["focus_in_headings"] and r["keyword_counts"]["מדריך"] == 1
    assert '"FAQPage"' in seo.article_jsonld("t", "d", faq=[("q", "a")])
    assert '"PT1M5S"' in seo.video_jsonld("n", "d", 65)
