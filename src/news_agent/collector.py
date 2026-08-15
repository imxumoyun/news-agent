"""RSS/Atom manbalardan maqolalarni paralel yig'ish.

Bu qadamda LLM ishlatilmaydi — yig'ish, filtrlash va dedupe butunlay determinstik.
Bitta feed ishlamay qolsa qolganlari ishlashda davom etadi.
"""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from .config import Source
from .dedupe import canonical_url, dedupe_articles, url_id
from .models import Article

# Reddit va ba'zi CDN'lar noma'lum bot'ni 403 bilan rad etadi.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
SNIPPET_LIMIT = 400


@dataclass
class FeedStatus:
    """`sources-check` uchun bitta feed natijasi."""

    name: str
    url: str
    ok: bool
    entries: int = 0
    fresh: int = 0
    error: str = ""


def _clean_html(text: str) -> str:
    """Teglarni olib tashlab, HTML entity'larni ochadi (&#8217; → ')."""
    return _WHITESPACE.sub(" ", html.unescape(_HTML_TAG.sub(" ", text or ""))).strip()


def _entry_datetime(entry) -> tuple[datetime, bool]:
    """Maqola sanasi. Topilmasa hozirgi vaqt qaytariladi va bayroq qo'yiladi."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc), False
    return datetime.now(timezone.utc), True


# Google News sarlavhada emas, alohida <source> elementida asl nashrni beradi.
# Domenni o'qiladigan nomga aylantiramiz.
_SOURCE_NAMES = {
    "techcrunch.com": "TechCrunch",
    "theverge.com": "The Verge",
    "arstechnica.com": "Ars Technica",
    "bloomberg.com": "Bloomberg",
    "reuters.com": "Reuters",
    "anthropic.com": "Anthropic",
    "openai.com": "OpenAI",
    "wired.com": "Wired",
    "ft.com": "Financial Times",
    "cnbc.com": "CNBC",
    "theinformation.com": "The Information",
}


def _origin_name(entry, fallback: str) -> str:
    """Google News o'ramidan asl nashr nomini oladi."""
    origin = entry.get("source")
    title = (origin or {}).get("title") if isinstance(origin, dict) else None
    if not title:
        return fallback

    domain = title.lower().removeprefix("www.")
    if domain in _SOURCE_NAMES:
        return _SOURCE_NAMES[domain]
    if "." in domain:  # noma'lum domen: "example.com" → "Example"
        return domain.split(".")[0].capitalize()
    return title


def _parse_feed(source: Source, content: bytes, cutoff: datetime) -> tuple[list[Article], int]:
    """Feed matnidan Article ro'yxatini yasaydi. (maqolalar, umumiy elementlar soni)"""
    feed = feedparser.parse(content)
    articles: list[Article] = []

    for entry in feed.entries:
        link = entry.get("link") or ""
        title = _clean_html(entry.get("title") or "")
        if not link or not title:
            continue

        published_at, date_missing = _entry_datetime(entry)
        if published_at < cutoff:
            continue

        snippet = _clean_html(entry.get("summary") or entry.get("description") or "")
        articles.append(
            Article(
                id=url_id(link),
                title=title,
                url=canonical_url(link),
                source=_origin_name(entry, source.name),
                source_category=source.category,
                weight=source.weight,
                published_at=published_at,
                snippet=snippet[:SNIPPET_LIMIT],
                date_missing=date_missing,
            )
        )

    # Eng yangilarini qoldirib, manba chegarasini qo'llaymiz.
    articles.sort(key=lambda a: a.published_at, reverse=True)
    return articles[: source.max_items], len(feed.entries)


async def _fetch_one(
    client: httpx.AsyncClient, source: Source, cutoff: datetime
) -> tuple[list[Article], FeedStatus]:
    try:
        response = await client.get(source.url)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return [], FeedStatus(source.name, source.url, False, error=f"HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        return [], FeedStatus(source.name, source.url, False, error=type(exc).__name__)

    try:
        articles, total = _parse_feed(source, response.content, cutoff)
    except Exception as exc:  # noqa: BLE001 — buzilgan feed pipeline'ni to'xtatmasin
        return [], FeedStatus(source.name, source.url, False, error=f"parse: {exc}")

    if total == 0:
        return [], FeedStatus(source.name, source.url, False, error="0 element (RSS emasmi?)")

    return articles, FeedStatus(source.name, source.url, True, entries=total, fresh=len(articles))


async def collect(
    sources: list[Source], hours: int, timeout: float = 20.0
) -> tuple[list[Article], list[FeedStatus]]:
    """Barcha manbalardan so'nggi `hours` soatdagi maqolalarni yig'adi."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, */*"},
    ) as client:
        results = await asyncio.gather(*(_fetch_one(client, s, cutoff) for s in sources))

    articles = [article for batch, _ in results for article in batch]
    statuses = [status for _, status in results]
    return dedupe_articles(articles), statuses
