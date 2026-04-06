"""Pipeline analytics logger for OpenClaw/Taris (§ logging & benchmarking).

Writes one JSONL record per pipeline stage to:
    ~/.taris/logs/pipeline_YYYY-MM-DD.jsonl

Each record contains:
    ts          – ISO-8601 timestamp
    session_id  – short random ID grouping STT+LLM+TTS from one request
    stage       – "stt" | "llm" | "tts" | "rag" | "decode"
    provider    – model/engine name (e.g. "faster_whisper:base", "ollama:qwen2:0.5b")
    lang        – language code ("ru", "en", "de")
    input_chars – character count of input text (or 0 for audio stages)
    output_chars– character count of output
    audio_ms    – audio duration in milliseconds (STT/TTS only, else 0)
    duration_ms – wall-clock time for this stage
    error       – error message if stage failed, else null

Usage:
    from core.pipeline_logger import PipelineLog
    pl = PipelineLog()                       # new request → new session_id
    pl.log_decode(audio_bytes, duration_ms)
    transcript = pl.timed_stt(lambda: stt_fn(pcm), audio_ms=1200, lang="ru")
    reply = pl.timed_llm(lambda: ask_llm(text), input_text=text)
    pl.timed_tts(lambda: tts_fn(reply), input_text=reply)

Or call the stage functions directly for async / pre-measured flows:
    pl.log("stt", provider="faster_whisper:base", lang="ru",
           input_chars=0, output_chars=len(text),
           audio_ms=1200, duration_ms=340)
"""
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TypeVar

# Log directory — respects TARIS_DIR env var like the rest of the app
_TARIS_DIR = os.environ.get("TARIS_DIR", str(Path.home() / ".taris"))
_LOG_DIR = Path(_TARIS_DIR) / "logs"

T = TypeVar("T")


class PipelineLog:
    """One instance per web/voice request.  Groups all stages by session_id."""

    def __init__(self, session_id: Optional[str] = None, user_id: Optional[str] = None):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.user_id = user_id or "anon"

    # ── Core write ────────────────────────────────────────────────────────────

    def log(
        self,
        stage: str,
        *,
        provider: str = "",
        lang: str = "ru",
        input_chars: int = 0,
        output_chars: int = 0,
        audio_ms: int = 0,
        duration_ms: int = 0,
        error: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "session_id": self.session_id,
            "user_id": self.user_id,
            "stage": stage,
            "provider": provider,
            "lang": lang,
            "input_chars": input_chars,
            "output_chars": output_chars,
            "audio_ms": audio_ms,
            "duration_ms": duration_ms,
            "error": error,
        }
        if extra:
            record.update(extra)
        _write_jsonl(record)

    # ── Timed helpers ─────────────────────────────────────────────────────────

    def timed_stt(
        self,
        fn: Callable[[], Optional[str]],
        *,
        audio_ms: int = 0,
        lang: str = "ru",
        provider: str = "",
    ) -> Optional[str]:
        """Run fn(), log STT stage with timing.  Returns transcript or None."""
        t0 = time.monotonic()
        error = None
        result = None
        try:
            result = fn()
        except Exception as e:
            error = str(e)
            raise
        finally:
            self.log(
                "stt",
                provider=provider or _stt_provider_label(),
                lang=lang,
                input_chars=0,
                output_chars=len(result) if result else 0,
                audio_ms=audio_ms,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=error,
            )
        return result

    def timed_llm(
        self,
        fn: Callable[[], Optional[str]],
        *,
        input_text: str = "",
        lang: str = "ru",
        provider: str = "",
    ) -> Optional[str]:
        """Run fn(), log LLM stage with timing.  Returns reply or None."""
        t0 = time.monotonic()
        error = None
        result = None
        try:
            result = fn()
        except Exception as e:
            error = str(e)
            raise
        finally:
            self.log(
                "llm",
                provider=provider or _llm_provider_label(),
                lang=lang,
                input_chars=len(input_text),
                output_chars=len(result) if result else 0,
                audio_ms=0,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=error,
            )
        return result

    def timed_tts(
        self,
        fn: Callable[[], Optional[bytes]],
        *,
        input_text: str = "",
        lang: str = "ru",
        provider: str = "piper",
    ) -> Optional[bytes]:
        """Run fn(), log TTS stage with timing.  Returns audio bytes or None."""
        t0 = time.monotonic()
        error = None
        result = None
        try:
            result = fn()
        except Exception as e:
            error = str(e)
            raise
        finally:
            audio_ms = int(len(result) / (16000 * 2) * 1000) if result else 0
            self.log(
                "tts",
                provider=provider,
                lang=lang,
                input_chars=len(input_text),
                output_chars=0,
                audio_ms=audio_ms,
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=error,
            )
        return result

    def log_decode(self, audio_bytes: bytes, duration_ms: int) -> None:
        """Log audio decode stage (ffmpeg WebM→PCM)."""
        audio_ms = int(len(audio_bytes) / (16000 * 2) * 1000)
        self.log("decode", provider="ffmpeg",
                 audio_ms=audio_ms, duration_ms=duration_ms)

    def log_rag(self, query: str, n_results: int, duration_ms: int, provider: str = "pgvector") -> None:
        """Log RAG retrieval stage."""
        self.log("rag", provider=provider,
                 input_chars=len(query), output_chars=n_results,
                 duration_ms=duration_ms)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _write_jsonl(record: dict) -> None:
    """Append one JSONL record to today's log file.  Thread-safe via append mode."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = _LOG_DIR / f"pipeline_{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # never raise from logger


def _stt_provider_label() -> str:
    """Return human-readable STT provider label from env."""
    provider = os.environ.get("STT_PROVIDER", "vosk")
    if provider == "faster_whisper":
        model = os.environ.get("FASTER_WHISPER_MODEL", "base")
        device = os.environ.get("FASTER_WHISPER_DEVICE", "cpu")
        return f"faster_whisper:{model}:{device}"
    return provider


def _llm_provider_label() -> str:
    """Return human-readable LLM provider label from env."""
    provider = os.environ.get("LLM_PROVIDER", "openclaw")
    if provider == "ollama":
        model = os.environ.get("OLLAMA_MODEL", "")
        return f"ollama:{model}" if model else "ollama"
    return provider


# ── Log reader (for /api/logs) ────────────────────────────────────────────────

def read_pipeline_logs(
    date: Optional[str] = None,
    last_n: int = 200,
    stage: Optional[str] = None,
) -> list[dict]:
    """Read pipeline log records.

    Args:
        date:   YYYY-MM-DD string (defaults to today)
        last_n: max records to return (most recent first)
        stage:  filter to specific stage ("stt", "llm", "tts", "rag")
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    log_file = _LOG_DIR / f"pipeline_{date}.jsonl"
    if not log_file.exists():
        return []
    records: list[dict] = []
    try:
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if stage is None or rec.get("stage") == stage:
                        records.append(rec)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return records[-last_n:]  # most recent N


def get_pipeline_stats(date: Optional[str] = None) -> dict:
    """Compute per-stage statistics for a given date.

    Returns dict keyed by stage with: count, avg_ms, p95_ms, error_count, providers.
    """
    records = read_pipeline_logs(date=date, last_n=10000)
    stats: dict[str, dict] = {}
    for rec in records:
        s = rec.get("stage", "?")
        if s not in stats:
            stats[s] = {"count": 0, "durations": [], "errors": 0, "providers": set()}
        stats[s]["count"] += 1
        stats[s]["durations"].append(rec.get("duration_ms", 0))
        if rec.get("error"):
            stats[s]["errors"] += 1
        if rec.get("provider"):
            stats[s]["providers"].add(rec["provider"])

    result = {}
    for s, d in stats.items():
        durs = sorted(d["durations"])
        p95_idx = max(0, int(len(durs) * 0.95) - 1)
        result[s] = {
            "count": d["count"],
            "avg_ms": int(sum(durs) / len(durs)) if durs else 0,
            "p95_ms": durs[p95_idx] if durs else 0,
            "min_ms": durs[0] if durs else 0,
            "max_ms": durs[-1] if durs else 0,
            "error_count": d["errors"],
            "providers": sorted(d["providers"]),
        }
    return result
