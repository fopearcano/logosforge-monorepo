"""Tests for Writing Methods RAG integration with Quantum generation."""

from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    OutlineMode,
    generate_branches,
    generate_outline,
    get_state,
)
from logosforge.quantum_outliner.possibilities import (
    _resolve_auto_mode,
    _stub_branches,
    build_rag_context,
    generate_possibilities,
)
from logosforge.quantum_outliner.state import _STATES
from logosforge.quantum_outliner.writing_methods_rag import reload as rag_reload


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("RAG Integration Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    rag_reload()
    yield
    _STATES.clear()


class TestAutoModeResolution:
    def test_structural_keyword_selects_hybrid(self):
        assert _resolve_auto_mode("Help me plot Act 2") == "hybrid"
        assert _resolve_auto_mode("What happens at the midpoint") == "hybrid"
        assert _resolve_auto_mode("catalyst for the inciting incident") == "hybrid"
        assert _resolve_auto_mode("climax resolution beat") == "hybrid"

    def test_no_structural_keyword_selects_quantum(self):
        assert _resolve_auto_mode("Hero meets enemy") == "quantum"
        assert _resolve_auto_mode("The village burns") == "quantum"
        assert _resolve_auto_mode("Continue from here") == "quantum"


class TestRAGContext:
    def test_classical_mode_retrieves_methods(self):
        ctx, methods = build_rag_context("Help me plot Act 2 structure", "classical")
        assert len(methods) >= 1
        assert "Relevant writing methods:" in ctx
        assert any(m.title for m in methods)

    def test_hybrid_mode_retrieves_methods(self):
        ctx, methods = build_rag_context("Midpoint of Save the Cat", "hybrid")
        assert len(methods) >= 1
        assert "Save the Cat" in ctx

    def test_quantum_mode_skips_rag(self):
        ctx, methods = build_rag_context("Hero meets enemy", "quantum")
        assert ctx == ""
        assert methods == []

    def test_no_match_returns_empty(self):
        ctx, methods = build_rag_context("xyzzy foobar", "classical")
        assert ctx == ""
        assert methods == []


class TestClassicalOutput:
    def test_classical_stubs_contain_method(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "classical"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Help me plot Act 2 structure",
            )

        assert result.kind == "possibilities"
        has_method = any(
            b["structure_method"] is not None
            for b in result.payload["branches"]
        )
        assert has_method

    def test_classical_wf_has_structure_method(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "classical"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Save the Cat midpoint",
            )

        assert result.payload.get("structure_method") is not None

    def test_classical_body_mentions_structure(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "classical"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Three-Act Structure setup",
            )

        assert "Gravity:" in result.body


class TestQuantumOutput:
    def test_quantum_stubs_have_no_method(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Hero meets enemy",
            )

        assert result.kind == "possibilities"
        for b in result.payload["branches"]:
            assert b["structure_method"] is None
            assert b["branch_type"] is None

    def test_quantum_wf_has_no_structure(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(db, project.id, "The village burns")

        assert result.payload.get("structure_method") is None

    def test_quantum_body_has_no_structure_line(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "quantum"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(db, project.id, "Continue the fight")

        assert "Structure:" not in result.body


class TestHybridOutput:
    def test_hybrid_has_branches_and_method(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "hybrid"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Scene-Sequel goal conflict",
            )

        assert result.kind == "possibilities"
        assert len(result.payload["branches"]) >= 3
        assert result.payload.get("structure_method") is not None

    def test_hybrid_stubs_have_branch_types(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "hybrid"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Hero's Journey Ordeal",
            )

        types = [b["branch_type"] for b in result.payload["branches"]]
        assert any(t is not None for t in types)


class TestAutoOutput:
    def test_auto_structural_query_gets_methods(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "auto"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Help me plot Act 2 midpoint",
            )

        assert result.payload.get("structure_method") is not None

    def test_auto_freeform_query_stays_quantum(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "auto"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "The dragon awakens",
            )

        assert result.payload.get("structure_method") is None


class TestPromptConstruction:
    def test_classical_system_prompt_sent(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "classical"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_branches(db, project.id, "Act 2 structure")

        messages = mock.call_args[0][0]
        system = messages[0]["content"]
        assert "classical writing" in system.lower() or "established story beat" in system.lower()

    def test_quantum_system_prompt_sent(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "quantum"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_branches(db, project.id, "Hero meets enemy")

        messages = mock.call_args[0][0]
        system = messages[0]["content"]
        assert "superposition" in system.lower()

    def test_hybrid_system_prompt_sent(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "hybrid"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_branches(db, project.id, "Midpoint twist")

        messages = mock.call_args[0][0]
        system = messages[0]["content"]
        assert "classical" in system.lower() or "structural" in system.lower()

    def test_rag_context_in_user_message(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "classical"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_branches(db, project.id, "Save the Cat midpoint")

        messages = mock.call_args[0][0]
        user = messages[1]["content"]
        assert "Relevant writing methods:" in user
        assert "Save the Cat" in user

    def test_quantum_has_no_rag_in_user_message(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "quantum"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_branches(db, project.id, "Save the Cat midpoint")

        messages = mock.call_args[0][0]
        user = messages[1]["content"]
        assert "Relevant writing methods:" not in user


class TestStubBranches:
    def test_quantum_stubs_no_structure(self):
        branches = _stub_branches("test", 3, "quantum", None)
        for b in branches:
            assert b.structure_method is None
            assert b.branch_type is None

    def test_classical_stubs_with_rag(self):
        from logosforge.quantum_outliner.writing_methods_rag import MethodResult
        methods = [MethodResult(title="Save the Cat", snippet="...", score=0.8)]
        branches = _stub_branches("test", 3, "classical", methods)
        for b in branches:
            assert b.structure_method == "Save the Cat"
        assert any(b.branch_type is not None for b in branches)

    def test_hybrid_stubs_with_rag(self):
        from logosforge.quantum_outliner.writing_methods_rag import MethodResult
        methods = [MethodResult(title="Three-Act Structure", snippet="...", score=0.7)]
        branches = _stub_branches("test", 4, "hybrid", methods)
        assert branches[0].structure_method == "Three-Act Structure"
        assert any(b.branch_type is not None for b in branches)
