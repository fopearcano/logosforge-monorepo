"""PyInstaller entrypoint for the bundled LogosForge Whiteboard backend.

The frozen equivalent of ``python -m uvicorn app.main:app``: it accepts
``--host``/``--port`` so ``backend-manager.ts`` can spawn the packaged
``logosforge-whiteboard-backend(.exe)`` exactly the way it spawns the dev venv.

The backend wraps the LogosForge core *in-process* (see ``app/core_client.py``),
so freezing this entry pulls the whole core into the bundle too — no Python is
needed on the user's machine.
"""

from __future__ import annotations

import argparse
import multiprocessing
import sys


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="logosforge-whiteboard-backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    args = parser.parse_args(argv)

    # Import lazily so ``--help`` is instant and any import failure surfaces with
    # a clean traceback rather than at module load. Pass the app OBJECT (not the
    # "app.main:app" import string) so uvicorn runs single-process with no
    # reload — the only mode that is correct for a frozen build.
    import uvicorn
    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    # Critical on Windows + PyInstaller: without freeze_support a frozen re-exec
    # can spawn duplicate servers. A safe no-op for our single-process run.
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv[1:]))
