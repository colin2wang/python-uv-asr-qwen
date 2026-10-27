"""Loading and lifecycle management for the Qwen3-ASR and SenseVoice models."""

from __future__ import annotations

import logging
from typing import Any

from ..config.settings import Settings

logger = logging.getLogger(__name__)


def _resolve_dtype(name: str) -> Any:
"""Resolve a configured dtype name (e.g. float16) to a torch.dtype."""
    import torch

    dtype = getattr(torch, name, None)
    if not isinstance(dtype, torch.dtype):
        raise ValueError(f"unsupported model.dtype: {name}")
    return dtype


class ModelRegistry:
    """Load and own the inference models; attributes stay None until loading finishes."""

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
        """Load the main model and the optional LID model, downloading them if missing."""
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
        except ImportError as exc:
            self._lid = None
            logger.warning(
                "SenseVoice LID dependency missing (%s): install it with "
                "`uv sync --extra lid`, or set lid.enabled to false in asr-qwen.yml; "
                "transcription does not depend on this model",
                exc,
            )
            return
        try:
            self._lid = AutoModel(
                model=str(lid_settings.model_path),
                disable_update=True,
                device=lid_settings.device,
            )
            logger.info("SenseVoice LID loaded (%s)", lid_settings.device)
        except Exception as exc:
            self._lid = None
            logger.warning("SenseVoice LID unavailable: %s", exc)
