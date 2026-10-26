"""进程入口：加载配置并通过 uvicorn 启动服务。"""

from __future__ import annotations

import os

import uvicorn

from .api.app import create_app
from .config.loader import load_settings

# qwen_asr 调用 generate 时带了 generation_config 不支持的 temperature，transformers
# 会逐次告警；默认压掉这条噪音，排查时可用环境变量 TRANSFORMERS_VERBOSITY=info 覆盖
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

# 供 `uvicorn <package>.server:app` 使用；配置在导入时读取
app = create_app()


def main() -> None:
    settings = app.state.context.settings
    server = settings.server
    target = app if server.workers <= 1 else f"{__package__}.server:app"
    uvicorn.run(
        target,
        host=server.host,
        port=server.port,
        log_level=server.log_level,
        workers=server.workers,
    )


if __name__ == "__main__":
    main()
