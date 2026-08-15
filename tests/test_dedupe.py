from news_agent.dedupe import (
    canonical_url,
    dedupe_articles,
    normalize_title,
    titles_similar,
    unwrap_google_news,
    url_id,
)


class TestCanonicalUrl:
    def test_strips_tracking_params(self):
        assert canonical_url(
            "https://example.com/post?utm_source=rss&utm_medium=feed&id=7"
        ) == "https://example.com/post?id=7"

    def test_normalizes_host_scheme_and_slash(self):
        assert canonical_url("http://WWW.Example.com/post/") == "https://example.com/post"

    def test_same_article_different_tracking_gets_same_id(self):
        a = url_id("https://example.com/x?ref=twitter")
        b = url_id("https://example.com/x?fbclid=abc123")
        assert a == b

    def test_query_order_does_not_matter(self):
        assert canonical_url("https://e.com/a?b=2&a=1") == canonical_url("https://e.com/a?a=1&b=2")


class TestGoogleNews:
    def test_opaque_url_returned_unchanged(self):
        url = "https://news.google.com/rss/articles/CBMiK2h0dHBzOi8vZXhhbX?oc=5"
        # Ajratib bo'lmasa ham yiqilmasligi kerak
        assert unwrap_google_news(url).startswith("http")

    def test_non_google_url_untouched(self):
        assert unwrap_google_news("https://reuters.com/a") == "https://reuters.com/a"


class TestTitleSimilarity:
    def test_strips_source_suffix(self):
        assert normalize_title("OpenAI ships GPT-6 - Reuters") == "openai ships gpt 6"

    def test_same_story_different_source_suffix(self):
        assert titles_similar(
            "Anthropic in talks to buy Decart AI, source says - Reuters",
            "Anthropic in talks to buy Decart AI | Bloomberg",
        )

    def test_different_stories_not_similar(self):
        assert not titles_similar(
            "NVIDIA announces new datacenter GPU",
            "Apple releases iOS 27 beta to developers",
        )

    def test_truncated_title_matches_full(self):
        assert titles_similar(
            "Microsoft begins merging its consumer and commercial Copilot apps",
            "Microsoft begins merging its consumer and commercial Copilot apps into one",
        )


class TestDedupeArticles:
    def test_removes_url_duplicates(self, article_factory):
        articles = [
            article_factory("Story A", "https://e.com/a?utm_source=x"),
            article_factory("Story A", "https://e.com/a"),
        ]
        assert len(dedupe_articles(articles)) == 1

    def test_keeps_highest_weight_source(self, article_factory):
        articles = [
            article_factory("Big news today", "https://media.com/x", "Media", weight=0.6),
            article_factory("Big news today", "https://openai.com/x", "OpenAI", weight=1.0),
        ]
        result = dedupe_articles(articles)
        assert len(result) == 1
        assert result[0].source == "OpenAI"

    def test_keeps_distinct_stories(self, article_factory):
        articles = [
            article_factory("NVIDIA earnings beat estimates", "https://e.com/1"),
            article_factory("EU passes new AI regulation", "https://e.com/2"),
        ]
        assert len(dedupe_articles(articles)) == 2
