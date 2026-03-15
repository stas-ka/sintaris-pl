# Concept: Vibe Coding & Rapid UI Development for PicoUI Platform

**Version:** 0.2 · **Date:** March 2026 · **Updated:** March 13, 2026  
**Builds on:** [roadmap-web-ui.md](roadmap-web-ui.md) — the PicoUI Platform implementation roadmap (FastAPI-first, multi-backend, multi-channel)  
**Primary framework:** FastAPI + Jinja2 + HTMX (decided — see roadmap §1, §16 Decision Log D3)  
**Future enhancement:** NiceGUI (see roadmap §12)  
**Goal:** Define the artifacts, agents, and workflows needed for effective AI-assisted ("vibe coding") UI development across Telegram + Web + future messenger channels, with **Rapid Design** as the #1 priority.

---

## Table of Contents

1. [GitHub Copilot — UI Development Capability Assessment](#1-github-copilot--ui-development-capability-assessment)
2. [What Must Be Defined for Effective Vibe Coding](#2-what-must-be-defined-for-effective-vibe-coding)
3. [Custom Copilot Agent: PicoUI Agent](#3-custom-copilot-agent-picoui-agent)
4. [Solution Comparison — Rapid Design Priority](#4-solution-comparison--rapid-design-priority)
5. [Recommended Approach](#5-recommended-approach)
6. [Screen Spec Format — Customer Requirements as Code](#6-screen-spec-format--customer-requirements-as-code)
7. [Implementation Roadmap](#7-implementation-roadmap)

---

## 1. GitHub Copilot — UI Development Capability Assessment

### 1.1 Available Copilot Features for This Project

| Feature | Status in workspace | UI dev relevance |
|---|---|---|
| **`copilot-instructions.md`** | Exists (`.github/copilot-instructions.md`) — 400+ lines of project context, deployment patterns, module dependency chain, voice regression tests | High — Copilot already knows the full bot architecture, all modules, callback keys, deployment workflow |
| **`AGENTS.md`** | Exists — remote host access, bot version, vibe coding protocol with complexity tracking | High — provides operational context and session tracking |
| **Custom agents (`.agent.md`)** | Not present — none created yet | **Critical gap** — a PicoUI agent would dramatically accelerate screen generation |
| **Prompt files (`.prompt.md`)** | Not present | **Opportunity** — reusable prompts for "generate screen X" / "add widget Y" |
| **Skills (`SKILL.md`)** | Only built-in `agent-customization` skill | Opportunity — a PicoUI skill could encode the Screen DSL rules |
| **MCP servers** | PostgreSQL available (not relevant); Pylance available | Low — current stack is file-based, no DB |

### 1.2 What Copilot Does Well for This Project

| Capability | How it helps UI dev | Quality assessment |
|---|---|---|
| **Code generation from context** | Given `bot_ui.py` (Screen DSL) + one example action handler, Copilot generates new Screen-returning functions accurately | Excellent — dataclass-based DSLs are Copilot's sweet spot; type hints + IDE autocomplete guide generation |
| **Jinja2 template generation** | Given a base template + widget type, Copilot generates HTMX-enabled templates | Good — HTMX is well-represented in training data |
| **i18n string generation** | Given existing `strings.json` structure, Copilot generates new keys in all 3 languages | Good — pattern is simple JSON; ru/en reliable, de occasionally needs manual fix |
| **Callback wiring** | Given the dispatch pattern in `telegram_menu_bot.py`, Copilot generates new `elif data.startswith(...)` branches | Excellent — the pattern is extremely consistent |
| **FastAPI route generation** | Given one route example, generates CRUD routes with auth checks | Excellent — FastAPI is one of the best-supported frameworks |
| **Test generation** | Given existing `test_voice_regression.py` pattern, generates new test cases | Good — follows assertion patterns well |
| **CSS/styling** | Pico CSS is classless — not much CSS to write; Copilot handles overrides well | Good |

### 1.3 Where Copilot Needs Guidance

| Gap | Why | Mitigation |
|---|---|---|
| **Dual-renderer consistency** | Copilot may generate a Telegram button without the corresponding web template (or vice versa) | Screen DSL enforces: one Screen → both renderers. The agent/prompt must require both outputs. |
| **Widget type selection** | May generate raw `bot.send_message()` instead of Screen objects when modifying old-style handlers | Custom instructions must say "NEVER call bot.send_message() directly — always return a Screen object" |
| **i18n completeness** | May add a Russian string without the English/German equivalent | Prompt must require all 3 language keys |
| **Picoclaw-specific patterns** | Fresh conversation may not know the callback dispatch pattern, voice opt toggle pattern | Solved by `.github/copilot-instructions.md` + `dev-patterns.md` (already loaded as context) |
| **LLM backend switching** | Copilot doesn't know about `bot_llm.py` pluggable backends (PicoClaw CLI/Gateway, OpenClaw, OpenAI) | Agent prompt must include `bot_llm.py` interface; always call `ask_llm()`, never `_ask_picoclaw()` directly |
| **Multi-channel rendering** | May generate Telegram-specific code instead of using the Screen DSL + renderer pipeline | Agent rules enforce: generate Screen objects only — renderers handle channel differences |

### 1.4 Overall Copilot Readiness Score

| Dimension | Score (1–5) | Notes |
|---|---|---|
| Project context available | **5** | `copilot-instructions.md` + `AGENTS.md` + `dev-patterns.md` + `bot-code-map.md` already cover everything |
| Screen DSL code generation | **4** | Excellent once `bot_ui.py` with types exists; Copilot autocompletes widget trees naturally |
| Web template generation (HTMX+Jinja2) | **5** | FastAPI + Jinja2 + HTMX are among the best-supported frameworks in Copilot training data |
| LLM backend abstraction | **4** | `bot_llm.py` follows a simple `ask_llm()` interface — Copilot generates calls correctly once it sees the interface |
| Multi-channel consistency | **2** | Requires explicit agent rules — Copilot won't automatically generate both renderers |
| Full-stack screen generation | **3** | Needs a custom agent/prompt to orchestrate: action handler + Jinja2 template + i18n strings + callback wiring |

**Conclusion:** Copilot is well-suited for this project. The existing documentation provides excellent context. FastAPI + Jinja2 + HTMX being among Copilot's best-supported frameworks maximises code generation quality. The main gap is a **custom agent** that ensures multi-channel completeness and follows the Screen DSL.

---

## 2. What Must Be Defined for Effective Vibe Coding

Effective AI-assisted UI development ("vibe coding") requires **three layers of artifacts**:

### 2.1 Layer 1 — Project Context (already exists)

These files are already loaded into every Copilot session:

| Artifact | File | Purpose |
|---|---|---|
| Architecture overview | `doc/architecture.md` | Module structure, process hierarchy, dependencies |
| Code map | `doc/bot-code-map.md` | Every function, line number, callback key |
| Dev patterns | `doc/dev-patterns.md` | Copy-paste patterns for callbacks, voice opts, i18n, multi-step flows |
| Copilot instructions | `.github/copilot-instructions.md` | Workspace rules, deployment workflow, voice tests |
| Session tracking | `AGENTS.md` | Vibe coding protocol, remote access, version |

**Assessment: Complete.** No additional work needed.

### 2.2 Layer 2 — UI-Specific Artifacts (must be created)

| Artifact | File (proposed) | Purpose | Priority |
|---|---|---|---|
| **Screen DSL types** | `src/bot_ui.py` | `Screen`, `Button`, `ButtonRow`, `Toggle`, `TextInput`, `Card`, `AudioPlayer`, etc. — Python dataclasses | **P0 — must exist before any vibe coding** |
| **LLM backend abstraction** | `src/bot_llm.py` | Pluggable `ask_llm()` interface — PicoClaw CLI/Gateway, OpenClaw, OpenAI direct (see roadmap §4.2) | **P0** |
| **Widget catalog** | `doc/widget-catalog.md` | Visual reference: for each widget type, show Telegram rendering + Web rendering + code example | P0 |
| **Screen spec format** | `doc/screen-spec-format.md` | YAML/JSON format for describing a screen as a customer requirement (see §6) | P1 |
| **Example screens** | `src/bot_actions.py` (first 3 screens) | Working examples of action handlers returning Screen objects — Copilot learns from these | P0 |
| **Jinja2 base templates** | `src/web/templates/` | Base layout + one widget template per type — Copilot generates new pages from these | P0 |
| **Jinja2 web renderer** | `src/render_web.py` | `Screen` → Jinja2 template context + HTMX partials — the primary web channel | P1 |

### 2.3 Layer 3 — Agent Configuration (must be created)

| Artifact | File (proposed) | Purpose | Priority |
|---|---|---|---|
| **PicoUI Agent** | `.github/pico-ui.agent.md` | Custom Copilot agent mode for UI generation (see §3) | P0 |
| **Screen generation prompt** | `.github/prompts/generate-screen.prompt.md` | Reusable prompt: "Generate a complete screen from this spec" | P1 |
| **Widget addition prompt** | `.github/prompts/add-widget.prompt.md` | "Add widget X to screen Y" | P2 |
| **Migrate handler prompt** | `.github/prompts/migrate-handler.prompt.md` | "Convert old Telegram handler to Screen-based action" | P1 |

### 2.4 Minimum Viable Vibe Coding Kit

To start productive AI-assisted UI development, create these **5 files** in order:

```
1. src/bot_ui.py              ← Screen + Widget dataclasses (the DSL)
2. src/bot_actions.py          ← 3 example action handlers
3. doc/widget-catalog.md       ← Visual reference
4. .github/pico-ui.agent.md   ← Custom Copilot agent
5. .github/prompts/generate-screen.prompt.md  ← Reusable generation prompt
```

After these exist, a typical vibe coding interaction becomes:

> **User:** `@pico-ui Generate the calendar month view screen. Events are colored dots on each day. Tapping a day shows that day's events.`  
> **Copilot (PicoUI agent):** Generates `action_calendar_month()` in `bot_actions_calendar.py` + `calendar_month.html` Jinja2 template + 3 new `strings.json` keys in ru/de/en + callback wiring in `telegram_menu_bot.py`.

---

## 3. Custom Copilot Agent: PicoUI Agent

### 3.1 Agent Definition

```yaml
# .github/pico-ui.agent.md
---
name: PicoUI
description: "Generates PicoUI Platform screens for Telegram, Web, and future messenger channels from natural language or screen specs. Knows the Screen DSL, FastAPI+Jinja2 templates, multi-backend LLM calls, and i18n."
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - grep_search
  - semantic_search
  - run_in_terminal
---
```

### 3.2 Agent System Prompt (content of the `.agent.md`)

The PicoUI agent's instructions would contain:

```markdown
You are PicoUI — a specialised agent for generating PicoUI Platform user interface screens.

## Your capabilities
1. Generate **action handlers** that return `Screen` objects (from `bot_ui.py`)
2. Generate **Jinja2 web templates** with HTMX interactivity for the FastAPI web UI
3. Generate **i18n strings** in all 3 languages (ru/de/en) in `strings.json`
4. Wire **callback dispatch** in `telegram_menu_bot.py`
5. Migrate existing Telegram-coupled handlers to the Screen DSL
6. Use **`ask_llm()`** from `bot_llm.py` for all LLM calls — never call `_ask_picoclaw()` directly

## Rules
- ALWAYS return a `Screen` object from action handlers — never call `bot.send_message()` directly
- ALWAYS add strings to ALL THREE language sections in `strings.json`
- ALWAYS update `doc/bot-code-map.md` callback key table when adding new callbacks
- Use `_t(user.chat_id, key)` for ALL user-visible text — never hardcode
- Use `ask_llm(prompt, timeout)` for LLM calls — it routes to the active backend automatically
- Follow the widget types defined in `src/bot_ui.py` — do not invent new widget types without asking
- When adding a new screen, generate BOTH: action handler + Jinja2 template + Telegram renderer mapping
- Access checks: every handler must start with `if not _is_allowed(user.chat_id): return deny_screen()`
- CRM context: new screens may serve as CRM module foundations — keep them generic and reusable

## References
- Screen DSL types: `src/bot_ui.py`
- LLM backend: `src/bot_llm.py` — pluggable `ask_llm()` interface
- Widget catalog: `doc/widget-catalog.md`
- Existing action examples: `src/bot_actions.py`
- Dev patterns: `doc/dev-patterns.md`
- Code map: `doc/bot-code-map.md`
- i18n strings: `src/strings.json`
- Platform roadmap: `concept/web-ui/roadmap-web-ui.md`
- Multi-channel renderers: `concept/web-ui/roadmap-web-ui.md` §9

## Output format for "Generate screen" requests
For each screen, produce:
1. **Action handler** — Python function in the appropriate `bot_actions_*.py` file
2. **Jinja2 web template** — file in `src/web/templates/screens/` with HTMX attributes
3. **i18n strings** — new keys added to `src/strings.json` (all 3 langs)
4. **Callback wiring** — new `elif` branch(es) in `telegram_menu_bot.py:callback_handler()`
5. **Code map update** — new rows in `doc/bot-code-map.md` callback key table
```

### 3.3 How It Works in Practice

**Scenario A — New screen from natural language:**
```
User: @pico-ui Create a "Password Generator" screen.
      User enters desired length (default 16) and checkboxes for uppercase,
      lowercase, digits, symbols. Button "Generate" shows the password in a
      code block with a "Copy" button. Add a "Generate another" button.

PicoUI agent:
  1. Reads bot_ui.py   → knows available widget types
  2. Reads bot_actions.py → sees example patterns
  3. Generates:
     - action_password_gen() → Screen with TextInput(length) + 4 Toggles + Button
     - action_password_result(params) → Screen with CodeBlock + ButtonRow
     - password_gen.html + password_result.html Jinja2 templates
     - strings.json: "pwd_title", "pwd_length", "pwd_generate", etc. × 3 langs
     - telegram_menu_bot.py: elif data == "pwd_gen": ...
```

**Scenario B — Screen from YAML spec (customer requirement):**
```yaml
# screens/password_generator.yaml
screen: password_generator
title_key: pwd_title
widgets:
  - type: text_input
    field: length
    default: "16"
    key: pwd_length_label
  - type: toggle_group
    items:
      - key: pwd_uppercase
        default: true
      - key: pwd_lowercase
        default: true
      - key: pwd_digits
        default: true
      - key: pwd_symbols
        default: false
  - type: button
    label_key: pwd_generate
    action: pwd_result
  - type: button
    label_key: back
    action: menu
```

The PicoUI agent reads this YAML and generates all 5 output artifacts.

**Scenario C — Migrate existing handler:**
```
User: @pico-ui Migrate _handle_notes_menu() from bot_handlers.py to the Screen DSL.

PicoUI agent:
  1. Reads current _handle_notes_menu() code
  2. Identifies: 2 buttons + back button + text
  3. Generates action_notes_menu() returning Screen with ButtonRow + Button
  4. Updates bot_handlers.py to call render(action_notes_menu(user), chat_id)
  5. Generates notes_menu.html template
```

---

## 4. Solution Comparison — Rapid Design Priority

The user's main criterion is **Rapid Design for web and messenger UIs**. Below is a comparative analysis of 5 approaches, scored on speed-to-first-screen and ongoing feature velocity.

### 4.1 Comparison Matrix

| Criterion (weight) | A: FastAPI + HTMX + Jinja2 | B: NiceGUI (full Python) | C: Streamlit | D: Gradio | E: NiceGUI + Telegram bridge |
|---|---|---|---|---|---|
| **Rapid first screen (25%)** | Medium — need templates + routes + CSS | **Fast** — 5 lines of Python = working UI | **Fastest** — 3 lines = app | Fast — `gr.Interface()` | **Fast** — same as B, plus Telegram |
| **Rapid new feature (25%)** | Medium — action handler + template + route | **Fast** — one Python function | Slow — reruns entire script on interaction | Medium — component-based | **Fast** |
| **Telegram + Web from one source (20%)** | Yes — via Screen DSL + 2 renderers | Partial — NiceGUI is web-only; Telegram needs separate renderer | **No** — web only | **No** — web only | **Yes** — NiceGUI for web + pyTelegramBotAPI for Telegram, shared Screen DSL |
| **Copilot generation quality (15%)** | **Excellent** — FastAPI, Jinja2, HTMX all well-known | Good — smaller training corpus | Good — Streamlit well-known | Good — Gradio well-known | Good — NiceGUI + Telegram both supported |
| **Pi 3 B+ RAM (10%)** | **30 MB** | 60 MB | **120+ MB** — disqualified | 80+ MB | 60 MB |
| **Customizability (5%)** | **Full** — raw HTML/CSS control | High — Quasar/Tailwind | Low — rigid layout | Low — fixed layouts | High |

### 4.2 Speed-to-First-Screen Comparison

How quickly can each approach show a working "Notes List" screen with 3 notes and action buttons?

| Approach | Setup time | First screen code | Total |
|---|---|---|---|
| **A: FastAPI + HTMX** | ~2 h (FastAPI app, base template, Pico CSS, auth stub) | ~30 min (route + Jinja2 template + action handler) | **~2.5 h** |
| **B: NiceGUI** | ~30 min (`pip install nicegui`, `ui.run()`, dark mode) | ~15 min (Python-only, no template) | **~45 min** |
| **C: Streamlit** | ~15 min (`pip install streamlit`, `streamlit run`) | ~10 min | **~25 min** — but no Telegram, no buttons, 120 MB RAM |
| **D: Gradio** | ~15 min | ~10 min | **~25 min** — but no Telegram integration |
| **E: NiceGUI + TG bridge** | ~45 min (NiceGUI + Screen DSL + render bridge) | ~20 min | **~1 h** |

### 4.3 Ongoing Feature Velocity (screens per day with Copilot)

Once the framework is set up, how many new screens can a developer produce per day using Copilot?

| Approach | Screens/day (with Copilot) | Bottleneck |
|---|---|---|
| **A: FastAPI + HTMX** | 6–8 | Writing Jinja2 templates (even with Copilot generating them) |
| **B: NiceGUI** | **10–15** | Almost no bottleneck — Python-only, Copilot autocompletes `ui.*` calls |
| **B+agent: NiceGUI + PicoUI agent** | **12–20** | Agent generates complete screen from one-line description |
| **E: NiceGUI + TG bridge** | 8–12 | Must verify both renderers work |

### 4.4 Disqualified Options

| Option | Reason |
|---|---|
| **C: Streamlit** | 120+ MB RAM (Pi 3 B+ has 1 GB total, already using ~640 MB). No WebSocket. No real-time buttons. No Telegram integration. Reruns entire script on each interaction. |
| **D: Gradio** | 80+ MB RAM baseline. Designed for ML demos, not interactive apps. No Telegram integration. Limited custom layouts. No persistent state. |
| **React/Vue/Svelte SPA** | Requires Node.js build toolchain. 50–150 KB bundles. Separate API layer. Copilot generates well but doubles the codebase (frontend + backend). Slowest rapid design. |

### 4.5 Final Three Contenders

| Rank | Approach | Best for | Trade-off |
|---|---|---|---|
| **#1** | **FastAPI + HTMX + Jinja2 + PicoUI Agent** | **Maximum control + multi-channel** — lightest RAM (30 MB), full HTML/CSS control, proven mockups already exist, excellent Copilot generation, CRM-ready | Need templates per screen (mitigated by PicoUI agent + YAML specs) |
| **#2** | **NiceGUI + Screen DSL + PicoUI Agent** | **Fastest rapid prototyping** — Python-only, one file per screen | +30 MB RAM; weaker Copilot support; Quasar JS bundle to browser |
| **#3** | **Hybrid: FastAPI for production + NiceGUI for internal admin** | **Best of both** — FastAPI public-facing + NiceGUI for quick admin tools | Two renderers to maintain |

> **Decision (March 2026):** FastAPI + HTMX + Jinja2 selected as primary framework. Working mockups already exist in `mockups-fastapi/`. NiceGUI remains available as future enhancement (roadmap §12). See roadmap §16 Decision Log D3 for full rationale.

---

## 5. Recommended Approach

### Primary: FastAPI + HTMX + Jinja2 + Screen DSL + PicoUI Agent

**Why FastAPI wins for production:**

1. **Lightest RAM footprint.** ~30 MB vs NiceGUI's 60 MB — critical on Pi 3 B+ (1 GB total, ~640 MB already used by bot + voice).

2. **Proven mockups.** `mockups-fastapi/` already demonstrates every screen (Dashboard, Chat, Notes, Calendar, Mail, Voice, Admin) with a polished dark theme, HTMX interactivity, and responsive CSS. Zero design work remaining.

3. **Copilot's best-supported stack.** FastAPI, Jinja2, and HTMX are among the most widely represented frameworks in Copilot training data. Code generation is excellent.

4. **Full HTML/CSS control.** Custom themes, responsive layouts, accessibility, CRM-customer branding — all possible without framework constraints.

5. **HTMX = minimal JS.** Interactive updates via HTTP attributes (`hx-get`, `hx-post`, `hx-swap`), no custom JavaScript needed for 90% of screens.

6. **Multi-backend ready.** `bot_llm.py` pluggable interface works identically whether the web route calls `ask_llm()` or the Telegram handler does.

7. **Multi-channel via Screen DSL.** Action handlers return `Screen` objects. `render_telegram.py` translates to `bot.send_message()`. `render_web.py` translates to Jinja2 template context. Future renderers (WhatsApp, Discord, Slack, Matrix) add ~50–100 lines each (see roadmap §9).

8. **CRM-ready.** Clean separation of business logic (action handlers) from presentation (renderers) means CRM modules plug in at the action layer without touching any channel-specific code.

### Screen DSL → FastAPI + Jinja2 Rendering Example

```python
# bot_ui.py — the DSL (framework-agnostic)
@dataclass
class Screen:
    text: str
    widgets: list[Widget]
    audio: bytes | None = None

# render_web.py — FastAPI + Jinja2 renderer
from fastapi import Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="src/web/templates")

def render_web(screen: Screen, request: Request, user: dict):
    """Render a Screen object as a Jinja2 HTML response."""
    return templates.TemplateResponse("screen.html", {
        "request": request,
        "user": user,
        "title": screen.text,
        "widgets": screen.widgets,
        "audio": screen.audio,
    })
```

```html
{# src/web/templates/screen.html — generic Screen renderer #}
{% extends "base.html" %}
{% block content %}
<h2>{{ title }}</h2>
{% for widget in widgets %}
  {% if widget.__class__.__name__ == 'Button' %}
    <button hx-get="/action/{{ widget.action }}" hx-target="#main">{{ widget.label }}</button>
  {% elif widget.__class__.__name__ == 'ButtonRow' %}
    <div class="grid">
      {% for btn in widget.buttons %}
        <button hx-get="/action/{{ btn.action }}" hx-target="#main">{{ btn.label }}</button>
      {% endfor %}
    </div>
  {% elif widget.__class__.__name__ == 'Card' %}
    <article>
      <header>{{ widget.title }}</header>
      {{ widget.body | safe }}
    </article>
  {% elif widget.__class__.__name__ == 'Toggle' %}
    <label><input type="checkbox" hx-post="/toggle/{{ widget.key }}"
      {% if widget.value %}checked{% endif %}> {{ widget.label }}</label>
  {% elif widget.__class__.__name__ == 'TextInput' %}
    <input type="text" placeholder="{{ widget.prompt }}" name="{{ widget.field_name }}"
      hx-post="/submit/{{ widget.field_name }}" hx-trigger="keyup[key=='Enter']">
  {% endif %}
{% endfor %}
{% endblock %}
```

```python
# render_telegram.py — Telegram renderer (same Screen objects)
def render_telegram(screen: Screen, chat_id: int):
    """Render a Screen object as Telegram messages."""
    kb = InlineKeyboardMarkup()
    for widget in screen.widgets:
        match widget:
            case Button(label=label, action=action):
                kb.add(InlineKeyboardButton(label, callback_data=action))
            case ButtonRow(buttons=buttons):
                kb.add(*[InlineKeyboardButton(b.label, callback_data=b.action) for b in buttons])
            # ... etc
    bot.send_message(chat_id, screen.text, reply_markup=kb, parse_mode="Markdown")
```

### RAM Budget (FastAPI on Pi 3 B+)

| Component | RAM |
|---|---|
| OS + kernel | 250 MB |
| Python bot + Vosk | 240 MB |
| Piper ONNX (active) | 150 MB |
| **FastAPI + uvicorn** | **30 MB** |
| **Total** | **670 MB** |
| **Remaining** | **~330 MB** — comfortable with zram |

### NiceGUI as Future Enhancement

NiceGUI remains available as a future option (roadmap §12). If rapid prototyping of internal/admin tools becomes a priority, NiceGUI can run alongside FastAPI on the same uvicorn server. The Screen DSL makes this a renderer swap, not a rewrite.

---

## 6. Screen Spec Format — Customer Requirements as Code

The key innovation for vibe coding: **customer requirements expressed as structured screen specs**. The PicoUI agent reads these and generates all implementation artifacts.

### 6.1 YAML Screen Spec Format

```yaml
# File: screens/notes_menu.yaml
screen: notes_menu
title_key: notes_title
description: "Notes submenu with create, list, and back buttons"
access: all_approved    # all_approved | admin_only | guest_ok

widgets:
  - type: button_row
    buttons:
      - label_key: note_create_btn
        action: note_create
        icon: "➕"
      - label_key: note_list_btn
        action: note_list
        icon: "📋"

  - type: button
    label_key: back
    action: menu
    style: secondary

i18n:
  notes_title:
    ru: "📝 Заметки"
    de: "📝 Notizen"
    en: "📝 Notes"
  note_create_btn:
    ru: "➕ Создать"
    de: "➕ Erstellen"
    en: "➕ Create"
  note_list_btn:
    ru: "📋 Список"
    de: "📋 Liste"
    en: "📋 List"
```

### 6.2 Complex Screen Spec Example

```yaml
# screens/calendar_month.yaml
screen: calendar_month
title_key: cal_month_title
description: "Monthly calendar view with event dots and day tap interaction"
access: all_approved

state:
  - name: current_month
    type: date
    default: today

widgets:
  - type: button_row
    buttons:
      - label: "◀"
        action: cal_month_prev
      - label: "{month_name} {year}"
        action: none
        style: header
      - label: "▶"
        action: cal_month_next

  - type: custom
    component: month_grid
    props:
      events: "cal_load(user.chat_id)"
      on_day_click: "cal_day:{date}"

  - type: button_row
    buttons:
      - label_key: cal_add_btn
        action: cal_add
        icon: "➕"
      - label_key: cal_console_btn
        action: cal_console
        icon: "💬"

  - type: button
    label_key: back
    action: menu

telegram_notes: |
  Telegram cannot render a month grid. Instead show a text list:
  "📅 March 2026\n• 5 Mar — Meeting\n• 12 Mar — Doctor"
  with per-event buttons below.
```

### 6.3 How Screen Specs Drive Vibe Coding

```
Customer describes feature
        │
        ▼
Developer writes YAML screen spec (5 min)
        │
        ▼
PicoUI agent reads spec + bot_ui.py + strings.json
        │
        ├── Generates action handler (Python)
        ├── Generates Jinja2 + HTMX renderer code
        ├── Generates i18n strings (3 languages)
        ├── Generates callback wiring
        └── Generates migration from old handler (if exists)
        │
        ▼
Developer reviews, tests, deploys (5–15 min)
```

**Average time per screen: 10–20 minutes** (vs 1–2 hours manual).

---

## 7. Implementation Roadmap

Aligned with the 5-phase plan in `roadmap-web-ui.md`.

### P0 — Core Extraction (Days 1–3)

| # | Task | Output |
|---|---|---|
| 0.1 | Create `src/bot_ui.py` — all 17 widget dataclasses + `Screen` + `UserContext` | Foundation DSL |
| 0.2 | Create `src/bot_llm.py` — `ask_llm()` pluggable backend (PicoClaw CLI default) | LLM backend abstraction |
| 0.3 | Create `src/bot_auth.py` — JWT tokens + bcrypt passwords + Telegram Login Widget | Shared auth module |
| 0.4 | Create `src/bot_actions.py` — 3 example screens (menu, notes list, note view) | Working examples for Copilot |
| 0.5 | Create `src/render_telegram.py` — `Screen` → `bot.send_message()` | Telegram keeps working |
| 0.6 | Create `.github/pico-ui.agent.md` — PicoUI agent definition with rules | Custom agent available |
| 0.7 | Create `doc/widget-catalog.md` — visual reference of all widget types | Documentation |

### P1 — FastAPI Web Server (Days 4–6)

| # | Task | Output |
|---|---|---|
| 1.1 | `pip install fastapi uvicorn jinja2` on Pi; create `src/web/app.py` | FastAPI running on Pi |
| 1.2 | Create `src/render_web.py` — `Screen` → Jinja2 template context | Web pages from same Screen objects |
| 1.3 | Port `mockups-fastapi/` templates to live Jinja2 (Pico CSS dark theme) | Polished UI from day one |
| 1.4 | Implement auth: login page + JWT session + Telegram Login Widget | Secure web access |
| 1.5 | 5 core screens: Menu, Chat, Notes (list/view/edit) | Usable web interface |
| 1.6 | Create `src/services/picoclaw-web.service` | Auto-start web server |

### P2 — Vibe-Code All Screens (Days 7–10)

Using the PicoUI agent, rapidly generate:

| Day | Screens | Method |
|---|---|---|
| 7 | Calendar (month view, add, detail, console) — 5 screens | PicoUI agent from YAML specs |
| 8 | Mail (digest, setup wizard) — 3 screens | PicoUI agent |
| 9 | Admin (panel, users, LLM, voice opts) — 4 screens | PicoUI agent |
| 10 | Voice, Profile, Error Protocol — 3 screens + polish | PicoUI agent |

**Total: ~18 screens in 4 days** — achievable with PicoUI agent generating 4–5 screens/day.

### P3 — Migrate Existing Handlers (Days 11–13)

Replace all 19 keyboard builders and 14 multi-step flows with Screen-based action handlers. Both Telegram and Web render from the same code. Voice pipeline enhancements: browser recording + audio playback.

### P4 — Full Migration & CRM-Ready (Days 14+)

Calendar month grid, notes Markdown preview, audio waveform, drag-and-drop, keyboard shortcuts, push notifications, PWA manifest. All screens unified under Screen DSL. CRM modules plug in at the action layer.

---

## Appendix A — Comparison Summary Table

| Criterion | FastAPI+HTMX (chosen) | NiceGUI (future) | Streamlit | Gradio |
|---|---|---|---|---|
| **First screen speed** | 2 h (with mockups) | 45 min | 25 min | 25 min |
| **Ongoing velocity** | 6–8 screens/day | 10–15 screens/day | 3–4 | 3–4 |
| **Multi-channel via DSL** | ✅ | ✅ | ❌ | ❌ |
| **Pi 3 B+ RAM** | **30 MB** | 60 MB | 120+ MB | 80+ MB |
| **Copilot quality** | **Excellent** | Good | Good | Good |
| **HTML/CSS control** | **Full** | High (via Tailwind) | None | None |
| **Dark mode** | Pico CSS auto | Built-in | Manual | Auto |
| **WebSocket/SSE** | Both | Built-in | None | Limited |
| **Auth** | Custom (JWT+bcrypt) | Built-in storage | None | Limited |
| **Testing** | pytest + httpx | Built-in (User fixture) | None | None |
| **LLM backend abstraction** | ✅ via `bot_llm.py` | ✅ via `bot_llm.py` | ❌ | ❌ |
| **CRM-ready** | ✅ action layer | ✅ action layer | ❌ | ❌ |
| **Widget count** | ~17 (custom DSL) | 80+ (Quasar) | ~30 | ~40 |

## Appendix B — Risk Analysis

| Risk | Impact | Mitigation |
|---|---|---|
| FastAPI 30 MB + bot 640 MB approaching 1 GB | Tight RAM under simultaneous TTS + web load | Monitor RSS; enable zram; consider Pi 4 upgrade |
| Jinja2 template errors are runtime-only | Broken screens discovered late | PicoUI agent pre-validates; `pytest + httpx` test suite catches rendering errors |
| HTMX complexity for real-time features | Chat / voice need WebSocket, not just partial swaps | Use SSE for streaming; WebSocket only for true bidirectional (voice) |
| Screen DSL doesn't cover a future UI pattern | Need to extend the DSL | Designed with `Custom` widget type as escape hatch; extend `bot_ui.py` as needed |
| Multi-renderer drift (Telegram shows X, Web shows Y) | User confusion | All screens generated from same action handler via PicoUI agent; automated test compares both renderers |
| CRM customer needs non-standard UI | Custom per-customer templates required | Screen DSL supports custom widgets; Jinja2 template inheritance for branding overrides |

## Appendix C — Decision Log: FastAPI over NiceGUI

The original concept (concept-web-interface.md) recommended **FastAPI + HTMX + Jinja2 + Pico CSS**. A later evaluation considered NiceGUI for rapid prototyping speed.

**Final decision (March 2026): FastAPI + HTMX + Jinja2 selected as the primary framework.**

| Factor | FastAPI+HTMX | NiceGUI | Decision |
|---|---|---|---|
| Lines of code per screen | ~80 (handler + template + route) | ~20 (Python function only) | NiceGUI faster, but PicoUI agent closes the gap |
| RAM on Pi 3 B+ | **30 MB** | 60 MB | FastAPI — every MB matters on 1 GB |
| Proven mockups exist | ✅ `mockups-fastapi/` | ❌ | FastAPI — zero design work remaining |
| Copilot code quality | **Excellent** | Good | FastAPI — ubiquitous in training data |
| Full HTML/CSS control | **Full** | Via escape hatch | FastAPI — critical for CRM branding |
| Multi-channel rendering | Via Screen DSL | Via Screen DSL | Tie |
| CRM customization | Template inheritance | Limited | FastAPI |

**NiceGUI remains available as a future enhancement** (see roadmap §12). The Screen DSL ensures switching from Jinja2 to NiceGUI rendering is a renderer swap — not a rewrite.

---

*This document complements [concept-web-interface.md](concept-web-interface.md) and implements the architecture defined in [roadmap-web-ui.md](roadmap-web-ui.md). The Screen DSL, pluggable LLM backend (`bot_llm.py`), and multi-channel renderers form the foundation for both the Telegram bot and the PicoUI web platform.*
