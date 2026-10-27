"""Process entry point: load configuration and serve through uvicorn."""

from __future__ import annotations

import os

import uvicorn

from .api.app import create_app
from .config.loader import load_settings

# qwen_asr passes a `temperature` generation flag that the generation config does not
# support, and transformers warns on every inference. Silence it by default; set
# TRANSFORMERS_VERBOSITY=info to see the details again.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

# Used by `uvicorn <package>.server:app`; configuration is read at import time
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
