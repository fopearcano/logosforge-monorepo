"""Tests for QuantumTimelineWidget — no Qt event loop required."""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.state import (
    Branch,
    NarrativeState,
    StateDelta,
    Wavefunction,
    _STATES,
    get_state,
)
from logosforge.quantum_outliner.persistence import save_state, load_state


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Timeline UI Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


def _make_branch(title="Branch A", stakes="", consequence=""):
    return Branch.new(
        title=title,
        description=f"Desc for {title}",
        stakes=stakes,
        consequence=consequence,
    )


def _make_wf(anchor="Test", branches=None, source_scene_id=None, collapsed_branch_id=None):
    wf = Wavefunction.new(
        anchor=anchor,
        branches=branches or [_make_branch()],
        source_scene_id=source_scene_id,
    )
    if collapsed_branch_id is not None:
        wf.collapsed_branch_id = collapsed_branch_id
    return wf


class TestQuantumTimelineData:
    """Test the data layer that the timeline widget reads."""

    def test_empty_state_no_wavefunctions(self, db, project):
        state = get_state(project.id)
        assert state.active() == []
        assert state.collapsed() == []
        assert len(state.wavefunctions) == 0

    def test_three_active_branches(self, db, project):
        state = get_state(project.id)
        branches = [
            _make_branch("Path A", stakes="High risk"),
            _make_branch("Path B", stakes="Low risk"),
            _make_branch("Path C", stakes="Medium risk"),
        ]
        wf = _make_wf(anchor="Crossroads", branches=branches)
        state.add(wf)

        assert len(state.active()) == 1
        assert len(state.active()[0].branches) == 3
        for b in state.active()[0].branches:
            assert b.title.startswith("Path ")

    def test_branch_selection_by_id(self, db, project):
        state = get_state(project.id)
        branches = [_make_branch("A"), _make_branch("B")]
        wf = _make_wf(branches=branches)
        state.add(wf)

        target = wf.get_branch(branches[1].id)
        assert target is not None
        assert target.title == "B"

    def test_collapsed_branch_status(self, db, project):
        state = get_state(project.id)
        branches = [_make_branch("Winner"), _make_branch("Loser")]
        wf = _make_wf(branches=branches, collapsed_branch_id=branches[0].id)
        state.add(wf)

        assert wf.is_collapsed()
        assert wf.collapsed_branch().title == "Winner"
        assert len(state.active()) == 0
        assert len(state.collapsed()) == 1

    def test_archive_removes_wavefunction(self, db, project):
        state = get_state(project.id)
        wf = _make_wf()
        state.add(wf)
        assert len(state.wavefunctions) == 1

        state.remove(wf.id)
        assert len(state.wavefunctions) == 0

    def test_wavefunction_grouped_by_source_scene(self, db, project):
        s1 = db.create_scene(project.id, title="Scene 1")
        s2 = db.create_scene(project.id, title="Scene 2")
        state = get_state(project.id)

        wf1 = _make_wf(anchor="From S1", source_scene_id=s1.id)
        wf2 = _make_wf(anchor="From S2", source_scene_id=s2.id)
        wf3 = _make_wf(anchor="Also S1", source_scene_id=s1.id)
        state.add(wf1)
        state.add(wf2)
        state.add(wf3)

        from collections import defaultdict
        by_scene = defaultdict(list)
        for wf in state.wavefunctions.values():
            by_scene[wf.source_scene_id].append(wf)

        assert len(by_scene[s1.id]) == 2
        assert len(by_scene[s2.id]) == 1

    def test_unlinked_wavefunctions(self, db, project):
        state = get_state(project.id)
        wf = _make_wf(anchor="Free floating", source_scene_id=None)
        state.add(wf)

        from collections import defaultdict
        by_scene = defaultdict(list)
        for w in state.wavefunctions.values():
            by_scene[w.source_scene_id].append(w)

        assert len(by_scene[None]) == 1

    def test_branch_node_data_complete(self, db, project):
        state = get_state(project.id)
        b = _make_branch("Bold Move", stakes="Everything", consequence="Total war")
        wf = _make_wf(branches=[b])
        state.add(wf)

        branch = wf.branches[0]
        assert branch.title == "Bold Move"
        assert branch.stakes == "Everything"
        assert branch.consequence == "Total war"
        assert branch.description == "Desc for Bold Move"

    def test_status_states(self, db, project):
        state = get_state(project.id)
        b1 = _make_branch("A")
        b2 = _make_branch("B")
        wf = _make_wf(branches=[b1, b2])
        state.add(wf)

        assert not wf.is_collapsed()
        for b in wf.branches:
            is_collapsed = wf.collapsed_branch_id == b.id
            is_archived = wf.is_collapsed() and not is_collapsed
            assert not is_collapsed
            assert not is_archived

        wf.collapsed_branch_id = b1.id
        assert wf.is_collapsed()

        for b in wf.branches:
            is_collapsed = wf.collapsed_branch_id == b.id
            is_archived = wf.is_collapsed() and not is_collapsed
            if b.id == b1.id:
                assert is_collapsed
                assert not is_archived
            else:
                assert not is_collapsed
                assert is_archived


class TestTimelinePersistence:
    """Verify timeline state survives save/load cycle."""

    def test_reload_preserves_branches_and_selection(self, db, project):
        state = get_state(project.id)
        s1 = db.create_scene(project.id, title="Sc1")
        branches = [
            _make_branch("X", stakes="high"),
            _make_branch("Y", consequence="doom"),
        ]
        wf = _make_wf(anchor="Decision", branches=branches, source_scene_id=s1.id)
        state.add(wf)

        save_state(db, project.id)

        _STATES.clear()

        loaded = load_state(db, project.id)
        assert len(loaded.wavefunctions) == 1
        loaded_wf = list(loaded.wavefunctions.values())[0]
        assert loaded_wf.anchor == "Decision"
        assert loaded_wf.source_scene_id == s1.id
        assert len(loaded_wf.branches) == 2
        assert loaded_wf.branches[0].stakes == "high"
        assert loaded_wf.branches[1].consequence == "doom"

    def test_reload_preserves_collapsed_state(self, db, project):
        state = get_state(project.id)
        b1 = _make_branch("Won")
        b2 = _make_branch("Lost")
        wf = _make_wf(branches=[b1, b2], collapsed_branch_id=b1.id)
        state.add(wf)

        save_state(db, project.id)
        _STATES.clear()

        loaded = load_state(db, project.id)
        loaded_wf = list(loaded.wavefunctions.values())[0]
        assert loaded_wf.is_collapsed()
        assert loaded_wf.collapsed_branch_id == b1.id

    def test_reload_preserves_archived_removal(self, db, project):
        state = get_state(project.id)
        wf1 = _make_wf(anchor="Keep")
        wf2 = _make_wf(anchor="Remove")
        state.add(wf1)
        state.add(wf2)

        state.remove(wf2.id)
        save_state(db, project.id)
        _STATES.clear()

        loaded = load_state(db, project.id)
        assert len(loaded.wavefunctions) == 1
        assert list(loaded.wavefunctions.values())[0].anchor == "Keep"


class TestBeatMarkers:
    """Test classical beat marker extraction for scene columns."""

    def test_beat_marker_with_method_and_beat(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        wf = _make_wf(anchor="Test")
        wf.structure_method = "Save the Cat"
        wf.structure_beat = "Midpoint"
        marker = QuantumTimelineWidget._extract_beat_marker([wf])
        assert "Save the Cat" in marker
        assert "Midpoint" in marker
        assert "→" in marker

    def test_beat_marker_method_only(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        wf = _make_wf(anchor="Test")
        wf.structure_method = "Story Circle"
        wf.structure_beat = None
        marker = QuantumTimelineWidget._extract_beat_marker([wf])
        assert "Story Circle" in marker
        assert "→" not in marker

    def test_beat_marker_empty_when_no_structure(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        wf = _make_wf(anchor="Test")
        marker = QuantumTimelineWidget._extract_beat_marker([wf])
        assert marker == ""

    def test_beat_marker_deduplicates_methods(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        wf1 = _make_wf(anchor="A")
        wf1.structure_method = "Save the Cat"
        wf1.structure_beat = "Midpoint"
        wf2 = _make_wf(anchor="B")
        wf2.structure_method = "Save the Cat"
        wf2.structure_beat = "Finale"
        marker = QuantumTimelineWidget._extract_beat_marker([wf1, wf2])
        assert marker.count("Save the Cat") == 1

    def test_beat_marker_truncates_long_method(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        wf = _make_wf(anchor="Test")
        wf.structure_method = "Seven-Point Story Structure"
        wf.structure_beat = "Hook"
        marker = QuantumTimelineWidget._extract_beat_marker([wf])
        assert len(marker) < 40


class TestBranchTypeDisplay:
    """Test branch_type and structure_beat display helpers."""

    def test_branch_type_short_labels(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        assert QuantumTimelineWidget._branch_type_short("deviation") == "dev"
        assert QuantumTimelineWidget._branch_type_short("alternative") == "alt"
        assert QuantumTimelineWidget._branch_type_short("intensification") == "int"
        assert QuantumTimelineWidget._branch_type_short("resolution") == "res"

    def test_branch_type_style_returns_color(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        style = QuantumTimelineWidget._branch_type_style("deviation")
        assert "color:" in style
        assert "#e06c75" in style

    def test_branch_with_structure_beat(self, db, project):
        state = get_state(project.id)
        b = Branch.new(
            title="False Victory",
            description="Hero wins at hidden cost",
            structure_beat="Midpoint",
            branch_type="intensification",
        )
        wf = _make_wf(branches=[b])
        state.add(wf)
        assert wf.branches[0].structure_beat == "Midpoint"
        assert wf.branches[0].branch_type == "intensification"

    def test_branch_without_structure_has_no_beat(self, db, project):
        state = get_state(project.id)
        b = _make_branch("Plain Branch")
        wf = _make_wf(branches=[b])
        state.add(wf)
        assert wf.branches[0].structure_beat is None
        assert wf.branches[0].branch_type is None

    def test_column_width_unchanged(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        assert hasattr(QuantumTimelineWidget, "_build_scene_column")
        assert hasattr(QuantumTimelineWidget, "_extract_beat_marker")


class TestWidgetModule:
    """Test that the widget module imports and has expected interface."""

    def test_import_widget(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        assert hasattr(QuantumTimelineWidget, "branch_selected")
        assert hasattr(QuantumTimelineWidget, "collapse_requested")
        assert hasattr(QuantumTimelineWidget, "archive_requested")
        assert hasattr(QuantumTimelineWidget, "refresh")

    def test_status_badge_values(self):
        from logosforge.ui.quantum_timeline import QuantumTimelineWidget
        assert QuantumTimelineWidget._status_badge("active") == "○"
        assert QuantumTimelineWidget._status_badge("selected") == "◉"
        assert QuantumTimelineWidget._status_badge("collapsed") == "●"
        assert QuantumTimelineWidget._status_badge("archived") == "◌"
        assert QuantumTimelineWidget._status_badge("unknown") == ""

    def test_assistant_view_imports_timeline(self):
        from logosforge.ui.assistant_view import AssistantPanel
        assert AssistantPanel is not None
