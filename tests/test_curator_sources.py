"""Agregator o'rniga asl manbani tanlash mantiqi."""

from datetime import datetime, timezone

from news_agent.agents.curator import _valid_stories
from news_agent.models import Article, SelectedStory


def article(source: str, category: str, weight: float) -> Article:
    return Article(
        id=source,
        title=f"{source} sarlavhasi",
        url=f"https://{source.lower()}.com/a",
        source=source,
        source_category=category,
        weight=weight,
        published_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )


def story(index: int, also: list[int]) -> SelectedStory:
    return SelectedStory(
        index=index, also_covered=also, score=0.9, category="Tadqiqot", why_selected="muhim"
    )


class TestPreferOriginalSource:
    def test_swaps_aggregator_for_original(self):
        articles = [
            article("Techmeme", "aggregator", 0.85),
            article("TechCrunch", "media", 0.75),
        ]
        result = _valid_stories([story(0, [1])], articles)

        assert result[0].index == 1              # asl manba asosiy bo'ldi
        assert result[0].also_covered == [0]     # agregator ikkinchi darajaga tushdi

    def test_picks_highest_weight_original(self):
        articles = [
            article("Techmeme", "aggregator", 0.85),
            article("Wired", "media", 0.7),
            article("OpenAI", "primary", 1.0),
        ]
        result = _valid_stories([story(0, [1, 2])], articles)

        assert result[0].index == 2
        assert set(result[0].also_covered) == {0, 1}

    def test_keeps_aggregator_when_no_original(self):
        articles = [
            article("Techmeme", "aggregator", 0.85),
            article("HackerNews", "aggregator", 0.8),
        ]
        result = _valid_stories([story(0, [1])], articles)

        assert result[0].index == 0

    def test_leaves_non_aggregator_primary_alone(self):
        articles = [
            article("Reuters", "business", 0.85),
            article("Techmeme", "aggregator", 0.85),
        ]
        result = _valid_stories([story(0, [1])], articles)

        assert result[0].index == 0
        assert result[0].also_covered == [1]

    def test_swap_does_not_create_duplicate_primary(self):
        """Ikki voqea bir xil asl manbaga ko'rsatsa, ikkinchisi tushib qolishi kerak."""
        articles = [
            article("Techmeme", "aggregator", 0.85),
            article("TechCrunch", "media", 0.75),
            article("HackerNews", "aggregator", 0.8),
        ]
        result = _valid_stories([story(0, [1]), story(2, [1])], articles)

        assert len(result) == 1
        assert result[0].index == 1
