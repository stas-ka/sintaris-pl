#!/usr/bin/env python3
"""
Transcribe audio/video files to UTF-8 text with faster-whisper.

Examples:
  python tools/transcribe_audio.py temp/audio_2026-03-07_17-29-22.ogg
  python tools/transcribe_audio.py temp --recursive --output-dir temp/transcripts
  python tools/transcribe_audio.py temp/a.ogg temp/b.mp3 --language ru --model small
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List

try:
    from faster_whisper import WhisperModel
except Exception as exc:  # pragma: no cover
    print("Missing dependency: faster-whisper", file=sys.stderr)
    print("Install with: pip install -r tools/requirements.txt", file=sys.stderr)
    raise SystemExit(2) from exc


SUPPORTED_EXTENSIONS = {
    ".aac",
    ".flac",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
    ".wma",
}


def format_ts(seconds: float) -> str:
    return f"{seconds:.2f}"


def collect_files(inputs: Iterable[str], recursive: bool, include_any: bool) -> List[Path]:
    files: List[Path] = []
    for item in inputs:
        p = Path(item)
        if not p.exists():
            print(f"Skip (not found): {p}", file=sys.stderr)
            continue

        if p.is_file():
            if include_any or p.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(p)
            else:
                print(f"Skip (unsupported extension): {p}", file=sys.stderr)
            continue

        iterator = p.rglob("*") if recursive else p.glob("*")
        for child in iterator:
            if child.is_file() and (include_any or child.suffix.lower() in SUPPORTED_EXTENSIONS):
                files.append(child)

    # Preserve deterministic order for reproducibility.
    return sorted(set(f.resolve() for f in files))


def out_path_for(audio_path: Path, output_dir: Path | None) -> Path:
    if output_dir is None:
        return audio_path.with_suffix(".transcript.txt")
    return output_dir / f"{audio_path.stem}.transcript.txt"


def write_transcript(
    out_path: Path,
    segments,
    info,
    source_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"Source: {source_path}",
        f"Language: {info.language} (prob={info.language_probability:.4f})",
        "",
    ]
    for seg in segments:
        text = seg.text.strip()
        lines.append(f"[{format_ts(seg.start)} -> {format_ts(seg.end)}] {text}")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe audio/video files into text using faster-whisper."
    )
    parser.add_argument("inputs", nargs="+", help="Audio/video file(s) or directories")
    parser.add_argument("--recursive", action="store_true", help="Recurse into directories")
    parser.add_argument(
        "--include-any-extension",
        action="store_true",
        help="Try processing all files, not only known audio/video extensions",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for transcript output files (default: next to each input)",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing transcripts")
    parser.add_argument("--model", default="small", help="Whisper model size/name")
    parser.add_argument("--device", default="cpu", help="Inference device: cpu, cuda, auto")
    parser.add_argument("--compute-type", default="int8", help="Compute type, e.g. int8, float16")
    parser.add_argument(
        "--language",
        default=None,
        help="Force language code (example: ru, en). Default: auto-detect.",
    )
    parser.add_argument(
        "--task",
        choices=("transcribe", "translate"),
        default="transcribe",
        help="Whisper task mode",
    )
    parser.add_argument(
        "--vad-filter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable voice activity detection filter (default: enabled)",
    )

    args = parser.parse_args()

    files = collect_files(args.inputs, recursive=args.recursive, include_any=args.include_any_extension)
    if not files:
        print("No input files to process.", file=sys.stderr)
        return 1

    print(f"Loading model: {args.model} (device={args.device}, compute_type={args.compute_type})")
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)

    failures = 0
    for audio in files:
        out_path = out_path_for(audio, args.output_dir)
        if out_path.exists() and not args.overwrite:
            print(f"Skip (exists): {out_path}")
            continue

        print(f"Transcribing: {audio}")
        try:
            segments, info = model.transcribe(
                str(audio),
                language=args.language,
                task=args.task,
                vad_filter=args.vad_filter,
                word_timestamps=False,
            )
            segments = list(segments)
            write_transcript(out_path, segments, info, audio)
            print(f"Saved: {out_path}")
        except Exception as exc:
            failures += 1
            print(f"Failed: {audio}\n  {exc}", file=sys.stderr)

    if failures:
        print(f"Done with {failures} failure(s).", file=sys.stderr)
        return 2

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
