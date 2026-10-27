"""Configuration data structures (structure only, no defaults are provided here)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when the config file, a section, or a value is missing or mistyped."""


@dataclass(frozen=True, slots=True)
class ModelSettings:
    """Qwen3-ASR main model and its forced aligner."""

    asr_path: Path
    aligner_path: Path
    dtype: str
    device: str
    max_inference_batch_size: int


@dataclass(frozen=True, slots=True)
class LidSettings:
    """SenseVoice language identification model."""

    enabled: bool
    model_path: Path
    device: str
    segment_seconds: int


@dataclass(frozen=True, slots=True)
class VadSettings:
    """Energy-based voice activity detection parameters."""

    frame_ms: int
    hop_ms: int
    threshold_db: float
    min_silence_ms: int
    min_speech_ms: int


@dataclass(frozen=True, slots=True)
class AudioSettings:
    """Audio sampling and chunking parameters."""

    sample_rate: int
    max_chunk_seconds: int


@dataclass(frozen=True, slots=True)
class SentenceSettings:
    """Sentence segmentation: pause threshold plus caps (0 disables an option)."""

    min_gap_seconds: float
    max_chars: int
    max_duration_seconds: float


@dataclass(frozen=True, slots=True)
class LlmSettings:
    """LLM connection parameters used for title splitting."""

    base_url: str
    model: str
    api_key: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class TitleSettings:
    """Title splitting strategy parameters."""

    llm: LlmSettings
    max_chars: int
    max_words: int


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """HTTP server parameters."""

    title: str
    version: str
    host: str
    port: int
    log_level: str
    workers: int


@dataclass(frozen=True, slots=True)
class Settings:
    """Complete configuration."""

    config_path: Path
    base_dir: Path
    model: ModelSettings
    lid: LidSettings
    vad: VadSettings
    audio: AudioSettings
    sentence: SentenceSettings
    title: TitleSettings
    server: ServerSettings
