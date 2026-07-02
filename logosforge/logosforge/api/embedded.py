"""Run the LogosForge FastAPI server INSIDE the desktop process (optional).

This is the piece that lets an external agent reach the user's **live** state:
because the server runs in the same process as the desktop UI and is handed the
*same* :class:`Database` instance, it sees the live project data, and the
in-process live-context registry (``logosforge.live_context``) lets it read
the current scene / selection that only exist in the running app.

Safety / constraints:

* OFF by default — gated by a setting; when off, none of this runs and startup
  is byte-for-byte unchanged.
* Bound to ``127.0.0.1`` in ``desktop`` mode (localhost CORS) — never exposed.
* Shares the desktop's ``Database`` (``check_same_thread=False`` + per-request
  sessions over a connection pool make this safe across the Qt thread and the
  uvicorn worker thread — no second connection is opened).
* uvicorn runs in a **daemon thread** with a clean ``should_exit`` shutdown so
  LogosForge always exits cleanly. No Docker / external infra.
"""

from __future__ import annotations

import threading
import time

from logosforge.api.config import DEFAULT_PORT, ApiConfig
from logosforge.db import Database


class EmbeddedApiServer:
    def __init__(
        self,
        db: Database,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
    ) -> None:
        self._db = db
        self._host = host
        self._port = int(port)
        self._server = None  # uvicorn.Server
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wait_until_serving(self, timeout: float = 2.0) -> bool:
        """Block briefly until uvicorn is actually serving, or the thread dies
        (e.g. the port is already in use — the bind happens on the worker
        thread, so ``start()`` cannot report it). Returns whether it bound."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server is not None and getattr(self._server, "started", False):
                return True
            if self._thread is not None and not self._thread.is_alive():
                return False  # exited (bind failure / error)
            time.sleep(0.05)
        return bool(self._server is not None and getattr(self._server, "started", False))

    def start(self) -> None:
        """Start the server in a daemon thread (no-op if already running)."""
        if self.is_running():
            return
        import uvicorn

        from logosforge.api.app import create_api

        config = ApiConfig(host=self._host, port=self._port, mode="desktop")
        app = create_api(db=self._db, config=config)
        uconfig = uvicorn.Config(
            app, host=self._host, port=self._port,
            log_level="warning", loop="asyncio", lifespan="off",
        )
        server = uvicorn.Server(uconfig)
        # We are not on the main thread, so uvicorn must not grab signal handlers.
        server.install_signal_handlers = lambda: None  # type: ignore[assignment]
        self._server = server
        self._thread = threading.Thread(
            target=server.run, name="logosforge-embedded-api", daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the server to exit and join its thread (only ours)."""
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.should_exit = True
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
