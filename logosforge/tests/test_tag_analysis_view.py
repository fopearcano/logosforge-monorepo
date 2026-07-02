"""Tag Analysis view: f-string header fix, case-insensitive grouping, coverage
stat, and navigable scene links."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.tag_analysis_view import TagAnalysisView


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _proj(db):
    return db.create_project("P", narrative_engine="novel").id


def test_empty_state():
    db = Database()
    pid = _proj(db)
    view = TagAnalysisView(db, pid)
    assert "No tags assigned" in view._last_html


def test_header_border_is_interpolated_not_literal():
    # The header row used a plain (non-f) string → "{theme.BORDER}" leaked into
    # the HTML, breaking the underline. It must now be a real colour.
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "S", tags="magic")
    view = TagAnalysisView(db, pid)
    assert "{theme.BORDER}" not in view._last_html
    # Both header (2px) and body (1px) borders are present.
    assert "border-bottom: 2px solid #" in view._last_html
    assert "border-bottom: 1px solid #" in view._last_html


def test_case_insensitive_grouping():
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "A", tags="Magic, betrayal")
    db.create_scene(pid, "B", tags="magic, hope")
    view = TagAnalysisView(db, pid)
    # "Magic" and "magic" collapse into ONE tag spanning both scenes.
    assert "magic" in view._tag_scenes
    assert len(view._tag_scenes["magic"]) == 2
    assert len(view._tag_scenes) == 3                 # magic, betrayal, hope
    assert view._display["magic"] == "Magic"          # first-seen casing kept


def test_coverage_stat():
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "A", tags="magic")
    db.create_scene(pid, "B")                         # untagged
    view = TagAnalysisView(db, pid)
    assert "1 of 2 scenes tagged (50%)" in view._last_html
    assert "1 scene(s) without tags" in view._last_html


def test_scene_entries_navigate_when_callback_given():
    calls = []
    db = Database()
    pid = _proj(db)
    sid = db.create_scene(pid, "S", tags="magic").id
    view = TagAnalysisView(db, pid, on_open_scene=lambda i: calls.append(i))
    assert f"scene:{sid}" in view._last_html          # rendered as a link
    view._on_anchor(QUrl(f"scene:{sid}"))             # click → navigate
    assert calls == [sid]


def test_no_links_without_callback():
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "S", tags="magic")
    view = TagAnalysisView(db, pid)                   # no navigation callback
    assert "scene:" not in view._last_html
    # A bogus anchor click is a safe no-op (no callback).
    view._on_anchor(QUrl("scene:999"))


def test_html_escaping_of_tag_and_title():
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "A<i>", tags="a<i>")
    view = TagAnalysisView(db, pid)
    assert "a&lt;i&gt;" in view._last_html        # tag escaped
    assert "A&lt;i&gt;" in view._last_html        # title escaped
    assert "a<i>" not in view._last_html          # no raw injection
    assert "A<i>" not in view._last_html
