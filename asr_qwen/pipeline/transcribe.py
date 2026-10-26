"""按音频长度选择直接转写或 VAD 分块转写。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

from ..audio.vad import chunk_by_silence, detect_speech_segments
from ..config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transcript:
    """一次转写的结果。"""

    language: str | None
    text: str
    segments: list[dict[str, Any]]


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


def transcribe_audio(
    model: Any,
    settings: Settings,
    audio_path: Path,
    mono: torch.Tensor,
    sample_rate: int,
    language: str | None,
    progress: Any | None = None,
) -> Transcript:
    """短音频直接转写；长音频按静音点分块转写后拼接时间轴。"""
    duration = mono.shape[0] / sample_rate
    if duration <= settings.audio.max_chunk_seconds:
        progress and progress.stage("transcribe", 0, 1)
        result = _first_result(model, str(audio_path), language)
        progress and progress.stage("transcribe", 1, 1)
        return Transcript(result.language, result.text, _to_segments(_timestamps(result)))

    segments = detect_speech_segments(mono, sample_rate, settings.vad)
    chunks = chunk_by_silence(segments, settings.audio.max_chunk_seconds * sample_rate)
    texts: list[str] = []
    all_segments: list[dict[str, Any]] = []
    chunk_languages: dict[str, int] = {}
    progress and progress.stage("transcribe", 0, len(chunks))
    for index, (chunk_start, chunk_end) in enumerate(chunks):
        chunk = mono[chunk_start:chunk_end].numpy()
        result = _first_result(model, (chunk, sample_rate), language)
        all_segments.extend(_to_segments(_timestamps(result), chunk_start / sample_rate))
        texts.append(result.text)
        if result.language:
            chunk_languages[result.language] = chunk_languages.get(result.language, 0) + 1
        logger.info("转写分块 %d/%d（时长 %.1fs）", index + 1, len(chunks), (chunk_end - chunk_start) / sample_rate)
        progress and progress.stage("transcribe", index + 1, len(chunks))
    detected = max(chunk_languages, key=chunk_languages.get) if chunk_languages else (language or "auto")
    return Transcript(detected, "".join(texts), all_segments)
