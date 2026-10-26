"""应用运行时上下文：配置 + 模型注册表。"""

from __future__ import annotations

from dataclasses import dataclass

from ..config.settings import Settings
from ..models.registry import ModelRegistry


@dataclass
class AppContext:
    settings: Settings
    registry: ModelRegistry
