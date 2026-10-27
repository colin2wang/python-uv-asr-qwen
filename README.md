# Qwen3-ASR Localization Service

**English** | [简体中文](README.zh-CN.md)

A FastAPI service that turns audio/video uploads into *localized* transcripts with
[Qwen3-ASR-1.7B](https://huggingface.co/Qwen) plus a forced aligner:
multi-language transcription, sentence-level timestamps, keyword time-range lookup,
and a title/body split.

## Features

- **Multi-language transcription** with Qwen3-ASR-1.7B (roughly 30 languages) on GPU.
- **Segments keep the original punctuation**: segment text comes from the model's full
  text (punctuation and spaces copied verbatim) while timestamps come from aligning
  that text with the token stream (`difflib` sequence matching; punctuation and
  whitespace consume no token, so normalization differences only cost a few characters
  their timestamp instead of desynchronizing everything). Segments break on
  sentence-ending punctuation and on the `sentence.max_chars` /
  `sentence.max_duration_seconds` caps — the aligner token stream carries **no
  punctuation**, so the caps are the fallback when the transcript has none — plus
  optional inter-token pauses via `sentence.min_gap_seconds` (default `0`, off: sung
  vocals drag notes and produce one-second fragments). Every segment carries
  `start` / `end`. Invalid token timestamps are repaired by interpolation.
- **Automatic language detection**: the model's own language output, plus a
  script-voting second pass for sung audio (Cyrillic / Han / Kana / Hangul), plus a
  Cantonese-character heuristic that promotes `Chinese` to `Cantonese`.
- **Keyword localization**: a comma-separated query such as `price,refund` is matched
  on the concatenated token stream and mapped to hit time ranges (spaces inside the
  query are ignored, so `killing me` matches English lyrics).
- **Title / body split**: rule-first (label, first line, first sentence, or first
  `title.max_words` words); an OpenAI-compatible LLM is consulted only when the rule
  result is not obviously a title. The title is always an exact prefix of the
  transcript — never rewritten or translated.
- **Whole-file transcription (no chunking by default)**: the full audio goes to the
  model in one call — chunking cuts sentences that straddle a boundary and, because
  each chunk is transcribed in isolation, loses the context that produces sentence-
  final punctuation. Set `audio.max_chunk_seconds` above `0` to bring back
  "VAD silence boundaries → chunks → stitched timelines".
- **Sync and async APIs**: `POST /asr/localize` blocks until done;
  `POST /asr/jobs` returns a job id whose stage, overall percentage, chunk counters
  and elapsed time you can poll.
- **Built-in test page** at `/ui`, no frontend build step, no extra dependencies:
  weighted progress bar per stage, clickable sentence rows that seek the player,
  and TXT / SRT / VTT / JSON export.
- **Strict configuration**: `asr-qwen.yml` has no defaults in code; a missing or
  mistyped field fails fast with `ConfigError`. Missing model weights are downloaded
  from ModelScope at startup.

## How it works

```
upload ──> audio/io.py       decode + resample to mono 16 kHz (torchaudio/torchcodec, ffmpeg fallback)
      ──> pipeline/transcribe  one pass over the whole file (VAD chunking only if audio.max_chunk_seconds > 0)
      ──> language/detector    normalize requested language, script-vote fallback, Cantonese check
      ──> text/sentences      timestamped segments (length/duration caps, punctuation & pause optional)
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
| `vad.frame_ms` / `hop_ms` | Energy analysis frame and hop size (chunking mode only) |
| `vad.threshold_db` | Speech threshold in dBFS |
| `vad.min_silence_ms` | Gaps shorter than this are treated as speech |
| `vad.min_speech_ms` | Speech runs shorter than this are dropped |
| `audio.sample_rate` | Target mono sample rate (16 kHz recommended) |
| `audio.max_chunk_seconds` | `0` = send the whole file at once (default); `> 0` = VAD-chunk audio longer than this |
| `sentence.min_gap_seconds` | Inter-token pause that ends a segment; `0` disables it (sung vocals produce fragments) |
| `sentence.max_chars` | Max characters per segment; `0` means unlimited |
| `sentence.max_duration_seconds` | Max duration per segment in seconds; `0` means unlimited |
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
| `GET` | `/asr/jobs/{job_id}` | Job status, stage, overall percentage, chunk progress, result |
| `GET` | `/ui` | Built-in test page |
| `GET` | `/docs` | OpenAPI UI |

Multipart fields for both transcription endpoints:

| Field | Required | Meaning |
| --- | --- | --- |
| `file` | yes | Audio/video file, any format your decoder supports (wav / mp3 / flac / ogg / m4a …) |
| `question` | no | Comma-separated keyword query |
| `language` | no | Language name or code (`Chinese`, `en`, `yue`, …); empty means auto |

Until the model finishes loading, both transcription endpoints return `503`.

`vad.*` and `audio.max_chunk_seconds` only apply in chunking mode: transcription is
whole-file by default and switches to chunking when `audio.max_chunk_seconds` is `> 0`.

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
`queued` / `decode` / `vad` / `transcribe` / `language` / `postprocess` (with a
`stage_label` alongside), `percent` is the overall percentage while `done`/`total` are
the chunk counters (both `0` when the audio was not chunked), `elapsed_seconds` is the
job runtime.

```json
{
  "job_id": "8f1c02a9d3e4",
  "status": "running",
  "stage": "transcribe",
  "stage_label": "转写中",
  "progress": 0.4128,
  "percent": 41,
  "done": 3,
  "total": 10,
  "elapsed_seconds": 26.4,
  "result": null,
  "error": null
}
```

The percentage is stage-weighted (decode 10% → vad 8% → transcribe 55% → language 12%
→ postprocess 15%) and never decreases: the re-transcription a sung clip can trigger
after script voting is mapped into the tail of the `language` stage, so the bar never
walks backwards. Finished jobs carry `result` (same shape as below) or `error`. The
registry is in-memory and entries older than one hour are evicted on the next job
creation.

### Response

```json
{
  "language": "Chinese",
  "duration": 4.86,
  "title": "今天的主题是价格。",
  "body": "下面看三个例子。",
  "text": "今天的主题是价格。下面看三个例子。",
  "segments": [
    {"index": 1, "text": "今天的主题是价格。", "start": 0.12, "end": 2.4, "duration": 2.28},
    {"index": 2, "text": "下面看三个例子。", "start": 2.4, "end": 4.86, "duration": 2.46}
  ],
  "matched": [
    {
      "rule": "价格", "start": 0.12, "end": 1.4,
      "timestamp": [0.12, 1.4], "segment_index": 1, "confidence": 1.0
    }
  ],
  "stats": {
    "sample_rate": 16000,
    "chunk_count": 1,
    "segment_count": 2,
    "char_count": 20,
    "elapsed_seconds": 3.42
  }
}
```

- `language` — as detected by the model, adjusted by the script-voting and Cantonese heuristics.
- `duration` — audio length in seconds.
- `text` — full transcript.
- `segments` — sentence segments merged from aligner tokens: `index` (1-based),
  `start` / `end` / `duration` in seconds.
- `matched` — per keyword hit: `rule`, `start` / `end` (same as `timestamp`), the
  `segment_index` it falls in, and `confidence` (always 1.0 for exact substring hits).
- `title` / `body` — `title` is an exact prefix of `text`; `title + body` reconstructs
  the transcript.
- `stats` — processing metadata: sample rate, chunk count, segment count, characters
  and pipeline elapsed time.

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
