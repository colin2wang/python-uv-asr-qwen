"""Language normalization and multi-strategy detection (SenseVoice / script voting)."""

from __future__ import annotations

import logging
import re
from typing import Any

import torch

from ..audio.io import temporary_wav
from .codes import (
    CANTONESE_CHARS,
    LANGUAGE_BY_CODE,
    SCRIPT_CANDIDATES,
    SCRIPT_TO_LANGUAGE,
    SENSEVOICE_TO_QWEN,
)

logger = logging.getLogger(__name__)

# SenseVoice votes over several slices: at least 2 slices must contain speech and one
# language must reach the ratio threshold before the vote is trusted
SENSEVOICE_SEGMENT_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
SENSEVOICE_MIN_SPEECH_SEGMENTS = 2
SENSEVOICE_VOTE_RATIO = 0.7

# Script voting: the same script must appear at least twice to decide the language
SCRIPT_VOTE_MIN_HITS = 2

# Scripts are detected by their Unicode ranges; the literals are input, not copy
_SCRIPT_PATTERNS = {
    "Cyrillic": re.compile(r"[Ѐ-ӿ]"),
    "Han": re.compile(r"[一-鿿]"),
    "Kana": re.compile(r"[぀-ヿ]"),
    "Hangul": re.compile(r"[가-힯]"),
}
_SENSEVOICE_LABEL_PATTERN = re.compile(r"<\|(\w+)\|>")


def normalize_language(value: str | None) -> str | None:
    """Normalize a requested language code/name to a Qwen3-ASR language name."""
    if not value:
        return None
    key = str(value).strip().lower().replace("_", "-").split("-")[0]
    return LANGUAGE_BY_CODE.get(key, str(value).strip())


def dominant_script(text: str) -> str | None:
    """Return the dominant non-Latin script (Cyrillic/Han/Kana/Hangul), or None."""
    counts = {script: len(pattern.findall(text)) for script, pattern in _SCRIPT_PATTERNS.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else None


def contains_cantonese(text: str) -> bool:
    """Whether the text contains characters specific to Cantonese."""
    return any(char in CANTONESE_CHARS for char in text)


def _slice_segment(mono: torch.Tensor, sample_rate: int, segment_seconds: int) -> torch.Tensor:
    segment_length = segment_seconds * sample_rate
    if mono.shape[0] > segment_length:
        start = (mono.shape[0] - segment_length) // 2
        return mono[start:start + segment_length]
    return mono


def detect_language_by_sensevoice(
    lid_model: Any,
    mono: torch.Tensor,
    sample_rate: int,
    segment_seconds: int,
) -> str | None:
    """Vote over SenseVoice slices, skipping nospeech; returns a language or None."""
    if lid_model is None:
        return None
    segment_length = segment_seconds * sample_rate
    total = mono.shape[0]
    if total <= segment_length:
        fractions = [0.0]
    else:
        fractions = list(SENSEVOICE_SEGMENT_FRACTIONS)
    votes: dict[str, int] = {}
    total_speech = 0
    for fraction in fractions:
        position = min(int((total - segment_length) * fraction), max(0, total - segment_length))
        segment = mono[position:position + segment_length]
        if segment.shape[0] < segment_length // 2:
            continue
        try:
            with temporary_wav(segment, sample_rate) as path:
                result = lid_model.generate(input=str(path), language="auto", use_itn=False)
            match = _SENSEVOICE_LABEL_PATTERN.search(result[0]["text"])
            if match:
                code = match.group(1).lower()
                if code != "nospeech":
                    total_speech += 1
                    language = SENSEVOICE_TO_QWEN.get(code)
                    if language:
                        votes[language] = votes.get(language, 0) + 1
        except Exception as exc:
            logger.debug("SenseVoice LID segment failed: %s", exc)
    if not votes or total_speech < SENSEVOICE_MIN_SPEECH_SEGMENTS:
        return None
    top = max(votes, key=votes.get)
    if votes[top] / total_speech >= SENSEVOICE_VOTE_RATIO:
        return top
    return None


def detect_language_by_script(
    model: Any,
    mono: torch.Tensor,
    sample_rate: int,
    segment_seconds: int,
) -> str | None:
    """Script voting for sung audio: transcribe 4 non-Latin candidates and count scripts.

    A language is decided when its script appears at least twice. Rationale: when
    singing, every forced language yields the same native script (a Russian song forced
    to Russian/Chinese/Korean still produces Cyrillic); in speech the model translates
    into each language's own script, so each script appears once and is not trusted.
    """
    segment = _slice_segment(mono, sample_rate, segment_seconds)
    script_counts: dict[str, int] = {}
    with temporary_wav(segment, sample_rate) as path:
        for language in SCRIPT_CANDIDATES:
            try:
                result = model.transcribe(str(path), language=language, return_time_stamps=False)[0]
            except Exception as exc:
                logger.debug("script vote transcribe failed for %s: %s", language, exc)
                continue
            cleaned = re.sub(r"\s", "", result.text or "")
            if not cleaned:
                continue
            script = dominant_script(cleaned)
            if script:
                script_counts[script] = script_counts.get(script, 0) + 1
    for script, count in sorted(script_counts.items(), key=lambda item: -item[1]):
        if count >= SCRIPT_VOTE_MIN_HITS:
            return SCRIPT_TO_LANGUAGE[script]
    return None
