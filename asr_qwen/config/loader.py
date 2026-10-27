"""Read and validate asr-qwen.yml; no default values live in code."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from .settings import (
    AudioSettings,
    ConfigError,
    LidSettings,
    LlmSettings,
    ModelSettings,
    SentenceSettings,
    ServerSettings,
    Settings,
    TitleSettings,
    VadSettings,
)

CONFIG_PATH_ENV = "ASR_CONFIG_PATH"
CONFIG_FILE_NAME = "asr-qwen.yml"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = PACKAGE_ROOT.parent


def default_config_candidates() -> list[Path]:
    """Default lookup order: project root > package directory > current directory."""
    return [
        PROJECT_ROOT / CONFIG_FILE_NAME,
        PACKAGE_ROOT / CONFIG_FILE_NAME,
        Path.cwd() / CONFIG_FILE_NAME,
    ]


def resolve_config_path(path: str | Path | None = None) -> Path:
    """Locate the config file: explicit arg > ASR_CONFIG_PATH > first existing candidate."""
    if path is not None:
        return Path(path).expanduser()
    from_env = os.environ.get(CONFIG_PATH_ENV)
    if from_env:
        return Path(from_env).expanduser()
    candidates = default_config_candidates()
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def load_settings(path: str | Path | None = None) -> Settings:
    """Read the configuration file and build Settings."""
    config_path = resolve_config_path(path)
    return build_settings(_read_yaml(config_path), config_path)


def build_settings(data: Mapping[str, Any], config_path: Path) -> Settings:
    """Convert a parsed YAML mapping into Settings."""
    source = config_path
    base_dir = config_path.parent

    model = _section(data, "model", "", source)
    lid = _section(data, "lid", "", source)
    vad = _section(data, "vad", "", source)
    audio = _section(data, "audio", "", source)
    sentence = _section(data, "sentence", "", source)
    title = _section(data, "title", "", source)
    title_llm = _section(title, "llm", "title", source)
    server = _section(data, "server", "", source)

    return Settings(
        config_path=config_path,
        base_dir=base_dir,
        model=ModelSettings(
            asr_path=_as_path(model, "asr_path", "model", source, base_dir),
            aligner_path=_as_path(model, "aligner_path", "model", source, base_dir),
            dtype=_as_str(model, "dtype", "model", source),
            device=_as_str(model, "device", "model", source),
            max_inference_batch_size=_as_int(model, "max_inference_batch_size", "model", source),
        ),
        lid=LidSettings(
            enabled=_as_bool(lid, "enabled", "lid", source),
            model_path=_as_path(lid, "model_path", "lid", source, base_dir),
            device=_as_str(lid, "device", "lid", source),
            segment_seconds=_as_int(lid, "segment_seconds", "lid", source),
        ),
        vad=VadSettings(
            frame_ms=_as_int(vad, "frame_ms", "vad", source),
            hop_ms=_as_int(vad, "hop_ms", "vad", source),
            threshold_db=_as_float(vad, "threshold_db", "vad", source),
            min_silence_ms=_as_int(vad, "min_silence_ms", "vad", source),
            min_speech_ms=_as_int(vad, "min_speech_ms", "vad", source),
        ),
        audio=AudioSettings(
            sample_rate=_as_int(audio, "sample_rate", "audio", source),
            max_chunk_seconds=_as_int(audio, "max_chunk_seconds", "audio", source),
        ),
        sentence=SentenceSettings(
            min_gap_seconds=_as_float(sentence, "min_gap_seconds", "sentence", source),
            max_chars=_as_int(sentence, "max_chars", "sentence", source),
            max_duration_seconds=_as_float(sentence, "max_duration_seconds", "sentence", source),
        ),
        title=TitleSettings(
            llm=LlmSettings(
                base_url=_as_str(title_llm, "base_url", "title.llm", source).rstrip("/"),
                model=_as_str(title_llm, "model", "title.llm", source),
                api_key=_as_str(title_llm, "api_key", "title.llm", source, allow_empty=True),
                timeout_seconds=_as_float(title_llm, "timeout_seconds", "title.llm", source),
            ),
            max_chars=_as_int(title, "max_chars", "title", source),
            max_words=_as_int(title, "max_words", "title", source),
        ),
        server=ServerSettings(
            title=_as_str(server, "title", "server", source),
            version=_as_str(server, "version", "server", source),
            host=_as_str(server, "host", "server", source),
            port=_as_int(server, "port", "server", source),
            log_level=_as_str(server, "log_level", "server", source),
            workers=_as_int(server, "workers", "server", source),
        ),
    )


def _read_yaml(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        searched = "、".join(str(candidate) for candidate in default_config_candidates())
        raise ConfigError(
            f"Config file not found: {path} (searched: {searched}; "
            f"{CONFIG_PATH_ENV} can point at one explicitly)"
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: failed to parse YAML: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ConfigError(f"{path}: the top level of the config must be a mapping")
    return data


def _dotted(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def _section(parent: Mapping[str, Any], key: str, prefix: str, source: Path) -> Mapping[str, Any]:
    dotted = _dotted(prefix, key)
    if key not in parent:
        raise ConfigError(f"{source}: missing config section {dotted}")
    value = parent[key]
    if not isinstance(value, Mapping):
        raise ConfigError(f"{source}: config section {dotted} must be a mapping")
    return value


def _raw(parent: Mapping[str, Any], key: str, prefix: str, source: Path) -> tuple[str, Any]:
    dotted = _dotted(prefix, key)
    if key not in parent:
        raise ConfigError(f"{source}: missing config key {dotted}")
    value = parent[key]
    if value is None:
        raise ConfigError(f"{source}: config key {dotted} must not be empty")
    return dotted, value


def _as_str(
    parent: Mapping[str, Any],
    key: str,
    prefix: str,
    source: Path,
    *,
    allow_empty: bool = False,
) -> str:
    dotted, value = _raw(parent, key, prefix, source)
    if not isinstance(value, str):
        raise ConfigError(f"{source}: config key {dotted} must be a string")
    value = value.strip()
    if not value and not allow_empty:
        raise ConfigError(f"{source}: config key {dotted} must not be an empty string")
    return value


def _as_bool(parent: Mapping[str, Any], key: str, prefix: str, source: Path) -> bool:
    dotted, value = _raw(parent, key, prefix, source)
    if not isinstance(value, bool):
        raise ConfigError(f"{source}: config key {dotted} must be a boolean")
    return value


def _as_int(parent: Mapping[str, Any], key: str, prefix: str, source: Path) -> int:
    dotted, value = _raw(parent, key, prefix, source)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{source}: config key {dotted} must be an integer")
    return value


def _as_float(parent: Mapping[str, Any], key: str, prefix: str, source: Path) -> float:
    dotted, value = _raw(parent, key, prefix, source)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{source}: config key {dotted} must be a number")
    return float(value)


def _as_path(
    parent: Mapping[str, Any],
    key: str,
    prefix: str,
    source: Path,
    base_dir: Path,
) -> Path:
    value = Path(_as_str(parent, key, prefix, source)).expanduser()
    return value if value.is_absolute() else base_dir / value
