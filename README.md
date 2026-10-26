# Qwen3-ASR Localization Service

**English** | [简体中文](README.zh-CN.md)

A FastAPI service that turns audio/video uploads into *localized* transcripts with
[Qwen3-ASR-1.7B](https://huggingface.co/Qwen) plus a forced aligner:
multi-language transcription, sentence-level timestamps, keyword time-range lookup,
and a title/body split.

## Features

- **Multi-language transcription** with Qwen3-ASR-1.7B (roughly 30 languages) on GPU.
- **Timestamps that survive post-processing**: forced-aligner tokens are merged into
  sentence segments (`sentence.max_chars`, `sentence.max_duration_seconds`) without
  losing the timeline; invalid tokens are repaired by interpolation.
- **Automatic language detection**: the model's own language output, plus a
  script-voting second pass for sung audio (Cyrillic / Han / Kana / Hangul), plus a
  Cantonese-character heuristic that promotes `Chinese` to `Cantonese`.
- **Keyword localization**: a comma-separated query such as `price,refund` is mapped
  to hit time ranges.
- **Title / body split**: rule-first (label, first line, first sentence, or first
  `title.max_words` words); an OpenAI-compatible LLM is consulted only when the rule
  result is not obviously a title. The title is always an exact prefix of the
  transcript — never rewritten or translated.
- **Long audio support**: energy-based VAD finds silence boundaries and chunks audio
  to `audio.max_chunk_seconds`, then stitches chunk timelines back together.
- **Sync and async APIs**: `POST /asr/localize` blocks until done;
  `POST /asr/jobs` returns a job id with stage/chunk progress you can poll.
- **Built-in test page** at `/ui`, no frontend build step, no extra dependencies.
- **Strict configuration**: `asr-qwen.yml` has no defaults in code; a missing or
  mistyped field fails fast with `ConfigError`. Missing model weights are downloaded
  from ModelScope at startup.

## How it works

```
upload ──> audio/io.py       decode + resample to mono 16 kHz (torchaudio/torchcodec, ffmpeg fallback)
      ──> pipeline/transcribe  short file: one pass
                               long file: VAD speech segments → chunks ≤ max_chunk_seconds → per-chunk pass
      ──> language/detector    normalize requested language, script-vote fallback, Cantonese check
      ──> text/sentences      merged, timestamped sentence segments
      ──> text/keywords       comma-separated terms → time ranges
      ──> text/title          rule split, optional LLM refinement (exact-prefix title)
```

The SenseVoice LID model (`lid.enabled`) is loaded at startup and its state is
reported by `/health`; language sampling for script voting uses
`lid.segment_seconds` as the window size.

Package layering is one-directional: `api` → `pipeline` → `models` / `audio` /
`language` / `text` / `config`.

## Requirements

| Item | Detail |
| --- | --- |
| Python | ≥ 3.12 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| GPU | NVIDIA GPU with a working CUDA driver (torch is pinned to the PyTorch `cu128` index) |
| FFmpeg | **shared** build on `PATH` (Windows); required by `torchcodec` for mp3/m4a/ogg decoding |
| Optional | `funasr` (the `lid` extra) when `lid.enabled: true` |

torch/torchaudio are installed from the CUDA 12.8 index configured in
`pyproject.toml` (`tool.uv.sources`), everything else from the Tsinghua mirror.

## Quick start

```powershell
# 1. install (add --extra lid when lid.enabled is true)
uv sync --extra lid

# 2. review the configuration
#    asr-qwen.yml — every field is required

# 3. start the service (first run downloads missing models to qwen-models/)
uv run main.py
```

The service prints its URLs on startup:

```
API      http://127.0.0.1:8010/docs
测试页面 http://127.0.0.1:8010/ui
```

Other entry points:

```powershell
uv run asr-qwen                                  # console script, same behaviour
uv run uvicorn asr_qwen.server:app --port 8010   # used automatically when server.workers > 1
```

Models are fetched from ModelScope only when the configured directory is missing or
empty:

| Local path (`asr-qwen.yml`) | ModelScope id |
| --- | --- |
| `model.asr_path` | `Qwen/Qwen3-ASR-1.7B` |
| `model.aligner_path` | `Qwen/Qwen3-ForcedAligner-0.6B` |
| `lid.model_path` | `iic/SenseVoiceSmall` (skipped when `lid.enabled: false`) |

## Configuration

`asr-qwen.yml` is located by: explicit argument → `ASR_CONFIG_PATH` env var → project
root → package directory → current working directory (first existing file wins).
Relative paths inside the file resolve against the file's own directory.

| Key | Meaning |
| --- | --- |
| `model.asr_path` | Qwen3-ASR model directory |
| `model.aligner_path` | Forced aligner directory (produces the timestamps) |
| `model.dtype` | torch dtype name, e.g. `float16` |
| `model.device` | torch device, e.g. `cuda:0` |
| `model.max_inference_batch_size` | Decoding batch size |
| `lid.enabled` | Load SenseVoiceSmall for language identification |
| `lid.model_path` | SenseVoiceSmall directory |
| `lid.device` | LID device, e.g. `cpu` |
| `lid.segment_seconds` | Audio window used for language sampling / script voting |
| `vad.frame_ms` / `hop_ms` | Energy analysis frame and hop size |
| `vad.threshold_db` | Speech threshold in dBFS |
| `vad.min_silence_ms` | Gaps shorter than this are treated as speech |
| `vad.min_speech_ms` | Speech runs shorter than this are dropped |
| `audio.sample_rate` | Target mono sample rate (16 kHz recommended) |
| `audio.max_chunk_seconds` | Longer audio is VAD-chunked before transcription |
| `sentence.max_chars` | Max characters per sentence segment |
| `sentence.max_duration_seconds` | Max duration per sentence segment |
| `title.max_chars` | Max title length accepted by the rule splitter |
| `title.max_words` | Max words accepted by the rule splitter |
| `title.llm.base_url` | OpenAI-compatible base URL |
| `title.llm.model` | Model name for title refinement |
| `title.llm.api_key` | API key; empty string disables the LLM path (rules only) |
| `title.llm.timeout_seconds` | LLM request timeout |
| `server.title` / `version` | OpenAPI metadata |
| `server.host` / `port` | Bind address; `0.0.0.0`/`::` are logged as `127.0.0.1` |
| `server.log_level` | uvicorn log level |
| `server.workers` | Worker processes; > 1 switches to the `asr_qwen.server:app` import string |

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | `status`, `loaded`, `lid`, `model`, `device` |
| `POST` | `/asr/localize` | Synchronous transcription (multipart) |
| `POST` | `/asr/jobs` | Create a background job, returns `{"job_id": "..."}` |
| `GET` | `/asr/jobs/{job_id}` | Job status, stage, chunk progress, result |
| `GET` | `/ui` | Built-in test page |
| `GET` | `/docs` | OpenAPI UI |

Multipart fields for both transcription endpoints:

| Field | Required | Meaning |
| --- | --- | --- |
| `file` | yes | Audio/video file, any format your decoder supports (wav / mp3 / flac / ogg / m4a …) |
| `question` | no | Comma-separated keyword query |
| `language` | no | Language name or code (`Chinese`, `en`, `yue`, …); empty means auto |

Until the model finishes loading, both transcription endpoints return `503`.

### Synchronous call

```powershell
curl.exe -X POST http://127.0.0.1:8010/asr/localize `
  -F "file=@sample.mp3" `
  -F "question=价格,退款" `
  -F "language="
```

### Async call

```powershell
$job = curl.exe -s -X POST http://127.0.0.1:8010/asr/jobs -F "file=@sample.mp3"
# {"job_id":"8f1c02a9d3e4"}

curl.exe -s http://127.0.0.1:8010/asr/jobs/8f1c02a9d3e4
```

Job states: `status` ∈ `queued` / `running` / `done` / `error`, `stage` ∈
`queued` / `decode` / `transcribe` / `postprocess`, `done`/`total` are the chunk
counters. Finished jobs carry `result` (same shape as below) or `error`. The registry
is in-memory and entries older than one hour are evicted on the next job creation.

### Response

```json
{
  "language": "Chinese",
  "text": "今天的主题是价格。下面看三个例子。",
  "segments": [
    {"text": "今天的主题是价格。", "start": 0.12, "end": 2.4},
    {"text": "下面看三个例子。", "start": 2.4, "end": 4.86}
  ],
  "matched": [
    {"timestamp": [0.12, 2.4], "rule": "价格", "confidence": 1.0}
  ],
  "title": "今天的主题是价格。",
  "body": "下面看三个例子。"
}
```

- `language` — as detected by the model, adjusted by the script-voting and Cantonese heuristics.
- `text` — full transcript.
- `segments` — sentence-level `[start, end]` seconds, merged from aligner tokens.
- `matched` — `{timestamp, rule, confidence}` per keyword hit; `rule` echoes the keyword.
- `title` / `body` — `title` is an exact prefix of `text`; `title + body` reconstructs
  the transcript.

## Project layout

```
asr_qwen/
  api/        FastAPI assembly (app.py), routes.py, embedded test page (testui.py)
  audio/      io.py (decode/resample/temp files), vad.py (energy VAD + chunking)
  config/     settings.py (frozen dataclasses), loader.py (strict YAML validation)
  language/   codes.py (code tables), detector.py (script voting, Cantonese check)
  models/     registry.py (model lifecycle), download.py (ModelScope fetch)
  pipeline/   localizer.py (orchestration), transcribe.py, progress.py (job table)
  text/       sentences.py, keywords.py, title.py
  server.py   process entry point (uvicorn)
asr-qwen.yml  the one configuration file
main.py       convenience launcher
```

## Notes and troubleshooting

- **Config has zero defaults.** Adding a setting means touching `config/settings.py`,
  `config/loader.py` and `asr-qwen.yml` together.
- **`ImportError` / decode errors on mp3/m4a (Windows)** — install a *shared* FFmpeg
  build and put its `bin` directory on `PATH`. `audio/io.py` also falls back to the
  `ffmpeg` CLI when `torchcodec` refuses a file.
- **CPU-only installs** — `tool.uv.sources` pins torch/torchaudio to the CUDA 12.8
  index because PyPI wheels for Windows are CPU-only; change the index before
  downgrading or switching to CPU wheels.
- **Model weights are not committed.** `qwen-models/` is git-ignored; the service
  downloads into it on first start (≈ several GB, needs a working ModelScope access).
- **No test suite or linter is configured** in this repository; validate changes
  statically or by running the service yourself.
- **Deployment scope** — `/ui` is unauthenticated and intended for local debugging;
  put the service behind a gateway if you expose it.
