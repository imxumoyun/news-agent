import json
from datetime import datetime, timedelta, timezone

from news_agent.store import PostedStore


class TestPostedStore:
    def test_remembers_across_instances(self, tmp_path):
        path = tmp_path / "posted.jsonl"
        store = PostedStore(path)
        store.add("https://e.com/a", "Birinchi yangilik")
        store.save()

        reloaded = PostedStore(path)
        assert reloaded.is_posted("https://e.com/a")

    def test_ignores_tracking_params(self, tmp_path):
        store = PostedStore(tmp_path / "p.jsonl")
        store.add("https://e.com/a", "Yangilik")
        assert store.is_posted("https://e.com/a?utm_source=telegram")

    def test_detects_same_story_by_title(self, tmp_path):
        store = PostedStore(tmp_path / "p.jsonl")
        store.add("https://reuters.com/x", "Anthropic Decart AI ni sotib olmoqchi")
        assert store.is_posted("https://bloomberg.com/y", "Anthropic Decart AI ni sotib olmoqchi")

    def test_unknown_url_not_posted(self, tmp_path):
        store = PostedStore(tmp_path / "p.jsonl")
        assert not store.is_posted("https://e.com/new", "Butunlay boshqa yangilik")

    def test_save_drops_old_records(self, tmp_path):
        path = tmp_path / "p.jsonl"
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        path.write_text(
            json.dumps({"id": "old1", "url": "https://e.com/old", "title": "Eski", "posted_at": old})
            + "\n",
            encoding="utf-8",
        )

        store = PostedStore(path)
        store.add("https://e.com/new", "Yangi")
        store.save(retention_days=30)

        assert len(PostedStore(path)) == 1

    def test_corrupt_line_does_not_break_load(self, tmp_path):
        path = tmp_path / "p.jsonl"
        good = json.dumps(
            {
                "id": "abc",
                "url": "https://e.com/a",
                "title": "Yaxshi",
                "posted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        path.write_text(f"{{buzilgan json\n{good}\n", encoding="utf-8")

        store = PostedStore(path)
        assert len(store) == 1
