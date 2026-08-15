from datetime import datetime

from news_agent import telegram
from news_agent.models import (
    Analysis,
    AnalyzedStory,
    EditedItem,
    EditorOutput,
)
from news_agent.telegram import TASHKENT, format_date_uz, render, to_markdown, visible_length


def make_story(title="Sarlavha", url="https://example.com/a", source="Test", section="Tadqiqot"):
    return AnalyzedStory(
        analysis=Analysis(
            title_uz=title, body_uz="Xulosa matni.\nMuhim.", confidence=0.9
        ),
        url=url,
        source=source,
        category=section,
        score=0.8,
    )


def make_edited(count, section="Tadqiqot", text="Matn."):
    return EditorOutput(
        intro_uz="Bugun asosiy mavzu — modellar.",
        items=[
            EditedItem(index=i, section=section, title_uz=f"Sarlavha {i}", text_uz=text)
            for i in range(count)
        ],
    )


class TestRender:
    def test_single_message_for_small_digest(self):
        stories = [make_story() for _ in range(3)]
        messages = render(make_edited(3), stories)
        assert len(messages) == 1
        assert "AI va Tech" in messages[0]
        assert "Bugun asosiy mavzu" in messages[0]

    def test_escapes_html_in_model_output(self):
        stories = [make_story(url="https://e.com/a")]
        edited = EditorOutput(
            intro_uz="",
            items=[
                EditedItem(
                    index=0,
                    section="Tadqiqot",
                    title_uz="<script>alert(1)</script> & Co",
                    text_uz="a < b > c",
                )
            ],
        )
        message = render(edited, stories)[0]
        assert "<script>" not in message
        assert "&lt;script&gt;" in message
        assert "&amp; Co" in message

    def test_no_section_headers_rendered(self):
        """Bo'lim nomlari postda ko'rinmaydi — ular faqat tartib uchun."""
        stories = [make_story() for _ in range(3)]
        message = render(make_edited(3), stories)[0]

        assert "Tadqiqot" not in message

    def test_same_section_items_end_up_adjacent(self):
        """Editor tartibi aralash bo'lsa ham bir mavzudagi yangiliklar yonma-yon turadi."""
        stories = [make_story() for _ in range(3)]
        edited = EditorOutput(
            intro_uz="",
            items=[
                EditedItem(index=0, section="Tadqiqot", title_uz="A", text_uz="a"),
                EditedItem(index=1, section="Biznes va investitsiya", title_uz="B", text_uz="b"),
                EditedItem(index=2, section="Tadqiqot", title_uz="C", text_uz="c"),
            ],
        )
        message = render(edited, stories)[0]

        assert message.index("<b>A</b>") < message.index("<b>C</b>") < message.index("<b>B</b>")

    def test_post_ends_with_source_link_not_summary(self):
        """Post umumlashtiruvchi jumla bilan emas, oxirgi manba havolasi bilan tugaydi."""
        stories = [make_story(url="https://reuters.com/x", source="Reuters")]
        message = render(make_edited(1), stories)[0]

        assert message.rstrip().endswith('<a href="https://reuters.com/x">Reuters</a>')

    def test_splits_when_over_limit(self):
        long_text = "Juda uzun matn. " * 40  # ~640 belgi
        stories = [make_story() for _ in range(10)]
        messages = render(make_edited(10, text=long_text), stories)
        assert len(messages) > 1
        assert all(visible_length(m) <= telegram.MAX_MESSAGE_CHARS for m in messages)

    def test_source_link_present(self):
        stories = [make_story(url="https://reuters.com/x", source="Reuters")]
        message = render(make_edited(1), stories)[0]
        assert '<a href="https://reuters.com/x">Reuters</a>' in message

    def test_also_covered_count_shown(self):
        story = make_story()
        story.also_covered_by = ["Bloomberg", "The Verge"]
        message = render(make_edited(1), [story])[0]
        assert "(+2)" in message


class TestVisibleLength:
    def test_ignores_tags_and_entities(self):
        assert visible_length("<b>abc</b>") == 3
        assert visible_length("a &amp; b") == 5  # "a & b"


class TestDateFormat:
    def test_morning_label(self):
        assert format_date_uz(datetime(2026, 8, 13, 8, 0, tzinfo=TASHKENT)) == "13-avgust, ertalab"

    def test_evening_label(self):
        assert format_date_uz(datetime(2026, 8, 13, 20, 0, tzinfo=TASHKENT)) == "13-avgust, kechqurun"


class TestMarkdown:
    def test_converts_links_and_strips_tags(self):
        text = to_markdown(['<b>Bosh</b>\n<a href="https://e.com">Manba</a>'])
        assert "[Manba](https://e.com)" in text
        assert "<" not in text
