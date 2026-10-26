"""端到端编排：语种判定 → 转写 → 句段/关键词/标题后处理。"""

from __future__ import annotations

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
from ..text.keywords import find_keywords
from ..text.sentences import merge_to_sentences
from ..text.title import TitleSplitter
from .transcribe import transcribe_audio


def localize(
    registry: ModelRegistry,
    settings: Settings,
    *,
    audio_path: Path,
    mono: torch.Tensor,
    sample_rate: int,
    question: str | None,
    language: str | None,
    progress: Any | None = None,
) -> dict[str, Any]:
    """转写音频并返回语言、全文、句段、关键词命中与标题正文。"""
    model = registry.asr
    requested_language = normalize_language(language)

    transcript = transcribe_audio(model, settings, audio_path, mono, sample_rate, requested_language, progress=progress)

    # 若判成拉丁语言且未显式指定，用脚本投票兜底（唱歌的非拉丁语）
    if not requested_language and transcript.language in LATIN_LANGUAGES:
        voted = detect_language_by_script(model, mono, sample_rate, settings.lid.segment_seconds)
        if voted and voted not in LATIN_LANGUAGES:
            progress and progress.stage("transcribe", 0, 1)
            transcript = transcribe_audio(model, settings, audio_path, mono, sample_rate, voted, progress=progress)
            progress and progress.stage("transcribe", 1, 1)

    detected_language = transcript.language
    if detected_language == "Chinese" and contains_cantonese(transcript.text):
        detected_language = "Cantonese"

    progress and progress.stage("postprocess")
    title_result = TitleSplitter(settings.title).split(transcript.text)
    return {
        "language": detected_language,
        "text": transcript.text,
        "segments": merge_to_sentences(
            transcript.segments,
            max_chars=settings.sentence.max_chars,
            max_duration_seconds=settings.sentence.max_duration_seconds,
        ),
        "matched": find_keywords(transcript.text, transcript.segments, question or ""),
        "title": title_result["title"],
        "body": title_result["body"],
    }
