"""Instagram Content Publishing API.

Post joylash uch bosqichda ketadi va bu Telegram'dagidan ancha nozik:

  1. Har bir rasm uchun "container" yaratiladi — Meta rasmni o'zi yuklab oladi
  2. Carousel bo'lsa, containerlar bitta ota-containerga yig'iladi
  3. Ota-container publish qilinadi

Har bosqichda xato bo'lishi mumkin, shuning uchun holat tekshirib turiladi.
"""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://graph.instagram.com/v23.0"

# Instagram carousel chegarasi.
MAX_CAROUSEL = 10
CAPTION_LIMIT = 2200

# Container tayyor bo'lishini kutish.
STATUS_TIMEOUT = 120.0
STATUS_INTERVAL = 5.0


class InstagramError(RuntimeError):
    pass


def _post(client: httpx.Client, path: str, params: dict) -> dict:
    response = client.post(f"{API_BASE}/{path}", params=params)
    data = response.json()
    if "error" in data:
        err = data["error"]
        raise InstagramError(
            f"{err.get('message')} (kod {err.get('code')}, "
            f"subcode {err.get('error_subcode')})"
        )
    if response.status_code != 200:
        raise InstagramError(f"HTTP {response.status_code}: {response.text[:200]}")
    return data


def _wait_for_container(client: httpx.Client, container_id: str, token: str) -> None:
    """Container FINISHED bo'lishini kutadi.

    Meta rasmni yuklab olishi bir necha soniya oladi. Kutmasdan publish
    qilsak 'Media ID is not available' xatosi chiqadi.
    """
    deadline = time.monotonic() + STATUS_TIMEOUT

    while time.monotonic() < deadline:
        response = client.get(
            f"{API_BASE}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
        )
        data = response.json()
        status = data.get("status_code")

        if status == "FINISHED":
            return
        if status == "ERROR":
            raise InstagramError(f"Container xatosi: {data.get('status')}")

        time.sleep(STATUS_INTERVAL)

    raise InstagramError(f"Container {STATUS_TIMEOUT:.0f}s ichida tayyor bo'lmadi")


def _create_image_container(
    client: httpx.Client,
    user_id: str,
    token: str,
    image_url: str,
    *,
    caption: str | None = None,
    alt_text: str | None = None,
    carousel_item: bool = False,
) -> str:
    params = {"image_url": image_url, "access_token": token}
    if carousel_item:
        params["is_carousel_item"] = "true"
    if caption:
        params["caption"] = caption
    if alt_text:
        # 2025-yil mart oyidan beri mavjud — ekran o'quvchilar uchun.
        params["alt_text"] = alt_text[:1000]

    return _post(client, f"{user_id}/media", params)["id"]


def publish(
    token: str,
    user_id: str,
    image_urls: list[str],
    caption: str,
    alt_texts: list[str] | None = None,
) -> str:
    """Rasmlarni Instagram'ga joylaydi. Post ID qaytaradi.

    Bitta rasm bo'lsa oddiy post, ko'p bo'lsa carousel.
    """
    if not image_urls:
        raise InstagramError("Rasm yo'q")
    if len(image_urls) > MAX_CAROUSEL:
        raise InstagramError(f"Instagram {MAX_CAROUSEL} tadan ortiq rasmni qabul qilmaydi")

    caption = caption[:CAPTION_LIMIT]
    alt_texts = alt_texts or []

    with httpx.Client(timeout=60.0) as client:
        if len(image_urls) == 1:
            container = _create_image_container(
                client, user_id, token, image_urls[0],
                caption=caption,
                alt_text=alt_texts[0] if alt_texts else None,
            )
            _wait_for_container(client, container, token)
        else:
            children = []
            for i, url in enumerate(image_urls):
                child = _create_image_container(
                    client, user_id, token, url,
                    alt_text=alt_texts[i] if i < len(alt_texts) else None,
                    carousel_item=True,
                )
                _wait_for_container(client, child, token)
                children.append(child)
                log.info("Container tayyor: %d/%d", i + 1, len(image_urls))

            container = _post(
                client,
                f"{user_id}/media",
                {
                    "media_type": "CAROUSEL",
                    "children": ",".join(children),
                    "caption": caption,
                    "access_token": token,
                },
            )["id"]
            _wait_for_container(client, container, token)

        published = _post(
            client,
            f"{user_id}/media_publish",
            {"creation_id": container, "access_token": token},
        )

    post_id = published["id"]
    log.info("Instagram: post joylandi (%s)", post_id)
    return post_id


def remaining_quota(token: str, user_id: str) -> int | None:
    """Kunlik limitdan qancha qolganini qaytaradi (100 dan)."""
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                f"{API_BASE}/{user_id}/content_publishing_limit",
                params={"access_token": token},
            )
            data = response.json().get("data", [])
            if data:
                return 100 - int(data[0].get("quota_usage", 0))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.warning("Limitni o'qib bo'lmadi: %s", exc)
    return None
