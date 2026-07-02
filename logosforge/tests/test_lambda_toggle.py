"""Tests for Lambda Mode toggle in the Quantum panel."""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import OutlineMode, get_state
from logosforge.quantum_outliner.state import _STATES


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Lambda Toggle Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


class TestLambdaToggleState:
    def test_default_is_classical(self, project):
        state = get_state(project.id)
        assert state.outline_mode is OutlineMode.CLASSICAL

    def test_toggle_to_lambda(self, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        assert state.outline_mode is OutlineMode.LAMBDA

    def test_toggle_back_to_classical(self, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.outline_mode = OutlineMode.CLASSICAL
        assert state.outline_mode is OutlineMode.CLASSICAL

    def test_toggle_updates_immediately(self, project):
        state = get_state(project.id)
        assert state.outline_mode is OutlineMode.CLASSICAL
        state.outline_mode = OutlineMode.LAMBDA
        assert get_state(project.id).outline_mode is OutlineMode.LAMBDA

    def test_toggle_independent_of_structure_mode(self, project):
        state = get_state(project.id)
        state.structure_mode = "quantum"
        state.outline_mode = OutlineMode.LAMBDA
        assert state.structure_mode == "quantum"
        assert state.outline_mode is OutlineMode.LAMBDA

    def test_persists_through_save_load(self, db, project):
        from logosforge.quantum_outliner import save_state, load_state
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        save_state(db, project.id)
        _STATES.clear()
        loaded = load_state(db, project.id)
        assert loaded.outline_mode is OutlineMode.LAMBDA


class TestLambdaToggleUI:
    def test_assistant_view_has_lambda_toggle(self):
        from logosforge.ui.assistant_view import AssistantPanel
        assert hasattr(AssistantPanel, "_on_lambda_toggle")
        assert hasattr(AssistantPanel, "_sync_lambda_toggle")
        assert hasattr(AssistantPanel, "_lambda_btn_style")

    def test_lambda_btn_style_active(self):
        from logosforge.ui.assistant_view import AssistantPanel
        style = AssistantPanel._lambda_btn_style(True)
        assert "bold" in style

    def test_lambda_btn_style_inactive(self):
        from logosforge.ui.assistant_view import AssistantPanel
        style = AssistantPanel._lambda_btn_style(False)
        assert "transparent" in style

    def test_outline_mode_importable(self):
        from logosforge.quantum_outliner import OutlineMode, OUTLINE_MODES
        assert OutlineMode.CLASSICAL.value == "classical"
        assert OutlineMode.LAMBDA.value == "lambda"
        assert "classical" in OUTLINE_MODES
        assert "lambda" in OUTLINE_MODES
