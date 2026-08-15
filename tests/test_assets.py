"""Rasm hosting — URL yasash va eskilarini tozalash."""

import os
import time
from pathlib import Path

import httpx
import pytest

from news_agent import assets
from news_agent.assets import prune_old_cards, raw_url, wait_until_reachable
from news_agent.config import PROJECT_ROOT


class TestRawUrl:
    def test_builds_public_github_url(self):
        path = PROJECT_ROOT / "assets" / "cards" / "2026-08-15-0800-00.png"
        url = raw_url(path, "imxumoyun/news-agent", "main")

        assert url == (
            "https://raw.githubusercontent.com/imxumoyun/news-agent/main/"
            "assets/cards/2026-08-15-0800-00.png"
        )

    def test_uses_forward_slashes(self):
        """Windows yo'l ajratuvchisi URL'ga tushmasin."""
        path = PROJECT_ROOT / "assets" / "cards" / "x.png"
        assert "\\" not in raw_url(path, "a/b", "main")


class TestPrune:
    def test_removes_old_files_keeps_recent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assets, "CARDS_DIR", tmp_path)

        old = tmp_path / "eski.png"
        new = tmp_path / "yangi.png"
        old.write_bytes(b"x")
        new.write_bytes(b"x")

        long_ago = time.time() - 60 * 24 * 3600
        os.utime(old, (long_ago, long_ago))

        removed = prune_old_cards(days=30)

        assert removed == 1
        assert not old.exists()
        assert new.exists()

    def test_missing_directory_does_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assets, "CARDS_DIR", tmp_path / "yo'q")
        assert prune_old_cards() == 0


class TestWaitUntilReachable:
    def test_returns_when_all_urls_are_live(self, monkeypatch):
        original = httpx.Client
        monkeypatch.setattr(
            httpx,
            "Client",
            lambda *a, **k: original(
                *a, **{**k, "transport": httpx.MockTransport(lambda r: httpx.Response(200))}
            ),
        )

        wait_until_reachable(["https://e.com/a.png"], timeout=5)

    def test_raises_with_helpful_message_when_not_public(self, monkeypatch):
        """Repo yopiq bo'lsa 404 keladi — xato sababni aytishi kerak."""
        original = httpx.Client
        monkeypatch.setattr(
            httpx,
            "Client",
            lambda *a, **k: original(
                *a, **{**k, "transport": httpx.MockTransport(lambda r: httpx.Response(404))}
            ),
        )

        with pytest.raises(RuntimeError, match="ochiqmi"):
            wait_until_reachable(["https://e.com/a.png"], timeout=0.1)
