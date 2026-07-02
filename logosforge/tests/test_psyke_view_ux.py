"""PSYKE console UX guards + context fallback cap.

Covers the polish fixes: blank-name save warns (and doesn't save), duplicate
name asks for confirmation, delete asks for confirmation, the relation editor
stores typed relations, and the unfiltered Assistant fallback caps entries.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from logosforge.context_builder import PSYKE_MAX_RELEVANT, _gather_psyke_all
from logosforge.db import Database
from logosforge.ui.psyke_view import PsykeView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _mk(db, pid, name, etype="character", is_global=False):
    return db.create_psyke_entry(pid, name, etype, "", f"note {name}", is_global)


# -- Console guards ----------------------------------------------------------

def test_blank_name_save_warns_and_skips(qapp, monkeypatch):
    db = Database()
    pid = db.create_project("P").id
    view = PsykeView(db, pid)
    warned = {"n": 0}
    monkeypatch.setattr(
        "logosforge.ui.psyke_view.QMessageBox.warning",
        lambda *a, **k: warned.__setitem__("n", warned["n"] + 1),
    )
    view._name_input.setText("   ")            # blank after strip
    view._on_save()
    assert warned["n"] == 1                    # user told why nothing happened
    assert db.get_all_psyke_entries(pid) == []  # and nothing was saved


def test_duplicate_name_declined_is_not_saved(qapp, monkeypatch):
    db = Database()
    pid = db.create_project("P").id
    _mk(db, pid, "Ada")
    view = PsykeView(db, pid)                   # _all_entries now contains Ada
    monkeypatch.setattr(
        "logosforge.ui.psyke_view.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    view._name_input.setText("Ada")            # duplicate, new entry
    view._on_save()
    assert len(db.get_all_psyke_entries(pid)) == 1   # declined → not created


def test_delete_cancelled_keeps_entry(qapp, monkeypatch):
    db = Database()
    pid = db.create_project("P").id
    a = _mk(db, pid, "Ada")
    view = PsykeView(db, pid)
    view.select_entry(a.id)
    assert view._selected_id == a.id
    monkeypatch.setattr(
        "logosforge.ui.psyke_view.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    view._on_delete()
    assert len(db.get_all_psyke_entries(pid)) == 1   # cancel → still there


# -- Typed relations ---------------------------------------------------------

def test_relation_editor_stores_typed_relation(qapp):
    db = Database()
    pid = db.create_project("P").id
    a = _mk(db, pid, "Ada")
    b = _mk(db, pid, "Manor", "place")
    view = PsykeView(db, pid)
    view.select_entry(a.id)
    rel_i = next(i for i in range(view._related_combo.count())
                 if view._related_combo.itemData(i) == b.id)
    view._related_combo.setCurrentIndex(rel_i)
    type_i = next(i for i in range(view._relation_type_combo.count())
                  if view._relation_type_combo.itemData(i) == "supports_setup")
    view._relation_type_combo.setCurrentIndex(type_i)
    view._on_add_relation()
    typed = {e.id: t for e, t in db.get_typed_related_psyke_entries(a.id)}
    assert typed.get(b.id) == "supports_setup"
    # Inverse edge keeps semantic direction (payoff on the reverse).
    inv = {e.id: t for e, t in db.get_typed_related_psyke_entries(b.id)}
    assert inv.get(a.id) == "payoff"


# -- Unfiltered fallback cap -------------------------------------------------

class _Entry:
    def __init__(self, i, name, is_global=False):
        self.id = i
        self.name = name
        self.entry_type = "character"
        self.notes = f"note {name}"
        self.aliases = ""
        self.is_global = is_global
        self.details_json = ""


def test_gather_psyke_all_caps_non_globals():
    entries = [_Entry(i, f"C{i}") for i in range(PSYKE_MAX_RELEVANT + 5)]
    entries.append(_Entry(999, "GlobalOne", is_global=True))
    out = _gather_psyke_all(entries)
    # Globals always present; non-globals capped; remainder noted, not dumped.
    assert "Global:" in out
    assert out.count("(character)") <= PSYKE_MAX_RELEVANT + 1   # +1 global
    assert "5 more entries omitted" in out


# -- Hover-card ellipsis -----------------------------------------------------

def test_hover_ellipsize():
    from logosforge.ui.entity_hover import _ellipsize
    assert _ellipsize("short", 150) == "short"
    out = _ellipsize("x" * 200, 150)
    assert len(out) == 150 and out.endswith("…")
    assert _ellipsize("", 10) == ""
