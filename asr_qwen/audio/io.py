"""音频读写与临时文件生命周期管理。"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import torch
import torchaudio


def _load_via_ffmpeg(path: Path) -> tuple[torch.Tensor, int]:
    """torchcodec 解码失败时，用系统 ffmpeg CLI 转封装为标准 wav 再加载。"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        wav_path = Path(handle.name)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vn", str(wav_path)],
            capture_output=True,
        )
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"ffmpeg decode failed: {detail}")
        return torchaudio.load(str(wav_path))
    finally:
        with suppress(OSError):
            wav_path.unlink(missing_ok=True)


def load_mono_audio(path: str | Path, sample_rate: int) -> tuple[torch.Tensor, int]:
    """加载音频并重采样为指定采样率的单声道。"""
    try:
        waveform, source_rate = torchaudio.load(str(path))
    except RuntimeError:
        waveform, source_rate = _load_via_ffmpeg(Path(path))
    if source_rate != sample_rate:
        waveform = torchaudio.functional.resample(waveform, source_rate, sample_rate)
        source_rate = sample_rate
    return waveform.mean(dim=0), source_rate


@contextmanager
def temporary_upload(filename: str | None, payload: bytes) -> Iterator[Path]:
    """把上传内容落盘到临时文件，退出时删除，后缀沿用原文件名。"""
    suffix = Path(filename or "").suffix or ".wav"
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(payload)
            path = Path(handle.name)
        yield path
    finally:
        if path is not None:
            # Windows 下解码器可能仍持有文件句柄，删除失败则交给系统清理临时目录
            with suppress(OSError):
                path.unlink(missing_ok=True)


@contextmanager
def temporary_wav(waveform: torch.Tensor, sample_rate: int) -> Iterator[Path]:
    """把张量片段写成临时 wav 文件，供需要文件路径的模型调用。"""
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            path = Path(handle.name)
        torchaudio.save(str(path), waveform.unsqueeze(0), sample_rate)
        yield path
    finally:
        if path is not None:
            with suppress(OSError):
                path.unlink(missing_ok=True)
