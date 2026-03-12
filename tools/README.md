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
