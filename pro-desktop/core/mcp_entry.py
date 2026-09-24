"""PyInstaller entrypoint for the standalone packaged Pro MCP companion."""

from __future__ import annotations

import multiprocessing
import os
import sys

from logosforge.librechat.mcp_runtime import resolve_runtime_descriptor_path
from logosforge.librechat.mcp_server import main as mcp_main


def main() -> int:
    os.environ.setdefault(
        "LOGOSFORGE_MCP_CONNECTION_FILE",
        str(resolve_runtime_descriptor_path()),
    )
    os.environ.setdefault("LOGOSFORGE_MCP_REQUIRE_CONNECTION", "1")
    return mcp_main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
