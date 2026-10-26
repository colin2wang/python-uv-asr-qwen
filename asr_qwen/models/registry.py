"""Qwen3-ASR 与 SenseVoice 模型的加载和生命周期管理。"""

from __future__ import annotations

import logging
from typing import Any

from ..config.settings import Settings

logger = logging.getLogger(__name__)


def _resolve_dtype(name: str) -> Any:
    """把配置中的 dtype 名称（如 float16）解析为 torch.dtype。"""
    import torch

    dtype = getattr(torch, name, None)
    if not isinstance(dtype, torch.dtype):
        raise ValueError(f"不支持的 model.dtype: {name}")
    return dtype


class ModelRegistry:
    """按配置加载并持有推理模型，模型未加载完成时属性为 None。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._asr: Any | None = None
        self._lid: Any | None = None

    @property
    def asr(self) -> Any | None:
        return self._asr

    @property
    def lid(self) -> Any | None:
        return self._lid

    @property
    def ready(self) -> bool:
        return self._asr is not None

    def load(self) -> None:
        """加载主模型与可选的语种识别模型；本地缺失的模型先从 ModelScope 下载。"""
        from .download import ensure_models

        ensure_models(self._settings)
        from qwen_asr import Qwen3ASRModel

        model_settings = self._settings.model
        dtype = _resolve_dtype(model_settings.dtype)
        self._asr = Qwen3ASRModel.from_pretrained(
            str(model_settings.asr_path),
            forced_aligner=str(model_settings.aligner_path),
            forced_aligner_kwargs={"dtype": dtype, "device_map": model_settings.device},
            dtype=dtype,
            device_map=model_settings.device,
            max_inference_batch_size=model_settings.max_inference_batch_size,
        )
        self._load_lid()
        logger.info(
            "model loaded on %s, lid=%s",
            model_settings.device,
            "on" if self._lid else "off",
        )

    def _load_lid(self) -> None:
        lid_settings = self._settings.lid
        if not lid_settings.enabled:
            logger.info("SenseVoice LID disabled by configuration")
            return
        try:
            from funasr import AutoModel

            self._lid = AutoModel(
                model=str(lid_settings.model_path),
                disable_update=True,
                device=lid_settings.device,
            )
            logger.info("SenseVoice LID loaded (%s)", lid_settings.device)
        except Exception as exc:
            self._lid = None
            logger.warning("SenseVoice LID unavailable: %s", exc)
