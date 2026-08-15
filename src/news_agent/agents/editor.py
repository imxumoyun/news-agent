"""3-agent: alohida tahlillarni yaxlit postga aylantiradi.

Analyst har bir voqeani alohida ko'radi va shuning uchun umumiy manzarani
bilmaydi — takroriy jumlalar, bir xil boshlanishlar, tartibsizlik chiqadi.
Editor shuni tuzatadi va uzunlikni belgilangan budjetga sig'diradi.
"""

from __future__ import annotations

import logging

from ..config import Style, load_style
from ..gemini import GeminiClient
from ..models import CATEGORIES, AnalyzedStory, EditedItem, EditorOutput

log = logging.getLogger(__name__)

SYSTEM = """Sen Telegram kanali muharririsan. O'quvching — o'zbekistonlik dasturchi,
kanalni telefonda, yo'lda o'qiydi.

{style}

Muharrir sifatida vazifang:
- Voqealarni muhimlik bo'yicha tartibla, eng kuchlisi birinchi.
- Bir mavzudagi voqealarni yonma-yon qo'y.
- Takroriy jumlalarni va bir xil boshlanishlarni yo'q qil. Ikki element bir xil
  ohangda boshlansa — birini qayta yoz.
- Analyst yozgan matnni yaxshilashing mumkin, lekin FAKTLARNI o'zgartirma:
  raqam, nom va sanalar o'z joyida qolsin.

Til: o'zbek tili, lotin alifbosi. Texnik atamalar inglizcha qoladi.
HTML teg, markdown belgi yoki emoji QO'SHMA — formatlashni dastur qiladi.
Qator ajratish uchun oddiy qator tashlashdan foydalan."""

PROMPT = """Quyidagi {count} ta voqeadan Telegram post tayyorla.

Berilgan voqealarning HAMMASINI postga kirit. Budjet yetarli.
Faqat ikki holatda tashlab yubor: voqea boshqasining takrori bo'lsa yoki
matnida hech qanday aniq ma'lumot bo'lmasa. Kamida {min_items} ta qolsin.

Uzunlik: barcha matnlar jami {budget} belgidan oshmasin.
Har bir voqea matni {item_min}-{item_max} belgi.

`intro_uz` — BIR QATOR, oddiy qilib: bugun asosan nima haqida ekani.
Salomlashuv emas, umumlashtirilgan xulosa ham emas. Aytadigan aniq narsa
bo'lmasa — bo'sh qoldir, majburan yozma.
`index` — quyidagi ro'yxatdagi tartib raqam, o'zgartirmasdan ko'chir.
`section` — faqat shu ro'yxatdan: {categories}

VOQEALAR:
{stories}"""


def _format_stories(stories: list[AnalyzedStory]) -> str:
    blocks = []
    for i, story in enumerate(stories):
        also = (
            f"\n    yana yoritgan: {', '.join(story.also_covered_by)}"
            if story.also_covered_by
            else ""
        )
        body = "\n".join(f"      {row}" for row in story.analysis.body_uz.splitlines())
        blocks.append(
            f"[{i}] bo'lim: {story.category} | muhimlik: {story.score:.2f} | "
            f"manba: {story.source} | ishonch: {story.analysis.confidence:.2f}\n"
            f"    sarlavha: {story.analysis.title_uz}\n"
            f"    matn:\n{body}{also}"
        )
    return "\n\n".join(blocks)


def _fallback(stories: list[AnalyzedStory]) -> EditorOutput:
    """Editor yiqilsa — Analyst matnlarini shundayligicha ishlatamiz.

    Post chiqmay qolgandan ko'ra, sal g'ali-g'uli chiqqani yaxshi.
    """
    items = [
        EditedItem(
            index=i,
            section=story.category,
            title_uz=story.analysis.title_uz,
            text_uz=story.analysis.body_uz,
        )
        for i, story in enumerate(stories)
    ]
    return EditorOutput(intro_uz="", items=items)


def _validate(result: EditorOutput, count: int) -> EditorOutput:
    seen: set[int] = set()
    items: list[EditedItem] = []
    for item in result.items:
        if not 0 <= item.index < count or item.index in seen:
            log.warning("Editor yaroqsiz raqam qaytardi: %s", item.index)
            continue
        seen.add(item.index)
        if item.section not in CATEGORIES:
            item.section = "Boshqa"
        items.append(item)
    result.items = items
    return result


async def edit(
    client: GeminiClient,
    model: str,
    stories: list[AnalyzedStory],
    budget: int = 3200,
    style: Style | None = None,
    min_items: int | None = None,
) -> EditorOutput:
    if not stories:
        return EditorOutput(intro_uz="", items=[])

    style = style or load_style()
    prompt = PROMPT.format(
        count=len(stories),
        budget=budget,
        item_min=style.item_min,
        item_max=style.item_max,
        min_items=min(min_items or len(stories), len(stories)),
        categories=", ".join(CATEGORIES),
        stories=_format_stories(stories),
    )

    try:
        result = await client.structured(
            model=model,
            prompt=prompt,
            schema=EditorOutput,
            system=SYSTEM.format(style=style.as_prompt_block()),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("Editor yiqildi, zaxira variantga o'tamiz: %s", exc)
        return _fallback(stories)

    result = _validate(result, len(stories))
    if not result.items:
        log.error("Editor bitta ham yaroqli element qaytarmadi, zaxira variant")
        return _fallback(stories)

    log.info("Editor: %d elementdan %d tasi postga kirdi", len(stories), len(result.items))
    return result
