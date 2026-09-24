"""PyInstaller entrypoint for the standalone Whiteboard MCP companion."""

from __future__ import annotations

import multiprocessing
import os
import sys

from app.whiteboard_mcp.runtime import (
    CONNECTION_FILE_ENV,
    resolve_runtime_descriptor_path,
)
from app.whiteboard_mcp.server import main as mcp_main


def main() -> int:
    os.environ.setdefault(CONNECTION_FILE_ENV, str(resolve_runtime_descriptor_path()))
    return mcp_main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
