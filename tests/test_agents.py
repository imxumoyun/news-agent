"""Agentlar testi — haqiqiy Gemini API chaqirilmaydi, soxta klient ishlatiladi."""

import pytest

from news_agent.agents.curator import curate
from news_agent.agents.editor import edit
from news_agent.config import Profile
from news_agent.models import (
    Analysis,
    AnalyzedStory,
    CuratorOutput,
    EditedItem,
    EditorOutput,
    SelectedStory,
)


class FakeGemini:
    """Oldindan tayyorlangan javobni qaytaradi yoki xato tashlaydi."""

    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = 0

    async def structured(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


PROFILE = Profile(audience="test", max_items=5, min_items=2)


def articles(n, factory):
    return [factory(f"Yangilik {i}", f"https://e.com/{i}") for i in range(n)]


def story(index, category="Tadqiqot", score=0.8, also=None):
    return SelectedStory(
        index=index,
        also_covered=also or [],
        score=score,
        category=category,
        why_selected="muhim",
    )


class TestCurator:
    async def test_drops_out_of_range_index(self, article_factory):
        client = FakeGemini(CuratorOutput(stories=[story(0), story(99)]))
        result = await curate(client, "m", articles(3, article_factory), PROFILE)

        assert [s.index for s in result] == [0]

    async def test_drops_duplicate_index(self, article_factory):
        client = FakeGemini(CuratorOutput(stories=[story(1), story(1)]))
        result = await curate(client, "m", articles(3, article_factory), PROFILE)

        assert len(result) == 1

    async def test_unknown_category_becomes_boshqa(self, article_factory):
        client = FakeGemini(CuratorOutput(stories=[story(0, category="Sport")]))
        result = await curate(client, "m", articles(2, article_factory), PROFILE)

        assert result[0].category == "Boshqa"

    async def test_sorts_by_score(self, article_factory):
        client = FakeGemini(
            CuratorOutput(stories=[story(0, score=0.3), story(1, score=0.9), story(2, score=0.6)])
        )
        result = await curate(client, "m", articles(3, article_factory), PROFILE)

        assert [s.index for s in result] == [1, 2, 0]

    async def test_respects_max_items(self, article_factory):
        client = FakeGemini(CuratorOutput(stories=[story(i) for i in range(8)]))
        result = await curate(client, "m", articles(8, article_factory), PROFILE)

        assert len(result) == PROFILE.max_items

    async def test_cleans_invalid_also_covered(self, article_factory):
        client = FakeGemini(CuratorOutput(stories=[story(0, also=[1, 99, 0])]))
        result = await curate(client, "m", articles(3, article_factory), PROFILE)

        assert result[0].also_covered == [1]

    async def test_empty_input_skips_api_call(self, article_factory):
        client = FakeGemini(CuratorOutput(stories=[]))
        assert await curate(client, "m", [], PROFILE) == []
        assert client.calls == 0


def analyzed(n):
    return [
        AnalyzedStory(
            analysis=Analysis(
                title_uz=f"Sarlavha {i}",
                body_uz="Xulosa.\nMuhim.",
                confidence=0.9,
            ),
            url=f"https://e.com/{i}",
            source="Test",
            category="Tadqiqot",
            score=0.8,
        )
        for i in range(n)
    ]


class TestEditor:
    async def test_passes_through_valid_output(self):
        client = FakeGemini(
            EditorOutput(
                intro_uz="Kirish",
                items=[EditedItem(index=0, section="Tadqiqot", title_uz="A", text_uz="B")],
            )
        )
        result = await edit(client, "m", analyzed(2))

        assert len(result.items) == 1
        assert result.intro_uz == "Kirish"

    async def test_falls_back_when_model_fails(self):
        client = FakeGemini(error=RuntimeError("API o'lik"))
        result = await edit(client, "m", analyzed(3))

        assert len(result.items) == 3
        assert result.items[0].title_uz == "Sarlavha 0"

    async def test_falls_back_when_all_indices_invalid(self):
        client = FakeGemini(
            EditorOutput(
                intro_uz="",
                items=[EditedItem(index=42, section="Tadqiqot", title_uz="A", text_uz="B")],
            )
        )
        result = await edit(client, "m", analyzed(2))

        assert len(result.items) == 2  # zaxira variant ishladi

    async def test_empty_input_returns_empty(self):
        client = FakeGemini(EditorOutput(intro_uz="", items=[]))
        result = await edit(client, "m", [])

        assert result.items == []
        assert client.calls == 0


@pytest.mark.parametrize("bad_section", ["Sport", "", "Random"])
async def test_editor_normalizes_unknown_section(bad_section):
    client = FakeGemini(
        EditorOutput(
            intro_uz="",
            items=[EditedItem(index=0, section=bad_section, title_uz="A", text_uz="B")],
        )
    )
    result = await edit(client, "m", analyzed(1))

    assert result.items[0].section == "Boshqa"
