# Demo Features — Level A / B / C

**Purpose:** Quick-win features for client demonstrations. Ordered by implementation cost.

---

## Level A — LLM only, <2 h each

| # | Feature | Button | Implementation |
|---|---|---|---|
| A1 | Weather — current weather for any city | 🌤 Weather | `curl wttr.in/<city>?format=3` — no API key |
| A2 | Translator — translate to any language | 🌍 Translate | LLM prompt |
| A3 | Date counter — days until event, day of week | 📅 Date | LLM + `datetime` |
| A4 | Calculator / converter — "100 lbs to kg" | 🧮 Calc | LLM reasoning |
| A5 | Idea generator — gifts, article topics, names | 💡 Ideas | LLM prompt |
| A6 | Fun fact on any topic | 🎲 Fact | LLM prompt |
| A7 | Joke / riddle | 😄 Joke | LLM prompt |

**Implementation notes:**
- A1: button → city input → `subprocess curl wttr.in` → text + voice reply
- A2: button → "to English: Привет мир" ForceReply → LLM translates
- A3–A7: one-shot menu buttons → LLM single-turn generation; no extra state

---

## Level B — Small helper, 2–4 h each

| # | Feature | Button | Pip deps | Implementation |
|---|---|---|---|---|
| B1 | Web search — find + summarise | 🔍 Search | `duckduckgo_search` | Fetch top-3 results → LLM summarises |
| B2 | Pi system status — CPU, RAM, temp, uptime | 📡 Status | `psutil` | `psutil` + `/sys/class/thermal` → text + voice |
| B3 | Timer / reminder — "remind me in 15 min" | ⏰ Timer | — | `threading.Timer` → Telegram push; `_pending_timers: dict[int, Timer]` |
| B4 | Text summariser — paste long text → summary | 📊 Summary | — | LLM via ForceReply |
| B5 | Text corrector — spelling, style, punctuation | ✏️ Correct | — | LLM prompt |
| B6 | Note formatter — draft → structured doc | 📋 Format | — | LLM prompt |
| B7 | Password generator — strong password by params | 🔐 Password | — | `secrets.choice` over char classes → `code` block |
| B8 | News headlines — top-5 from open RSS | 📰 News | `feedparser` | `feedparser` lenta.ru / BBC-RU → LLM summary |

---

## Level C — Impressive, 4–8 h each

| # | Feature | Button | Requires | Implementation |
|---|---|---|---|---|
| C1 | Image analysis — send photo → description | 🖼 Photo | OpenRouter vision model (gpt-4o) | `photo_handler` → base64 → LLM vision prompt |
| C2 | Interview trainer — practice Q&A by topic | 🎓 Interview | — | `_user_mode='interview'`; LLM asks questions + scores answers via voice |
| C3 | QR code generator — text/URL → PNG image | 📷 QR | `qrcode pillow` | `qrcode.make(text)` → BytesIO → `bot.send_photo()` |
| C4 | Mini quiz — 5 questions + inline answer buttons | 🏆 Quiz | — | LLM generates `{question, options[4], correct}` → `InlineKeyboardMarkup` |

---

## Demo Priority Order

**Minimum demo (1 day):**
A1 Weather + A2 Translator + B2 System Status + B3 Timer + C3 QR Code
→ shows voice, text, offline system status, push notifications, multimedia output

**Extended demo (2–3 days):**
Above + B1 Search + B4 Summariser + C1 Image analysis + C4 Quiz

**Flagship (already implemented):**
Smart Calendar — user says "remind me tomorrow at 10 for a team meeting",
bot replies by voice "saved", sends morning briefing + reminder push
