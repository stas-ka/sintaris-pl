# Sintaris: контент-стратегия для привлечения российских клиентов через экспертные статьи

Дата исследования: 2026-04-19

Цель: подготовить 10 тем для экспертных публикаций, которые привлекают российских заказчиков на `sintaris.net`, показывают опыт в Hybrid RAG, n8n, распределенных AI-системах, Taris, безопасной работе с данными и инженерном процессе AI-разработки.

## Короткий вывод

Основной вектор: не "продажа AI", а спокойное объяснение того, как внедрять AI в реальные бизнес-процессы без хаоса, утечек, vendor lock-in и неконтролируемых ответов модели.

Для российских клиентов сейчас наиболее сильные триггеры:

| Триггер | Почему это работает | Как раскрывать в статьях |
|---|---|---|
| Безопасность данных и 152-ФЗ | Российские заказчики боятся передавать клиентские данные в внешние LLM и SaaS | Показывать схемы: локальное хранение, разделение данных, роли, аудит, маскирование, локальные модели, RAG без передачи лишнего |
| Практический ROI | Бизнес устал от AI-демо без эффекта | Считать процессы: скорость ответа, снижение ручной нагрузки, повторные продажи, follow-up, стоимость ошибки |
| Сложные документы и знания | У многих компаний есть инструкции, регламенты, PDF, базы знаний, но поиск работает плохо | Писать про RAG как инженерную систему: chunking, metadata, hybrid search, citations, тесты качества |
| Интеграции вместо "еще одного бота" | CRM, Telegram, почта, Google Sheets, сайт, N8N живут отдельно | Показывать AI-контур: webhook, очередь, n8n, API, human-in-the-loop, мониторинг |
| Недоверие к AI-разработке | Vibe coding ассоциируется с быстрым, но рискованным кодом | Позиционировать Sintaris как команду с процессом: docs, skills, tests, review, deploy discipline |
| Ненавязчивый стиль | Агрессивный маркетинг плохо работает на Habr и у экспертной аудитории | Формат "разбор практической проблемы", "что сломалось", "как мы решили", "чеклист" |

## Локальная экспертиза, которую нужно вынести в публикации

Из материалов `doc/marketing`, архитектуры Taris и Worksafety-superassistant:

| Актив | Что доказывает | Как использовать в статьях |
|---|---|---|
| Taris | Реальный AI-ассистент с Telegram, Web UI, голосом, календарем, заметками, почтой, RAG, RBAC, JWT, локальными LLM, PostgreSQL/SQLite | Пример "не чатбота", а операционной системы вокруг пользователя и бизнес-процессов |
| OpenClaw/PicoClaw архитектура | Умение адаптировать AI под железо: Raspberry Pi, laptop/PC, VPS, локальные LLM, STT/TTS | Писать про offline/local-first AI, стоимость инфраструктуры, приватность |
| Taris RAG | FTS5, pgvector/sqlite-vec, RRF, adaptive retrieval, shared docs, per-user settings, RAG monitoring | Технические статьи про зрелый RAG и диагностику качества |
| Worksafety-superassistant | Production RAG для охраны труда: около 200 документов, около 100K chunks, PostgreSQL 15 + pgvector, OpenAI embeddings, GPT-4o-mini, 11 n8n workflows, Telegram, activation-code auth, LDA topics, metadata filtering | Сильный кейс для статьи о слабостях классического RAG и преимуществах structure-aware hybrid RAG |
| N8N workflows | Campaign Select/Send, CRM sync, inbound callbacks, webhook-first integration | Показать, что Sintaris связывает AI с реальными бизнес-системами |
| Маркетинговые продукты Sintaris | AI Front Desk, AI Content Engine, AI Reactivation, AI Knowledge Assistant, AI-ассистенты по диагностике, консалтинг и пилоты | Разложить по сериям: знания, коммуникации, маркетинг, автоматизация, разработка |

Важное ограничение: при публикации Worksafety как публичного кейса нужно заранее санитизировать любые production endpoints, credentials, внутренние hostname, реальные клиентские документы и фрагменты дампов. В статьях можно показывать архитектурные паттерны, формулы ранжирования, тестовый набор запросов и обезличенные метрики.

## Площадки публикации

Основная публикация должна выходить на `sintaris.net`. Внешние площадки лучше использовать как каналы дистрибуции, обсуждения и доверия, а не как единственное место хранения статей.

| Площадка | Роль | Что публиковать | Ограничения и стиль |
|---|---|---|---|
| `sintaris.net/ru/blog/` | Главный источник, который должны находить Google, Yandex и AI-поиск | Полные версии статей, схемы, FAQ, кейсы, ссылки на услуги | Нужны Article schema, автор, дата, internal links, sitemap, canonical, русская версия |
| Habr | Доверие у IT-аудитории и технических руководителей | Глубокие технические разборы: Hybrid RAG, pgvector, n8n, локальные LLM, AI coding process | Не рекламировать услуги напрямую. На Habr правила ограничивают коммерческие упоминания вне корпоративных блогов. Нужен формат "инженерный опыт" |
| vc.ru | Бизнес, IT, маркетинг, AI, предприниматели | Кейсы автоматизации, ROI, AI Front Desk, контент-фабрика, безопасный пилот | Можно быть ближе к бизнесу, но лучше сохранять доказательность и цифры |
| Дзен | Широкая российская аудитория, предприниматели, эксперты вне IT | Упрощенные версии: "как понять, нужен ли вам AI-ассистент", "как не утечь данными в AI" | Меньше кода, больше примеров и чеклистов |
| TenChat | B2B networking, владельцы, директора, консультанты | Короткие экспертные посты и выжимки из статей | Работает как прогрев и личный бренд, а не как основная база знаний |
| Telegram канал/личный канал | Удержание аудитории и диалог | Анонсы статей, схемы, короткие заметки, ответы на комментарии | Не заменяет SEO-страницы, но помогает распространению |
| GitHub README/case pages | Доказательство технической экспертизы | Санитизированные архитектурные описания Worksafety/Taris, диаграммы, changelog | Не публиковать operational secrets и production URLs |

Рекомендуемая модель: сначала полная статья на `sintaris.net`, через 5-10 дней адаптация под Habr/vc.ru/Дзен, в конце каждой внешней публикации - нейтральная ссылка на полный разбор или related case на сайте. Для Habr лучше не ставить прямой CTA на продажу, а ссылаться на технический материал или GitHub/case page.

## Техническая подготовка сайта под поиск и AI-индексацию

Минимальный набор для `sintaris.net`:

| Элемент | Что сделать |
|---|---|
| Раздел блога | `/ru/blog/` плюс отдельные стабильные URL, например `/ru/blog/hybrid-rag-real-documents/` |
| Структура страницы | H1, короткое резюме, дата обновления, автор, оглавление, схемы, FAQ, блок "для кого" |
| Schema.org | `Article` или `BlogPosting`, `Organization`, `Person`, `BreadcrumbList`, `FAQPage` там, где есть FAQ |
| Internal links | Из каждой статьи вести на услуги: RAG, AI automation, n8n, Taris, консультация, кейсы |
| Sources | Указывать источники и дату проверки для юридических/технических утверждений |
| Диаграммы | Mermaid/SVG/PNG со схемами: RAG pipeline, data flow, n8n integration, Taris architecture |
| Не дублировать полностью | На внешних площадках публиковать адаптацию, а не 1:1 копию. Основной текст должен жить на сайте |
| Robots/sitemap | Проверить `robots.txt`, `sitemap.xml`, индексацию в Google Search Console и Яндекс Вебмастер |
| Авторство | Страница автора: опыт, GitHub, проекты, направления экспертизы |
| "How we built it" | Для AI-поиска полезны конкретные технические детали: `pgvector`, `BM25`, `FTS5`, `RRF`, `n8n`, `PostgreSQL`, `Telegram Bot API`, `152-ФЗ`, `local LLM` |

Google в официальной документации по AI features рекомендует не отдельную "магическую оптимизацию под AI", а те же основы: полезный, надежный, people-first контент, техническая доступность страницы и соблюдение Search policies. Поэтому сильнее всего будут работать оригинальные разборы с вашим опытом, схемами и конкретикой.

## 10 тем статей

### 1. AI с персональными данными: как внедрять LLM и не превращать бизнес в источник утечек

| Поле | Содержание |
|---|---|
| Для кого | Владельцы бизнеса, руководители сервисных компаний, юристы, IT-директора, эксперты с клиентскими базами |
| Основной вопрос | Можно ли использовать AI, если в процессах есть ФИО, телефоны, почта, история клиентов, медицинские/финансовые/кадровые данные? |
| Главная мысль | AI-внедрение начинается не с выбора модели, а с карты данных: что хранится, где хранится, кто имеет доступ, что можно отправлять во внешний LLM, что должно оставаться локально |
| Содержание | Разбор типов данных: публичные, внутренние, персональные, чувствительные. Как строить data boundary. Когда использовать local LLM/Ollama, когда облако допустимо. Как RAG меняет риски: документы не "обучают модель", но попадают в контекст запроса. Как нужны роли, аудит, TTL, маскирование, согласия, backup, delete policy |
| Технический крючок | Схема "Cloud LLM vs Local LLM vs Hybrid RAG": где данные хранятся, где обрабатываются, что логируется |
| Пример Sintaris | Taris: per-user storage, RBAC/JWT, локальные LLM на OpenClaw, Telegram/Web UI, document RAG, mail creds with consent gate |
| Площадки | `sintaris.net`, vc.ru, Дзен, TenChat |
| Нейтральный CTA | "Если вы хотите понять, какие данные можно безопасно включить в AI-процесс, начните с data/process audit" |

### 2. Почему классический RAG ломается на реальных документах

| Поле | Содержание |
|---|---|
| Для кого | IT-руководители, разработчики, владельцы компаний с регламентами, инструкциями, юридическими и отраслевыми документами |
| Основной вопрос | Почему "загрузили PDF в векторную базу" часто дает уверенные, но неполные или неправильные ответы? |
| Главная мысль | Классический vector-only RAG теряет структуру документа, порядок глав, точные номера разделов, терминологию и границы контекста |
| Содержание | Разбор проблем: fixed-size chunking, lost-in-the-middle, одинаковые embeddings для разных юридических формулировок, отсутствие metadata filters, плохой порядок chunks, отсутствие тестов качества. Показать, почему BM25/FTS, metadata и structure-aware retrieval нужны вместе |
| Технический крючок | До/после: vector top-k vs hybrid retrieval. Пример запроса "требования из приказа 883Н, раздел IV" |
| Пример Sintaris | Worksafety-superassistant: около 100K chunks, PostgreSQL/pgvector, structure-aware chunking, chapter regex, LDA topic signal, context assembly by chapter order |
| Площадки | Habr, `sintaris.net`, vc.ru |
| Нейтральный CTA | "Перед внедрением RAG стоит провести retrieval audit на 20-50 типовых вопросах" |

### 3. Hybrid RAG на практике: BM25, векторы, структура документа и RRF вместо одной магической базы

| Поле | Содержание |
|---|---|
| Для кого | Разработчики, CTO, data engineers, интеграторы AI |
| Основной вопрос | Как проектировать RAG, если нужны точные ответы по документам, а не просто "похожий текст"? |
| Главная мысль | Production RAG - это композиция сигналов: keyword search, semantic search, metadata, section match, recency, ownership, reranking, traces |
| Содержание | Объяснить BM25/FTS5, pgvector/cosine, Reciprocal Rank Fusion, metadata filtering, chunk quality, shared vs personal docs, query classification, RAG tracing. Отдельно показать, когда достаточно FTS5, когда нужен hybrid, когда нужен server-grade pipeline |
| Технический крючок | Формула scoring из Worksafety и адаптация Taris: FTS5 + vector + section + recency + owner priority |
| Пример Sintaris | Taris RAG: adaptive strategy `fts5`, `hybrid`, `hybrid+mcp`, RRF, RAG monitoring dashboard, per-user settings |
| Площадки | Habr, `sintaris.net` |
| Нейтральный CTA | "Мы можем помочь спроектировать RAG не как демо, а как измеряемый retrieval pipeline" |

### 4. AI-справочник по документам: как превратить PDF, DOCX, RTF и регламенты в ассистента, которому можно доверять

| Поле | Содержание |
|---|---|
| Для кого | Эксперты, консультанты, образовательные проекты, охрана труда, медицина, юристы, HR, производственные компании |
| Основной вопрос | Как сделать ассистента, который отвечает по вашим материалам, а не фантазирует? |
| Главная мысль | Нужно проектировать полный lifecycle документа: ingestion, parse, chunk, metadata, embeddings, tests, update, citations, feedback |
| Содержание | Pipeline: загрузка документов, извлечение текста, сохранение структуры, дедупликация, embedding coverage, контроль качества chunks, тестовые вопросы, цитирование источников, обновление документов. Показать "что делать с таблицами, сканами, длинными главами, версиями документов" |
| Технический крючок | Checklist: 12 проверок перед запуском AI-справочника |
| Пример Sintaris | Worksafety-superassistant как AI-ассистент по охране труда. Taris как универсальный RAG для документов пользователя |
| Площадки | `sintaris.net`, vc.ru, Дзен, Habr в более технической версии |
| Нейтральный CTA | "Начните с пилота на одном наборе документов и 30 контрольных вопросах" |

### 5. N8N как интеграционный слой для AI: где no-code помогает, а где нужен инженерный контроль

| Поле | Содержание |
|---|---|
| Для кого | Владельцы бизнеса, операционные директора, интеграторы, разработчики, маркетологи-автоматизаторы |
| Основной вопрос | Можно ли связать сайт, Telegram, CRM, почту, Google Sheets и AI без большого enterprise-проекта? |
| Главная мысль | n8n хорош как слой orchestration, но production-автоматизация требует версионирования, логирования, схем данных, error handling и security boundaries |
| Содержание | Когда использовать n8n: webhooks, CRM sync, уведомления, рассылки, human approval. Когда не надо: сложная бизнес-логика, тяжелый RAG, критичные транзакции без тестов. Как разделять workflow и code. Как документировать workflows и не превращать JSON в "невидимый код" |
| Технический крючок | Архитектура webhook-first: Taris -> n8n -> CRM/Gmail/Sheets -> callback в Taris |
| Пример Sintaris | Taris Campaign Select/Send, CRM sync, inbound event router. Worksafety: 11 n8n workflows для RAG и Telegram |
| Площадки | Habr, vc.ru, `sintaris.net`, TenChat |
| Нейтральный CTA | "Если у вас уже есть n8n, полезно провести workflow audit: где есть риски, где можно быстро добавить ценность" |

### 6. Taris как пример персонального и бизнес AI-ассистента: голос, Telegram, Web UI, RAG и автоматизация в одном контуре

| Поле | Содержание |
|---|---|
| Для кого | Владельцы малого бизнеса, эксперты, технические руководители, потенциальные партнеры |
| Основной вопрос | Чем AI-ассистент отличается от обычного чатбота? |
| Главная мысль | Полезный ассистент - это не один prompt, а система каналов, памяти, документов, календаря, почты, ролей, интеграций и локального/облачного LLM dispatch |
| Содержание | Компоненты Taris: Telegram + Web UI, voice STT -> LLM -> TTS, smart calendar, notes, mail digest, contacts, RAG, admin panel, local Ollama/OpenAI fallback, PostgreSQL/SQLite variants, REST API, skills/MCP, n8n integration |
| Технический крючок | Diagram: three channels -> shared LLM backend -> storage/RAG -> workflow integrations |
| Пример Sintaris | Сам Taris как живой внутренний продукт и showcase архитектуры Sintaris |
| Площадки | `sintaris.net`, vc.ru, Habr |
| Нейтральный CTA | "Такая архитектура может стать основой для персонального ассистента, AI Front Desk или внутреннего knowledge assistant" |

### 7. AI Front Desk 24/7: как автоматизировать ответы, запись и follow-up без потери человеческого качества

| Поле | Содержание |
|---|---|
| Для кого | Сервисный бизнес, клиники, образовательные проекты, консультанты, HoReCa, студии, частные эксперты |
| Основной вопрос | Как не терять клиентов из-за медленных ответов и нерегулярных касаний? |
| Главная мысль | AI Front Desk должен не "заменять администратора", а стандартизировать первичный контакт, квалификацию, запись, напоминания и передачу человеку |
| Содержание | Карта клиентского пути: входящий вопрос, классификация, ответ по базе знаний, сбор контактов, запись, reminder, follow-up, escalation. Риски: неверный ответ, обещания от имени бизнеса, персональные данные. Метрики: response time, missed leads, conversion to consultation, repeat touches |
| Технический крючок | Схема "AI + rules + human approval": где модель свободна, где работает только шаблон, где нужна подтвержденная запись |
| Пример Sintaris | Taris calendar, notification templates, contacts, mail, n8n campaign workflow, AI Knowledge Assistant |
| Площадки | vc.ru, Дзен, TenChat, `sintaris.net` |
| Нейтральный CTA | "Первый пилот лучше строить на одном канале и одном сценарии, например FAQ + запись + reminder" |

### 8. Контент-фабрика без AI-мусора: как делать статьи, посты и рассылки из реальной экспертизы

| Поле | Содержание |
|---|---|
| Для кого | Эксперты, консультанты, B2B-компании, владельцы услуг, маркетологи |
| Основной вопрос | Почему AI-контент часто выглядит одинаково и не приводит клиентов? |
| Главная мысль | AI должен помогать упаковывать опыт, а не заменять опыт. Хороший контент строится из кейсов, архитектурных решений, ошибок, цифр, чеклистов и ответов на реальные возражения клиентов |
| Содержание | Процесс: интервью с экспертом, сбор артефактов, тезисы, research, outline, draft, technical review, legal/security review, публикация, crossposting, analytics. Как не писать агрессивно. Как использовать RAG по собственным материалам для сохранения стиля |
| Технический крючок | "Content RAG": база презентаций, кейсов, FAQ, звонков и заметок, из которой AI собирает черновики в вашем стиле |
| Пример Sintaris | Текущая задача: из презентаций Sintaris, Taris и Worksafety сформировать серию материалов без потери технической глубины |
| Площадки | `sintaris.net`, vc.ru, Дзен, TenChat |
| Нейтральный CTA | "Если у вас есть экспертиза, но нет регулярного контента, можно начать с 10-статейной карты и контент-пайплайна" |

### 9. Vibe coding по-взрослому: почему AI-разработка требует процесса, skills, agents, тестов и документации

| Поле | Содержание |
|---|---|
| Для кого | Заказчики разработки, CTO, product owners, разработчики, технические предприниматели |
| Основной вопрос | Можно ли быстро разрабатывать с AI и при этом не получить неуправляемый код? |
| Главная мысль | Vibe coding без процесса создает технический долг. AI-разработка становится надежной только при наличии контекста, ограничений, skills, agents, тестов, review, deploy rules и документации |
| Содержание | Разобрать риски: hallucinated APIs, unsafe refactors, секреты, отсутствие тестов, нарушение архитектуры. Показать рабочий framework: `AGENTS.md`, quick-ref, skills, narrow tasks, file ownership, regression tests, code review, deployment checklist, protected production targets |
| Технический крючок | "AI coding pipeline": problem -> context pack -> plan -> implementation -> tests -> review -> changelog -> deploy -> postmortem |
| Пример Sintaris | Taris development process: quick-ref, test-suite decision table, deployment rules, vibe-coding protocol, regression IDs, production confirmation rules |
| Площадки | Habr, `sintaris.net`, vc.ru |
| Нейтральный CTA | "Если вы внедряете AI в разработку, сначала опишите процесс и критерии качества, а не просто покупайте инструмент" |

### 10. Как считать ROI AI-автоматизации: от диагностики процессов до пилота и масштабирования

| Поле | Содержание |
|---|---|
| Для кого | Владельцы бизнеса, операционные директора, руководители продаж/маркетинга/сервиса |
| Основной вопрос | Как понять, где AI даст деньги, а где будет игрушкой? |
| Главная мысль | ROI появляется там, где есть повторяемый процесс, измеримая потеря и понятная точка внедрения |
| Содержание | Методика Sintaris: 30-60 минут диагностики, карта процессов, baseline, выбор 1-2 сценариев, пилот, KPI, масштабирование. Метрики: время ответа, количество ручных операций, стоимость lead loss, повторные касания, качество базы знаний, стоимость ошибки, нагрузка на персонал |
| Технический крючок | Таблица оценки: частота операции x время x стоимость x риск x степень автоматизируемости |
| Пример Sintaris | AI Front Desk, AI Reactivation, AI Knowledge Assistant, Taris, n8n workflows, content engine |
| Площадки | vc.ru, Дзен, TenChat, `sintaris.net` |
| Нейтральный CTA | "Начать можно с небольшого пилота с измеримым результатом за 2-4 недели" |

## Рекомендуемый порядок публикаций

| Очередь | Статья | Почему так |
|---|---|---|
| 1 | AI с персональными данными | Высокий доверительный вход, важен для российского рынка |
| 2 | Почему классический RAG ломается | Сразу демонстрирует техническую глубину |
| 3 | Hybrid RAG на практике | Продолжает тему и дает Habr-grade технический материал |
| 4 | AI-справочник по документам | Переводит RAG в понятный бизнес-продукт |
| 5 | N8N как интеграционный слой | Показывает автоматизацию вокруг AI |
| 6 | Taris как пример AI-ассистента | Дает собственный case/showcase |
| 7 | AI Front Desk 24/7 | Ведет к понятной услуге для МСП |
| 8 | ROI AI-автоматизации | Помогает конвертировать интерес в консультацию |
| 9 | Контент-фабрика без AI-мусора | Раскрывает маркетинговую услугу и стиль |
| 10 | Vibe coding по-взрослому | Закрывает доверие к разработке и качеству |

## Рубрикатор для `sintaris.net`

| Рубрика | Статьи |
|---|---|
| AI и данные | 1, 2, 3, 4 |
| AI-автоматизация бизнеса | 5, 7, 10 |
| Продукты и кейсы Sintaris | 4, 6, 7 |
| AI-маркетинг и контент | 8 |
| AI-разработка и engineering process | 9 |

## Формат каждой статьи

Использовать одинаковый, но не шаблонный каркас:

1. Короткий практический конфликт: "почему это стало проблемой".
2. Для кого статья и когда она не подходит.
3. Ошибочный простой подход.
4. Инженерный/операционный подход.
5. Схема или таблица.
6. Мини-кейс Sintaris/Taris/Worksafety.
7. Чеклист внедрения.
8. Риски и ограничения.
9. Нейтральный следующий шаг: аудит, пилот, технический разбор, демонстрация.

## Что не делать

| Не делать | Почему |
|---|---|
| Не писать "мы внедрим AI за 3 дня и заменим сотрудников" | Снижает доверие и привлекает неподходящих клиентов |
| Не публиковать одинаковый текст на всех площадках | Риск дублей и потери ценности основного сайта |
| Не ссылаться на закрытые/опасные operational details | Риск безопасности и лишняя поверхность атаки |
| Не обещать 100% отсутствие hallucinations | RAG снижает риски, но требует тестов и ограничений |
| Не уходить в чистый technical jargon | Часть аудитории - эксперты из других областей, которым нужны бизнес-смысл и риски |
| Не делать статьи слишком рекламными для Habr | Площадка чувствительна к коммерческим упоминаниям |

## Источники и ориентиры исследования

Площадки и аудитория:

- Habr rules: https://habr.com/docs/help/rules/
- Habr publications help: https://habr.com/ru/docs/help/publications/
- Habr partner/audience page: https://company.habr.com/ru/agency/
- vc.ru audience article: https://vc.ru/team/2629769-auditoriya-vc-ru-kto-chitaet-i-zachem
- vc.ru mediakit: https://vc.ru/team/1095451-mediakit
- Dzen audience summary via AdIndex: https://adindex.ru/news/media/2025/12/17/341039.phtml
- TenChat B2B examples and platform positioning: https://tenchat.ru/

AI, RAG, retrieval:

- Original RAG paper, Lewis et al., 2020: https://arxiv.org/abs/2005.11401
- NeurIPS RAG abstract: https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html
- Lost in the Middle, TACL/MIT Press: https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00638/119630/Lost-in-the-Middle-How-Language-Models-Use-Long
- Reciprocal Rank Fusion, SIGIR 2009 reference: https://dblp.org/rec/conf/sigir/CormackCB09
- Worksafety-superassistant repository: https://github.com/stas-ka/Worksafety-superassistant

n8n and workflow automation:

- n8n Docs: https://docs.n8n.io/
- n8n AI workflow tutorial: https://docs.n8n.io/advanced-ai/intro-tutorial/
- n8n AI agents page: https://n8n.io/ai-agents/
- n8n self-hosting docs: https://docs.n8n.io/hosting/installation/

AI coding and software quality:

- Stack Overflow 2025 AI survey: https://survey.stackoverflow.co/2025/ai
- Stack Overflow 2025 survey summary: https://stackoverflow.blog/2025/12/29/developers-remain-willing-but-reluctant-to-use-ai-the-2025-developer-survey-results-are-here/
- GitHub Copilot code quality study: https://github.blog/news-insights/research/does-github-copilot-improve-code-quality-heres-what-the-data-says/
- Kaspersky on vibe coding risks: https://www.kaspersky.com/blog/vibe-coding-2025-risks/54584/

SEO, AI search, structured data:

- Google helpful people-first content: https://developers.google.com/search/docs/fundamentals/creating-helpful-content
- Google guidance on generative AI content: https://developers.google.com/search/docs/fundamentals/using-gen-ai-content
- Google AI features and your website: https://developers.google.com/search/docs/appearance/ai-features
- Google Article structured data: https://developers.google.com/search/docs/appearance/structured-data/article
- Google SEO starter guide: https://developers.google.com/search/docs/fundamentals/seo-starter-guide

Персональные данные:

- 152-ФЗ на сайте Кремля: https://www.kremlin.ru/acts/bank/24154/print
- 152-ФЗ на сайте Правительства РФ: https://government.ru/docs/all/98196/
- 152-ФЗ на сайте приемной Государственной Думы: https://priemnaya.duma.gov.ru/ru/info/inf/fz/

Локальные материалы:

- `doc/marketing/*.pptx`: презентации Sintaris, продукты, партнерство, Taris
- `doc/architecture/knowledge-base.md`: Taris RAG architecture
- `doc/architecture/conversation.md`: Taris LLM context, memory, RAG injection
- `doc/architecture/features.md`: Taris mail/calendar/RAG/n8n/campaign/CRM features
- `doc/research/rag-memory-extended-research.md`: Worksafety patterns and Taris RAG adaptation
