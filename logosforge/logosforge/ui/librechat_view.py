"""LibreChat workspace panel.

A dedicated LogosForge section that connects to an OPTIONAL LibreChat sidecar.
It shows connection status and offers actions (open / retry / open in browser /
settings). When LibreChat is reachable, ``prefer_embedded`` is on, and Qt
WebEngine is importable, it embeds LibreChat in a ``QWebEngineView``; otherwise
it falls back to the system browser or a clear setup/unavailable message.

It never touches the active LogosForge project — selecting this section leaves
project/editor state untouched.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from logosforge.librechat.service import (
    ConnectionState,
    ConnectionStatus,
    LibreChatService,
)
from logosforge.ui import theme


def webengine_available() -> bool:
    """True when Qt WebEngine can be imported (PySide6-Addons present)."""
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        return True
    except Exception:
        return False


# Per-state status label + body message (kept out of the widget for testability).
def status_message(status: ConnectionStatus) -> tuple[str, str]:
    """Return (short status text, body message) for a connection status."""
    url = status.url or ""
    if status.state is ConnectionState.DISABLED:
        return (
            "Disabled",
            "LibreChat integration is turned off.\n\n"
            "Enable it in Settings → LibreChat to use the advanced chat workspace.",
        )
    if status.state is ConnectionState.INVALID_URL:
        return (
            "Invalid URL",
            f"The configured LibreChat URL is not valid.\n\n{status.detail}\n\n"
            "Fix it in Settings → LibreChat.",
        )
    if status.state is ConnectionState.CONNECTED:
        return ("Connected", f"Connected to LibreChat at {url}.")
    # UNREACHABLE
    return (
        "Not running",
        f"LibreChat is not reachable at {url or 'the configured URL'}.\n\n"
        "Start your LibreChat instance (it manages its own AI providers), then "
        "use “Retry connection”. You can also open it in your browser, or adjust "
        "the URL in Settings → LibreChat.",
    )


class LibreChatView(QWidget):
    """The LibreChat workspace section."""

    def __init__(
        self,
        service: LibreChatService | None = None,
        on_open_settings: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service or LibreChatService()
        self._on_open_settings = on_open_settings or (lambda: None)
        self._web: QWidget | None = None  # lazy QWebEngineView
        self._build_ui()
        self.refresh()

    # -- UI ---------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("LibreChat")
        title.setStyleSheet(
            f"color: {theme.get('TEXT_PRIMARY')}; font-size: 22px; font-weight: 600;"
        )
        header.addWidget(title)

        self._status_label = QLabel("…")
        self._status_label.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')}; font-size: 12px;"
        )
        header.addWidget(self._status_label)
        header.addStretch(1)

        self._open_btn = self._chip("Open LibreChat", self._on_open)
        self._retry_btn = self._chip("Retry connection", self.refresh)
        self._browser_btn = self._chip("Open in browser", self._open_in_browser)
        self._settings_btn = self._chip("LibreChat settings", self._open_settings)
        for btn in (self._open_btn, self._retry_btn, self._browser_btn, self._settings_btn):
            header.addWidget(btn)
        layout.addLayout(header)

        self._stack = QStackedWidget()
        self._message = QLabel("")
        self._message.setWordWrap(True)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')}; font-size: 14px;"
        )
        wrap = QWidget()
        wlay = QVBoxLayout(wrap)
        wlay.addStretch(1)
        wlay.addWidget(self._message)
        wlay.addStretch(1)
        self._stack.addWidget(wrap)  # index 0 — message panel
        layout.addWidget(self._stack, 1)

        self.setStyleSheet(f"QWidget {{ background-color: {theme.get('BG_PANEL')}; }}")

    def _chip(self, text: str, handler: Callable[[], None]) -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet(
            f"QPushButton {{ color: {theme.get('TEXT_MUTED')};"
            f" background: transparent; border: 1px solid {theme.get('BORDER')};"
            f" padding: 4px 10px; border-radius: 4px; }}"
            f"QPushButton:hover {{ color: {theme.get('TEXT_PRIMARY')}; }}"
        )
        btn.clicked.connect(handler)
        return btn

    # -- State ------------------------------------------------------------

    def refresh(self) -> ConnectionStatus:
        """Re-probe the service and update the panel. Auto-embeds when possible.

        Uses the service's current config (the MainWindow reloads it from
        settings whenever the settings dialog closes), so the view always
        reflects the latest configuration."""
        status = self._service.check_connection()
        short, body = status_message(status)
        connected = status.state is ConnectionState.CONNECTED
        accent = theme.get("ACCENT") if connected else theme.get("TEXT_MUTED")
        self._status_label.setText(short)
        self._status_label.setStyleSheet(f"color: {accent}; font-size: 12px;")
        self._message.setText(body)

        cfg = self._service.config
        # Enable/disable actions sensibly for the current state.
        self._open_btn.setEnabled(connected)
        self._browser_btn.setEnabled(cfg.is_valid_url() and cfg.enabled)

        if connected and cfg.prefer_embedded and webengine_available():
            self._show_embedded(cfg.normalized_url())
        else:
            self._stack.setCurrentIndex(0)  # message panel
        return status

    # -- Actions ----------------------------------------------------------

    def _on_open(self) -> None:
        status = self._service.check_connection()
        if status.state is not ConnectionState.CONNECTED:
            self.refresh()
            return
        cfg = self._service.config
        if cfg.prefer_embedded and webengine_available():
            self._show_embedded(cfg.normalized_url())
        elif cfg.browser_fallback:
            self._open_in_browser()
        else:
            self.refresh()

    def _open_in_browser(self) -> None:
        cfg = self._service.config
        if cfg.is_valid_url():
            QDesktopServices.openUrl(QUrl(cfg.normalized_url()))

    def _open_settings(self) -> None:
        self._on_open_settings()
        # The MainWindow reloads the shared service config when the dialog
        # closes; reflect any change immediately.
        self.refresh()

    def _show_embedded(self, url: str) -> None:
        if not webengine_available():
            self._stack.setCurrentIndex(0)
            return
        from PySide6.QtWebEngineWidgets import QWebEngineView
        if self._web is None:
            self._web = QWebEngineView()
            self._stack.addWidget(self._web)  # index 1
        current = self._web.url().toString() if self._web.url() else ""
        if current != url:
            self._web.setUrl(QUrl(url))
        self._stack.setCurrentWidget(self._web)
