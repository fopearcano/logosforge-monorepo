"""UI tests for the LibreChat integration: the workspace view, the nav button,
browser fallback, and that the existing Chat section is untouched."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from logosforge.db import Database
from logosforge.librechat.config import LibreChatConfig
from logosforge.librechat.service import (
    ConnectionState,
    ConnectionStatus,
    LibreChatService,
)
from logosforge.ui.chat_view import ChatView
from logosforge.ui.librechat_view import (
    LibreChatView,
    status_message,
    webengine_available,
)
from logosforge.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _setup():
    db = Database()
    return db, db.create_project("LCViewTest")


# -- Status messages ---------------------------------------------------------

def test_status_message_for_each_state():
    for state in ConnectionState:
        short, body = status_message(ConnectionStatus(state, "d", "http://x"))
        assert short and body  # every state has user-facing text


def test_webengine_available_is_bool():
    assert isinstance(webengine_available(), bool)


# -- View --------------------------------------------------------------------

def test_view_shows_disabled_state(qapp):
    view = LibreChatView(service=LibreChatService(LibreChatConfig(enabled=False)))
    assert view._status_label.text() == "Disabled"
    assert "turned off" in view._message.text().lower()
    assert view._open_btn.isEnabled() is False  # can't open when not connected


def test_view_shows_unreachable_state(qapp):
    import urllib.error
    from unittest import mock
    from logosforge.librechat import service as lc_service
    svc = LibreChatService(LibreChatConfig(enabled=True, base_url="http://127.0.0.1:6"))
    with mock.patch.object(lc_service.urllib.request, "urlopen",
                           side_effect=urllib.error.URLError("x")):
        view = LibreChatView(service=svc)
    assert view._status_label.text() == "Not running"
    assert view._open_btn.isEnabled() is False


def test_view_open_in_browser_uses_desktop_services(qapp, monkeypatch):
    opened = []
    import logosforge.ui.librechat_view as lv
    monkeypatch.setattr(lv.QDesktopServices, "openUrl",
                        lambda url: opened.append(url.toString()))
    cfg = LibreChatConfig(enabled=True, base_url="http://localhost:3080",
                          browser_fallback=True)
    view = LibreChatView(service=LibreChatService(cfg))
    view._open_in_browser()
    assert opened == ["http://localhost:3080"]


def test_view_open_settings_callback(qapp):
    called = []
    view = LibreChatView(
        service=LibreChatService(LibreChatConfig()),
        on_open_settings=lambda: called.append(True),
    )
    view._open_settings()
    assert called == [True]


# -- Navigation + non-regression --------------------------------------------

def test_librechat_button_below_chat_in_layout(qapp):
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    assert "LibreChat" in win.sidebar_buttons
    assert "LibreChat" in win._nav_section_handlers
    # ordering: LibreChat registered immediately after Chat in the nav labels.
    labels = win._nav_labels
    assert labels.index("LibreChat") == labels.index("Chat") + 1


def test_show_librechat_opens_workspace_without_touching_project(qapp):
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    pid_before = win._project_id
    win._show_librechat()
    assert isinstance(win.content_area, LibreChatView)
    assert win._project_id == pid_before  # project/editor state untouched


def test_existing_chat_section_is_preserved(qapp):
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    # Chat button + handler still present and working.
    assert "Chat" in win.sidebar_buttons
    assert win._nav_section_handlers["Chat"] == win._show_chat
    win._show_chat()
    assert isinstance(win._chat_view, ChatView)


def test_startup_without_librechat_is_fine(qapp):
    # Integration OFF by default — the app builds normally and LibreChat is
    # never required for launch.
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    assert win._librechat_service.config.enabled is False
    assert "LibreChat" in win.sidebar_buttons  # button still present


def test_button_hidden_only_by_explicit_setting(qapp):
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    btn = win.sidebar_buttons["LibreChat"]
    LibreChatConfig(button_visible=False).save()
    win._apply_librechat_button_visibility()
    assert btn.isVisible() is False
    LibreChatConfig(button_visible=True).save()
    win._apply_librechat_button_visibility()
    # (offscreen visibility can be False until shown, but the hidden flag clears)
    assert not btn.isHidden()
