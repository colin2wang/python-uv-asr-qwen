"""语种归一化与多策略语种判定（SenseVoice 投票 / 文本脚本投票）。"""

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

# SenseVoice 多段投票：至少 2 段有语音，票数占比达到阈值才采信
SENSEVOICE_SEGMENT_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
SENSEVOICE_MIN_SPEECH_SEGMENTS = 2
SENSEVOICE_VOTE_RATIO = 0.7

# 脚本投票：同一脚本至少出现 2 次才判为该语言
SCRIPT_VOTE_MIN_HITS = 2

_SCRIPT_PATTERNS = {
    "Cyrillic": re.compile(r"[Ѐ-ӿ]"),
    "Han": re.compile(r"[一-鿿]"),
    "Kana": re.compile(r"[぀-ヿ]"),
    "Hangul": re.compile(r"[가-힯]"),
}
_SENSEVOICE_LABEL_PATTERN = re.compile(r"<\|(\w+)\|>")


def normalize_language(value: str | None) -> str | None:
    """把请求中的语言代码/名称归一化为 Qwen3-ASR 语言名，无法识别时保留原值。"""
    if not value:
        return None
    key = str(value).strip().lower().replace("_", "-").split("-")[0]
    return LANGUAGE_BY_CODE.get(key, str(value).strip())


def dominant_script(text: str) -> str | None:
    """返回文本的主导非拉丁脚本（Cyrillic/Han/Kana/Hangul），无则返回 None。"""
    counts = {script: len(pattern.findall(text)) for script, pattern in _SCRIPT_PATTERNS.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else None


def contains_cantonese(text: str) -> bool:
    """文本中是否出现粤语专用字。"""
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
    """SenseVoice 多段投票，跳过 nospeech，要求一致性，返回语言名；不一致返回 None。"""
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
    """唱歌脚本投票：转写 4 个非拉丁候选，统计主导脚本，某脚本出现 ≥2 次判该语言。

    原理：唱歌时模型对多个强制语言都输出同一个母语脚本（如俄语歌强制俄/中/韩都出西里尔）；
    口语时模型会翻译成各语言自己的脚本（各脚本只出现一次），故 ≥2 次才可信。
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
