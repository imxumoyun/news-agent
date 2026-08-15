"""Pipeline bo'ylab uzatiladigan ma'lumot tuzilmalari."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# Dayjestdagi bo'limlar. Curator va Editor shu ro'yxatdan tashqariga chiqmaydi.
CATEGORIES = [
    "Modellar va relizlar",
    "Chip va infratuzilma",
    "Biznes va investitsiya",
    "Dasturchilar uchun",
    "Tadqiqot",
    "Siyosat va tartibga solish",
    "Boshqa",
]


class Article(BaseModel):
    """RSS'dan yig'ilgan bitta xom maqola."""

    id: str  # kanonik URL hashi
    title: str
    url: str
    source: str
    source_category: str
    weight: float
    published_at: datetime
    snippet: str = ""
    date_missing: bool = False


# ---------- Curator ----------


class SelectedStory(BaseModel):
    """Curator tanlagan bitta voqea (bir nechta manba bitta voqeaga birlashishi mumkin).

    Havola emas, ro'yxatdagi TARTIB RAQAMI qaytariladi — model URL'ni o'zidan
    to'qib chiqarishi mumkin, tartib raqamni esa Python tekshira oladi.
    """

    index: int = Field(description="Ro'yxatdagi maqola raqami")
    also_covered: list[int] = Field(
        default_factory=list, description="Shu voqeani yoritgan boshqa maqolalar raqami"
    )
    score: float = Field(description="Muhimlik bahosi 0.0-1.0")
    category: str = Field(description="Bo'lim nomi")
    why_selected: str = Field(description="Nega tanlandi — bir qisqa jumla")


class CuratorOutput(BaseModel):
    stories: list[SelectedStory]


# ---------- Analyst ----------


class Analysis(BaseModel):
    """Bitta voqeaning o'zbek tilidagi tahlili.

    Matn ataylab bo'linmagan: "xulosa + nega muhim" ni alohida maydonga
    ajratsak, model ikkalasini bir-biriga ulab, mexanik ohangda yozadi.
    """

    title_uz: str = Field(
        description="Voqeaning o'zi bir sodda jumlada. 70 belgigacha, nuqtasiz"
    )
    body_uz: str = Field(
        description=(
            "Matn tanasi. 2-3 ta qisqa paragraf, orasida BO'SH QATOR. Birinchi "
            "paragraf — nima bo'lgani, keyingisi — aniq raqam va tafsilotlar, "
            "oxirgisi — bu nimani o'zgartirishi. Shaxsiy fikr yozilmaydi"
        )
    )
    confidence: float = Field(description="Ma'lumot ishonchliligi 0.0-1.0")


class AnalyzedStory(BaseModel):
    """Tahlil + uning manbasi haqidagi ma'lumot."""

    analysis: Analysis
    url: str
    source: str
    category: str
    score: float
    also_covered_by: list[str] = Field(default_factory=list)


# ---------- Editor ----------


class EditedItem(BaseModel):
    """Editor tayyorlagan yakuniy element."""

    index: int = Field(description="Kirishdagi voqea tartib raqami (0 dan boshlab)")
    section: str = Field(description="Bo'lim nomi")
    title_uz: str = Field(description="Yakuniy sarlavha")
    text_uz: str = Field(description="Yakuniy matn — xulosa va nega muhimligi birga")


class EditorOutput(BaseModel):
    """Yakuniy post.

    Yakunlovchi qator (`outro`) ataylab yo'q: har postni umumlashtiruvchi
    jumla bilan tugatish qolipga aylanadi va sun'iy eshitiladi.
    """

    intro_uz: str = Field(description="Bir qatorli kirish, ixtiyoriy")
    items: list[EditedItem]
