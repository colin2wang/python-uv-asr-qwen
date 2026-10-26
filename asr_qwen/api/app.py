"""FastAPI 应用装配：注册路由并在启动时加载模型。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config.loader import load_settings
from ..config.settings import Settings
from ..models.registry import ModelRegistry
from .context import AppContext
from .routes import router
from .testui import router as testui_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    context: AppContext = app.state.context
    context.registry.load()
    server = context.settings.server
    host = "127.0.0.1" if server.host in ("0.0.0.0", "::") else server.host
    print(f"API      http://{host}:{server.port}/docs")
    print(f"测试页面 http://{host}:{server.port}/ui")
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """构建应用；未传入配置时从 asr-qwen.yml 读取。"""
    settings = settings or load_settings()
    app = FastAPI(
        title=settings.server.title,
        version=settings.server.version,
        lifespan=_lifespan,
    )
    app.state.context = AppContext(settings=settings, registry=ModelRegistry(settings))
    app.include_router(router)
    app.include_router(testui_router)
    return app
