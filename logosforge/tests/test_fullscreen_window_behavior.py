"""Alpha UI stability — fullscreen/window behavior is always reversible.

The window must never trap the user in full screen: there is an in-app Toggle /
Exit Full Screen action (F11) in addition to the native control, exit always
returns to normal, repeated toggles never lock, and full screen is never forced
at startup. (Offscreen Qt may not raise a real fullscreen Space, so the tests
assert the reversible-state invariants and action wiring, which hold regardless.)
"""

import pytest

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _win():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_scene(pid, "S1", content="x", summary="s", act="Act I")
    return db, pid, MainWindow(db, pid)


def _menu_action_texts(win):
    texts = []
    for menu_action in win.menuBar().actions():
        menu = menu_action.menu()
        if menu is not None:
            texts.extend(a.text() for a in menu.actions())
    return texts


# 15-16. Toggle + Exit Full Screen actions exist in the menu.
def test_fullscreen_actions_exist():
    _db, _pid, win = _win()
    texts = _menu_action_texts(win)
    assert "Toggle Full Screen" in texts
    assert "Exit Full Screen" in texts
    assert hasattr(win, "toggle_fullscreen")
    assert hasattr(win, "enter_fullscreen")
    assert hasattr(win, "exit_fullscreen")


# 13. Full screen is never forced at startup.
def test_not_fullscreen_at_startup():
    _db, _pid, win = _win()
    assert win.isFullScreen() is False


# 18. Exit always returns to normal (guaranteed way out).
def test_exit_always_leaves_fullscreen():
    _db, _pid, win = _win()
    win.enter_fullscreen()
    win.exit_fullscreen()
    assert win.isFullScreen() is False


# 19. Repeated toggling never locks; exit afterwards always normalizes.
def test_repeated_toggle_then_exit_is_safe():
    _db, _pid, win = _win()
    for _ in range(3):
        win.toggle_fullscreen()
    win.exit_fullscreen()
    assert win.isFullScreen() is False


# Exit when not in full screen is a safe no-op (no crash).
def test_exit_when_not_fullscreen_is_noop():
    _db, _pid, win = _win()
    assert win.isFullScreen() is False
    win.exit_fullscreen()                         # must not raise
    assert win.isFullScreen() is False


# 22. Main navigation (sidebar) remains reachable after fullscreen toggles.
def test_navigation_reachable_after_fullscreen():
    _db, _pid, win = _win()
    win.toggle_fullscreen()
    win.exit_fullscreen()
    assert win.sidebar_buttons                    # sidebar buttons still present


# 26. No standalone Pages route mounted (disabled for Alpha; fullscreen-hostile).
def test_no_standalone_pages_route():
    _db, _pid, win = _win()
    assert "Pages" not in win.sidebar_buttons
