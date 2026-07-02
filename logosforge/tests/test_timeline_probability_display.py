"""Tests for probability display in Quantum Timeline UI.

Verifies that branch nodes show probability percentages and visual
weight bars, and that collapsed/archived/unscored branches hide them.
"""

import pytest

from PySide6.QtWidgets import QFrame, QLabel

from logosforge.db import Database
from logosforge.quantum_outliner.state import (
    Branch,
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
    return db.create_project("Prob Display Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


def _branch(title="Test", probability=0.0, score=0.0, **kw):
    return Branch.new(
        title=title, description=f"Desc for {title}",
        score=score, probability=probability, **kw,
    )


def _wf(branches, source_scene_id=None, **kw):
    wf = Wavefunction.new(
        anchor="Test",
        branches=branches,
        source_scene_id=source_scene_id,
    )
    for k, v in kw.items():
        setattr(wf, k, v)
    return wf


def _find_prob_labels(widget):
    return [lbl for lbl in widget.findChildren(QLabel)
            if lbl.objectName() == "qtlProbLabel"]


def _find_prob_bars(widget):
    return [f for f in widget.findChildren(QFrame)
            if f.objectName() == "qtlProbBar"]


class TestProbabilityLabelInNode:
    def test_scored_branch_shows_percentage(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        b = _branch("Conflict", probability=0.42, score=0.7)
        wf = _wf([b], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        node = widget._build_branch_node(wf, b)

        labels = _find_prob_labels(node)
        assert len(labels) == 1
        assert "42%" in labels[0].text()

    def test_unscored_branch_hides_percentage(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        b = _branch("Calm", probability=0.0, score=0.0)
        wf = _wf([b], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        node = widget._build_branch_node(wf, b)

        labels = _find_prob_labels(node)
        assert len(labels) == 0

    def test_collapsed_branch_hides_percentage(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        b = _branch("Winner", probability=0.6, score=0.8)
        wf = _wf([b], source_scene_id=scene.id)
        wf.collapsed_branch_id = b.id

        widget = QuantumTimelineWidget(db, project.id)
        node = widget._build_branch_node(wf, b)

        labels = _find_prob_labels(node)
        assert len(labels) == 0

    def test_archived_branch_hides_percentage(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        winner = _branch("Winner", probability=0.6, score=0.8)
        loser = _branch("Loser", probability=0.4, score=0.5)
        wf = _wf([winner, loser], source_scene_id=scene.id)
        wf.collapsed_branch_id = winner.id

        widget = QuantumTimelineWidget(db, project.id)
        node = widget._build_branch_node(wf, loser)

        labels = _find_prob_labels(node)
        assert len(labels) == 0

    def test_tooltip_shows_detail(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        b = _branch("Conflict", probability=0.42, score=0.7)
        wf = _wf([b], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        node = widget._build_branch_node(wf, b)

        labels = _find_prob_labels(node)
        tip = labels[0].toolTip()
        assert "42" in tip
        assert "0.70" in tip


class TestProbabilityBarInNode:
    def test_scored_branch_has_bar(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        b = _branch("Conflict", probability=0.5, score=0.7)
        wf = _wf([b], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        node = widget._build_branch_node(wf, b)

        bars = _find_prob_bars(node)
        assert len(bars) == 1

    def test_bar_width_proportional(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        b_high = _branch("High", probability=0.8, score=0.9)
        b_low = _branch("Low", probability=0.2, score=0.3)
        wf = _wf([b_high, b_low], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        node_high = widget._build_branch_node(wf, b_high)
        node_low = widget._build_branch_node(wf, b_low)

        bar_high = _find_prob_bars(node_high)[0]
        bar_low = _find_prob_bars(node_low)[0]
        assert bar_high.width() > bar_low.width()

    def test_bar_height_is_two(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        b = _branch("Test", probability=0.5, score=0.6)
        wf = _wf([b], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        node = widget._build_branch_node(wf, b)

        bars = _find_prob_bars(node)
        assert bars[0].height() == 2

    def test_unscored_branch_has_no_bar(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        b = _branch("Plain", probability=0.0)
        wf = _wf([b], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        node = widget._build_branch_node(wf, b)

        bars = _find_prob_bars(node)
        assert len(bars) == 0

    def test_collapsed_branch_has_no_bar(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        b = _branch("Done", probability=0.7, score=0.8)
        wf = _wf([b], source_scene_id=scene.id)
        wf.collapsed_branch_id = b.id

        widget = QuantumTimelineWidget(db, project.id)
        node = widget._build_branch_node(wf, b)

        bars = _find_prob_bars(node)
        assert len(bars) == 0


class TestVisualWeight:
    def test_high_prob_accent_bar(self, db, project):
        from logosforge.ui import theme
        scene = db.create_scene(project.id, title="Test")
        b = _branch("High", probability=0.5, score=0.8)
        wf = _wf([b], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        color = widget._prob_bar_color(b.probability)
        assert color == theme.ACCENT

    def test_mid_prob_dim_bar(self, db, project):
        from logosforge.ui import theme
        widget = QuantumTimelineWidget(db, project.id)
        color = widget._prob_bar_color(0.25)
        assert color == theme.ACCENT_DIM

    def test_low_prob_muted_bar(self, db, project):
        from logosforge.ui import theme
        widget = QuantumTimelineWidget(db, project.id)
        color = widget._prob_bar_color(0.1)
        assert color == theme.TEXT_MUTED

    def test_high_prob_border_accent(self, db, project):
        from logosforge.ui import theme
        widget = QuantumTimelineWidget(db, project.id)
        border = widget._prob_border_color(0.5)
        assert border == theme.ACCENT_DIM

    def test_low_prob_border_default(self, db, project):
        from logosforge.ui import theme
        widget = QuantumTimelineWidget(db, project.id)
        border = widget._prob_border_color(0.1)
        assert border == theme.BORDER


class TestMultipleBranchesInLane:
    def test_three_branches_all_show_probability(self, db, project):
        scene = db.create_scene(project.id, title="Decision")
        b1 = _branch("Fight", probability=0.45, score=0.7)
        b2 = _branch("Flee", probability=0.35, score=0.5)
        b3 = _branch("Talk", probability=0.20, score=0.3)
        wf = _wf([b1, b2, b3], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_scene_column(scene, [wf])

        prob_labels = _find_prob_labels(col)
        assert len(prob_labels) == 3

        texts = [lbl.text() for lbl in prob_labels]
        assert "45%" in texts
        assert "35%" in texts
        assert "20%" in texts

    def test_three_branches_all_have_bars(self, db, project):
        scene = db.create_scene(project.id, title="Decision")
        b1 = _branch("Fight", probability=0.45, score=0.7)
        b2 = _branch("Flee", probability=0.35, score=0.5)
        b3 = _branch("Talk", probability=0.20, score=0.3)
        wf = _wf([b1, b2, b3], source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_scene_column(scene, [wf])

        bars = _find_prob_bars(col)
        assert len(bars) == 3

        widths = sorted([bar.width() for bar in bars], reverse=True)
        assert widths[0] > widths[1] > widths[2]

    def test_unlinked_column_shows_probability(self, db, project):
        b1 = _branch("A", probability=0.6, score=0.8)
        b2 = _branch("B", probability=0.4, score=0.5)
        wf = _wf([b1, b2])

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_unlinked_column([wf])

        prob_labels = _find_prob_labels(col)
        assert len(prob_labels) == 2


class TestClassicalModeUnchanged:
    def test_classical_column_has_no_prob_labels(self, db, project):
        scene = db.create_scene(project.id, title="Test")
        wf = _wf([_branch("A", probability=0.5, score=0.7)],
                  source_scene_id=scene.id)

        widget = QuantumTimelineWidget(db, project.id)
        col = widget._build_classical_column(scene, [wf])

        assert len(_find_prob_labels(col)) == 0
        assert len(_find_prob_bars(col)) == 0
