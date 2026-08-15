# news-agent

AI va texnologiya yangiliklarini RSS manbalardan yig'ib, Gemini agentlari orqali
saralab va o'zbek tilida xulosalab, kuniga ikki marta Telegram kanalga post qiladi.

## Qanday ishlaydi

```
25 ta RSS manba
   ↓  Collector (LLM'siz)     paralel yig'ish → 14 soatlik filtr → dedupe → avval post qilinganlarni chiqarish
~100 nomzod maqola
   ↓  Curator                 faqat sarlavhalarni ko'radi, 5-11 ta voqea tanlaydi
   ↓  Analyst (+ url_context) maqolaning to'liq matnini o'qib, o'zbekcha xulosa yozadi
   ↓  Editor                  tartiblaydi, ixchamlaydi, uzunlik budjetiga sig'diradi
Telegram post
```

Uch bosqichga bo'linishining sababi: bitta chaqiruvda 100 ta maqolani to'liq matni
bilan o'qish qimmat va sifatsiz. Arzon model ko'pchilikni filtrlaydi, qimmati esa
faqat tanlangan 10 tasiga sarflanadi.

## O'rnatish

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -e .
cp .env.example .env   # keyin .env ni to'ldiring
```

`.env` da uchta qiymat kerak:

| O'zgaruvchi | Qayerdan olinadi |
|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `TELEGRAM_BOT_TOKEN` | Telegram'dagi @BotFather |
| `TELEGRAM_CHANNEL_ID` | `@kanalnomi` yoki `-100...` raqami |

Bot kanalga **admin** qilib qo'shilgan bo'lishi va "Post messages" huquqiga ega
bo'lishi shart.

## Buyruqlar

```bash
./venv/bin/python -m news_agent sources-check   # RSS manbalar ishlayaptimi
./venv/bin/python -m news_agent collect         # maqolalarni yig'ish (LLM'siz, bepul)
./venv/bin/python -m news_agent run --dry-run   # to'liq dayjest, yubormasdan
./venv/bin/python -m news_agent run             # Telegram kanaliga yuborish
./venv/bin/python -m news_agent run --instagram # Telegram + Instagram
```

`--hours N` vaqt oynasini, `--no-telegram` faqat Instagram'ga joylashni,
`-v` batafsil logni beradi.

## Instagram

Instagram'da matnli post yo'q — har postda rasm bo'lishi shart. Shuning uchun
har yangilik uchun karta rasmi yasaladi (`src/news_agent/cards.py`, Pillow bilan,
brauzersiz).

Post shakli kontentga ergashadi:

| Yangilik soni | Rasm |
|---|---|
| 1 ta | 1 rasm, muqovasiz |
| 2-3 ta | 2-3 rasm, muqovasiz |
| 4+ | muqova + kartalar |
| ko'p | 10 tada to'xtaydi (Instagram chegarasi) |

Karta ko'rinishi ham matnga qarab tanlanadi: matnda ikkitadan ortiq qisqa
raqamli qator bo'lsa, raqamlar yirik qilib alohida chiqariladi.

**Rasm hosting.** Instagram rasmni o'zi yuklab oladi va autentifikatsiya qila
olmaydi — fayl ochiq manzilda turishi shart. Rasmlar shu repo'ning
`assets/cards/` papkasiga commit qilinadi va `raw.githubusercontent.com` orqali
beriladi. **Shu sababli repo OCHIQ bo'lishi kerak.** Repo'da sir yo'q:
`.env` gitignore'da, kalitlar GitHub Secrets'da.

Eski kartalar 30 kundan keyin avtomatik o'chiriladi.

**Token.** `INSTAGRAM_ACCESS_TOKEN` 60 kunda tugaydi. Yangilash:

```
GET https://graph.instagram.com/refresh_access_token
    ?grant_type=ig_refresh_token&access_token=ESKI_TOKEN
```

Token 60 kun ishlatilmasa butunlay o'ladi va tiklab bo'lmaydi.

Instagram yiqilsa Telegram posti baribir chiqadi — xato loglanadi, pipeline
to'xtamaydi.

## Sozlash

Dayjest sifati yoqmasa — **kodni emas, konfiguratsiyani** o'zgartiring:

- `config/profile.yaml` — **nima haqida** yozilsin: nima muhim, nima kerak emas,
  nechta yangilik chiqsin. Curator agenti shu faylga qarab saralaydi.
- `config/style.yaml` — **qanday** yozilsin: ovoz, qoidalar, man etilgan iboralar,
  matn uzunligi va shakllar. Analyst va Editor shu faylga qarab yozadi.
- `config/sources.yaml` — manbalar ro'yxati, ularning vazni va har biridan
  olinadigan maksimal maqola soni.

### Uslub haqida

Mohiyati: faktni ayt, tafsilotni ber, tugat. Birinchi qator — voqeaning o'zi,
ilmoq emas. Matn bo'sh qator bilan ajratilgan 2-3 paragraf. Har postda kamida
bitta aniq raqam yoki taqqoslash bo'lishi shart.

**Nega shaxsiy fikr yo'q.** Agent hech narsani sinab ko'rmagan va hech qayerda
bo'lmagan. "Menimcha yaxshi chiqibdi" degan jumla — soxta tajriba, o'quvchi
buni sezadi. Uning o'rniga fakt beriladi: "menimcha arzon" emas, "oldingi
modeldan 3 barobar arzon". Bunday iboralar `banned` ro'yxatida.

**Nega yakunlovchi qator yo'q.** Avvalgi versiyada har post umumlashtiruvchi
jumla bilan tugardi ("...davr boshlandi"). Bir postda 5 marta takrorlanganda u
qolipga aylandi va sun'iy eshitildi. Shuning uchun `EditorOutput` dan `outro`
butunlay olib tashlandi.

Paragrafga bo'lish `telegram.paragraphize()` da **kod bilan** kafolatlangan:
model buni faqat prompt asosida barqaror bajarmaydi.

Manba qo'shgandan keyin **albatta** `sources-check` ni ishlating: RSS manzillari
tez-tez o'zgaradi va o'lik feed jimgina yo'qoladi.

## Avtomatik ishga tushish

`.github/workflows/digest.yml` har kuni 03:00 va 15:00 UTC (Toshkent bo'yicha
08:00 va 20:00) da ishlaydi. GitHub Secrets'ga yuqoridagi uchta qiymatni
qo'shish kerak.

Runner har safar toza boshlanadi, shuning uchun `state/posted.jsonl` va
`digests/` workflow oxirida repo'ga commit qilinadi. **Shu qadam bo'lmasa
ertalabki yangiliklar kechqurun takrorlanadi.**

## Testlar

```bash
./venv/bin/python -m pytest
```

Testlar haqiqiy API'ga chiqmaydi — Gemini o'rniga soxta klient ishlatiladi,
RSS o'rniga fixture XML.

## Xarajat va modellar

Standart holatda uchala agent ham `gemini-3.5-flash-lite` da ishlaydi —
bepul tarif chegarasiga sig'ish uchun. Bir yugurish ~9-10 chaqiruv,
~15k kirish + ~4k chiqish token.

Bepul tarifda chaqiruvlar orasida majburiy pauza bor (`RPM_LIMIT=5`),
shuning uchun bir yugurish ~2 daqiqa davom etadi.

Billing yoqsangiz `.env` da quyidagini oching — matn sifati sezilarli
yaxshilanadi va yugurish ~20 soniyaga tushadi (oyiga ~$10):

```
ANALYST_MODEL=gemini-3.6-flash
EDITOR_MODEL=gemini-3.6-flash
RPM_LIMIT=60
```

### Ma'lum cheklov

`url_context` tooli `gemini-3.6-flash` bilan ba'zan oddiy maqolalarda ham
soxta "safety violation" (HTTP 400) qaytaradi. Bunday holatda agent RSS
snippetiga qaytadi va xulosa sifati pasayadi. `flash-lite` da bu muammo
kuzatilmadi.
