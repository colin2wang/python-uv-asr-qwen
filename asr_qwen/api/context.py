"""Runtime application context: settings plus the model registry."""

from __future__ import annotations

from dataclasses import dataclass

from ..config.settings import Settings
from ..models.registry import ModelRegistry


@dataclass
class AppContext:
    settings: Settings
    registry: ModelRegistry
