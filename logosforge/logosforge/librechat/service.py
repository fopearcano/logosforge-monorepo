"""Detection, connection, and OPTIONAL process management for LibreChat.

Design constraints (see the task spec):

* LibreChat is never a launch dependency for LogosForge.
* Detection/connection use a lightweight HTTP probe (same ``urllib`` stack the
  rest of the core uses) against the configured base URL.
* If a startup command is configured, the launcher: detects an already-running
  instance and never starts a duplicate; tracks ONLY the process LogosForge
  started; shuts down only that one (never an independently-launched instance);
  captures startup errors; and lets LogosForge exit cleanly.
* No Docker / Mongo / Meilisearch orchestration lives here. Container-based
  auto-launch is intentionally out of scope for this phase (documented).
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum

from logosforge.librechat.config import LibreChatConfig


class ConnectionState(str, Enum):
    DISABLED = "disabled"          # integration turned off in settings
    INVALID_URL = "invalid_url"    # base URL malformed
    CONNECTED = "connected"        # reachable (any HTTP response)
    UNREACHABLE = "unreachable"    # enabled + valid URL but no response


@dataclass
class ConnectionStatus:
    state: ConnectionState
    detail: str = ""
    url: str = ""

    @property
    def ok(self) -> bool:
        return self.state is ConnectionState.CONNECTED


class LibreChatService:
    """Helper around a :class:`LibreChatConfig`.

    Owns at most ONE child process: the LibreChat instance LogosForge itself
    started (only when a startup command is configured). Independently-started
    instances are never touched.
    """

    def __init__(self, config: LibreChatConfig | None = None) -> None:
        self._config = config or LibreChatConfig.load()
        self._proc: subprocess.Popen | None = None

    @property
    def config(self) -> LibreChatConfig:
        return self._config

    def reload_config(self) -> LibreChatConfig:
        self._config = LibreChatConfig.load()
        return self._config

    # -- Detection / connection -------------------------------------------

    def check_connection(self, timeout: float = 2.0) -> ConnectionStatus:
        cfg = self._config
        if not cfg.enabled:
            return ConnectionStatus(
                ConnectionState.DISABLED, "LibreChat integration is off.",
            )
        if not cfg.is_valid_url():
            return ConnectionStatus(
                ConnectionState.INVALID_URL,
                f"Invalid LibreChat base URL: {cfg.base_url!r}",
            )
        url = cfg.health_url()
        try:
            req = urllib.request.Request(
                url, method="GET", headers={"User-Agent": "LogosForge"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = getattr(resp, "status", None) or resp.getcode()
            return ConnectionStatus(ConnectionState.CONNECTED, f"HTTP {code}", url)
        except urllib.error.HTTPError as exc:
            # A served HTTP error (401/403/404…) still proves the service is up.
            return ConnectionStatus(ConnectionState.CONNECTED, f"HTTP {exc.code}", url)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return ConnectionStatus(
                ConnectionState.UNREACHABLE, f"{type(exc).__name__}: {exc}", url,
            )

    def is_running(self, timeout: float = 2.0) -> bool:
        return self.check_connection(timeout).ok

    # -- Optional process launcher ----------------------------------------

    def can_launch(self) -> bool:
        """True when a localhost startup command is configured. (Docker-based
        auto-launch is out of scope; configure a simple local command instead.)"""
        return bool((self._config.startup_command or "").strip()) and self._config.is_localhost

    def is_our_process_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, timeout: float = 2.0) -> ConnectionStatus:
        """Launch LibreChat via the configured startup command — but only if it
        is not already reachable and we have not already started one. Never
        starts a duplicate. Returns the post-launch connection status."""
        if self.is_our_process_running():
            return self.check_connection(timeout)
        if self.is_running(timeout):
            # Already served by something (e.g. a user-run docker-compose).
            return ConnectionStatus(
                ConnectionState.CONNECTED,
                "Already running (not started by LogosForge).",
                self._config.health_url(),
            )
        cmd = (self._config.startup_command or "").strip()
        if not cmd:
            return ConnectionStatus(
                ConnectionState.UNREACHABLE, "No startup command configured.",
            )
        if not self._config.is_localhost:
            return ConnectionStatus(
                ConnectionState.UNREACHABLE,
                "Refusing to launch a non-localhost LibreChat instance.",
            )
        try:
            self._proc = subprocess.Popen(  # noqa: S603 (user-configured command)
                self._split_command(cmd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, ValueError) as exc:
            self._proc = None
            return ConnectionStatus(
                ConnectionState.UNREACHABLE, f"Launch failed: {exc}",
            )
        if self._proc.poll() is not None:  # exited immediately → startup error
            code = self._proc.returncode
            self._proc = None
            return ConnectionStatus(
                ConnectionState.UNREACHABLE, f"Startup command exited ({code}).",
            )
        return self.check_connection(timeout)

    def stop(self) -> None:
        """Shut down ONLY the instance LogosForge started (a no-op otherwise)."""
        proc = self._proc
        self._proc = None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except OSError:
            pass

    @staticmethod
    def _split_command(cmd: str) -> list[str]:
        # posix=False on Windows keeps drive letters / backslashes intact.
        return shlex.split(cmd, posix=not sys.platform.startswith("win"))
