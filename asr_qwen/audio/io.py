"""Audio I/O and temporary-file lifecycle management."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import torch
import torchaudio


def _load_via_ffmpeg(path: Path) -> tuple[torch.Tensor, int]:
    """Fall back to the system ffmpeg CLI: remux to plain wav, then load it."""
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
    """Load audio and resample it to mono at the requested sample rate."""
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
    """Write an upload to a temporary file, removing it on exit; keep the original suffix."""
    suffix = Path(filename or "").suffix or ".wav"
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(payload)
            path = Path(handle.name)
        yield path
    finally:
        if path is not None:
            # On Windows the decoder may still hold the handle; the OS cleans up instead
            with suppress(OSError):
                path.unlink(missing_ok=True)


@contextmanager
def temporary_wav(waveform: torch.Tensor, sample_rate: int) -> Iterator[Path]:
    """Write a tensor slice to a temporary wav file for models that need a path."""
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
