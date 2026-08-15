"""1-agent: yuzlab maqoladan eng muhim 8-12 tasini tanlaydi.

Faqat sarlavha va qisqa snippet ko'radi — maqola matnini o'qimaydi. Shuning uchun
eng arzon modelda ishlaydi. Uning vazifasi — qimmat Analyst agentiga nima
berishni hal qilish.
"""

from __future__ import annotations

import logging

from ..config import Profile
from ..gemini import GeminiClient
from ..models import CATEGORIES, Article, CuratorOutput, SelectedStory

log = logging.getLogger(__name__)

SYSTEM = """Sen tajribali texnologiya muharririsan. Vazifang — kun davomida
to'plangan yangiliklardan haqiqatan muhimlarini ajratib olish.

Qat'iy qoidalar:
- Bir voqea bir necha manbada chiqqan bo'lsa, ularni BITTA element sifatida ber:
  eng ishonchli manbani `index` ga, qolganlarini `also_covered` ga qo'y.
- Manba ishonchliligini hisobga ol: kompaniyaning o'z blogi > tahlil > agregator > media.
- Techmeme va Hacker News — AGREGATOR, ular boshqa saytlarga havola qiladi.
  Bir voqea agregatorda ham, asl manbada ham bo'lsa, `index` ga ASL MANBANI qo'y,
  agregatorni `also_covered` ga. O'quvchi agregator sahifasiga emas, maqolaning
  o'ziga tushishi kerak.
- `category` faqat berilgan bo'limlar ro'yxatidan bo'lsin.
- Shubha bo'lsa — tanlama. Kam va muhim yaxshi, ko'p va bo'sh yomon."""

PROMPT = """{profile}

BO'LIMLAR (faqat shulardan birini tanla):
{categories}

MAQOLALAR:
{articles}

{min_items} tadan {max_items} tagacha eng muhim voqeani tanla va muhimlik bo'yicha
`score` (0.0-1.0) ber. Har biri uchun bir jumlada nega tanlaganingni yoz."""


def _format_articles(articles: list[Article]) -> str:
    lines = []
    for i, article in enumerate(articles):
        snippet = article.snippet[:220]
        lines.append(
            f"[{i}] {article.title}\n"
            f"    manba: {article.source} (ishonch {article.weight:.2f}, {article.source_category})\n"
            f"    {snippet}"
        )
    return "\n".join(lines)


def _prefer_original_source(story: SelectedStory, articles: list[Article]) -> None:
    """Agregator asosiy havola bo'lib qolgan bo'lsa, asl manba bilan almashtiradi.

    Promptda ham aytilgan, lekin model buni doim bajarmaydi. O'quvchi
    Techmeme'ning qisqacha xulosasiga emas, maqolaning o'ziga tushishi kerak.
    """
    if articles[story.index].source_category != "aggregator":
        return

    originals = [i for i in story.also_covered if articles[i].source_category != "aggregator"]
    if not originals:
        return

    best = max(originals, key=lambda i: articles[i].weight)
    story.also_covered = [i for i in story.also_covered if i != best] + [story.index]
    log.info(
        "Asosiy manba almashtirildi: %s → %s",
        articles[story.index].source,
        articles[best].source,
    )
    story.index = best


def _valid_stories(
    raw: list[SelectedStory], articles: list[Article]
) -> list[SelectedStory]:
    """Mavjud bo'lmagan raqamlarni va takrorlarni chiqarib tashlaydi."""
    count = len(articles)
    seen: set[int] = set()
    valid: list[SelectedStory] = []

    for story in raw:
        if not 0 <= story.index < count or story.index in seen:
            log.warning("Curator yaroqsiz raqam qaytardi: %s", story.index)
            continue
        story.also_covered = [i for i in story.also_covered if 0 <= i < count and i != story.index]
        _prefer_original_source(story, articles)
        if story.index in seen:
            continue
        seen.add(story.index)
        if story.category not in CATEGORIES:
            story.category = "Boshqa"
        valid.append(story)

    valid.sort(key=lambda s: s.score, reverse=True)
    return valid


async def curate(
    client: GeminiClient, model: str, articles: list[Article], profile: Profile
) -> list[SelectedStory]:
    if not articles:
        return []

    prompt = PROMPT.format(
        profile=profile.as_prompt_block(),
        categories="\n".join(f"- {c}" for c in CATEGORIES),
        articles=_format_articles(articles),
        min_items=profile.min_items,
        max_items=profile.max_items,
    )

    result = await client.structured(
        model=model, prompt=prompt, schema=CuratorOutput, system=SYSTEM
    )
    stories = _valid_stories(result.stories, articles)[: profile.max_items]

    log.info("Curator: %d maqoladan %d voqea tanlandi", len(articles), len(stories))
    return stories
