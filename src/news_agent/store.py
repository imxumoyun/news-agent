"""Post qilingan yangiliklar tarixi.

JSONL formatida saqlanadi (SQLite emas) — chunki GitHub Actions runner har safar
toza boshlanadi va bu fayl repo'ga commit qilinadi. Matn formati git uchun qulay,
diff'i o'qiladi va konflikt bo'lsa qo'lda tuzatish mumkin.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .dedupe import titles_similar, url_id


class PostedStore:
    """Qaysi yangiliklar allaqachon kanalga chiqqanini eslab qoladi."""

    def __init__(self, path: Path):
        self.path = path
        self._records: list[dict] = []
        self._ids: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # buzilgan qator butun tarixni yiqitmasin
            self._records.append(record)
            self._ids.add(record["id"])

    def is_posted(self, url: str, title: str = "") -> bool:
        """URL yoki unga juda o'xshash sarlavha allaqachon chiqqanmi?"""
        if url_id(url) in self._ids:
            return True
        if title:
            return any(titles_similar(title, r.get("title", "")) for r in self._records)
        return False

    def add(self, url: str, title: str) -> None:
        record = {
            "id": url_id(url),
            "url": url,
            "title": title,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        self._records.append(record)
        self._ids.add(record["id"])

    def save(self, retention_days: int = 30) -> None:
        """Eski yozuvlarni tozalab, faylni qayta yozadi."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        kept = []
        for record in self._records:
            try:
                posted_at = datetime.fromisoformat(record["posted_at"])
            except (KeyError, ValueError):
                continue
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            if posted_at >= cutoff:
                kept.append(record)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            for record in kept:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        self._records = kept
        self._ids = {r["id"] for r in kept}

    def __len__(self) -> int:
        return len(self._records)
