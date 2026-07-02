"""Tests for mode-aware timeline display — Classical vs Lambda visualization."""

import pytest

from PySide6.QtWidgets import QFrame, QLabel

from logosforge.db import Database
from logosforge.quantum_outliner.state import (
    Branch,
    NarrativeState,
    OutlineMode,
    Wavefunction,
    _STATES,
    get_state,
)
from logosforge.ui.quantum_timeline import QuantumTimelineWidget


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Timeline Mode Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


def _make_branch(title="Branch A", **kw):
    return Branch.new(title=title, description=f"Desc for {title}", **kw)


def _make_wf(anchor="Test", branches=None, source_scene_id=None, **kw):
    wf = Wavefunction.new(
        anchor=anchor,
        branches=branches or [_make_branch()],
        source_scene_id=source_scene_id,
    )
    for k, v in kw.items():
        setattr(wf, k, v)
    return wf


class TestModeStripText:
    def test_lambda_mode_strip(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        wf = _make_wf()
        state.add(wf)

        widget = QuantumTimelineWidget(db, project.id)
        widget._update_mode_strip(state)

        assert "Lambda" in widget._mode_strip.text()
        assert "branching" in widget._mode_strip.text()

    def test_classical_mode_strip(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        wf = _make_wf()
        state.add(wf)

        widget = QuantumTimelineWidget(db, project.id)
        widget._update_mode_strip(state)

        assert "Classical" in widget._mode_strip.text()
        assert "linear" in widget._mode_strip.text()

    def test_mode_strip_hidden_when_empty(self, db, project):
        state = get_state(project.id)
        widget = QuantumTimelineWidget(db, project.id)
        widget._update_mode_strip(state)

        assert not widget._mode_strip.isVisible()

    def test_mode_strip_visible_with_wavefunctions(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.add(_make_wf())

        widget = QuantumTimelineWidget(db, project.id)
        widget._update_mode_strip(state)

        assert not widget._mode_strip.isHidden()


class TestClassicalColumn:
    def test_classical_column_has_title(self, db, project):
        scene = db.create_scene(project.id, title="Act 2 Opening")
        wf = _make_wf(source_scene_id=scene.id, structure_method="Save the Cat",
                       structure_beat="Midpoint")

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_classical_column(scene, [wf])

        labels = col.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert any("Act 2 Opening" in t for t in texts)

    def test_classical_column_has_beat_marker(self, db, project):
        scene = db.create_scene(project.id, title="Midpoint")
        wf = _make_wf(source_scene_id=scene.id, structure_method="Save the Cat",
                       structure_beat="Midpoint")

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_classical_column(scene, [wf])

        labels = col.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert any("Save the Cat" in t for t in texts)

    def test_classical_column_no_branch_nodes(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        branches = [_make_branch("A"), _make_branch("B"), _make_branch("C")]
        wf = _make_wf(branches=branches, source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_classical_column(scene, [wf])

        frames = col.findChildren(QFrame)
        branch_frames = [f for f in frames if f.objectName() == "qtlBranch"]
        assert len(branch_frames) == 0


class TestLambdaColumn:
    def test_lambda_column_has_branch_nodes(self, db, project):
        scene = db.create_scene(project.id, title="Crossroads")
        branches = [_make_branch("Path A"), _make_branch("Path B")]
        wf = _make_wf(branches=branches, source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_scene_column(scene, [wf])

        frames = col.findChildren(QFrame)
        branch_frames = [f for f in frames if f.objectName() == "qtlBranch"]
        assert len(branch_frames) == 2

    def test_lambda_column_with_structure_labels(self, db, project):
        scene = db.create_scene(project.id, title="Midpoint")
        b1 = _make_branch("False Victory", structure_beat="Midpoint",
                           branch_type="intensification")
        b2 = _make_branch("Betrayal", structure_beat="Midpoint",
                           branch_type="deviation")
        wf = _make_wf(branches=[b1, b2], source_scene_id=scene.id,
                       structure_method="Save the Cat", structure_beat="Midpoint")

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_scene_column(scene, [wf])

        labels = col.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert any("int" in t for t in texts)
        assert any("dev" in t for t in texts)


class TestUncertaintyZone:
    def test_uncertainty_shown_for_active_branches(self, db, project):
        scene = db.create_scene(project.id, title="Decision")
        branches = [_make_branch("A"), _make_branch("B"), _make_branch("C")]
        wf = _make_wf(branches=branches, source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_scene_column(scene, [wf])

        labels = col.findChildren(QLabel)
        uz_labels = [lbl for lbl in labels if lbl.objectName() == "qtlUncertainty"]
        assert len(uz_labels) == 1
        assert "3 paths" in uz_labels[0].text()

    def test_no_uncertainty_for_single_branch(self, db, project):
        scene = db.create_scene(project.id, title="Single")
        wf = _make_wf(branches=[_make_branch("Only")], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_scene_column(scene, [wf])

        labels = col.findChildren(QLabel)
        uz_labels = [lbl for lbl in labels if lbl.objectName() == "qtlUncertainty"]
        assert len(uz_labels) == 0

    def test_no_uncertainty_for_collapsed(self, db, project):
        scene = db.create_scene(project.id, title="Done")
        b1 = _make_branch("Winner")
        b2 = _make_branch("Loser")
        wf = _make_wf(branches=[b1, b2], source_scene_id=scene.id)
        wf.collapsed_branch_id = b1.id

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_scene_column(scene, [wf])

        labels = col.findChildren(QLabel)
        uz_labels = [lbl for lbl in labels if lbl.objectName() == "qtlUncertainty"]
        assert len(uz_labels) == 0

    def test_uncertainty_in_unlinked_column(self, db, project):
        branches = [_make_branch("X"), _make_branch("Y")]
        wf = _make_wf(branches=branches)

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_unlinked_column([wf])

        labels = col.findChildren(QLabel)
        uz_labels = [lbl for lbl in labels if lbl.objectName() == "qtlUncertainty"]
        assert len(uz_labels) == 1
        assert "2 paths" in uz_labels[0].text()


class TestClassicalVsLambdaHeight:
    def test_classical_shorter_than_lambda(self, db, project):
        state = get_state(project.id)
        scene = db.create_scene(project.id, title="Test")
        branches = [_make_branch("A"), _make_branch("B"), _make_branch("C")]
        wf = _make_wf(branches=branches, source_scene_id=scene.id)
        state.add(wf)

        state.outline_mode = OutlineMode.CLASSICAL
        widget_c = QuantumTimelineWidget(db, project.id)
        widget_c.refresh()
        height_c = widget_c._scroll.height()

        state.outline_mode = OutlineMode.LAMBDA
        widget_l = QuantumTimelineWidget(db, project.id)
        widget_l.refresh()
        height_l = widget_l._scroll.height()

        assert height_c < height_l


class TestWidgetInterface:
    def test_has_mode_strip(self):
        assert hasattr(QuantumTimelineWidget, "_update_mode_strip")

    def test_has_classical_column(self):
        assert hasattr(QuantumTimelineWidget, "_build_classical_column")

    def test_refresh_respects_mode(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        scene = db.create_scene(project.id, title="S1")
        wf = _make_wf(source_scene_id=scene.id)
        state.add(wf)

        widget = QuantumTimelineWidget(db, project.id)
        widget.refresh()

        assert not widget._mode_strip.isHidden()
        assert "Lambda" in widget._mode_strip.text()
