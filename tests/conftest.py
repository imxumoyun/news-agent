from datetime import datetime, timezone

import pytest

from news_agent.models import Article


def make_article(
    title: str,
    url: str,
    source: str = "Test",
    weight: float = 0.7,
    minutes_ago: int = 0,
) -> Article:
    from news_agent.dedupe import canonical_url, url_id

    return Article(
        id=url_id(url),
        title=title,
        url=canonical_url(url),
        source=source,
        source_category="media",
        weight=weight,
        published_at=datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
        snippet="test snippet",
    )


@pytest.fixture
def article_factory():
    return make_article
