"""Graphic Novel pre-finalization refactor — canonical Act → Page → Scene → Panel.

The Graphic Novel Outline's visible hierarchy is **Project → Act → Page →
Scene → Panel** and the Manuscript derives from it: an Act owns its act-wide
Pages and its Scenes; a Panel belongs to exactly one Scene and sits on exactly
one Page; a Scene can span several Pages (its panels distributed across them);
one Page can hold Panels from several Scenes ("Scene … continued" labels in
page-first physical order). Storage stays the scene-local body script — the
act-wide coordinates come from :mod:`graphic_novel_structure` over the single
new nullable ``Scene.gn_page_start`` offset (NULL = auto-chain after the
previous scene, i.e. the exact legacy layout). Chapters are hidden in Graphic
Novel mode (compat labels only); other writing modes are untouched; the
standalone Pages section stays disabled.
"""

from __future__ import annotations

import sqlite3
import warnings

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QLabel, QPushButton, QSpinBox,
)

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_outline as gno
from logosforge import graphic_novel_structure as gns
from logosforge import story_structure as ss
from logosforge.ui import safe_dialogs

_ROLE = Qt.ItemDataRole.UserRole


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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


def _gn(db, title="GN"):
    return db.create_project(title, narrative_engine="graphic_novel",
                             default_writing_format="graphic_novel").id


def _scene(db, pid, title="S", act="Act 1"):
    return ss.create_scene(db, pid, act=act, title=title).id


def _pages(db, sid, n, panels_per_page=1):
    for i in range(n):
        gno.add_page(db, sid)
        for _ in range(panels_per_page):
            gno.add_panel(db, sid, i)


def _outline(db, pid, **callbacks):
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    callbacks.setdefault("on_data_changed", lambda: None)
    callbacks.setdefault("on_open_manuscript", lambda i: None)
    return GraphicNovelOutlineView(db, pid, **callbacks)


def _manuscript(db, pid):
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    return GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)


def _find(tree, predicate):
    stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    while stack:
        it = stack.pop(0)
        if predicate(it):
            return it
        for i in range(it.childCount()):
            stack.append(it.child(i))
    return None


def _shared_page_project(db):
    """The spec example: Act 1 — Scene A spans Pages 1–2; Scene B pinned to
    start on Page 2, so Page 2 holds panels from BOTH scenes."""
    pid = _gn(db)
    a = _scene(db, pid, "A")
    b = _scene(db, pid, "B")
    _pages(db, a, 2)
    _pages(db, b, 2)
    assert gns.set_scene_start_page(db, b, 2)
    return pid, a, b


# ==========================================================================
# 1. Model — act-wide page coordinates (gn_page_start + auto-chain)
# ==========================================================================


def test_gn_page_start_defaults_to_none():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    assert db.get_scene_by_id(sid).gn_page_start is None


def test_first_scene_auto_chains_to_page_one():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    _pages(db, sid, 1)
    _act, placement = gns.find_placement(db, pid, sid)
    assert placement.start_page == 1 and placement.explicit is False


def test_auto_chain_starts_after_previous_scene():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    b = _scene(db, pid, "B")
    _pages(db, a, 3)
    _pages(db, b, 1)
    _act, pb = gns.find_placement(db, pid, b)
    assert pb.start_page == 4                      # A used 1-3
    assert pb.explicit is False


def test_scene_spans_multiple_pages():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    _pages(db, sid, 3)
    _act, placement = gns.find_placement(db, pid, sid)
    assert (placement.start_page, placement.end_page) == (1, 3)
    [( _act2, pages, _pl )] = [
        (a, p, pl) for a, p, pl in gns.act_view(db, pid)]
    assert [no for no, _s in pages] == [1, 2, 3]
    # Continuation: pages after the scene's first are marked continued.
    flags = [s.continued for _no, slices in pages for s in slices]
    assert flags == [False, True, True]


def test_pinned_start_lets_two_scenes_share_a_page():
    db = Database()
    pid, a, b = _shared_page_project(db)
    view = gns.act_view(db, pid)
    (_act, pages, _placements) = view[0]
    by_no = dict(pages)
    assert sorted(by_no) == [1, 2, 3]
    # Page 2 = Scene A (continued) + Scene B (its first page).
    page2 = [(s.placement.scene.title, s.continued) for s in by_no[2]]
    assert page2 == [("A", True), ("B", False)]
    assert [s.placement.scene.title for s in by_no[1]] == ["A"]
    assert [(s.placement.scene.title, s.continued)
            for s in by_no[3]] == [("B", True)]


def test_panel_belongs_to_one_scene_and_one_page():
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    seen = set()
    for _act, pages, _pl in gns.act_view(db, pid):
        for no, slices in pages:
            for sl in slices:
                for panel in sl.page.panels:
                    key = (sl.placement.scene.id, sl.local_idx,
                           panel.number)
                    assert key not in seen        # placed exactly once
                    seen.add(key)
    assert len(seen) == 4                          # 2 scenes × 2 pages × 1


def test_release_pin_returns_to_auto_chain():
    db = Database()
    pid, _a, b = _shared_page_project(db)
    assert gns.set_scene_start_page(db, b, None)
    _act, pb = gns.find_placement(db, pid, b)
    assert pb.start_page == 3 and pb.explicit is False


@pytest.mark.parametrize("bad", [0, -1, "nope"])
def test_invalid_start_page_is_refused(bad):
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    assert gns.set_scene_start_page(db, sid, bad) is False
    assert db.get_scene_by_id(sid).gn_page_start is None
    _ = pid


def test_garbage_stored_value_falls_back_to_auto():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    _pages(db, a, 1)
    scene = db.get_scene_by_id(a)
    # Defensive: a corrupt/legacy value must never break the layout.
    for raw in (None, -3, 0):
        db.set_scene_gn_page_start(a, raw)
        _act, placement = gns.find_placement(db, pid, a)
        assert placement.start_page == 1
        _ = scene


def test_page_numbers_reset_per_act():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A", act="Act 1")
    c = _scene(db, pid, "C", act="Act 2")
    _pages(db, a, 2)
    _pages(db, c, 1)
    view = {act: pages for act, pages, _pl in gns.act_view(db, pid)}
    assert [no for no, _ in view["Act 1"]] == [1, 2]
    assert [no for no, _ in view["Act 2"]] == [1]  # acts own their pages


def test_empty_scene_occupies_no_pages_and_does_not_advance():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    empty = _scene(db, pid, "Empty")
    b = _scene(db, pid, "B")
    _pages(db, a, 2)
    _pages(db, b, 1)
    _act, pe = gns.find_placement(db, pid, empty)
    assert pe.page_count == 0
    assert gns.scene_page_range_label(pe) == "no pages yet"
    _act, pb = gns.find_placement(db, pid, b)
    assert pb.start_page == 3                      # Empty did not advance


def test_backward_pin_does_not_shrink_the_chain():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    b = _scene(db, pid, "B")
    c = _scene(db, pid, "C")
    _pages(db, a, 4)
    _pages(db, b, 1)
    _pages(db, c, 1)
    gns.set_scene_start_page(db, b, 2)             # B shares A's Page 2
    _act, pc = gns.find_placement(db, pid, c)
    assert pc.start_page == 5                      # after A's high water


def test_scene_page_range_label_forms():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    _pages(db, a, 1)
    _act, pa = gns.find_placement(db, pid, a)
    assert gns.scene_page_range_label(pa) == "Page 1"
    _pages(db, a, 2)
    _act, pa = gns.find_placement(db, pid, a)
    assert gns.scene_page_range_label(pa) == "Pages 1–3"


def test_migration_adds_column_to_legacy_db(tmp_path):
    path = str(tmp_path / "legacy.db")
    db = Database(path)
    pid = _gn(db)
    sid = _scene(db, pid, "Legacy")
    # Simulate a pre-refactor database: drop the new column entirely.
    raw = sqlite3.connect(path)
    raw.execute("ALTER TABLE scene DROP COLUMN gn_page_start")
    raw.commit()
    raw.close()
    db2 = Database(path)                           # migration runs on open
    assert db2.get_scene_by_id(sid).gn_page_start is None
    db2.set_scene_gn_page_start(sid, 7)
    db3 = Database(path)                           # idempotent on re-open
    assert db3.get_scene_by_id(sid).gn_page_start == 7


def test_pin_persists_across_reopen(tmp_path):
    path = str(tmp_path / "persist.db")
    db = Database(path)
    pid, _a, b = _shared_page_project(db)
    db2 = Database(path)
    _act, pb = gns.find_placement(db2, pid, b)
    assert pb.start_page == 2 and pb.explicit is True


# ==========================================================================
# 2. Outline — visible Act → Page → Scene → Panel hierarchy
# ==========================================================================


def test_outline_tree_is_act_page_scene_panel():
    from PySide6.QtWidgets import QFrame
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    v = _outline(db, pid)
    acts = [c for c in v._cards if c.gn_data["kind"] == "act"]
    pages = [c for c in v._cards if c.gn_data["kind"] == "act_page"]
    assert len(acts) == 1 and [p.gn_data["page_no"] for p in pages] == [1, 2, 3]
    panel = next(c for c in v._cards if c.gn_data["kind"] == "panel")
    chain = []
    w = panel.parentWidget()
    while w is not None:
        if isinstance(w, QFrame) and w.objectName().startswith("gn"):
            chain.append(w.objectName())
        w = w.parentWidget()
    assert chain[:3] == ["gnSceneGroup", "gnPageCard", "gnActCard"]



def test_outline_page_first_physical_order():
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    v = _outline(db, pid)
    pages = [c.gn_data["page_no"] for c in v._cards
             if c.gn_data["kind"] == "act_page"]
    assert pages == [1, 2, 3]



def test_outline_continued_label_for_spanning_scene():
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    v = _outline(db, pid)
    page2 = next(c for c in v._cards
                 if c.gn_data["kind"] == "act_page"
                 and c.gn_data["page_no"] == 2)
    texts = [w.text() for w in page2.findChildren(QLabel)
             if w.objectName() == "gnOutlineSceneLabel"]
    assert any(t.startswith("SCENE — A (continued)") for t in texts)
    assert any(t.startswith("SCENE — B") and "(continued)" not in t
               for t in texts)



def test_outline_shared_page_lists_both_scenes():
    db = Database()
    pid, a, b = _shared_page_project(db)
    v = _outline(db, pid)
    groups = [c.gn_data["scene_id"] for c in v._cards
              if c.gn_data["kind"] == "scene_page"
              and c.gn_data["page_no"] == 2]
    assert groups == [a, b]



def test_outline_hides_chapter_everywhere():
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    v = _outline(db, pid)
    assert not any("Chapter" in w.text() for w in v.findChildren(QLabel))
    # The stored compat label still exists — it is just never shown.
    assert db.get_scene_by_id(_a).chapter



def test_outline_empty_scene_visible_under_act():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "Lonely")
    v = _outline(db, pid)
    group = next(c for c in v._cards if c.gn_data.get("kind") == "scene")
    assert group.gn_data["scene_id"] == sid
    texts = [w.text() for w in group.findChildren(QLabel)
             if w.objectName() == "gnOutlineSceneLabel"]
    assert texts and "no pages yet" in texts[0] and "Lonely" in texts[0]



def test_outline_empty_state_a_offers_create_act():
    db = Database()
    v = _outline(db, _gn(db))
    msgs = [w.text() for w in v._host.findChildren(QLabel)]
    assert "Create an Act to begin your Graphic Novel." in msgs
    btn = v._host.findChild(QPushButton, "gnOutlineDetailAddAct")
    assert btn is not None and btn.text() == "+ Act"



def test_outline_add_act_button_creates_act_one():
    db = Database()
    pid = _gn(db)
    v = _outline(db, pid)
    v._host.findChild(QPushButton, "gnOutlineDetailAddAct").click()
    assert ss.list_acts(db, pid) == ["Act 1"]
    acts = [c for c in v._cards if c.gn_data.get("kind") == "act"]
    assert len(acts) == 1



def test_outline_toolbar_add_act_appends_act_two():
    db = Database()
    pid = _gn(db)
    _scene(db, pid, "A")
    v = _outline(db, pid)
    v._add_act()
    assert ss.list_acts(db, pid) == ["Act 1", "Act 2"]


def test_outline_add_page_on_empty_act_seeds_scene():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "Solo")
    v = _outline(db, pid)
    v._sel = {"kind": "act", "act": "Act 1"}
    v._add_page()                                   # acts own pages
    assert len(gnb.load_scene_script(db, sid).pages) == 1
    assert v._sel["kind"] == "scene_page" and v._sel["page_no"] == 1


def test_outline_add_page_selects_new_scene_page():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    _pages(db, sid, 1)
    v = _outline(db, pid)
    v._sel = {"kind": "scene", "act": "Act 1", "scene_id": sid}
    v._add_page()
    assert v._sel == {"kind": "scene_page", "act": "Act 1", "scene_id": sid,
                      "page": 1, "page_no": 2, "continued": True}


def test_outline_shared_page_card_lists_contributing_scenes():
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    v = _outline(db, pid)
    page2 = next(c for c in v._cards
                 if c.gn_data["kind"] == "act_page"
                 and c.gn_data["page_no"] == 2)
    labels = [w.text() for w in page2.findChildren(QLabel)
              if w.objectName() == "gnOutlineSceneLabel"]
    assert len(labels) == 2                       # both scenes on the card



def test_outline_start_page_controls_pin_and_release():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    b = _scene(db, pid, "B")
    _pages(db, a, 2)
    _pages(db, b, 1)
    v = _outline(db, pid)

    def b_controls():
        group = next(c for c in v._cards
                     if c.gn_data.get("kind") == "scene_page"
                     and c.gn_data.get("scene_id") == b)
        return (group.findChild(QSpinBox, "gnOutlineStartPage"),
                group.findChild(QCheckBox, "gnOutlineStartAuto"))

    spin, auto = b_controls()
    assert spin.value() == 3 and auto.isChecked()   # auto-chained today
    assert spin.isEnabled() is False                # spin follows the chain
    spin.setValue(2)
    auto.setChecked(False)                          # pin it
    assert db.get_scene_by_id(b).gn_page_start == 2
    _act, pb = gns.find_placement(db, pid, b)
    assert pb.start_page == 2 and pb.explicit
    spin, auto = b_controls()                       # rebuilt after refresh
    assert not auto.isChecked()
    auto.setChecked(True)                           # release back to auto
    assert db.get_scene_by_id(b).gn_page_start is None



def test_outline_panel_deep_link_uses_scene_local_page():
    db = Database()
    pid, _a, b = _shared_page_project(db)
    hits = []
    v = _outline(db, pid, on_open_panel=lambda s, p, c: hits.append((s, p, c)))
    card = next(c for c in v._cards
                if c.gn_data.get("kind") == "panel"
                and c.gn_data.get("scene_id") == b
                and c.gn_data.get("page_no") == 2)
    v._activate(card.gn_data)
    assert hits == [(b, 0, 0)]                      # local page idx, not 2



def test_outline_scene_page_double_click_opens_manuscript():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    _pages(db, sid, 1)
    opened = []
    v = _outline(db, pid, on_open_manuscript=opened.append)
    card = next(c for c in v._cards if c.gn_data.get("kind") == "scene_page")
    v._activate(card.gn_data)
    assert opened == [sid]



def test_outline_selection_never_mutates_shared_page():
    db = Database()
    pid, a, b = _shared_page_project(db)
    before = (db.get_scene_by_id(a).content, db.get_scene_by_id(b).content,
              db.get_scene_by_id(b).gn_page_start)
    v = _outline(db, pid)
    for card in v._cards:
        v._select(card.gn_data)
    assert (db.get_scene_by_id(a).content, db.get_scene_by_id(b).content,
            db.get_scene_by_id(b).gn_page_start) == before



def test_outline_delete_scene_page_removes_only_that_local_page(monkeypatch):
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: True)
    db = Database()
    pid, a, _b = _shared_page_project(db)
    v = _outline(db, pid)
    v._sel = {"kind": "scene_page", "act": "Act 1", "scene_id": a,
              "page": 1, "page_no": 2, "continued": True}
    v._delete_selected()
    assert len(gnb.load_scene_script(db, a).pages) == 1


def test_outline_move_panel_capability_with_act_wide_numbers():
    from PySide6.QtWidgets import QToolButton
    db = Database()
    pid, _a, b = _shared_page_project(db)        # B pinned: local pages → 2,3
    v = _outline(db, pid)
    card = next(c for c in v._cards
                if c.gn_data.get("kind") == "panel"
                and c.gn_data.get("scene_id") == b)
    assert card.findChild(QToolButton, "gnOutlinePanelMove") is not None
    # The move itself preserves the body (act-wide labels come from the
    # placement when the menu is built).
    gno.set_panel_field(db, b, 0, 0, "visual_description", "KEEP")
    v._assign_panel_to_page(b, 0, 0, 1)
    body = gnb.load_scene_script(db, b)
    assert len(body.pages[0].panels) == 0
    assert body.pages[1].panels[-1].visual_description == "KEEP"


# ==========================================================================
# 3. Manuscript — derives from the Outline structure
# ==========================================================================


def test_manuscript_page_headers_use_act_wide_numbers():
    db = Database()
    pid, _a, b = _shared_page_project(db)
    m = _manuscript(db, pid)
    heads = [w.text() for w in m._host.findChildren(QLabel)
             if w.objectName() == "gnPageHeader"]
    assert heads == ["PAGE 1", "PAGE 2", "PAGE 2", "PAGE 3"]   # A:1-2, B:2-3



def test_manuscript_context_shows_act_and_page_range_no_chapter():
    db = Database()
    pid, _a, b = _shared_page_project(db)
    m = _manuscript(db, pid)
    acts = [w.text() for w in m._host.findChildren(QLabel)
            if w.objectName() == "gnActHeader"]
    assert acts == ["ACT 1"]
    chips = [w.text() for w in m._host.findChildren(QLabel)
             if w.objectName() == "gnScenePagesChip"]
    assert "Pages 2–3" in chips                    # B's act-wide range
    assert not any("Chapter" in w.text()
                   for w in m._host.findChildren(QLabel))



def test_manuscript_document_has_no_dropdown_or_chapter():
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    m = _manuscript(db, pid)
    assert not hasattr(m, "_scene_combo")          # full document, no combo
    assert not any("Chapter" in w.text() for w in m.findChildren(QLabel))



def test_manuscript_renumbers_when_other_scene_grows():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    b = _scene(db, pid, "B")
    _pages(db, a, 1)
    _pages(db, b, 1)
    m = _manuscript(db, pid)
    heads = [w.text() for w in m._host.findChildren(QLabel)
             if w.objectName() == "gnPageHeader"]
    assert heads == ["PAGE 1", "PAGE 2"]
    gno.add_page(db, a)                            # A grows → B shifts
    m.refresh()
    heads = [w.text() for w in m._host.findChildren(QLabel)
             if w.objectName() == "gnPageHeader"]
    assert heads == ["PAGE 1", "PAGE 2", "PAGE 3"]



def test_manuscript_panel_blocks_grouped_by_page_for_spanning_scene():
    db = Database()
    pid, _a, b = _shared_page_project(db)
    m = _manuscript(db, pid)
    # Scene B's panels grouped under its (act-wide) pages in the document.
    assert ("panel", b, 0, 0) in m._field_editors
    assert ("panel", b, 1, 0) in m._field_editors



def test_manuscript_panel_selection_keeps_local_coordinates():
    db = Database()
    pid, _a, b = _shared_page_project(db)
    m = _manuscript(db, pid)
    m.select_scene(b)
    m.select_panel(1, 0)                           # local page idx
    assert m.current_panel_ref() == (b, 1, 0)      # voice/commit unchanged


def test_manuscript_empty_state_then_act_then_page_ladder():
    db = Database()
    pid = _gn(db)
    m = _manuscript(db, pid)
    msgs = [w.text() for w in m._host.findChildren(QLabel)
            if w.objectName() == "gnScriptEmpty"]
    assert msgs == ["Create an Act to begin your Graphic Novel."]   # state A
    m._host.findChild(QPushButton, "gnScriptCreateAct").click()
    assert ss.list_acts(db, pid) == ["Act 1"]
    assert m._host.findChild(QPushButton, "gnDetailAddPage") is not None  # B


# ==========================================================================
# 4. Outline ⇄ Manuscript mirroring (one body, one coordinate system)
# ==========================================================================


def test_pinning_in_outline_renumbers_manuscript():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    b = _scene(db, pid, "B")
    _pages(db, a, 2)
    _pages(db, b, 1)
    m = _manuscript(db, pid)
    gns.set_scene_start_page(db, b, 2)             # the Outline's control
    m.refresh()
    heads = [w.text() for w in m._host.findChildren(QLabel)
             if w.objectName() == "gnPageHeader"]
    assert heads == ["PAGE 1", "PAGE 2", "PAGE 2"]  # B shares A's Page 2



def test_outline_add_page_appears_in_manuscript_numbering():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _outline(db, pid)
    v._sel = {"kind": "scene", "act": "Act 1", "scene_id": sid}
    v._add_page()
    m = _manuscript(db, pid)
    m.select_scene(sid)
    heads = [w.text() for w in m._host.findChildren(QLabel)
             if w.objectName() == "gnPageHeader"]
    assert heads == ["PAGE 1"]


def test_manuscript_add_page_appears_as_new_act_page_in_outline():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    _pages(db, sid, 1)
    m = _manuscript(db, pid)
    m.select_scene(sid)
    m._add_page()
    v = _outline(db, pid)
    assert any(c.gn_data.get("kind") == "act_page"
               and c.gn_data.get("page_no") == 2 for c in v._cards)


def test_panel_field_edit_mirrors_into_outline_snippet():
    db = Database()
    pid, _a, b = _shared_page_project(db)
    gno.set_panel_field(db, b, 1, 0, "visual_description", "MIRRORED")
    v = _outline(db, pid)
    card = next(c for c in v._cards
                if c.gn_data.get("kind") == "panel"
                and any("MIRRORED" in w.text()
                        for w in c.findChildren(QLabel)))
    assert card.gn_data["page_no"] == 3            # B local 2 → act Page 3


# ==========================================================================
# 5. Export — Act → Page → Scene → Panel with assignments
# ==========================================================================


def test_export_page_first_with_assignments_and_continued():
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    gno.set_panel_field(db, _a, 1, 0, "dialogue", "A2_LINE")
    gno.set_panel_field(db, _b, 0, 0, "dialogue", "B1_LINE")
    md = gns.export_structure_markdown(db, pid)
    assert "## Act 1" in md
    assert md.index("### Page 1") < md.index("### Page 2") < md.index(
        "### Page 3")
    assert "**Scene: A — continued**" in md        # spanning marker
    assert "(Scene: A → Page 2)" in md             # explicit assignments
    assert "(Scene: B → Page 2)" in md
    a2 = md.index("A2_LINE")
    b1 = md.index("B1_LINE")
    assert a2 < b1                                 # shared page, story order


def test_export_panel_text_appears_exactly_once():
    db = Database()
    pid, a, _b = _shared_page_project(db)
    gno.set_panel_field(db, a, 0, 0, "dialogue", "ONLY_ONCE_LINE")
    md = gns.export_structure_markdown(db, pid)
    assert md.count("ONLY_ONCE_LINE") == 1


def test_export_hides_chapter_and_lists_empty_scenes():
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    _scene(db, pid, "Empty")
    _pages(db, a, 1)
    md = gns.export_structure_markdown(db, pid)
    assert "Chapter" not in md
    assert "_Scenes without pages:_" in md and "- Empty" in md


def test_export_no_image_data_or_secrets():
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    settings = db.get_project_settings(pid) or {}
    settings["api_key"] = "sk-SECRET"
    db.save_project_settings(pid, settings)
    md = gns.export_structure_markdown(db, pid)
    low = md.lower()
    for banned in ("comfyui", "image prompt", "lora", "img2img", "txt2img"):
        assert banned not in low
    assert "sk-SECRET" not in md and "SECRET" not in md


def test_legacy_export_name_delegates_to_canonical():
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    assert gno.export_outline_markdown(db, pid) == \
        gns.export_structure_markdown(db, pid)


# ==========================================================================
# 6. Compatibility, isolation and regression
# ==========================================================================


def test_legacy_null_offsets_reproduce_sequential_layout():
    # A pre-refactor project (all gn_page_start NULL) reads exactly as the
    # old sequential chain — non-destructive adapter, no data rewrite.
    db = Database()
    pid = _gn(db)
    a = _scene(db, pid, "A")
    b = _scene(db, pid, "B")
    _pages(db, a, 2)
    _pages(db, b, 2)
    bodies = (db.get_scene_by_id(a).content, db.get_scene_by_id(b).content)
    view = gns.act_view(db, pid)
    (_act, pages, placements) = view[0]
    assert [no for no, _s in pages] == [1, 2, 3, 4]
    assert [p.start_page for p in placements] == [1, 3]
    # Bodies untouched (still scene-local PAGE 1..n script).
    assert (db.get_scene_by_id(a).content,
            db.get_scene_by_id(b).content) == bodies
    assert "PAGE 1" in bodies[1]                   # scene-local storage


def test_orphan_scenes_group_under_unassigned_without_crash():
    db = Database()
    pid = _gn(db)
    sid = db.create_scene(pid, title="Orphan").id  # no act label at all
    gno.add_page(db, sid)
    view = dict((act, pages) for act, pages, _pl in gns.act_view(db, pid))
    assert ss.UNASSIGNED_ACT in view
    assert [no for no, _s in view[ss.UNASSIGNED_ACT]] == [1]
    v = _outline(db, pid)                          # renders without error
    assert any("Orphan" in w.text() for w in v.findChildren(QLabel)
               if w.objectName() == "gnOutlineSceneLabel")


def test_other_modes_ignore_gn_page_start():
    db = Database()
    for engine in ("novel", "screenplay", "stage_script", "series"):
        pid = db.create_project(engine, narrative_engine=engine,
                                default_writing_format=engine).id
        sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                              title="S").id
        assert db.get_scene_by_id(sid).gn_page_start is None


def test_non_gn_outline_still_plan_view():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.plan_view import PlanView
    db = Database()
    pid = db.create_project("novel", narrative_engine="novel",
                            default_writing_format="novel").id
    win = MainWindow(db, pid)
    win._show_plan()
    assert isinstance(win.content_area, PlanView)


def test_standalone_pages_still_hidden_and_inert():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_scene_pages_view import (
        GraphicNovelScenePagesView)
    db = Database()
    win = MainWindow(db, _gn(db))
    assert "Pages" not in win._nav_labels and "Pages" not in win.sidebar_buttons
    win._show_gn_pages()
    assert not isinstance(win.content_area, GraphicNovelScenePagesView)


def test_outline_mount_fullscreen_safe():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    win = MainWindow(db, _gn(db))
    before = set(QApplication.topLevelWidgets())
    win._show_plan()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible == [] and win.content_area.window() is win


def test_project_isolation_of_placements(tmp_path):
    db = Database(str(tmp_path / "iso.db"))
    p1 = _gn(db, "One")
    a = _scene(db, p1, "A")
    _pages(db, a, 3)
    p2 = _gn(db, "Two")
    c = _scene(db, p2, "C")
    _pages(db, c, 1)
    _act, pc = gns.find_placement(db, p2, c)
    assert pc.start_page == 1                      # other project invisible
    assert gns.find_placement(db, p2, a) == (None, None)


def test_body_grammar_and_renumber_untouched():
    # The storage format stays the scene-local script; _renumber still
    # numbers pages 1..n per scene regardless of act-wide coordinates.
    db = Database()
    pid, _a, b = _shared_page_project(db)
    script = gnb.load_scene_script(db, b)
    assert [p.number for p in script.pages] == [1, 2]
    gnb._renumber(script)
    assert [p.number for p in script.pages] == [1, 2]
    _ = pid


# ==========================================================================
# Post-refactor RE-certification pins (2026-06-11): Unicode matrix,
# project-language coordination, Dexter routing — after the scope cleanup.
# ==========================================================================

_GATE_STRINGS = {
    "zh": "这是一个测试场景。角色走进房间。",
    "ja": "これはテストシーンです。登場人物が部屋に入る。",
    "ko": "이것은 테스트 장면입니다. 인물이 방에 들어간다.",
    "ar": "هذا مشهد اختبار. تدخل الشخصية إلى الغرفة.",
    "he": "זו סצנת בדיקה. הדמות נכנסת לחדר.",
    "hi": "यह एक परीक्षण दृश्य है। पात्र कमरे में प्रवेश करता है।",
    "bn": "এটি একটি পরীক্ষামূলক দৃশ্য। চরিত্রটি ঘরে প্রবেশ করে।",
    "th": "นี่คือฉากทดสอบ ตัวละครเดินเข้าไปในห้อง",
    "mixed": "“Curly quotes”, em dash — ellipsis … emoji 🐕, accented: "
             "Zampanò, città, perché.",
}
_PANEL_FIELDS = ("visual_description", "caption", "dialogue", "sfx", "notes")


@pytest.mark.parametrize("key", sorted(_GATE_STRINGS))
def test_recert_unicode_in_every_panel_field(key, tmp_path):
    """Every gate script (CJK/RTL/Indic/Thai/mixed) survives every Panel
    field through save, full reload and the canonical Act → Page → Scene →
    Panel export."""
    text = _GATE_STRINGS[key]
    path = str(tmp_path / f"gn-{key}.db")
    db = Database(path)
    pid = _gn(db)
    sid = _scene(db, pid, f"Scene {key}")
    _pages(db, sid, 1, panels_per_page=0)
    gno.add_panel(db, sid, 0)
    for field in _PANEL_FIELDS:
        gno.set_panel_field(db, sid, 0, 0, field, text)
    db2 = Database(path)                               # reload from disk
    panel = gnb.load_scene_script(db2, sid).pages[0].panels[0]
    for field in _PANEL_FIELDS:
        assert getattr(panel, field) == text, field
    md = gns.export_structure_markdown(db2, pid)
    assert text in md                                  # UTF-8 export intact
    # Outline snippets never crash on the script (labels only truncate).
    assert gno.panel_snippet(panel)


def test_recert_project_language_coordinates_gn_without_mutation():
    from logosforge import languages as L
    from logosforge import i18n
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "一")
    _pages(db, sid, 1)
    gno.set_panel_field(db, sid, 0, 0, "dialogue", _GATE_STRINGS["ja"])
    before = db.get_scene_by_id(sid).content
    L.set_project_writing_language(db, pid, "ja")
    # AI context: project language + no Latin-word-spacing assumption.
    assert L.language_context_line(db, pid).startswith(
        "[Writing Language] Japanese (ja)")
    assert "does not separate words" in L.ai_language_instruction("ja")
    assert "right-to-left" in L.ai_language_instruction("ar")
    # Dexter "Use project language" resolves to the GN project's language.
    assert L.dexter_language_for_project(db, pid) == "ja"
    # Language changes never rewrite Panel text; the UI stays English.
    L.set_project_writing_language(db, pid, "ar")
    L.set_project_writing_language(db, pid, "ja")
    assert db.get_scene_by_id(sid).content == before
    assert i18n.ui_language() == "en"


def test_recert_voice_commit_routes_unicode_into_panel_field():
    """Dexter's writing-room routing: a CJK transcript commits into the
    selected Panel's Dialogue field (explicit target, append-preserving,
    undoable) — no grammar pass anywhere in the path."""
    from logosforge.voice.commit_router import (
        T_GN_DIALOGUE, VoiceCommitContext, commit_transcript)
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "ja")
    _pages(db, sid, 1)
    gno.set_panel_field(db, sid, 0, 0, "dialogue", _GATE_STRINGS["ja"])
    ctx = VoiceCommitContext(db=db, project_id=pid,
                             writing_mode="graphic_novel",
                             gn_panel_ref=(sid, 0, 0))
    spoken = "「ザンパノ」と彼は言った。🐕"
    ok, msg = commit_transcript(spoken, T_GN_DIALOGUE, ctx)
    assert ok, msg
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert spoken in panel.dialogue
    assert _GATE_STRINGS["ja"] in panel.dialogue       # appended, not replaced


# ==========================================================================
# Block-UX post-fix gate pins (2026-06-11): old UI gone, shared paradigm in.
# ==========================================================================


def test_gate_old_gn_ui_markers_are_gone():
    """The old 'Comics Script' single-scene renderer and the tree-only
    Outline are unreachable: their markers no longer exist in the GN view
    sources (no user-facing 'Comics Script', no scene dropdown, no tree)."""
    for path in ("logosforge/ui/graphic_novel_manuscript_view.py",
                 "logosforge/ui/graphic_novel_outline_view.py"):
        src = open(path, encoding="utf-8").read()
        assert "Comics Script" not in src, path
        assert "QTreeWidget" not in src, path
    ms = open("logosforge/ui/graphic_novel_manuscript_view.py", encoding="utf-8").read()
    assert "QComboBox" not in ms                   # no scene dropdown
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    m = _manuscript(db, pid)
    assert not any("Comics Script" in w.text()
                   for w in m.findChildren(QLabel))
    assert m.findChild(QLabel, "gnModeLabel").text() == "Graphic Novel"
    assert "words" in m._word_count_label.text()   # shared toolbar vocabulary


def test_gate_unicode_entered_in_block_reaches_outline_snippet():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "一")
    _pages(db, sid, 1)
    m = _manuscript(db, pid)
    text = "Visual:\nこれはテストシーンです。🐕 Zampanò, città"
    ed = m._field_editors[("panel", sid, 0, 0)]
    ed.setPlainText(text)
    m._commit_panel_script(sid, 0, 0, text)
    assert "これはテストシーンです。🐕" in db.get_scene_by_id(sid).content
    v = _outline(db, pid)
    snippets = [w.text() for w in v.findChildren(QLabel)
                if w.objectName() == "gnOutlinePanelSnippet"]
    assert any("これはテストシーン" in t for t in snippets)


def test_gate_screenplay_outline_and_manuscript_untouched():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.plan_view import PlanView
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    pid = db.create_project("sp", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    win = MainWindow(db, pid)
    win._show_plan()
    assert isinstance(win.content_area, PlanView)
    assert win.content_area.objectName() == \
        "outline_target_block_card_planner_view"
    win._show_manuscript()
    assert isinstance(win.content_area, WritingCoreView)


def test_phase2_shared_editor_routing_and_clean_chrome():
    """Phase 2: GN mounts the SHARED editor family — WritingCoreView for
    Manuscript (no page-manager chrome, chapters hidden) and PlanView for
    Outline (GN schema cards); legacy GN views are not routed."""
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    from logosforge.ui.plan_view import PlanView
    from PySide6.QtWidgets import QFrame
    db = Database()
    pid, _a, b = _shared_page_project(db)
    win = MainWindow(db, pid)
    win._show_manuscript()
    assert isinstance(win.content_area, WritingCoreView)
    texts = [w.text() for w in win.content_area.findChildren(QLabel)]
    assert not any(t in ("Delete Page", "+ Panel", "Comics Script")
                   for t in texts)
    assert not any("Chapter" in t for t in texts)
    win._show_plan()
    pv = win.content_area
    assert isinstance(pv, PlanView)
    pages = [w.text() for w in pv.findChildren(QLabel)
             if w.objectName() == "planGnPageLabel"]
    assert pages == ["Page 1", "Page 2", "Page 3"]
    scenes = [w.text() for w in pv.findChildren(QLabel)
              if w.objectName() == "planGnSceneLabel"]
    assert any("(continued)" in t for t in scenes)
    assert len([w for w in pv.findChildren(QFrame)
                if w.objectName() == "planGnPanel"]) == 4
    # Deep-link: cursor lands in the Panel inside the shared editor.
    win._open_gn_panel_in_manuscript(b, 1, 0)
    ed = win.content_area._editors[b]
    assert gnb.panel_at_offset(ed.toPlainText(),
                               ed.textCursor().position()) == (1, 0)


# ==========================================================================
# Phase 2 routing pins (2026-06-11): GN mounts the SHARED editor family.
# ==========================================================================


def test_p2_manuscript_route_mounts_shared_editor_not_legacy():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    win = MainWindow(db, pid)
    win._show_manuscript()
    view = win.content_area
    assert isinstance(view, WritingCoreView)             # shared family
    assert not isinstance(view, GraphicNovelManuscriptView)
    texts = [w.text() for w in view.findChildren(QLabel)]
    # No page-manager chrome, no legacy markers, no chapters.
    for banned in ("Comics Script", "Delete Page", "+ Panel", "+ Add Page"):
        assert banned not in texts, banned
    assert not any("Chapter" in t for t in texts)


def test_p2_outline_route_mounts_shared_planner_with_gn_schema():
    from PySide6.QtWidgets import QFrame
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.plan_view import PlanView
    from logosforge.ui.graphic_novel_outline_view import (
        GraphicNovelOutlineView)
    db = Database()
    pid, _a, _b = _shared_page_project(db)
    win = MainWindow(db, pid)
    win._show_plan()
    pv = win.content_area
    assert isinstance(pv, PlanView)                      # shared family
    assert not isinstance(pv, GraphicNovelOutlineView)
    assert pv.objectName() == "outline_target_block_card_planner_view"
    pages = [w.text() for w in pv.findChildren(QLabel)
             if w.objectName() == "planGnPageLabel"]
    assert pages == ["Page 1", "Page 2", "Page 3"]       # GN schema
    scenes = [w.text() for w in pv.findChildren(QLabel)
              if w.objectName() == "planGnSceneLabel"]
    assert any("(continued)" in t for t in scenes)       # span rendering
    panels = [w for w in pv.findChildren(QFrame)
              if w.objectName() == "planGnPanel"]
    assert len(panels) == 4
    assert not any("Chapter" in w.text() for w in pv.findChildren(QLabel))
    # No page-form-manager as primary UX: no per-page title/notes inputs,
    # no starts-on-page spinners in the shared planner.
    from PySide6.QtWidgets import QLineEdit, QSpinBox
    assert pv.findChildren(QSpinBox) == []
    assert not [e for e in pv.findChildren(QLineEdit)
                if e.objectName().startswith("gnOutline")]


def test_p2_shared_planner_gn_add_actions_work():
    from logosforge.ui.plan_view import PlanView
    db = Database()
    pid = _gn(db)
    pv = PlanView(db, pid, on_data_changed=lambda: None)
    assert pv.findChild(QPushButton, "planGnAddAct") is not None  # state A
    pv._gn_add_act()
    assert ss.list_acts(db, pid) == ["Act 1"]
    pv._gn_add_page()
    sid = ss.list_scenes(db, pid)[0].id
    assert len(gnb.load_scene_script(db, sid).pages) == 1
    pv._gn_add_panel()
    assert gnb.load_scene_script(db, sid).panel_count() == 1
    pv._gn_add_scene()
    assert len(ss.list_scenes(db, pid)) == 2
    bar = [pv.findChild(QPushButton, n) for n in
           ("planGnAddAct", "planGnAddPage", "planGnAddScene",
            "planGnAddPanel")]
    assert all(b is not None for b in bar)               # action bar


def test_p2_outline_panel_double_click_places_manuscript_cursor():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    pid, _a, b = _shared_page_project(db)
    win = MainWindow(db, pid)
    win._open_gn_panel_in_manuscript(b, 1, 0)            # PlanView deep-link
    view = win.content_area
    assert isinstance(view, WritingCoreView)
    editor = view._editors[b]
    assert gnb.panel_at_offset(editor.toPlainText(),
                               editor.textCursor().position()) == (1, 0)


def test_p2_voice_panel_ref_resolves_from_shared_editor_cursor(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid, _a, b = _shared_page_project(db)
    win = MainWindow(db, pid)
    win._open_gn_panel_in_manuscript(b, 1, 0)    # opens + positions cursor
    editor = win.content_area._editors[b]
    monkeypatch.setattr(QApplication, "focusWidget",
                        staticmethod(lambda: editor))
    assert win._gn_panel_ref_at_cursor() == (b, 1, 0)
    # Outside GN mode the resolver stays silent.
    np = db.create_project("n", narrative_engine="novel").id
    win2 = MainWindow(db, np)
    assert win2._gn_panel_ref_at_cursor() is None


def test_p2_cursor_panel_mapping_round_trips():
    text = ("PAGE 1\n\nPANEL 1\nVisual: a\n\nPANEL 2\nVisual: b\n\n"
            "PAGE 2\n\nPANEL 1\nVisual: c\n")
    for (pi, ci) in ((0, 0), (0, 1), (1, 0)):
        off = gnb.panel_offset(text, pi, ci)
        assert off is not None
        assert gnb.panel_at_offset(text, off) == (pi, ci)
    assert gnb.panel_at_offset(text, 0) is None          # before first panel
    assert gnb.panel_offset(text, 5, 0) is None          # missing → None


def test_p2gate_legacy_renderers_not_constructed_in_production():
    """Verification-gate pin: no production module instantiates the LEGACY
    GraphicNovel*View renderers (their modules carry the LEGACY — NOT
    ROUTED label); 'Comics Script' exists nowhere in production code."""
    import pathlib
    legacy_defs = {"logosforge/ui/graphic_novel_manuscript_view.py",
                   "logosforge/ui/graphic_novel_outline_view.py"}
    for path in pathlib.Path("logosforge").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "Comics Script" not in src, path
        if str(path) in legacy_defs:
            assert src.startswith('"""LEGACY — NOT ROUTED')
            continue
        assert "GraphicNovelManuscriptView(" not in src, path
        assert "GraphicNovelOutlineView(" not in src, path
