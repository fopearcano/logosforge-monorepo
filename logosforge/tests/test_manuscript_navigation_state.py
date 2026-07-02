"""Alpha UI stability — Manuscript view/state is preserved across navigation.

The Manuscript editor must NOT be destroyed/recreated when the user visits
another section and returns (which reset scroll / focus / selection / current
screenplay element type). It is cached per-project, reused on return, refreshed
(state-preservingly) only when data changed elsewhere, and reset on project
switch.
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


def _win(engine="screenplay"):
    db = Database()
    pid = db.create_project("P", narrative_engine=engine).id
    db.create_scene(pid, "S1", content="INT. ARCHIVE - DAWN\n\nAda enters.",
                    summary="open", act="Act I")
    return db, pid, MainWindow(db, pid)


# 1-3. Navigating away and back reuses the SAME manuscript widget (not a rebuild).
def test_manuscript_cached_across_navigation():
    _db, _pid, win = _win()
    win._show_manuscript()
    v1 = win._cached_manuscript_view
    assert v1 is not None and win.content_area is v1
    win._show_notes()
    assert win.content_area is not v1            # switched away
    win._show_manuscript()
    assert win._cached_manuscript_view is v1     # SAME instance reused
    assert win.content_area is v1


def test_navigation_through_multiple_sections_preserves_instance():
    _db, _pid, win = _win()
    win._show_manuscript()
    v1 = win._cached_manuscript_view
    for nav in (win._show_notes, win._show_dashboard, win._show_plan):
        nav()
        win._show_manuscript()
        assert win._cached_manuscript_view is v1


def test_screenplay_element_type_accessor_stable():
    _db, _pid, win = _win("screenplay")
    win._show_manuscript()
    v1 = win._cached_manuscript_view
    before = v1.current_element_type()
    win._show_notes()
    win._show_manuscript()
    assert win._cached_manuscript_view is v1
    assert v1.current_element_type() == before   # same widget → preserved


# 4. Simple navigation (no data change) does NOT refresh/reload/normalize.
def test_plain_navigation_does_not_refresh(monkeypatch):
    _db, _pid, win = _win()
    win._show_manuscript()
    v1 = win._cached_manuscript_view
    win._manuscript_needs_refresh = False
    calls = {"n": 0}
    monkeypatch.setattr(v1, "refresh",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    win._show_notes()
    win._show_manuscript()
    assert calls["n"] == 0                        # no reload / no normalization


# 5. A data change elsewhere marks the manuscript for a (state-preserving)
# refresh, which runs once on return and then clears.
def test_data_change_triggers_one_refresh_on_return(monkeypatch):
    _db, _pid, win = _win()
    win._show_manuscript()
    v1 = win._cached_manuscript_view
    calls = {"n": 0}
    monkeypatch.setattr(v1, "refresh",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    win._show_notes()
    win._on_data_changed()
    assert win._manuscript_needs_refresh is True
    win._show_manuscript()
    assert calls["n"] == 1
    assert win._manuscript_needs_refresh is False


# 6. Dirty state survives navigation (an unsaved edit stays dirty).
def test_dirty_survives_navigation():
    _db, _pid, win = _win()
    win._show_manuscript()
    win._on_data_changed()                        # simulate an edit
    assert win._dirty is True
    win._show_notes()
    win._show_manuscript()
    assert win._dirty is True


# 7. The cached manuscript view is hidden (not destroyed) when navigating away.
def test_cached_manuscript_not_destroyed_on_switch():
    _db, _pid, win = _win()
    win._show_manuscript()
    v1 = win._cached_manuscript_view
    win._show_notes()
    # Still a live, usable object (we only hide it) — accessing it never raises.
    assert win._cached_manuscript_view is v1
    assert v1.current_element_type() is not None


# 8. Graphic Novel manuscript uses the shared WritingCoreView (not legacy).
def test_graphic_novel_uses_shared_renderer_and_caches():
    from logosforge.ui.writing_core_view import WritingCoreView
    _db, _pid, win = _win("graphic_novel")
    win._show_manuscript()
    assert isinstance(win._cached_manuscript_view, WritingCoreView)
    v1 = win._cached_manuscript_view
    win._show_plan()
    win._show_manuscript()
    assert win._cached_manuscript_view is v1


# 9. A fresh window starts with no cached manuscript (new project → clean state).
def test_fresh_window_has_no_cached_manuscript():
    _db, _pid, win = _win()
    assert win._cached_manuscript_view is None
    assert win._manuscript_needs_refresh is False
