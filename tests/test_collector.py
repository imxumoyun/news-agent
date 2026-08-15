from datetime import datetime, timedelta, timezone

from news_agent.collector import _parse_feed
from news_agent.config import Source

NOW = datetime.now(timezone.utc)


def rss(items: str) -> bytes:
    return f"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Test feed</title>{items}</channel></rss>""".encode()


def item(title: str, link: str, when: datetime, summary: str = "") -> str:
    return f"""<item>
        <title>{title}</title>
        <link>{link}</link>
        <pubDate>{when.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
        <description>{summary}</description>
    </item>"""


def source(**kwargs) -> Source:
    return Source(
        **{"name": "Test", "url": "https://e.com/feed", "category": "media", **kwargs}
    )


class TestParseFeed:
    def test_parses_basic_entry(self):
        content = rss(item("Yangi model chiqdi", "https://e.com/a", NOW))
        articles, total = _parse_feed(source(), content, NOW - timedelta(hours=24))

        assert total == 1
        assert articles[0].title == "Yangi model chiqdi"
        assert articles[0].source == "Test"

    def test_filters_out_old_entries(self):
        content = rss(
            item("Yangi", "https://e.com/new", NOW)
            + item("Eski", "https://e.com/old", NOW - timedelta(days=5))
        )
        articles, total = _parse_feed(source(), content, NOW - timedelta(hours=24))

        assert total == 2
        assert [a.title for a in articles] == ["Yangi"]

    def test_applies_max_items_keeping_newest(self):
        content = rss(
            "".join(
                item(f"Yangilik {i}", f"https://e.com/{i}", NOW - timedelta(minutes=i * 10))
                for i in range(10)
            )
        )
        articles, _ = _parse_feed(source(max_items=3), content, NOW - timedelta(hours=24))

        assert [a.title for a in articles] == ["Yangilik 0", "Yangilik 1", "Yangilik 2"]

    def test_decodes_html_entities_and_strips_tags(self):
        content = rss(
            item("Samsung&amp;#8217;s foldable", "https://e.com/a", NOW, "<p>Matn <b>qalin</b></p>")
        )
        articles, _ = _parse_feed(source(), content, NOW - timedelta(hours=24))

        assert articles[0].title == "Samsung’s foldable"
        assert articles[0].snippet == "Matn qalin"

    def test_skips_entries_without_link(self):
        content = rss(f"<item><title>Havolasiz</title><pubDate>{NOW:%a, %d %b %Y %H:%M:%S} +0000</pubDate></item>")
        articles, _ = _parse_feed(source(), content, NOW - timedelta(hours=24))

        assert articles == []

    def test_missing_date_is_flagged_and_kept(self):
        content = rss("<item><title>Sanasiz</title><link>https://e.com/a</link></item>")
        articles, _ = _parse_feed(source(), content, NOW - timedelta(hours=24))

        assert len(articles) == 1
        assert articles[0].date_missing is True

    def test_non_feed_content_yields_nothing(self):
        articles, total = _parse_feed(source(), b"<html><body>404</body></html>", NOW)
        assert articles == []
        assert total == 0
