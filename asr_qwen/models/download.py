"""Missing-model detection and automatic ModelScope download."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from ..config.settings import Settings

logger = logging.getLogger(__name__)

# Settings accessor -> ModelScope model id (the model source is fixed)
def _lid_path(settings: Settings) -> Path:
    return settings.lid.model_path


MODEL_TARGETS: tuple[tuple[Callable[[Settings], Path], str], ...] = (
    (lambda s: s.model.asr_path, "Qwen/Qwen3-ASR-1.7B"),
    (lambda s: s.model.aligner_path, "Qwen/Qwen3-ForcedAligner-0.6B"),
    (_lid_path, "iic/SenseVoiceSmall"),
)


def ensure_models(settings: Settings) -> None:
    """Check the configured model paths; download missing or empty ones from ModelScope."""
    from modelscope import snapshot_download

    for get_path, model_id in MODEL_TARGETS:
        local_dir = get_path(settings)
        if get_path is _lid_path and not settings.lid.enabled:
            logger.info("lid disabled, skipping %s", model_id)
            continue
        if local_dir.is_dir() and any(local_dir.iterdir()):
            continue
        logger.info("model missing, downloading %s from ModelScope -> %s", model_id, local_dir)
        snapshot_download(model_id, local_dir=str(local_dir))
