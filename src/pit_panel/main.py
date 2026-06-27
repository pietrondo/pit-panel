import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import uvicorn

from pit_panel.config import Settings


def main():
    parser = argparse.ArgumentParser(description="pit-panel VPS Management Panel")
    parser.add_argument("--host", default=None, help="Bind address")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--config", default=None, help="Config file path")
    args = parser.parse_args()

    settings = Settings.from_config_file(args.config)

    host = args.host or settings.host
    port = args.port or settings.port
    reload = args.reload or settings.debug

    # Ensure /var/log/pit-panel exists
    log_dir = Path("/var/log/pit-panel")
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(log_dir / "app.log", maxBytes=5_242_880, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logging.getLogger().addHandler(handler)

    # When no domain configured, bind to all interfaces for direct IP access
    if not settings.base_domain and host == "127.0.0.1":
        host = "0.0.0.0"

    uvicorn.run(
        "pit_panel.web.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    main()
