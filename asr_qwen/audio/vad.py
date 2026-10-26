"""基于能量的语音活动检测与静音点分块。"""

from __future__ import annotations

import math

import torch

from ..config.settings import VadSettings


def detect_speech_segments(
    mono: torch.Tensor,
    sample_rate: int,
    settings: VadSettings,
) -> list[tuple[int, int]]:
    """返回语音片段列表，元素为 (起始样本, 结束样本)。"""
    frame = int(sample_rate * settings.frame_ms / 1000)
    hop = int(sample_rate * settings.hop_ms / 1000)
    total = mono.shape[0]

    energies = []
    for start in range(0, max(0, total - frame), hop):
        rms = float(mono[start:start + frame].pow(2).mean().sqrt())
        energies.append(20.0 * math.log10(rms + 1e-12))
    is_speech = [energy > settings.threshold_db for energy in energies]

    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(is_speech):
        if is_speech[index]:
            end = index
            while end < len(is_speech) and is_speech[end]:
                end += 1
            runs.append((index, end))
            index = end
        else:
            index += 1

    min_silence_frames = int(settings.min_silence_ms / settings.hop_ms)
    merged: list[tuple[int, int]] = []
    for start, end in runs:
        if merged and start - merged[-1][1] < min_silence_frames:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    min_speech_frames = int(settings.min_speech_ms / settings.hop_ms)
    return [(start * hop, end * hop) for start, end in merged if (end - start) >= min_speech_frames]


def chunk_by_silence(
    segments: list[tuple[int, int]],
    max_samples: int,
) -> list[tuple[int, int]]:
    """在静音边界处把语音片段合并成不超过 max_samples 的块。"""
    chunks: list[tuple[int, int]] = []
    current: list[int] | None = None
    for start, end in segments:
        if current is None:
            current = [start, end]
        elif end - current[0] <= max_samples:
            current[1] = end
        else:
            chunks.append((current[0], current[1]))
            current = [start, end]
    if current is not None:
        chunks.append((current[0], current[1]))
    return chunks
