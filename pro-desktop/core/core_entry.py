"""PyInstaller entrypoint for the bundled LogosForge core API.

This is the frozen equivalent of ``python -m logosforge.api``: it accepts the
same CLI (``--host --port --mode --db``) so ``core-manager.ts`` can spawn the
packaged ``logosforge-core(.exe)`` exactly the way it spawns the dev venv.
"""

from __future__ import annotations

import multiprocessing
import sys

from logosforge.api.server import main

if __name__ == "__main__":
    # Safe no-op for our single-process uvicorn run; guards against a frozen
    # re-exec spawning duplicate servers if multiprocessing is ever used.
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv[1:]))
