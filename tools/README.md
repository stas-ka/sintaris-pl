# Tools

## Audio Transcription

Convert common audio/video formats to text transcripts using `faster-whisper`.

### Install

```bash
pip install -r tools/requirements.txt
```

### Usage

Single file:

```bash
python tools/transcribe_audio.py temp/audio_2026-03-07_17-29-22.ogg
```

Directory:

```bash
python tools/transcribe_audio.py temp --recursive
```

Output location:
- Default: next to each source file as `<name>.transcript.txt`
- Custom: `--output-dir <dir>`

Useful options:
- `--language ru` to force language
- `--model small` to choose model
- `--overwrite` to replace existing transcripts
- `--no-vad-filter` to disable VAD filtering

---

## Benchmarks

Performance test suite for storage operations and Telegram menu handler latency.
Results accumulate in `tools/benchmark_results.json` and are compared across platforms.

> **Copilot skill**: `/claw_performancetest` — Copilot will run the right command
> based on what you ask.  Full protocol in `.github/prompts/claw_performancetest.prompt.md`.

### Scripts

| Script | Purpose |
|---|---|
| `benchmark_suite.py` | Unified orchestrator — runs storage and/or menu benchmarks locally and/or on Pi targets, merges results, prints comparison table |
| `benchmark_storage.py` | Standalone — measures raw JSON vs SQLite read/write ops |
| `benchmark_menus.py` | Standalone — measures Telegram menu handler latency (13 TCs) |

### Quick Usage

```bat
rem All suites, local dev machine (default 500 storage / 100 menu iterations)
python tools\benchmark_suite.py

rem Quick sanity run (50 iterations)
python tools\benchmark_suite.py -n 50

rem Storage ops only
python tools\benchmark_suite.py --suite storage

rem Run on PI1 (requires HOSTPWD env var)
python tools\benchmark_suite.py --platform pi1

rem Run on all platforms (local + PI1 + PI2)
python tools\benchmark_suite.py --platform all

rem Print comparison table from existing results (no re-run)
python tools\benchmark_suite.py --compare
```

### CLI Options

| Flag | Default | Description |
|---|---|---|
| `--suite [storage\|menus\|all]` | `all` | Which benchmark suite to run |
| `--platform [local\|pi1\|pi2\|all]` | `local` | Target platform |
| `--iterations / -n` | 500 (storage) / 100 (menus) | Number of iterations per op |
| `--compare` | off | Print comparison table and exit (no benchmarks run) |
| `--results PATH` | `tools/benchmark_results.json` | Results file path |

### Environment Variables

| Variable | Required for |
|---|---|
| `HOSTPWD` | PI1 runs (`--platform pi1` or `--platform all`) |
| `HOSTPWD2` | PI2 runs (`--platform pi2` or `--platform all`) |

Both variables are read from the environment or the workspace `.env` file.

### Results File

`tools/benchmark_results.json` is a JSON array (append-only).  Commit it
alongside any code change that measurably shifts performance so the comparison
baseline stays accurate.  ⚠️ flags in the comparison table indicate a >20%
regression versus the previous run from the same host.
