"""Telegram kanalga post tayyorlash va yuborish.

HTML formatlash ataylab Python tomonida — model to'g'ridan-to'g'ri HTML yozsa,
bitta yopilmagan teg butun postni yiqitadi. Model faqat matn beradi, teglarni
shu modul qo'yadi va hamma narsani escape qiladi.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .models import AnalyzedStory, EditorOutput

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
TASHKENT = ZoneInfo("Asia/Tashkent")

# Telegram chegarasi 4096. Zaxira qoldiramiz.
MAX_MESSAGE_CHARS = 3900

UZ_MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]

_TAG = re.compile(r"<[^>]+>")


def visible_length(text: str) -> int:
    """Telegram hisoblaydigan uzunlik — HTML teglarsiz."""
    return len(html.unescape(_TAG.sub("", text)))


def format_date_uz(moment: datetime) -> str:
    local = moment.astimezone(TASHKENT)
    part = "ertalab" if local.hour < 14 else "kechqurun"
    return f"{local.day}-{UZ_MONTHS[local.month - 1]}, {part}"


def _e(text: str) -> str:
    return html.escape(text.strip(), quote=False)


# Jumla oxiri: nuqta/undov/so'roq + probel + bosh harf. Oldida raqam bo'lsa
# bo'linmaydi ("$1.5 mlrd", "3.7 Flash" kabi holatlar buzilmasin).
# Bosh harfdan keyin apostrof kelishi mumkin — o'zbekchada O' va G' shunday.
_SENTENCE_END = re.compile(r"(?<![0-9])([.!?])\s+(?=[A-ZÀ-Þ]['’ʻ]?[a-zà-ÿ])")


def paragraphize(text: str) -> str:
    """Matnni bo'sh qator bilan ajratilgan paragraflarga bo'ladi.

    Uslub manbasidagi postlarning 96 foizi shunday tuzilgan: birinchi jumla —
    voqeaning o'zi, qolgani — tafsilot. Model buni faqat prompt asosida
    barqaror bajarmaydi, shuning uchun kafolat kodda.

    Model o'zi paragraf ajratgan bo'lsa — tegilmaydi.
    """
    text = text.strip()
    if "\n" in text:
        return text

    parts = _SENTENCE_END.sub(r"\1\n", text).split("\n")
    if len(parts) < 2:
        return text

    # Birinchi jumla alohida turadi, qolganlari birga.
    return parts[0] + "\n\n" + " ".join(parts[1:])


def render(
    edited: EditorOutput, stories: list[AnalyzedStory], moment: datetime | None = None
) -> list[str]:
    """Postni tayyor HTML xabarlarga aylantiradi (kerak bo'lsa bir nechta)."""
    moment = moment or datetime.now(TASHKENT)

    header = f"<b>🤖 AI va Tech — {_e(format_date_uz(moment))}</b>"
    if edited.intro_uz.strip():
        header += f"\n\n<i>{_e(edited.intro_uz)}</i>"

    # Bo'lim sarlavhalari ataylab chiqarilmaydi: ular postni katalogga
    # o'xshatadi. Bo'lim faqat TARTIB uchun ishlatiladi — bir mavzudagi
    # yangiliklar yonma-yon tursin.
    grouped: dict[str, list] = {}
    for item in edited.items:
        grouped.setdefault(item.section, []).append(item)

    blocks: list[str] = []

    for items in grouped.values():
        for item in items:
            story = stories[item.index]

            source_label = _e(story.source)
            if story.also_covered_by:
                source_label += _e(f" (+{len(story.also_covered_by)})")

            blocks.append(
                f"<b>{_e(item.title_uz)}</b>\n"
                f"{_e(paragraphize(item.text_uz))}\n"
                f'<a href="{html.escape(story.url, quote=True)}">{source_label}</a>'
            )

    # Bloklarni xabarlarga taqsimlash
    messages: list[str] = []
    current = header
    for block in blocks:
        candidate = f"{current}\n\n{block}"
        if visible_length(candidate) > MAX_MESSAGE_CHARS and current != header:
            messages.append(current)
            current = block
        else:
            current = candidate

    if current.strip():
        messages.append(current)

    return messages


def to_markdown(messages: list[str]) -> str:
    """Arxiv fayli uchun sodda matn ko'rinishi."""
    text = "\n\n".join(messages)
    text = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r"[\2](\1)", text)
    text = re.sub(r"</?b>", "**", text)
    text = re.sub(r"</?i>", "_", text)
    return html.unescape(_TAG.sub("", text))


async def send(token: str, chat_id: str, messages: list[str]) -> None:
    """Xabarlarni ketma-ket kanalga yuboradi."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, message in enumerate(messages, 1):
            response = await client.post(
                f"{API_BASE}/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Telegram xatosi ({i}-xabar): HTTP {response.status_code} — {response.text}"
                )
            log.info("Telegram: %d/%d xabar yuborildi", i, len(messages))
