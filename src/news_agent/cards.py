"""Instagram uchun karta rasmlarini yasaydi.

Brauzersiz — Pillow bilan to'g'ridan-to'g'ri chiziladi. Sabab: GitHub Actions'da
har yugurishda Chromium yuklab olish (~150MB) shu darajadagi sodda karta uchun
ortiqcha. Dizayn murakkablashsa, faqat shu modul almashtiriladi.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import PROJECT_ROOT

FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "Inter.ttf"

# Instagram feed uchun 4:5 — vertikal lentada eng ko'p joy egallaydi.
WIDTH, HEIGHT = 1080, 1350
PADDING = 88

# Kartalarda ko'rinadigan nom. O'zgartirish uchun shu bitta joy yetadi.
BRAND = "xumoyuntech"

# Instagram carousel chegarasi.
MAX_SLIDES = 10

BG = "#0E1116"
BG_ACCENT = "#151A22"
TEXT = "#F2F4F7"
MUTED = "#8B94A3"
ACCENT = "#4C8DFF"


@dataclass
class Theme:
    """Ranglar bir joyda — o'zgartirish oson bo'lsin."""

    bg: str = BG
    bg_accent: str = BG_ACCENT
    text: str = TEXT
    muted: str = MUTED
    accent: str = ACCENT


def _font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_PATH), size)
    font.set_variation_by_name(weight)
    return font


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Matnni berilgan kenglikka sig'adigan qatorlarga bo'ladi."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if font.getlength(candidate) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    line_height: int,
    fill: str,
) -> int:
    """Qatorlarni chizadi va oxirgi y koordinatani qaytaradi."""
    for line in lines:
        if line:
            draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def _fit_title(
    title: str, max_width: int, max_lines: int
) -> tuple[list[str], ImageFont.FreeTypeFont, int]:
    """Sarlavha uchun sig'adigan eng katta o'lchamni tanlaydi.

    Uzun sarlavhani kesib tashlagandan ko'ra shriftni kichraytirgan ma'qul —
    ma'no yo'qolmaydi.
    """
    for size in (68, 62, 56, 50, 46):
        font = _font(size, "Bold")
        lines = _wrap(title, font, max_width)
        if len(lines) <= max_lines:
            return lines, font, int(size * 1.22)

    font = _font(46, "Bold")
    lines = _wrap(title, font, max_width)[:max_lines]
    return lines, font, int(46 * 1.22)


def _extract_stats(body: str) -> tuple[list[str], str]:
    """Raqamli qisqa qatorlarni matndan ajratadi.

    "Chiqish tezligi: sekundiga 750 token" kabi qatorlar kartada katta qilib
    ko'rsatilsa, o'quvchi asosiy raqamni bir qarashda oladi.
    Qaytaradi: (raqamli qatorlar, qolgan matn).
    """
    stats: list[str] = []
    rest: list[str] = []

    for line in body.split("\n"):
        stripped = line.strip()
        is_stat = (
            stripped
            and len(stripped) <= 52
            and any(ch.isdigit() for ch in stripped)
            and not stripped.endswith(".")
        )
        if is_stat and len(stats) < 4:
            stats.append(stripped)
        else:
            rest.append(line)

    if len(stats) < 2:  # bitta raqam alohida blokka arzimaydi
        return [], body
    return stats, "\n".join(rest).strip()


STAT_INDENT = 30


def _fit_stat(
    text: str, max_width: int
) -> tuple[list[str], ImageFont.FreeTypeFont, int]:
    """Raqamli qator uchun sig'adigan o'lchamni tanlaydi.

    Avval bitta qatorga sig'dirishga urinamiz — raqam bo'lingandan ko'ra
    kichikroq shriftda yaxlit turgani yaxshi. Sig'masa ikki qatorga o'tkazamiz.
    """
    for size in (44, 40, 36, 32):
        font = _font(size, "SemiBold")
        lines = _wrap(text, font, max_width)
        if len(lines) == 1:
            return lines, font, int(size * 1.25)

    font = _font(32, "SemiBold")
    return _wrap(text, font, max_width)[:2], font, 42


def render_stats_card(
    title: str,
    stats: list[str],
    rest: str,
    source: str,
    index: int,
    total: int,
    theme: Theme | None = None,
) -> Image.Image:
    """Raqamlar asosiy o'rinda turadigan karta."""
    theme = theme or Theme()
    image = Image.new("RGB", (WIDTH, HEIGHT), theme.bg)
    draw = ImageDraw.Draw(image)
    content_width = WIDTH - PADDING * 2

    _draw_header(draw, index, total, theme)

    title_lines, title_font, title_lh = _fit_title(title, content_width, max_lines=3)
    rest_font = _font(34, "Regular")
    rest_lines = _wrap(rest, rest_font, content_width) if rest else []

    # Raqamli qatorlar chekkadan chiqib ketmasligi uchun oldindan o'lchaymiz.
    stat_width = content_width - STAT_INDENT
    fitted = [_fit_stat(stat, stat_width) for stat in stats]
    stats_height = sum(len(lines) * lh + 34 for lines, _, lh in fitted)

    block = (
        len(title_lines) * title_lh
        + 50
        + stats_height
        + (40 + len(rest_lines) * 48 if rest_lines else 0)
    )
    top_limit, bottom_limit = PADDING + 120, HEIGHT - PADDING - 90
    y = max(top_limit, top_limit + (bottom_limit - top_limit - block) // 2)

    y = _draw_lines(draw, title_lines, title_font, PADDING, y, title_lh, theme.text)
    y += 50

    for lines, font, line_height in fitted:
        bar_height = len(lines) * line_height - 10
        draw.rectangle([PADDING, y + 8, PADDING + 6, y + bar_height], fill=theme.accent)
        y = _draw_lines(draw, lines, font, PADDING + STAT_INDENT, y, line_height, theme.text)
        y += 34

    if rest_lines:
        y += 40
        _draw_lines(draw, rest_lines, rest_font, PADDING, y, 48, theme.muted)

    _draw_source(draw, source, theme)
    return image


def _draw_header(draw: ImageDraw.ImageDraw, index: int, total: int, theme: Theme) -> None:
    label_font = _font(30, "SemiBold")
    draw.text((PADDING, PADDING), BRAND, font=label_font, fill=theme.accent)
    counter = f"{index}/{total}"
    draw.text(
        (WIDTH - PADDING - label_font.getlength(counter), PADDING),
        counter,
        font=label_font,
        fill=theme.muted,
    )


def _draw_source(draw: ImageDraw.ImageDraw, source: str, theme: Theme) -> None:
    draw.text(
        (PADDING, HEIGHT - PADDING - 30),
        f"Manba: {source}",
        font=_font(30, "Medium"),
        fill=theme.muted,
    )


def render_card(
    title: str,
    body: str,
    source: str,
    index: int,
    total: int,
    theme: Theme | None = None,
) -> Image.Image:
    """Bitta yangilik kartasi. Matn tuzilishiga qarab ko'rinish tanlanadi."""
    theme = theme or Theme()

    stats, rest = _extract_stats(body)
    if stats:
        return render_stats_card(title, stats, rest, source, index, total, theme)
    image = Image.new("RGB", (WIDTH, HEIGHT), theme.bg)
    draw = ImageDraw.Draw(image)

    content_width = WIDTH - PADDING * 2

    _draw_header(draw, index, total, theme)

    title_lines, title_font, title_lh = _fit_title(title, content_width, max_lines=4)
    body_font = _font(36, "Regular")
    body_lines = _wrap(body, body_font, content_width)
    body_lh = 52

    # Blokni sarlavha satri bilan manba satri orasidagi bo'sh sohaga markazlaymiz.
    # Aks holda kontent yuqoriga qisilib, pastda katta bo'shliq qoladi.
    top_limit = PADDING + 120
    bottom_limit = HEIGHT - PADDING - 90
    block_height = len(title_lines) * title_lh + 70 + len(body_lines) * body_lh
    y = max(top_limit, top_limit + (bottom_limit - top_limit - block_height) // 2)

    y = _draw_lines(draw, title_lines, title_font, PADDING, y, title_lh, theme.text)

    # Sarlavha va matn orasidagi ajratuvchi
    y += 26
    draw.rectangle([PADDING, y, PADDING + 90, y + 5], fill=theme.accent)
    y += 40

    _draw_lines(draw, body_lines, body_font, PADDING, y, body_lh, theme.muted)

    _draw_source(draw, source, theme)
    return image


def render_cover(date_label: str, headlines: list[str], theme: Theme | None = None) -> Image.Image:
    """Carousel'ning birinchi slaydi — kun sarlavhalari ro'yxati."""
    theme = theme or Theme()
    image = Image.new("RGB", (WIDTH, HEIGHT), theme.bg)
    draw = ImageDraw.Draw(image)

    content_width = WIDTH - PADDING * 2

    item_font = _font(34, "Medium")
    number_font = _font(34, "Bold")
    shown = headlines[:6]

    # Avval balandlikni o'lchaymiz, keyin markazlaymiz — sarlavhalar soni
    # o'zgargani sari muqova muvozanatini yo'qotmasin.
    wrapped = [_wrap(h, item_font, content_width - 56)[:2] for h in shown]
    list_height = sum(len(lines) * 46 + 26 for lines in wrapped)
    block_height = 104 + 20 + 6 + 62 + list_height

    top_limit = PADDING + 90
    bottom_limit = HEIGHT - PADDING - 90
    y = max(top_limit, top_limit + (bottom_limit - top_limit - block_height) // 2)

    draw.text((PADDING, y - 56), date_label, font=_font(32, "Medium"), fill=theme.muted)

    heading_font = _font(88, "Bold")
    y = _draw_lines(draw, [BRAND], heading_font, PADDING, y, 104, theme.text)

    y += 20
    draw.rectangle([PADDING, y, PADDING + 120, y + 6], fill=theme.accent)
    y += 62

    for i, lines in enumerate(wrapped, 1):
        draw.text((PADDING, y), str(i), font=number_font, fill=theme.accent)
        y = _draw_lines(draw, lines, item_font, PADDING + 56, y, 46, theme.text)
        y += 26

    draw.text(
        (PADDING, HEIGHT - PADDING - 30),
        "Batafsil — keyingi slaydlarda",
        font=_font(30, "Medium"),
        fill=theme.muted,
    )

    return image


@dataclass
class CardItem:
    title: str
    body: str
    source: str


def build_post(items: list[CardItem], date_label: str, theme: Theme | None = None) -> list[Image.Image]:
    """Yangiliklar soniga qarab post shaklini tanlaydi.

    Har kuni bir xil 10 slaydli carousel chiqarish zerikarli va sun'iy.
    Bitta kuchli yangilik bo'lsa — bitta rasm yetadi; ko'p bo'lsa muqova
    qo'shiladi. Post shakli kontentga ergashadi, aksincha emas.
    """
    if not items:
        return []

    # Muqova faqat ro'yxat foyda beradigan darajada yangilik bo'lganda.
    with_cover = len(items) >= 4
    room = MAX_SLIDES - (1 if with_cover else 0)
    items = items[:room]
    total = len(items) + (1 if with_cover else 0)

    images: list[Image.Image] = []
    if with_cover:
        images.append(render_cover(date_label, [item.title for item in items], theme))

    start = 2 if with_cover else 1
    for offset, item in enumerate(items):
        images.append(
            render_card(item.title, item.body, item.source, start + offset, total, theme)
        )

    return images


def save_carousel(images: list[Image.Image], directory: Path, prefix: str) -> list[Path]:
    """Rasmlarni PNG qilib saqlaydi va yo'llarini qaytaradi."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, image in enumerate(images):
        path = directory / f"{prefix}-{i:02d}.png"
        image.save(path, "PNG", optimize=True)
        paths.append(path)
    return paths
