"""Voice pipeline debug recorder.

Saves every stage of a voice request to a timestamped directory so the
recordings can be inspected or re-used as regression-test fixtures.

Usage (in bot_web.py voice endpoints):

    from core.voice_debug import VoiceDebugSession
    dbg = VoiceDebugSession(user_id=user.get("sub", "anon"))

    dbg.save_raw_audio(audio_data, ext="webm")
    dbg.save_pcm(raw_pcm, sample_rate=16000)
    dbg.save_stt(user_text)
    dbg.save_llm_answer(reply_text)
    dbg.save_tts_input(tts_text)
    dbg.save_tts_output(ogg_bytes)
    dbg.finalise(pipeline_dict)        # writes pipeline.json and index entry

Enable with VOICE_DEBUG_MODE=1 in bot.env.
Debug files are written to VOICE_DEBUG_DIR (default ~/.taris/debug/voice/).

File layout per session:
    YYYY-MM-DD_HH-MM-SS_mmm__<user>/
        input.webm      raw browser audio (or .ogg / .wav)
        decoded.pcm     16 kHz mono s16le raw PCM
        stt.txt         transcript from STT
        llm_answer.txt  LLM reply text
        tts_input.txt   text fed to Piper TTS (after cleaning)
        tts_output.ogg  synthesised OGG Opus audio
        pipeline.json   full stage timings + metadata
"""

from __future__ import annotations

import json
import logging
import os
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("taris")

# Resolved at import time from bot_config via env vars already loaded.
_DEBUG_MODE: bool = os.environ.get("VOICE_DEBUG_MODE", "0").lower() in ("1", "true", "yes")
_DEBUG_DIR: Path = Path(os.environ.get(
    "VOICE_DEBUG_DIR",
    os.path.expanduser("~/.taris/debug/voice"),
))


class VoiceDebugSession:
    """Records all pipeline stages for one voice request.

    When VOICE_DEBUG_MODE is disabled the instance is a no-op —
    every method returns immediately without I/O.
    """

    def __init__(self, user_id: str = "anon", debug_mode: Optional[bool] = None,
                 debug_dir: Optional[Path] = None):
        self._enabled: bool = _DEBUG_MODE if debug_mode is None else debug_mode
        self._dir: Optional[Path] = None

        if self._enabled:
            base = debug_dir or _DEBUG_DIR
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:23]
            # Sanitise user_id to safe dirname chars
            safe_user = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(user_id))[:32]
            self._dir = Path(base) / f"{ts}__{safe_user}"
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
                log.debug(f"[VoiceDebug] session dir: {self._dir}")
            except OSError as exc:
                log.warning(f"[VoiceDebug] cannot create debug dir: {exc}")
                self._dir = None

    # ── Public properties ──────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled and self._dir is not None

    @property
    def session_id(self) -> Optional[str]:
        """Directory name — used as the key in download URLs."""
        return self._dir.name if self._dir else None

    @property
    def dir_path(self) -> Optional[Path]:
        return self._dir

    # ── Stage savers ───────────────────────────────────────────────────────────

    def save_raw_audio(self, data: bytes, ext: str = "webm") -> None:
        """Save the raw browser audio exactly as received."""
        self._write(f"input.{ext}", data)

    def save_pcm(self, data: bytes, sample_rate: int = 16000) -> None:
        """Save decoded 16 kHz mono s16le PCM.

        Also writes a WAV wrapper (decoded.wav) for easy playback in
        any audio tool without needing ffmpeg.
        """
        self._write("decoded.pcm", data)
        try:
            import io
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(data)
            self._write("decoded.wav", buf.getvalue())
        except Exception as exc:
            log.debug(f"[VoiceDebug] WAV write skipped: {exc}")

    def save_stt(self, text: str) -> None:
        """Save the raw STT transcript."""
        self._write_text("stt.txt", text)

    def save_llm_answer(self, text: str) -> None:
        """Save the LLM response text."""
        self._write_text("llm_answer.txt", text)

    def save_tts_input(self, text: str) -> None:
        """Save the cleaned text sent to TTS (after markdown/emoji strip)."""
        self._write_text("tts_input.txt", text)

    def save_tts_output(self, data: bytes) -> None:
        """Save the synthesised OGG Opus audio."""
        self._write("tts_output.ogg", data)

    def finalise(self, pipeline_meta: Optional[dict] = None) -> None:
        """Write pipeline.json with stage timings + metadata."""
        if not self._dir:
            return
        meta = pipeline_meta or {}
        meta["session_id"] = self.session_id
        meta["recorded_at"] = datetime.now().isoformat()
        files = [p.name for p in sorted(self._dir.iterdir())]
        meta["files"] = files
        self._write_text("pipeline.json", json.dumps(meta, ensure_ascii=False, indent=2))
        log.debug(f"[VoiceDebug] finalised — {len(files)} files in {self._dir}")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _write(self, name: str, data: bytes) -> None:
        if not self._dir:
            return
        try:
            (self._dir / name).write_bytes(data)
        except OSError as exc:
            log.warning(f"[VoiceDebug] write {name} failed: {exc}")

    def _write_text(self, name: str, text: str) -> None:
        if not self._dir:
            return
        try:
            (self._dir / name).write_text(text, encoding="utf-8")
        except OSError as exc:
            log.warning(f"[VoiceDebug] write {name} failed: {exc}")


# ── Module-level helpers ───────────────────────────────────────────────────────

def list_debug_sessions(debug_dir: Optional[Path] = None, last_n: int = 50) -> list[dict]:
    """Return metadata for the most-recent debug sessions (newest first)."""
    base = debug_dir or _DEBUG_DIR
    if not base.is_dir():
        return []
    sessions = []
    for d in sorted(base.iterdir(), reverse=True)[:last_n]:
        if not d.is_dir():
            continue
        meta_file = d / "pipeline.json"
        meta: dict = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        files = [p.name for p in sorted(d.iterdir())]
        sessions.append({
            "session_id": d.name,
            "path": str(d),
            "files": files,
            "stt": _read_text(d / "stt.txt"),
            "llm_answer": _read_text(d / "llm_answer.txt"),
            "recorded_at": meta.get("recorded_at", ""),
        })
    return sessions


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
