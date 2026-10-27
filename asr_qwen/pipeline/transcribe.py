"""Transcribe whole audio, or VAD-chunked when a chunk limit is configured."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

from ..audio.vad import chunk_by_silence, detect_speech_segments
from ..config.settings import Settings
from .progress import ProgressReporter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transcript:
    """The result of one transcription pass."""

    language: str | None
    text: str
    segments: list[dict[str, Any]]
    chunk_count: int


def _to_segments(items: Any, offset: float = 0.0) -> list[dict[str, Any]]:
    return [
        {
            "text": item.text,
            "start": round(item.start_time + offset, 3),
            "end": round(item.end_time + offset, 3),
        }
        for item in items
    ]


def _first_result(model: Any, audio: Any, language: str | None) -> Any:
    return model.transcribe(audio, language=language, return_time_stamps=True)[0]


def _timestamps(result: Any) -> list[dict[str, Any]]:
    return result.time_stamps.items if result.time_stamps is not None else []


def _advance(progress: ProgressReporter | None, stage: str, ratio: float) -> None:
    """Report the in-stage completion ratio (used where chunks do not apply)."""
    if progress is not None:
        progress.advance(stage, ratio)


def _report(progress: ProgressReporter | None, stage: str, done: int = 0, total: int = 0) -> None:
    if progress is not None:
        progress.stage(stage, done, total)


def transcribe_audio(
    model: Any,
    settings: Settings,
    audio_path: Path,
    mono: torch.Tensor,
    sample_rate: int,
    language: str | None,
    progress: ProgressReporter | None = None,
) -> Transcript:
    """Transcribe in one pass; chunk at silence only when `audio.max_chunk_seconds > 0`.

    Whole-file by default: chunking cuts sentences that straddle a boundary, and each
    chunk is transcribed without the surrounding context.
    """
    duration = mono.shape[0] / sample_rate
    if settings.audio.max_chunk_seconds <= 0 or duration <= settings.audio.max_chunk_seconds:
        # Without chunking there is no vad stage; mark it done so the bar does not jump
        _advance(progress, "vad", 1.0)
        _advance(progress, "transcribe", 0.0)
        logger.info("transcribing %.1fs in a single pass (no chunking)", duration)
        result = _first_result(model, str(audio_path), language)
        _advance(progress, "transcribe", 1.0)
        return Transcript(result.language, result.text, _to_segments(_timestamps(result)), 1)

    _report(progress, "vad")
    speech_segments = detect_speech_segments(mono, sample_rate, settings.vad)
    chunks = chunk_by_silence(speech_segments, settings.audio.max_chunk_seconds * sample_rate)
    if not chunks:
        logger.info("no speech detected in %.1fs, skipping transcription", duration)
        _advance(progress, "transcribe", 1.0)
        return Transcript(language, "", [], 0)

    logger.info("splitting %.1fs of audio into %d chunks", duration, len(chunks))
    texts: list[str] = []
    all_segments: list[dict[str, Any]] = []
    chunk_languages: dict[str, int] = {}
    _report(progress, "transcribe", 0, len(chunks))
    for index, (chunk_start, chunk_end) in enumerate(chunks):
        chunk = mono[chunk_start:chunk_end].numpy()
        result = _first_result(model, (chunk, sample_rate), language)
        all_segments.extend(_to_segments(_timestamps(result), chunk_start / sample_rate))
        texts.append(result.text)
        if result.language:
            chunk_languages[result.language] = chunk_languages.get(result.language, 0) + 1
        logger.info(
            "transcribing chunk %d/%d (%.1fs~%.1fs)",
            index + 1,
            len(chunks),
            chunk_start / sample_rate,
            chunk_end / sample_rate,
        )
        _report(progress, "transcribe", index + 1, len(chunks))
    detected = max(chunk_languages, key=chunk_languages.get) if chunk_languages else (language or "auto")
    return Transcript(detected, "".join(texts), all_segments, len(chunks))
