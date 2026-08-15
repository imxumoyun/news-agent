"""Instagram uchun caption yozadi.

Telegram matni bu yerga to'g'ridan-to'g'ri to'g'ri kelmaydi: Instagram'da
havolalar bosilmaydi va matn rasmlar bilan takrorlanmasligi kerak. Caption —
rasmlarni takrorlash emas, ularni to'ldirish.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from ..config import Style, load_style
from ..gemini import GeminiClient
from ..models import AnalyzedStory

log = logging.getLogger(__name__)

CAPTION_LIMIT = 2200
MAX_HASHTAGS = 12

SYSTEM = """Sen Instagram uchun caption yozadigan muharrirsan.

{style}

Instagram xususiyatlari:
- Caption'dagi havolalar BOSILMAYDI. Shuning uchun havola yozma, manba
  nomini ayt ("Reuters xabar qildi" emas — shunchaki "Reuters").
- Birinchi ikki qator lentada ko'rinadi, qolgani "yana" tugmasi ostida
  qoladi. Eng muhim narsani boshiga qo'y.
- Rasmlardagi matnni so'zma-so'z takrorlama. Caption qo'shimcha kontekst beradi."""

PROMPT = """Quyidagi {count} ta yangilik uchun Instagram caption yoz.

`caption_uz`:
- Birinchi qator — bugungi eng muhim voqea, bitta jumla.
- Keyin qolgan yangiliklarni qisqa sanab o't (har biri bir qator).
- Oxirida manbalarni ayt.
- Jami 500-900 belgi. Emoji ishlatma yoki bittadan oshirma.

`hashtags`:
- 6 tadan 10 tagacha. `#` belgisiz, faqat so'z.
- O'zbekcha va inglizcha aralash bo'lishi mumkin.
- Mavzuga aniq mos bo'lsin. Umumiy "#instagood" kabi teglar kerak emas.

YANGILIKLAR:
{stories}"""

_HASHTAG_CLEAN = re.compile(r"[^0-9A-Za-zА-Яа-я_]")


class CaptionOutput(BaseModel):
    caption_uz: str = Field(description="Caption matni")
    hashtags: list[str] = Field(default_factory=list, description="Hashtaglar, # belgisiz")


def _format(stories: list[AnalyzedStory]) -> str:
    blocks = []
    for i, story in enumerate(stories, 1):
        blocks.append(
            f"{i}. {story.analysis.title_uz}\n"
            f"   manba: {story.source}\n"
            f"   {story.analysis.body_uz.replace(chr(10), ' ')[:220]}"
        )
    return "\n\n".join(blocks)


def _clean_hashtags(raw: list[str]) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for tag in raw:
        cleaned = _HASHTAG_CLEAN.sub("", tag.strip().lstrip("#"))
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            tags.append(cleaned)
    return tags[:MAX_HASHTAGS]


def _fallback(stories: list[AnalyzedStory]) -> str:
    """Model yiqilsa — sarlavhalardan oddiy caption."""
    lines = [story.analysis.title_uz for story in stories]
    sources = sorted({story.source for story in stories})
    return "\n".join(lines) + "\n\nManbalar: " + ", ".join(sources)


async def write_caption(
    client: GeminiClient,
    model: str,
    stories: list[AnalyzedStory],
    style: Style | None = None,
) -> str:
    """Yakuniy caption matnini qaytaradi (hashtaglar bilan)."""
    if not stories:
        return ""

    style = style or load_style()

    try:
        result = await client.structured(
            model=model,
            prompt=PROMPT.format(count=len(stories), stories=_format(stories)),
            schema=CaptionOutput,
            system=SYSTEM.format(style=style.as_prompt_block()),
        )
        caption = result.caption_uz.strip()
        tags = _clean_hashtags(result.hashtags)
    except Exception as exc:  # noqa: BLE001
        log.error("Caption yozilmadi, zaxira variant: %s", exc)
        caption, tags = _fallback(stories), []

    if tags:
        caption = f"{caption}\n\n" + " ".join(f"#{tag}" for tag in tags)

    if len(caption) > CAPTION_LIMIT:
        caption = caption[: CAPTION_LIMIT - 1].rsplit("\n", 1)[0]

    log.info("Caption tayyor: %d belgi, %d hashtag", len(caption), len(tags))
    return caption
