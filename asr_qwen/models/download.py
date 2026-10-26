"""模型缺失检测与 ModelScope 自动下载。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from ..config.settings import Settings

logger = logging.getLogger(__name__)

# 配置取值函数 -> ModelScope 模型 ID（模型来源固定）
def _lid_path(settings: Settings) -> Path:
    return settings.lid.model_path


MODEL_TARGETS: tuple[tuple[Callable[[Settings], Path], str], ...] = (
    (lambda s: s.model.asr_path, "Qwen/Qwen3-ASR-1.7B"),
    (lambda s: s.model.aligner_path, "Qwen/Qwen3-ForcedAligner-0.6B"),
    (_lid_path, "iic/SenseVoiceSmall"),
)


def ensure_models(settings: Settings) -> None:
    """检查配置中的模型路径，目录缺失或为空的从 ModelScope 下载。"""
    from modelscope import snapshot_download

    for get_path, model_id in MODEL_TARGETS:
        local_dir = get_path(settings)
        if get_path is _lid_path and not settings.lid.enabled:
            logger.info("lid 未启用，跳过 %s", model_id)
            continue
        if local_dir.is_dir() and any(local_dir.iterdir()):
            continue
        logger.info("模型缺失，从 ModelScope 下载 %s -> %s", model_id, local_dir)
        snapshot_download(model_id, local_dir=str(local_dir))
