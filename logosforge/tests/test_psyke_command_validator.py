"""Tests for PSYKE command safety validation."""

import pytest

from logosforge.psyke_command_registry import CommandRegistry
from logosforge.psyke_command_validator import (
    ValidationResult,
    ValidationStatus,
    validate_command,
)


def _noop(ctx):
    return {"ok": True}


@pytest.fixture
def registry():
    reg = CommandRegistry()
    reg.register("create", _noop, description="Create entry")
    reg.register("open", _noop, description="Open entry")
    reg.register("go", _noop, description="Navigate", aliases=["goto"])
    reg.register("ai", _noop, description="AI actions", aliases=["ask"])
    return reg


# --- Unknown commands ---

class TestUnknownCommands:
    def test_unknown_command_blocked(self, registry):
        result = validate_command("fly", [], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "Unknown command" in result.error

    def test_unknown_no_registry(self):
        result = validate_command("fly", [], registry=None)
        assert result.status == ValidationStatus.ERROR

    def test_known_command_passes(self, registry):
        result = validate_command("create", ["character", "Alice"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_alias_passes(self, registry):
        result = validate_command("goto", ["scene", "next"], registry=registry)
        assert result.status == ValidationStatus.OK


# --- Missing arguments ---

class TestMissingArgs:
    def test_create_no_args(self, registry):
        result = validate_command("create", [], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "Missing arguments" in result.error

    def test_open_no_args(self, registry):
        result = validate_command("open", [], registry=registry)
        assert result.status == ValidationStatus.ERROR

    def test_go_no_args(self, registry):
        result = validate_command("go", [], registry=registry)
        assert result.status == ValidationStatus.ERROR

    def test_ai_no_args(self, registry):
        result = validate_command("ai", [], registry=registry)
        assert result.status == ValidationStatus.ERROR

    def test_insert_no_args(self):
        result = validate_command("insert", [])
        assert result.status == ValidationStatus.ERROR

    def test_delete_no_args(self):
        result = validate_command("delete", [])
        assert result.status == ValidationStatus.ERROR


# --- Invalid first argument ---

class TestInvalidFirstArg:
    def test_create_invalid_type(self, registry):
        result = validate_command("create", ["alien"], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "Invalid argument" in result.error
        assert "alien" in result.error

    def test_create_valid_type(self, registry):
        result = validate_command("create", ["character", "Bob"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_open_invalid_target(self, registry):
        result = validate_command("open", ["database"], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "database" in result.error

    def test_go_invalid_target(self, registry):
        result = validate_command("go", ["moon"], registry=registry)
        assert result.status == ValidationStatus.ERROR


# --- Open scene validation ---

class TestOpenSceneValidation:
    def test_open_scene_no_id(self, registry):
        result = validate_command("open", ["scene"], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "Missing scene id" in result.error

    def test_open_scene_bad_id(self, registry):
        result = validate_command("open", ["scene", "abc"], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "Invalid scene id" in result.error

    def test_open_scene_negative_id(self, registry):
        result = validate_command("open", ["scene", "-1"], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "positive" in result.error

    def test_open_scene_zero_id(self, registry):
        result = validate_command("open", ["scene", "0"], registry=registry)
        assert result.status == ValidationStatus.ERROR

    def test_open_scene_valid(self, registry):
        result = validate_command("open", ["scene", "5"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_open_psyke_no_name(self, registry):
        result = validate_command("open", ["psyke"], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "Missing entry name" in result.error

    def test_open_psyke_valid(self, registry):
        result = validate_command("open", ["psyke", "John"], registry=registry)
        assert result.status == ValidationStatus.OK


# --- Go scene validation ---

class TestGoSceneValidation:
    def test_go_scene_no_direction(self, registry):
        result = validate_command("go", ["scene"], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "Missing direction" in result.error

    def test_go_scene_bad_direction(self, registry):
        result = validate_command("go", ["scene", "sideways"], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "Invalid direction" in result.error

    def test_go_scene_next(self, registry):
        result = validate_command("go", ["scene", "next"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_go_scene_previous(self, registry):
        result = validate_command("go", ["scene", "previous"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_go_scene_prev(self, registry):
        result = validate_command("go", ["scene", "prev"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_go_scene_valid_id(self, registry):
        result = validate_command("go", ["scene", "3"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_go_scene_negative_id(self, registry):
        result = validate_command("go", ["scene", "-5"], registry=registry)
        assert result.status == ValidationStatus.ERROR
        assert "positive" in result.error


# --- Destructive commands require confirmation ---

class TestDestructiveConfirmation:
    def test_delete_requires_confirm(self):
        result = validate_command("delete", ["John"])
        assert result.status == ValidationStatus.CONFIRM
        assert "Delete" in result.confirm_message
        assert "John" in result.confirm_message
        assert "cannot be undone" in result.confirm_message

    def test_rename_requires_confirm(self):
        result = validate_command("rename", ["Old", "to", "New"])
        assert result.status == ValidationStatus.CONFIRM
        assert "Rename" in result.confirm_message
        assert "Old" in result.confirm_message
        assert "New" in result.confirm_message

    def test_rename_multi_word(self):
        result = validate_command("rename", ["Old", "Name", "to", "New", "Name"])
        assert result.status == ValidationStatus.CONFIRM
        assert "Old Name" in result.confirm_message
        assert "New Name" in result.confirm_message

    def test_create_not_destructive(self, registry):
        result = validate_command("create", ["character", "Bob"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_open_not_destructive(self, registry):
        result = validate_command("open", ["scene", "1"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_go_not_destructive(self, registry):
        result = validate_command("go", ["scene", "next"], registry=registry)
        assert result.status == ValidationStatus.OK


# --- Rename validation ---

class TestRenameValidation:
    def test_rename_missing_to(self):
        result = validate_command("rename", ["Alice", "Bob"])
        assert result.status == ValidationStatus.ERROR
        assert "'to'" in result.error

    def test_rename_no_old_name(self):
        result = validate_command("rename", ["to", "New"])
        assert result.status == ValidationStatus.ERROR
        assert "original name" in result.error

    def test_rename_no_new_name(self):
        result = validate_command("rename", ["Old", "to"])
        assert result.status == ValidationStatus.ERROR
        assert "new name" in result.error

    def test_rename_valid(self):
        result = validate_command("rename", ["Alice", "to", "Bob"])
        assert result.status == ValidationStatus.CONFIRM


# --- Safe commands pass through ---

class TestSafeCommands:
    def test_ai_passes(self, registry):
        result = validate_command("ai", ["rewrite"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_create_all_types(self, registry):
        for t in ("character", "place", "object", "lore", "theme", "other"):
            result = validate_command("create", [t], registry=registry)
            assert result.status == ValidationStatus.OK, f"Failed for type: {t}"

    def test_case_insensitive(self, registry):
        result = validate_command("CREATE", ["Character"], registry=registry)
        assert result.status == ValidationStatus.OK

    def test_insert_valid(self):
        result = validate_command("insert", ["john"])
        assert result.status == ValidationStatus.OK


# --- ValidationResult fields ---

class TestValidationResult:
    def test_error_has_command(self, registry):
        result = validate_command("create", [], registry=registry)
        assert result.command == "create"
        assert result.args == []

    def test_ok_has_command_and_args(self, registry):
        result = validate_command("create", ["character", "Bob"], registry=registry)
        assert result.command == "create"
        assert result.args == ["character", "Bob"]

    def test_confirm_has_command_and_args(self):
        result = validate_command("delete", ["John"])
        assert result.command == "delete"
        assert result.args == ["John"]
