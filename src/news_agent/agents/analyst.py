"""2-agent: har bir tanlangan voqeani o'qib, o'zbek tilida xulosa yozadi.

`url_context` tooli maqolaning to'liq matnini oladi — RSS snippet ko'pincha
birinchi ikki jumla bo'lgani uchun xulosa sifati keskin farq qiladi.
Sahifa ochilmasa (paywall, bloklangan bot) snippetga qaytadi.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import Style, load_style
from ..gemini import GeminiClient
from ..models import Analysis, AnalyzedStory, Article, SelectedStory

log = logging.getLogger(__name__)

URL_CONTEXT_TOOL = {"type": "url_context"}
SEARCH_TOOL = {"type": "google_search"}

# Ishonch shu darajadan past bo'lsa, google_search bilan qayta tekshiriladi.
RECHECK_BELOW = 0.6

SYSTEM = """Sen texnologiya yangiliklarini o'zbek tilida tushuntirib beradigan
muharrirsan. Sohani bilasan, lekin o'z fikringni yozmaysan — faktni yozasan.

{style}

Til:
- O'zbek tili, lotin alifbosi. Kirill ishlatma.
- Texnik atamalarni tarjima qilma: model, token, chip, inference, fine-tuning,
  benchmark, startup, API, open-source, valuation — shundayligicha qoldir.
- Kompaniya va mahsulot nomlari asl holida: OpenAI, NVIDIA, Gemini.
- So'zma-so'z tarjima qilma. O'zbekcha tabiiy gapir.

Aniqlik:
- Raqam, sana va nomlarni manbadan aniq ko'chir. Manbada yo'q narsani QO'SHMA.
- Maqolada raqam bo'lsa — uni albatta matnga chiqar. Narx, tezlik, foiz,
  hajm, muddat: o'quvchi uchun eng qimmatli qism shu.
- Fakt o'ylab topilmasin. Bo'rttirish ham yolg'on.
- Sen hech narsani sinab ko'rmagansan va hech qayerda bo'lmagansan. Shuning
  uchun "menimcha", "sinab ko'rdim", "bilmadim" kabi jumla YOZMA.
- Manba noaniq bo'lsa, buni fakt sifatida ayt ("bitim hali imzolanmagan"),
  shaxsiy shubha sifatida emas.
- `confidence`: mish-mish yoki "manbalarga ko'ra" darajasidagi xabarga past ball.

`body_uz` uzunligi: {item_min}-{item_max} belgi. Undan oshsa — qisqartir, ikkinchi
fikrni tashla."""

PROMPT_WITH_URL = """Quyidagi maqolani o'qi va o'zbek tilida xulosa yoz.

Havola: {url}
Manba: {source}
Asl sarlavha: {title}

Muharrir izohi (nega tanlandi): {why}"""

PROMPT_FALLBACK = """Quyidagi yangilik haqida o'zbek tilida xulosa yoz.
Maqola matni ochilmadi, faqat qisqacha ma'lumot bor — shuning uchun
`confidence` ni 0.5 dan oshirma va faqat quyida yozilganiga tayan.

Manba: {source}
Sarlavha: {title}
Qisqacha: {snippet}"""

# Ba'zi feedlar (masalan DeepMind blogi) tavsifsiz keladi. Sahifa ham ochilmasa,
# yagona ma'lumot — sarlavha. Bunday voqeani tashlab yuborgandan ko'ra,
# Google Search orqali tiklashga urinamiz: aks holda kunning eng muhim
# yangiligi jimgina yo'qolib qolishi mumkin.
PROMPT_TITLE_ONLY = """Quyidagi yangilik haqida o'zbek tilida xulosa yoz.
Maqola matni ham, tavsifi ham yo'q — faqat sarlavha bor.
Google Search orqali bu voqea haqida ma'lumot top va shunga tayanib yoz.

Manba: {source}
Sarlavha: {title}
Havola: {url}

Ishonchli ma'lumot topa olmasang, `confidence` ni 0.3 dan past qo'y."""

RECHECK_SUFFIX = """

Muhim: bu xabarni Google Search orqali tekshir. Boshqa manbalar tasdiqlagan
bo'lsa `confidence` ni oshir, tasdiq topilmasa pasaytir."""


async def _analyze_one(
    client: GeminiClient,
    model: str,
    article: Article,
    story: SelectedStory,
    also_names: list[str],
    semaphore: asyncio.Semaphore,
    system: str,
) -> AnalyzedStory | None:
    async with semaphore:
        analysis: Analysis | None = None
        read_full_text = True

        try:
            analysis = await client.structured(
                model=model,
                prompt=PROMPT_WITH_URL.format(
                    url=article.url,
                    source=article.source,
                    title=article.title,
                    why=story.why_selected,
                ),
                schema=Analysis,
                tools=[URL_CONTEXT_TOOL],
                system=system,
            )
        except Exception as exc:  # noqa: BLE001
            read_full_text = False
            log.warning("url_context ishlamadi (%s): %s — snippetga qaytamiz", article.url, exc)

        if analysis is None:
            if article.snippet:
                prompt = PROMPT_FALLBACK.format(
                    source=article.source, title=article.title, snippet=article.snippet
                )
                tools = None
            else:
                prompt = PROMPT_TITLE_ONLY.format(
                    source=article.source, title=article.title, url=article.url
                )
                tools = [SEARCH_TOOL]

            try:
                analysis = await client.structured(
                    model=model, prompt=prompt, schema=Analysis, tools=tools, system=system
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Tahlil muvaffaqiyatsiz, tashlab ketildi: %s (%s)", article.url, exc)
                return None

        # Ishonch past bo'lsa — qidiruv bilan bir marta qayta tekshirish.
        # Snippetdan yozilgan bo'lsa ma'nosi yo'q: ishonch pastligining sababi
        # allaqachon ma'lum (matn yo'q), qayta chaqiruv esa kvotani yeydi.
        if read_full_text and analysis.confidence < RECHECK_BELOW:
            try:
                analysis = await client.structured(
                    model=model,
                    prompt=PROMPT_WITH_URL.format(
                        url=article.url,
                        source=article.source,
                        title=article.title,
                        why=story.why_selected,
                    )
                    + RECHECK_SUFFIX,
                    schema=Analysis,
                    tools=[URL_CONTEXT_TOOL, SEARCH_TOOL],
                    system=SYSTEM,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("Qayta tekshirish o'tmadi: %s (%s)", article.url, exc)

        return AnalyzedStory(
            analysis=analysis,
            url=article.url,
            source=article.source,
            category=story.category,
            score=story.score,
            also_covered_by=also_names,
        )


async def analyze_all(
    client: GeminiClient,
    model: str,
    stories: list[SelectedStory],
    articles: list[Article],
    concurrency: int = 4,
    style: Style | None = None,
) -> list[AnalyzedStory]:
    """Tanlangan voqealarni paralel tahlil qiladi. Yiqilganlari tashlab ketiladi."""
    semaphore = asyncio.Semaphore(concurrency)
    style = style or load_style()
    system = SYSTEM.format(
        style=style.as_prompt_block(), item_min=style.item_min, item_max=style.item_max
    )

    tasks = [
        _analyze_one(
            client,
            model,
            articles[story.index],
            story,
            [articles[i].source for i in story.also_covered],
            semaphore,
            system,
        )
        for story in stories
    ]
    results = await asyncio.gather(*tasks)

    analyzed = [r for r in results if r is not None]
    log.info("Analyst: %d/%d voqea tahlil qilindi", len(analyzed), len(stories))
    return analyzed
