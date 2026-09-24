"""PyInstaller entrypoint for the bundled LogosForge core and MCP gateway.

This is the frozen equivalent of ``python -m logosforge.api``: it accepts the
same API CLI (``--host --port --mode --db``) so ``core-manager.ts`` can spawn
the packaged ``logosforge-core(.exe)`` exactly the way it spawns the dev venv.
``--mcp`` switches the same trusted binary into stdio gateway mode.
"""

from __future__ import annotations

import multiprocessing
import os
import sys


def _main(argv: list[str]) -> int:
    if argv and argv[0] == "--mcp":
        if len(argv) != 1:
            print("logosforge-core --mcp accepts no additional arguments.", file=sys.stderr)
            return 2
        from logosforge.librechat.mcp_runtime import resolve_runtime_descriptor_path
        from logosforge.librechat.mcp_server import main as mcp_main

        os.environ.setdefault(
            "LOGOSFORGE_MCP_CONNECTION_FILE",
            str(resolve_runtime_descriptor_path()),
        )
        os.environ.setdefault("LOGOSFORGE_MCP_REQUIRE_CONNECTION", "1")
        return mcp_main()

    from logosforge.api.server import main as api_main

    return api_main(argv)

if __name__ == "__main__":
    # Safe no-op for our single-process uvicorn run; guards against a frozen
    # re-exec spawning duplicate servers if multiprocessing is ever used.
    multiprocessing.freeze_support()
    sys.exit(_main(sys.argv[1:]))
