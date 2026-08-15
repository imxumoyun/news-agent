"""Karta rasmlarini ochiq URL'ga chiqarish.

Instagram rasmni O'ZI yuklab oladi va autentifikatsiya qila olmaydi — shuning
uchun fayl ochiq manzilda turishi shart. Rasmlar shu repo'ga commit qilinadi
va raw.githubusercontent.com orqali beriladi. Bu qo'shimcha xizmat ham,
qo'shimcha kalit ham talab qilmaydi.
"""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .config import PROJECT_ROOT

log = logging.getLogger(__name__)

CARDS_DIR = PROJECT_ROOT / "assets" / "cards"
RAW_BASE = "https://raw.githubusercontent.com"

# Rasmlar cheksiz to'planmasin — repo shishib ketadi.
RETENTION_DAYS = 30


def raw_url(path: Path, repo: str, branch: str) -> str:
    relative = path.relative_to(PROJECT_ROOT).as_posix()
    return f"{RAW_BASE}/{repo}/{branch}/{relative}"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def prune_old_cards(days: int = RETENTION_DAYS) -> int:
    """Eski kartalarni o'chiradi. Post chiqqach ular kerak emas."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for path in CARDS_DIR.glob("*.png"):
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if modified < cutoff:
            path.unlink()
            removed += 1
    return removed


def commit_and_push(paths: list[Path], branch: str, message: str) -> None:
    """Rasmlarni repo'ga yuklaydi.

    Instagram'ga havola berishdan OLDIN bajarilishi shart — aks holda Meta
    mavjud bo'lmagan manzilni yuklab olishga urinadi.
    """
    if not paths:
        return

    _git("add", "assets/cards")
    staged = _git("diff", "--staged", "--quiet")
    if staged.returncode == 0:
        log.info("Rasmlarda o'zgarish yo'q, push qilinmadi")
        return

    commit = _git(
        "-c", "user.name=news-agent",
        "-c", "user.email=actions@github.com",
        "commit", "-m", message,
    )
    if commit.returncode != 0:
        raise RuntimeError(f"Rasm commit qilinmadi: {commit.stderr.strip()}")

    push = _git("push", "origin", branch)
    if push.returncode != 0:
        raise RuntimeError(f"Rasm push qilinmadi: {push.stderr.strip()}")

    log.info("%d ta rasm repo'ga yuklandi", len(paths))


def wait_until_reachable(urls: list[str], timeout: float = 90.0) -> None:
    """Havolalar ochiq bo'lishini kutadi.

    raw.githubusercontent.com push'dan keyin bir necha soniya kechikadi.
    Kutmasak Instagram 'media fetch failed' xatosini beradi va sabab
    tushunarsiz bo'lib qoladi.
    """
    deadline = time.monotonic() + timeout
    pending = list(urls)

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        while pending and time.monotonic() < deadline:
            still: list[str] = []
            for url in pending:
                try:
                    if client.head(url).status_code == 200:
                        continue
                except httpx.HTTPError:
                    pass
                still.append(url)

            pending = still
            if pending:
                time.sleep(4)

    if pending:
        raise RuntimeError(
            "Rasmlar ochiq manzilda ko'rinmadi (repo ochiqmi?):\n  "
            + "\n  ".join(pending[:3])
        )

    log.info("Barcha rasmlar ochiq manzilda tasdiqlandi")
