"""Uslub kafolatlari — matn qanday ko'rinishda chiqishi."""

from news_agent.config import load_style
from news_agent.telegram import paragraphize


class TestParagraphize:
    """Birinchi jumla alohida paragraf, qolgani birga — uslub manbasidagi shakl."""

    def test_first_sentence_becomes_its_own_paragraph(self):
        text = "Apple yangi Macbook chiqardi. Narxi oshdi. Chip ham yangilandi."
        assert paragraphize(text) == (
            "Apple yangi Macbook chiqardi.\n\nNarxi oshdi. Chip ham yangilandi."
        )

    def test_leaves_model_paragraphs_alone(self):
        text = "Model o'zi ajratgan.\n\nIkkinchi paragraf. Uchinchi jumla."
        assert paragraphize(text) == text

    def test_does_not_split_decimals(self):
        text = "Narx $1.5 mlrdga yetdi. Bu ko'p."
        assert paragraphize(text) == "Narx $1.5 mlrdga yetdi.\n\nBu ko'p."

    def test_does_not_split_version_numbers(self):
        text = "Gemini 3.7 Flash chiqdi. Tez ishlaydi."
        assert paragraphize(text) == "Gemini 3.7 Flash chiqdi.\n\nTez ishlaydi."

    def test_handles_question_and_exclamation(self):
        assert paragraphize("Nima o'zgardi? Hammasi.") == "Nima o'zgardi?\n\nHammasi."

    def test_single_sentence_unchanged(self):
        assert paragraphize("Bitta jumla.") == "Bitta jumla."

    def test_apostrophe_words_start_new_paragraph(self):
        text = "Birinchi jumla. O'zbekcha jumla ham ajralsin."
        assert paragraphize(text) == "Birinchi jumla.\n\nO'zbekcha jumla ham ajralsin."


class TestStyleConfig:
    def test_loads_and_builds_prompt_block(self):
        style = load_style()
        block = style.as_prompt_block()

        assert "OVOZ:" in block
        assert "QOIDALAR:" in block
        assert "MAN ETILGAN:" in block
        assert style.item_min < style.item_max

    def test_patterns_present(self):
        assert len(load_style().patterns) >= 2
