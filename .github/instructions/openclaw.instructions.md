---
applyTo: "src/core/bot_config.py,src/core/bot_llm.py,src/features/bot_voice.py,src/voice_assistant.py,src/setup/setup_voice_openclaw.sh,src/setup/setup_llm_openclaw.sh,src/tests/benchmark_stt.py"
---

# OpenClaw Variant — Coding Instructions

These instructions apply when editing OpenClaw-specific source files.

## Branch & Variant

- Active branch: **`taris-openclaw`** (not `master`, not `taris`)
- `DEVICE_VARIANT=openclaw` in `~/.taris/bot.env` activates all openclaw defaults
- Deployment: source in `sintaris-pl/src/` → deployed to `~/.taris/` (manual `cp`)
- Service: `systemctl --user restart taris-web` (NOT the Pi pattern)

## Key Constants (`bot_config.py`)

```python
DEVICE_VARIANT = os.environ.get("DEVICE_VARIANT", "taris")  # "openclaw" on this machine
STT_PROVIDER   = os.environ.get("STT_PROVIDER",   "faster_whisper" if DEVICE_VARIANT == "openclaw" else "vosk")
FASTER_WHISPER_MODEL   = os.environ.get("FASTER_WHISPER_MODEL", "base")
FASTER_WHISPER_DEVICE  = os.environ.get("FASTER_WHISPER_DEVICE", "cpu")
FASTER_WHISPER_COMPUTE = os.environ.get("FASTER_WHISPER_COMPUTE", "int8")
OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2:0.5b")
```

Always add new OpenClaw constants here with `os.environ.get()` + sensible default.

## STT Pattern — hybrid architecture

- **Hotword detection**: always Vosk (streaming, low-latency)
- **Command recognition**: faster-whisper (batch, after hotword triggers)
- Do NOT switch hotword detection to whisper — it buffers audio and kills latency

New STT providers:
1. Add constant to `bot_config.py`
2. Add `_stt_<provider>()` function to `bot_voice.py` (same signature as `_stt_faster_whisper`)
3. Add routing branch in `bot_voice.py` STT routing block
4. Update `voice_assistant.py` `main()` routing
5. Add voice opt key to `_VOICE_OPTS_DEFAULTS` if it needs a toggle

## LLM Pattern

- All LLM calls go through `ask_llm()` in `bot_llm.py`
- Add new providers to `_DISPATCH` dict: `"provider_name": _ask_provider`
- Provider functions must match signature: `_ask_provider(prompt: str, timeout: int) -> str`
- Set `LLM_PROVIDER=<name>` in `~/.taris/bot.env` (never hardcode)
- `LLM_LOCAL_FALLBACK=1` → Ollama is tried when primary provider fails

## Sync Rule — mandatory after every source change

```bash
cp /home/stas/projects/sintaris-pl/src/core/bot_config.py ~/.taris/core/
cp /home/stas/projects/sintaris-pl/src/core/bot_llm.py    ~/.taris/core/
cp /home/stas/projects/sintaris-pl/src/features/bot_voice.py ~/.taris/features/
systemctl --user restart taris-web
```

Never forget to sync — `~/.taris/` is NOT symlinked to the source tree.

## Test Protocol for OpenClaw Changes

```bash
# After any change to bot_config.py, bot_llm.py, or bot_voice.py:
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py \
  --test t_openclaw_stt_routing t_openclaw_ollama_provider

# After STT changes:
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py \
  --test t_faster_whisper_stt t_openclaw_stt_routing

# Full suite:
DEVICE_VARIANT=openclaw PYTHONPATH=src python3 src/tests/test_voice_regression.py
```

T29/T30 must always PASS. T27/T28 SKIP if packages not installed (OK).

## Regression Test IDs (T27–T30)

| ID | Function | What it tests |
|----|----------|---------------|
| T27 | `t_faster_whisper_stt` | faster-whisper model load + silence inference (SKIP if not installed) |
| T28 | `t_openclaw_llm_connectivity` | LLM provider connectivity (SKIP if ollama not running/not openclaw) |
| T29 | `t_openclaw_stt_routing` | `STT_PROVIDER` defaults correctly for openclaw vs taris |
| T30 | `t_openclaw_ollama_provider` | `_ask_ollama` in `_DISPATCH` + constants present |

## Documentation Maintenance

When adding OpenClaw features, update in the same commit:
- `doc/arch/openclaw-integration.md` — Implementation Status table + relevant section
- `TODO.md` — §19 or §25 items

Skill reference: `/taris-openclaw-setup` for setup/troubleshoot workflows.
