# Pi Targets (OpenClawPI / OpenClawPI2)

Raspberry Pi targets use the service files from `src/services/` in the repository root.

## Service files (in `src/services/`)

| File | Service | Scope |
|---|---|---|
| `taris-telegram.service` | Telegram bot | system (`/etc/systemd/system/`) |
| `taris-web.service` | Web UI (FastAPI) | system |
| `taris-voice.service` | Voice assistant | system |
| `taris-llm.service` | Local LLM helper | system |
| `taris-tunnel.service` | SSH reverse tunnel to VPS | system |
| `taris-pg-tunnel.service` | SSH tunnel to VPS PostgreSQL | system |
| `taris-logrotate` | Log rotation config | `/etc/logrotate.d/` |

## Key differences from OpenClaw (SintAItion/TariStation2)

| | Pi targets | OpenClaw targets |
|---|---|---|
| STT | Vosk (streaming) | faster-whisper |
| TTS | Piper binary | Piper binary (same) |
| LLM | Remote (OpenAI) | Ollama (local GPU/CPU) |
| Service scope | system (`sudo systemctl`) | user (`systemctl --user`) |
| `DEVICE_VARIANT` | `taris` | `openclaw` |
| `STORE_BACKEND` | `sqlite` | `postgres` |

## Setup

See `src/setup/` for Pi-specific setup scripts:
- `setup_voice.sh` — install Vosk, Piper, ffmpeg
- `setup_pi.sh` — base Pi configuration

## bot.env template for Pi

```
BOT_TOKEN=CHANGE_ME
ALLOWED_USERS=CHANGE_ME
ADMIN_USERS=CHANGE_ME
BOT_NAME=Taris
DEVICE_VARIANT=taris
STT_PROVIDER=vosk
LLM_PROVIDER=openai
OPENAI_API_KEY=CHANGE_ME
OPENAI_MODEL=gpt-4o-mini
STORE_BACKEND=sqlite
STORE_DB_PATH=/home/stas/.taris/taris.db
WEB_HOST=0.0.0.0
WEB_PORT=8080
ROOT_PATH=/taris
PIPER_BIN=/home/stas/.taris/piper/piper
PIPER_MODEL=/home/stas/.taris/ru_RU-irina-medium.onnx
```
