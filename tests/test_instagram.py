"""Instagram publisher — soxta HTTP transport bilan, haqiqiy API chaqirilmaydi."""

import httpx
import pytest

from news_agent import instagram
from news_agent.instagram import InstagramError, publish

TOKEN = "test-token"
USER = "123"


class FakeInstagram:
    """Meta API'ning minimal taqlidi. Chaqiruvlarni yozib boradi."""

    def __init__(self, *, fail_on: str | None = None, status: str = "FINISHED"):
        self.calls: list[tuple[str, dict]] = []
        self.fail_on = fail_on
        self.status = status
        self._next_id = 1000

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = dict(request.url.params)
        self.calls.append((path, params))

        if self.fail_on and self.fail_on in path:
            return httpx.Response(
                200,
                json={"error": {"message": "Sinov xatosi", "code": 100, "error_subcode": 2207003}},
            )

        if request.method == "GET":  # container holati
            return httpx.Response(200, json={"status_code": self.status})

        if path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "post-1"})

        self._next_id += 1
        return httpx.Response(200, json={"id": str(self._next_id)})

    @property
    def created_containers(self) -> list[dict]:
        return [p for path, p in self.calls if path.endswith("/media")]

    @property
    def published(self) -> list[dict]:
        return [p for path, p in self.calls if path.endswith("/media_publish")]


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(instagram, "STATUS_INTERVAL", 0.0)


@pytest.fixture
def fake(monkeypatch):
    api = FakeInstagram()
    original = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(api.handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    return api


class TestSingleImage:
    def test_creates_container_then_publishes(self, fake):
        post_id = publish(TOKEN, USER, ["https://e.com/a.png"], "Caption matni")

        assert post_id == "post-1"
        assert len(fake.created_containers) == 1
        assert len(fake.published) == 1

    def test_caption_goes_on_the_container(self, fake):
        publish(TOKEN, USER, ["https://e.com/a.png"], "Caption matni")

        assert fake.created_containers[0]["caption"] == "Caption matni"

    def test_single_image_is_not_marked_as_carousel_item(self, fake):
        publish(TOKEN, USER, ["https://e.com/a.png"], "Caption")

        assert "is_carousel_item" not in fake.created_containers[0]


class TestCarousel:
    def test_creates_child_containers_then_parent(self, fake):
        urls = [f"https://e.com/{i}.png" for i in range(4)]
        publish(TOKEN, USER, urls, "Caption")

        containers = fake.created_containers
        children = [c for c in containers if c.get("is_carousel_item") == "true"]
        parents = [c for c in containers if c.get("media_type") == "CAROUSEL"]

        assert len(children) == 4
        assert len(parents) == 1
        assert len(parents[0]["children"].split(",")) == 4

    def test_caption_goes_on_parent_not_children(self, fake):
        publish(TOKEN, USER, ["https://e.com/a.png", "https://e.com/b.png"], "Caption")

        children = [c for c in fake.created_containers if c.get("is_carousel_item") == "true"]
        parent = [c for c in fake.created_containers if c.get("media_type") == "CAROUSEL"][0]

        assert all("caption" not in c for c in children)
        assert parent["caption"] == "Caption"

    def test_alt_text_attached_to_each_child(self, fake):
        publish(
            TOKEN, USER,
            ["https://e.com/a.png", "https://e.com/b.png"],
            "Caption",
            alt_texts=["Birinchi", "Ikkinchi"],
        )

        children = [c for c in fake.created_containers if c.get("is_carousel_item") == "true"]
        assert [c["alt_text"] for c in children] == ["Birinchi", "Ikkinchi"]


class TestLimits:
    def test_rejects_more_than_ten_images(self, fake):
        with pytest.raises(InstagramError, match="10"):
            publish(TOKEN, USER, [f"https://e.com/{i}.png" for i in range(11)], "Caption")

    def test_rejects_empty_input(self, fake):
        with pytest.raises(InstagramError, match="Rasm yo'q"):
            publish(TOKEN, USER, [], "Caption")

    def test_caption_is_truncated(self, fake):
        publish(TOKEN, USER, ["https://e.com/a.png"], "x" * 3000)

        assert len(fake.created_containers[0]["caption"]) == instagram.CAPTION_LIMIT


class TestErrors:
    def test_api_error_is_raised_with_message(self, monkeypatch):
        api = FakeInstagram(fail_on="/media")
        original = httpx.Client
        monkeypatch.setattr(
            httpx, "Client",
            lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(api.handler)}),
        )

        with pytest.raises(InstagramError, match="Sinov xatosi"):
            publish(TOKEN, USER, ["https://e.com/a.png"], "Caption")

    def test_container_error_status_stops_publishing(self, monkeypatch):
        api = FakeInstagram(status="ERROR")
        original = httpx.Client
        monkeypatch.setattr(
            httpx, "Client",
            lambda *a, **k: original(*a, **{**k, "transport": httpx.MockTransport(api.handler)}),
        )

        with pytest.raises(InstagramError, match="Container xatosi"):
            publish(TOKEN, USER, ["https://e.com/a.png"], "Caption")

        assert api.published == []  # publish bosqichiga yetib bormadi
