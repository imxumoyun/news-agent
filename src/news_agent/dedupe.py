"""URL kanonizatsiyasi va takroriy maqolalarni aniqlash.

Bir voqea bir necha manbada chiqadi va URL'lar tracking parametrlari bilan keladi.
Bu modul ikkalasini ham tozalaydi — LLM'gacha, ya'ni tekinga.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Tracking parametrlari — mazmunga ta'sir qilmaydi, olib tashlanadi.
_TRACKING_PREFIXES = ("utm_", "mc_", "pk_")
_TRACKING_KEYS = {
    "ref", "ref_src", "source", "src", "fbclid", "gclid", "igshid",
    "cmpid", "smid", "partner", "sh", "guccounter", "at_medium",
}

_TITLE_NOISE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")

# Sarlavha oxiridagi manba qo'shimchasi: "... - Reuters", "... | TechCrunch",
# Google News esa domen qo'yadi: "... - bloomberg.com"
_SOURCE_SUFFIX = re.compile(
    r"\s*[-|–—]\s*(?:[A-Z][\w .&]{2,30}|[a-z0-9-]+\.[a-z]{2,6}(?:\.[a-z]{2})?)$"
)

SIMILARITY_THRESHOLD = 0.85


def unwrap_google_news(url: str) -> str:
    """Google News o'ram havolasidan asl URL'ni ajratishga urinadi.

    Google News havolalari `news.google.com/rss/articles/<base64>` ko'rinishida
    keladi va asl manbaga ishora qilmaydi. Eski formatda base64 ichida asl URL
    bo'ladi; yangi (opaque) formatda ajratib bo'lmaydi — u holda URL o'zgarishsiz
    qaytariladi va dedupe sarlavha o'xshashligiga tayanadi.
    """
    parsed = urlparse(url)
    if "news.google.com" not in parsed.netloc:
        return url

    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        return url
    token = segments[-1].split("?")[0]

    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded)
    except (binascii.Error, ValueError):
        return url

    match = re.search(rb"https?://[\w\-./%?=&+#:,~]{10,}", raw)
    if not match:
        return url
    try:
        return match.group(0).decode("utf-8")
    except UnicodeDecodeError:
        return url


def canonical_url(url: str) -> str:
    """URL'ni taqqoslash uchun bir xil ko'rinishga keltiradi."""
    url = unwrap_google_news(url.strip())
    parsed = urlparse(url)

    scheme = "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    netloc = netloc.removesuffix(":443").removesuffix(":80")

    path = parsed.path.rstrip("/") or "/"

    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if not k.lower().startswith(_TRACKING_PREFIXES) and k.lower() not in _TRACKING_KEYS
    ]
    query = urlencode(sorted(kept))

    return urlunparse((scheme, netloc, path, "", query, ""))


def url_id(url: str) -> str:
    """Kanonik URL uchun qisqa barqaror identifikator."""
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def normalize_title(title: str) -> str:
    """Sarlavhani taqqoslash uchun soddalashtiradi."""
    title = _SOURCE_SUFFIX.sub("", title.strip())
    title = _TITLE_NOISE.sub(" ", title.lower())
    return _WHITESPACE.sub(" ", title).strip()


def titles_similar(a: str, b: str, threshold: float = SIMILARITY_THRESHOLD) -> bool:
    """Ikki sarlavha bir voqea haqidami?"""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Biri ikkinchisining ichida bo'lsa (qisqartirilgan sarlavha)
    if len(na) > 25 and len(nb) > 25 and (na in nb or nb in na):
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def dedupe_articles(articles: list) -> list:
    """Takroriy maqolalarni olib tashlaydi, eng vaznli manbani qoldiradi.

    Kirish va chiqish — `models.Article` ro'yxati. Avval URL bo'yicha, keyin
    sarlavha o'xshashligi bo'yicha tozalanadi.
    """
    # Vazni yuqori manba oldinda tursin, shunda saqlanadigan nusxa eng yaxshisi bo'ladi.
    ordered = sorted(articles, key=lambda a: (-a.weight, a.published_at))

    by_id: dict[str, object] = {}
    for article in ordered:
        by_id.setdefault(article.id, article)

    unique: list = []
    for article in by_id.values():
        if any(titles_similar(article.title, kept.title) for kept in unique):
            continue
        unique.append(article)

    unique.sort(key=lambda a: a.published_at, reverse=True)
    return unique
