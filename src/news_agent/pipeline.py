"""To'liq pipeline: yig'ish → saralash → tahlil → tahrir → e'lon."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from . import assets, instagram, telegram
from .agents import analyze_all, curate, edit, write_caption
from .cards import CardItem, build_post, save_carousel
from .collector import collect
from .config import DIGESTS_DIR, STATE_DIR, load_profile, load_sources
from .gemini import GeminiClient
from .models import AnalyzedStory, Article, EditorOutput
from .store import PostedStore
from .telegram import TASHKENT, format_date_uz

log = logging.getLogger(__name__)

POSTED_PATH = STATE_DIR / "posted.jsonl"


def _drop_already_posted(articles: list[Article], store: PostedStore) -> list[Article]:
    fresh = [a for a in articles if not store.is_posted(a.url, a.title)]
    dropped = len(articles) - len(fresh)
    if dropped:
        log.info("Avval post qilingan %d maqola chiqarib tashlandi", dropped)
    return fresh


def _cap(articles: list[Article], limit: int) -> list[Article]:
    """Curator promptini cheklash uchun eng istiqbolli maqolalarni qoldiradi."""
    if len(articles) <= limit:
        return articles
    ranked = sorted(articles, key=lambda a: (a.weight, a.published_at), reverse=True)
    log.info("%d maqoladan eng yaxshi %d tasi Curator'ga beriladi", len(articles), limit)
    return ranked[:limit]


def _card_items(edited: EditorOutput, analyzed: list[AnalyzedStory]) -> list[CardItem]:
    return [
        CardItem(
            title=item.title_uz,
            body=item.text_uz,
            source=analyzed[item.index].source,
        )
        for item in edited.items
    ]


async def publish_instagram(
    settings,
    client: GeminiClient,
    edited: EditorOutput,
    analyzed: list[AnalyzedStory],
    moment: datetime,
    *,
    dry_run: bool = False,
) -> tuple[list, str]:
    """Kartalarni yasab Instagram'ga joylaydi. (rasm yo'llari, caption) qaytaradi."""
    settings.require("instagram_access_token", "instagram_user_id")

    date_label = format_date_uz(moment)
    images = build_post(_card_items(edited, analyzed), date_label)
    if not images:
        return [], ""

    prefix = f"{moment.astimezone(TASHKENT):%Y-%m-%d-%H%M}"
    paths = save_carousel(images, assets.CARDS_DIR, prefix)
    log.info("Instagram: %d ta karta yasaldi", len(paths))

    # Caption faqat POSTGA KIRGAN yangiliklardan yozilsin. Barcha tahlillarni
    # bersak, caption'da rasmda yo'q voqealar sanalib qoladi.
    in_post = [analyzed[item.index] for item in edited.items]
    caption = await write_caption(client, settings.caption_model, in_post)

    if dry_run:
        return paths, caption

    assets.prune_old_cards()
    assets.commit_and_push(paths, settings.assets_branch, f"kartalar: {prefix}")

    urls = [assets.raw_url(p, settings.assets_repo, settings.assets_branch) for p in paths]
    assets.wait_until_reachable(urls, settings.assets_wait_timeout)

    # Ekran o'quvchilar uchun: har kartaning sarlavhasi.
    alt_texts = [f"{date_label} dayjesti"] + [item.title for item in _card_items(edited, analyzed)]

    instagram.publish(
        settings.instagram_access_token,
        settings.instagram_user_id,
        urls,
        caption,
        alt_texts[: len(urls)],
    )
    return paths, caption


def _archive_path(moment: datetime) -> str:
    local = moment.astimezone(TASHKENT)
    return f"{local:%Y-%m-%d}-{'AM' if local.hour < 14 else 'PM'}.md"


@dataclass
class RunResult:
    """Bitta yugurish natijasi."""

    messages: list[str] = field(default_factory=list)
    card_paths: list = field(default_factory=list)
    caption: str = ""
    instagram_error: str = ""

    def __bool__(self) -> bool:
        return bool(self.messages or self.card_paths)


async def run_digest(
    settings,
    *,
    dry_run: bool = False,
    hours: int | None = None,
    telegram_enabled: bool = True,
    instagram_enabled: bool = False,
) -> RunResult:
    """Bitta to'liq yugurish."""
    settings.require("gemini_api_key")
    if not dry_run and telegram_enabled:
        settings.require("telegram_bot_token", "telegram_channel_id")

    sources = load_sources()
    profile = load_profile()
    store = PostedStore(POSTED_PATH)
    window = hours or settings.window_hours

    articles, statuses = await collect(sources, window, settings.fetch_timeout)
    failed = [s for s in statuses if not s.ok]
    if failed:
        log.warning("Ishlamagan feedlar: %s", ", ".join(f"{s.name} ({s.error})" for s in failed))
    log.info("So'nggi %d soatda %d ta noyob maqola yig'ildi", window, len(articles))

    articles = _cap(_drop_already_posted(articles, store), settings.max_candidates)
    if len(articles) < profile.min_items:
        log.warning("Yangilik juda kam (%d ta) — post qilinmaydi", len(articles))
        return RunResult()

    client = GeminiClient(settings.gemini_api_key, rpm_limit=settings.rpm_limit)

    stories = await curate(client, settings.curator_model, articles, profile)
    if not stories:
        log.warning("Curator hech narsa tanlamadi — post qilinmaydi")
        return RunResult()

    analyzed = await analyze_all(
        client, settings.analyst_model, stories, articles, settings.analyst_concurrency
    )
    if not analyzed:
        log.warning("Tahlil qilingan voqea yo'q — post qilinmaydi")
        return RunResult()

    edited = await edit(client, settings.editor_model, analyzed, min_items=profile.min_items)
    if not edited.items:
        return RunResult()

    moment = datetime.now(TASHKENT)
    result = RunResult(messages=telegram.render(edited, analyzed, moment))

    if instagram_enabled:
        # Instagram yiqilsa Telegram baribir chiqsin. Token 60 kunda tugaydi va
        # o'sha kuni butun dayjestni yo'qotish mantiqsiz.
        try:
            result.card_paths, result.caption = await publish_instagram(
                settings, client, edited, analyzed, moment, dry_run=dry_run
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Instagram'ga joylanmadi (Telegram davom etadi): %s", exc)
            result.instagram_error = str(exc)

    log.info("Gemini sarfi: %s", client.usage.summary())

    if dry_run:
        return result

    if telegram_enabled:
        await telegram.send(
            settings.telegram_bot_token, settings.telegram_channel_id, result.messages
        )

    # Faqat muvaffaqiyatli yuborilgandan keyin holatni yangilaymiz.
    for item in edited.items:
        story = analyzed[item.index]
        store.add(story.url, story.analysis.title_uz)
    store.save(settings.posted_retention_days)

    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    (DIGESTS_DIR / _archive_path(moment)).write_text(
        telegram.to_markdown(result.messages), encoding="utf-8"
    )

    return result
