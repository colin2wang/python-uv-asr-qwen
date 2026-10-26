"""服务配置的数据结构定义（仅声明结构，不含任何默认值）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """配置文件缺失、字段缺失或类型错误。"""


@dataclass(frozen=True, slots=True)
class ModelSettings:
    """Qwen3-ASR 主体与强制对齐模型。"""

    asr_path: Path
    aligner_path: Path
    dtype: str
    device: str
    max_inference_batch_size: int


@dataclass(frozen=True, slots=True)
class LidSettings:
    """SenseVoice 语种识别模型。"""

    enabled: bool
    model_path: Path
    device: str
    segment_seconds: int


@dataclass(frozen=True, slots=True)
class VadSettings:
    """基于能量的语音活动检测参数。"""

    frame_ms: int
    hop_ms: int
    threshold_db: float
    min_silence_ms: int
    min_speech_ms: int


@dataclass(frozen=True, slots=True)
class AudioSettings:
    """音频采样与分块参数。"""

    sample_rate: int
    max_chunk_seconds: int


@dataclass(frozen=True, slots=True)
class SentenceSettings:
    """句段合并的长度上限。"""

    max_chars: int
    max_duration_seconds: float


@dataclass(frozen=True, slots=True)
class LlmSettings:
    """标题拆分的 LLM 接入参数。"""

    base_url: str
    model: str
    api_key: str
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class TitleSettings:
    """标题拆分策略参数。"""

    llm: LlmSettings
    max_chars: int
    max_words: int


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """HTTP 服务参数。"""

    title: str
    version: str
    host: str
    port: int
    log_level: str
    workers: int


@dataclass(frozen=True, slots=True)
class Settings:
    """完整配置。"""

    config_path: Path
    base_dir: Path
    model: ModelSettings
    lid: LidSettings
    vad: VadSettings
    audio: AudioSettings
    sentence: SentenceSettings
    title: TitleSettings
    server: ServerSettings
