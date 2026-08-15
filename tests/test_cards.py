"""Karta renderi — matn chegaradan chiqib ketmasligi asosiy tekshiruv."""

import pytest

from news_agent.cards import (
    HEIGHT,
    PADDING,
    STAT_INDENT,
    WIDTH,
    CardItem,
    _extract_stats,
    _fit_stat,
    _fit_title,
    _wrap,
    build_post,
    render_card,
    render_cover,
)

CONTENT_WIDTH = WIDTH - PADDING * 2


class TestTextFits:
    """Chegaradan chiqish jimgina sodir bo'ladi — faqat rasmga qaraganda bilinadi."""

    @pytest.mark.parametrize(
        "stat",
        [
            "750 token",
            "SpaceX aksiyalaridagi ulushi: 21 milliard dollar",
            "Juda uzun ko'rsatkich nomi va uning qiymati: 1 234 567 890 dollar hamda qo'shimcha izoh",
        ],
    )
    def test_stat_lines_never_exceed_width(self, stat):
        max_width = CONTENT_WIDTH - STAT_INDENT
        lines, font, _ = _fit_stat(stat, max_width)

        assert lines
        for line in lines:
            assert font.getlength(line) <= max_width

    @pytest.mark.parametrize(
        "title",
        [
            "Qisqa sarlavha",
            "NVIDIA SpaceX va Intel kompaniyalaridagi ulushlarini oshkor qildi",
            "Juda uzun sarlavha " * 8,
        ],
    )
    def test_title_lines_never_exceed_width(self, title):
        lines, font, _ = _fit_title(title, CONTENT_WIDTH, max_lines=4)

        assert lines
        for line in lines:
            assert font.getlength(line) <= CONTENT_WIDTH

    def test_long_word_does_not_overflow_silently(self):
        """Bo'linmaydigan uzun so'z — o'ralmaydi, lekin yiqilmasligi kerak."""
        lines, _, _ = _fit_stat("A" * 200, CONTENT_WIDTH - STAT_INDENT)
        assert lines


class TestExtractStats:
    def test_pulls_out_short_numeric_lines(self):
        body = "Voqea.\n\nTezlik: 750 token\n5 baravar tezroq\n\nXulosa."
        stats, rest = _extract_stats(body)

        assert stats == ["Tezlik: 750 token", "5 baravar tezroq"]
        assert "Voqea." in rest and "Xulosa." in rest

    def test_single_number_stays_in_prose(self):
        """Bitta raqam uchun alohida blok yasash ortiqcha."""
        body = "Narxi 100 dollar\n\nQolgan matn."
        stats, rest = _extract_stats(body)

        assert stats == []
        assert rest == body

    def test_sentences_are_not_treated_as_stats(self):
        body = "2026-yilda kompaniya katta o'sishga erishdi va bozorni egalladi."
        stats, _ = _extract_stats(body)

        assert stats == []


class TestPostShape:
    """Har kuni bir xil shakl chiqmasin — post kontentga ergashadi."""

    def items(self, n):
        return [CardItem(f"Sarlavha {i}", "Matn bor.", "Manba") for i in range(n)]

    def test_single_story_gets_one_image_without_cover(self):
        assert len(build_post(self.items(1), "15-avgust")) == 1

    def test_three_stories_get_no_cover(self):
        assert len(build_post(self.items(3), "15-avgust")) == 3

    def test_four_stories_get_cover(self):
        assert len(build_post(self.items(4), "15-avgust")) == 5

    def test_never_exceeds_instagram_limit(self):
        assert len(build_post(self.items(30), "15-avgust")) == 10

    def test_empty_input_produces_nothing(self):
        assert build_post([], "15-avgust") == []


class TestRendering:
    def test_card_has_expected_size(self):
        image = render_card("Sarlavha", "Matn.", "Manba", 1, 3)
        assert image.size == (WIDTH, HEIGHT)

    def test_stats_layout_is_used_when_numbers_present(self):
        """Raqamli karta boshqacha ko'rinadi — piksellar mos kelmasligi kerak."""
        plain = render_card("Sarlavha", "Bitta jumla matn.", "Manba", 1, 3)
        with_stats = render_card(
            "Sarlavha", "Kirish.\n\nTezlik: 750 token\nHajmi: 200 GB", "Manba", 1, 3
        )
        assert plain.tobytes() != with_stats.tobytes()

    def test_cover_renders(self):
        image = render_cover("15-avgust", ["Birinchi", "Ikkinchi", "Uchinchi"])
        assert image.size == (WIDTH, HEIGHT)

    def test_wrap_respects_explicit_newlines(self):
        from news_agent.cards import _font

        lines = _wrap("Birinchi\n\nIkkinchi", _font(34), CONTENT_WIDTH)
        assert lines == ["Birinchi", "", "Ikkinchi"]
