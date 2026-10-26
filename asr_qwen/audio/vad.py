"""基于能量的语音活动检测与静音点分块。"""

from __future__ import annotations

import torch

from ..config.settings import VadSettings

# 每批参与能量计算的帧数：长音频分批处理，避免一次性展开出超大矩阵
_FRAMES_PER_BATCH = 4096


def _frame_energies(mono: torch.Tensor, frame: int, hop: int) -> torch.Tensor:
    """逐帧 RMS 能量（dBFS）：向量化滑动窗口，按批计算以限制峰值内存。"""
    usable = mono.shape[0]
    if usable < frame:
        return torch.empty(0, dtype=torch.float32)
    total_frames = (usable - frame) // hop + 1
    batches: list[torch.Tensor] = []
    for offset in range(0, total_frames, _FRAMES_PER_BATCH):
        count = min(_FRAMES_PER_BATCH, total_frames - offset)
        start = offset * hop
        length = (count - 1) * hop + frame
        windows = mono[start:start + length].unfold(0, frame, hop)
        batches.append(20.0 * torch.log10(windows.pow(2).mean(dim=1).sqrt() + 1e-12))
    return torch.cat(batches)


def detect_speech_segments(
    mono: torch.Tensor,
    sample_rate: int,
    settings: VadSettings,
) -> list[tuple[int, int]]:
    """返回语音片段列表，元素为 (起始样本, 结束样本)。"""
    frame = int(sample_rate * settings.frame_ms / 1000)
    hop = int(sample_rate * settings.hop_ms / 1000)

    energies = _frame_energies(mono, frame, hop)
    is_speech = (energies > settings.threshold_db).tolist()

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
    """在静音边界处把语音片段合并成不超过 max_samples 的块。

    合并后仍超过上限的单段按上限切片：切点未必落在静音处，但保证每块都不超长，
    避免长语音（如连续说话几分钟）一次性送进模型。
    """
    packed: list[tuple[int, int]] = []
    current: list[int] | None = None
    for start, end in segments:
        if current is None:
            current = [start, end]
        elif end - current[0] <= max_samples:
            current[1] = end
        else:
            packed.append((current[0], current[1]))
            current = [start, end]
    if current is not None:
        packed.append((current[0], current[1]))

    chunks: list[tuple[int, int]] = []
    for start, end in packed:
        while end - start > max_samples:
            chunks.append((start, start + max_samples))
            start += max_samples
        chunks.append((start, end))
    return chunks
