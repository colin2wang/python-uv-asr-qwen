"""End-to-end orchestration: language → transcription → sentences/keywords/title."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import torch

from ..config.settings import Settings
from ..language.codes import LATIN_LANGUAGES
from ..language.detector import (
    contains_cantonese,
    detect_language_by_script,
    normalize_language,
)
from ..models.registry import ModelRegistry
from ..text.keywords import find_keywords, with_sentence_index
from ..text.sentences import merge_to_sentences, number_segments
from ..text.title import TitleSplitter
from .progress import ProgressReporter
from .transcribe import transcribe_audio

# Share of the language stage spent on script voting; the rest belongs to re-transcription
_SCRIPT_VOTE_RATIO = 0.6


def localize(
    registry: ModelRegistry,
    settings: Settings,
    *,
    audio_path: Path,
    mono: torch.Tensor,
    sample_rate: int,
    question: str | None,
    language: str | None,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    """Transcribe audio and return language, text, segments, keyword hits and title."""
    started = time.perf_counter()
    model = registry.asr
    requested_language = normalize_language(language)
    duration = mono.shape[0] / sample_rate if sample_rate else 0.0

    transcript = transcribe_audio(
        model, settings, audio_path, mono, sample_rate, requested_language, progress=progress
    )

    # Latin output with no explicit request: fall back to script voting (sung non-Latin)
    if not requested_language and transcript.language in LATIN_LANGUAGES:
        if progress:
            progress.advance("language", _SCRIPT_VOTE_RATIO / 3)
        voted = detect_language_by_script(model, mono, sample_rate, settings.lid.segment_seconds)
        if voted and voted not in LATIN_LANGUAGES:
            # Map the re-transcription into the tail of the language stage so the
            # overall progress cannot move backwards
            retranscribe = (
                progress.subrange(_SCRIPT_VOTE_RATIO, 1.0, alias="language") if progress else None
            )
            transcript = transcribe_audio(
                model, settings, audio_path, mono, sample_rate, voted, progress=retranscribe
            )
        elif progress:
            progress.advance("language", 1.0)
    elif progress:
        progress.advance("language", 1.0)

    detected_language = transcript.language
    if detected_language == "Chinese" and contains_cantonese(transcript.text):
        detected_language = "Cantonese"

    if progress:
        progress.stage("postprocess")
    title_result = TitleSplitter(settings.title).split(transcript.text)
    segments = number_segments(
        merge_to_sentences(
            transcript.segments,
            max_chars=settings.sentence.max_chars,
            max_duration_seconds=settings.sentence.max_duration_seconds,
            min_gap_seconds=settings.sentence.min_gap_seconds,
            text=transcript.text,
        )
    )
    if progress:
        progress.advance("postprocess", 0.5)
    matched = with_sentence_index(find_keywords(transcript.segments, question or ""), segments)
    if progress:
        progress.advance("postprocess", 1.0)

    return {
        "language": detected_language,
        "duration": round(duration, 3),
        "title": title_result["title"],
        "body": title_result["body"],
        "text": transcript.text,
        "segments": segments,
        "matched": matched,
        "stats": {
            "sample_rate": sample_rate,
            "chunk_count": transcript.chunk_count,
            "segment_count": len(segments),
            "char_count": len(transcript.text),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        },
    }
