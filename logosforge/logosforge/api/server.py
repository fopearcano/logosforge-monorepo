"""Programmatic + CLI entry point for running the API with uvicorn.

Desktop/Electron launches this bound to localhost; a LAN/remote deployment can
override host/port/origins via ``API_*`` environment variables.

    python -m logosforge.api            # run with env config
    python -m logosforge.api --port 9000
"""

from __future__ import annotations

import argparse

from logosforge.api.app import create_api
from logosforge.api.config import ApiConfig


def run(config: ApiConfig | None = None) -> None:
    import uvicorn

    config = config or ApiConfig.from_env()
    app = create_api(config=config)
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Logosforge API server.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--mode", default=None, choices=["desktop", "lan", "remote"])
    parser.add_argument("--db", default=None, help="Path to the SQLite project DB")
    args = parser.parse_args(argv)

    config = ApiConfig.from_env()
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.mode:
        config.mode = args.mode
    if args.db:
        config.db_path = args.db

    run(config)
    return 0
