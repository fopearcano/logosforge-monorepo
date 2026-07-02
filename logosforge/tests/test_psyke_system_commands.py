"""Tests for PSYKE system command handlers."""

import pytest

from logosforge.db import Database
from logosforge.psyke_command_registry import CommandContext, CommandRegistry
from logosforge.psyke_system_commands import SystemCommandHandlers


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Test Project")


@pytest.fixture
def callbacks():
    class Callbacks:
        def __init__(self):
            self.opened_scenes: list[int] = []
            self.opened_entries: list[int] = []
            self.data_changed_count = 0

        def open_scene(self, scene_id):
            self.opened_scenes.append(scene_id)

        def open_entry(self, entry_id):
            self.opened_entries.append(entry_id)

        def on_data_changed(self):
            self.data_changed_count += 1

    return Callbacks()


@pytest.fixture
def handlers(db, project, callbacks):
    return SystemCommandHandlers(
        db,
        project.id,
        open_scene=callbacks.open_scene,
        open_psyke_entry=callbacks.open_entry,
        on_data_changed=callbacks.on_data_changed,
    )


@pytest.fixture
def registry(handlers):
    reg = CommandRegistry()
    handlers.register_all(reg)
    return reg


class TestCreateCommand:
    def test_create_character(self, handlers):
        ctx = CommandContext(command="create", args=["character"])
        result = handlers.handle_create(ctx)
        assert result["ok"]
        assert result["type"] == "character"
        assert result["name"] == "New Character"

    def test_create_place(self, handlers):
        ctx = CommandContext(command="create", args=["place"])
        result = handlers.handle_create(ctx)
        assert result["ok"]
        assert result["type"] == "place"

    def test_create_object(self, handlers):
        ctx = CommandContext(command="create", args=["object"])
        result = handlers.handle_create(ctx)
        assert result["ok"]
        assert result["type"] == "object"

    def test_create_with_name(self, handlers):
        ctx = CommandContext(command="create", args=["character", "Jean", "Moreau"])
        result = handlers.handle_create(ctx)
        assert result["ok"]
        assert result["name"] == "Jean Moreau"

    def test_create_default_type(self, handlers):
        ctx = CommandContext(command="create", args=[])
        result = handlers.handle_create(ctx)
        assert result["ok"]
        assert result["type"] == "other"

    def test_create_invalid_type(self, handlers):
        ctx = CommandContext(command="create", args=["spaceship"])
        result = handlers.handle_create(ctx)
        assert not result["ok"]
        assert "Unknown type" in result["error"]

    def test_create_triggers_data_changed(self, handlers, callbacks):
        ctx = CommandContext(command="create", args=["character"])
        handlers.handle_create(ctx)
        assert callbacks.data_changed_count == 1

    def test_create_opens_entry(self, handlers, callbacks):
        ctx = CommandContext(command="create", args=["character"])
        result = handlers.handle_create(ctx)
        assert callbacks.opened_entries == [result["entry_id"]]

    def test_create_persists_to_db(self, db, project, handlers):
        ctx = CommandContext(command="create", args=["character", "Test", "Person"])
        result = handlers.handle_create(ctx)
        entry = db.get_psyke_entry_by_id(result["entry_id"])
        assert entry is not None
        assert entry.name == "Test Person"
        assert entry.entry_type == "character"


class TestOpenCommand:
    def test_open_scene(self, db, project, handlers, callbacks):
        scene = db.create_scene(project.id, "Scene 1")
        ctx = CommandContext(command="open", args=["scene", str(scene.id)])
        result = handlers.handle_open(ctx)
        assert result["ok"]
        assert callbacks.opened_scenes == [scene.id]

    def test_open_scene_not_found(self, handlers):
        ctx = CommandContext(command="open", args=["scene", "9999"])
        result = handlers.handle_open(ctx)
        assert not result["ok"]
        assert "not found" in result["error"]

    def test_open_scene_invalid_id(self, handlers):
        ctx = CommandContext(command="open", args=["scene", "abc"])
        result = handlers.handle_open(ctx)
        assert not result["ok"]
        assert "Invalid" in result["error"]

    def test_open_scene_no_id(self, handlers):
        ctx = CommandContext(command="open", args=["scene"])
        result = handlers.handle_open(ctx)
        assert not result["ok"]

    def test_open_psyke_entry(self, db, project, handlers, callbacks):
        db.create_psyke_entry(project.id, "Jean Moreau", "character")
        ctx = CommandContext(command="open", args=["psyke", "jean"])
        result = handlers.handle_open(ctx)
        assert result["ok"]
        assert result["name"] == "Jean Moreau"
        assert len(callbacks.opened_entries) == 1

    def test_open_psyke_not_found(self, handlers):
        ctx = CommandContext(command="open", args=["psyke", "zzzzz"])
        result = handlers.handle_open(ctx)
        assert not result["ok"]
        assert "No entry" in result["error"]

    def test_open_no_args(self, handlers):
        ctx = CommandContext(command="open", args=[])
        result = handlers.handle_open(ctx)
        assert not result["ok"]
        assert "Usage" in result["error"]

    def test_open_unknown_target(self, handlers):
        ctx = CommandContext(command="open", args=["spaceship"])
        result = handlers.handle_open(ctx)
        assert not result["ok"]
        assert "Unknown target" in result["error"]


class TestGoCommand:
    def test_go_scene_next(self, db, project, callbacks):
        s1 = db.create_scene(project.id, "Scene 1")
        s2 = db.create_scene(project.id, "Scene 2")
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
            get_active_scene_id=lambda: s1.id,
        )
        ctx = CommandContext(command="go", args=["scene", "next"])
        result = h.handle_go(ctx)
        assert result["ok"]
        assert result["scene_id"] == s2.id
        assert callbacks.opened_scenes == [s2.id]

    def test_go_scene_previous(self, db, project, callbacks):
        s1 = db.create_scene(project.id, "Scene 1")
        s2 = db.create_scene(project.id, "Scene 2")
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
            get_active_scene_id=lambda: s2.id,
        )
        ctx = CommandContext(command="go", args=["scene", "previous"])
        result = h.handle_go(ctx)
        assert result["ok"]
        assert result["scene_id"] == s1.id

    def test_go_scene_next_at_end(self, db, project, callbacks):
        s1 = db.create_scene(project.id, "Scene 1")
        s2 = db.create_scene(project.id, "Scene 2")
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
            get_active_scene_id=lambda: s2.id,
        )
        ctx = CommandContext(command="go", args=["scene", "next"])
        result = h.handle_go(ctx)
        assert result["ok"]
        assert result["scene_id"] == s2.id

    def test_go_scene_previous_at_start(self, db, project, callbacks):
        s1 = db.create_scene(project.id, "Scene 1")
        db.create_scene(project.id, "Scene 2")
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
            get_active_scene_id=lambda: s1.id,
        )
        ctx = CommandContext(command="go", args=["scene", "previous"])
        result = h.handle_go(ctx)
        assert result["ok"]
        assert result["scene_id"] == s1.id

    def test_go_scene_no_active(self, db, project, callbacks):
        s1 = db.create_scene(project.id, "Scene 1")
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
            get_active_scene_id=lambda: None,
        )
        ctx = CommandContext(command="go", args=["scene", "next"])
        result = h.handle_go(ctx)
        assert result["ok"]
        assert result["scene_id"] == s1.id

    def test_go_scene_by_id(self, db, project, callbacks):
        s1 = db.create_scene(project.id, "Scene 1")
        s2 = db.create_scene(project.id, "Scene 2")
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
        )
        ctx = CommandContext(command="go", args=["scene", str(s2.id)])
        result = h.handle_go(ctx)
        assert result["ok"]
        assert result["scene_id"] == s2.id
        assert callbacks.opened_scenes == [s2.id]

    def test_go_no_scenes(self, db, project, callbacks):
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
            get_active_scene_id=lambda: None,
        )
        ctx = CommandContext(command="go", args=["scene", "next"])
        result = h.handle_go(ctx)
        assert not result["ok"]
        assert "No scenes" in result["error"]

    def test_go_no_args(self, handlers):
        ctx = CommandContext(command="go", args=[])
        result = handlers.handle_go(ctx)
        assert not result["ok"]
        assert "Usage" in result["error"]

    def test_go_unknown_target(self, handlers):
        ctx = CommandContext(command="go", args=["chapter"])
        result = handlers.handle_go(ctx)
        assert not result["ok"]

    def test_go_scene_invalid_direction(self, handlers):
        ctx = CommandContext(command="go", args=["scene", "sideways"])
        result = handlers.handle_go(ctx)
        assert not result["ok"]


class TestAiCommand:
    def test_ai_rewrite(self, db, project, callbacks):
        ai_calls = []

        def mock_run(action, text):
            ai_calls.append((action, text))
            return True

        h = SystemCommandHandlers(
            db, project.id,
            get_selected_text=lambda: "The castle was big.",
            run_ai_action=mock_run,
        )
        ctx = CommandContext(command="ai", args=["rewrite"])
        result = h.handle_ai(ctx)
        assert result["ok"]
        assert result["action"] == "rewrite"
        assert ai_calls == [("rewrite", "The castle was big.")]

    def test_ai_expand(self, db, project):
        ai_calls = []
        h = SystemCommandHandlers(
            db, project.id,
            get_selected_text=lambda: "Short text.",
            run_ai_action=lambda a, t: (ai_calls.append((a, t)) or True),
        )
        ctx = CommandContext(command="ai", args=["expand"])
        result = h.handle_ai(ctx)
        assert result["ok"]
        assert ai_calls[0][0] == "expand"

    def test_ai_summarize(self, db, project):
        ai_calls = []
        h = SystemCommandHandlers(
            db, project.id,
            get_selected_text=lambda: "Long passage here.",
            run_ai_action=lambda a, t: (ai_calls.append((a, t)) or True),
        )
        ctx = CommandContext(command="ai", args=["summarize"])
        result = h.handle_ai(ctx)
        assert result["ok"]
        assert ai_calls[0][0] == "summarize"

    def test_ai_no_action(self, db, project):
        h = SystemCommandHandlers(db, project.id, run_ai_action=lambda a, t: True)
        ctx = CommandContext(command="ai", args=[])
        result = h.handle_ai(ctx)
        assert not result["ok"]
        assert "Usage" in result["error"]

    def test_ai_unknown_action(self, db, project):
        h = SystemCommandHandlers(db, project.id, run_ai_action=lambda a, t: True)
        ctx = CommandContext(command="ai", args=["destroy"])
        result = h.handle_ai(ctx)
        assert not result["ok"]
        assert "Unknown action" in result["error"]

    def test_ai_no_assistant(self, db, project):
        h = SystemCommandHandlers(db, project.id)
        ctx = CommandContext(command="ai", args=["rewrite"])
        result = h.handle_ai(ctx)
        assert not result["ok"]
        assert "not available" in result["error"]

    def test_ai_busy(self, db, project):
        h = SystemCommandHandlers(
            db, project.id,
            get_selected_text=lambda: "text",
            run_ai_action=lambda a, t: False,
        )
        ctx = CommandContext(command="ai", args=["rewrite"])
        result = h.handle_ai(ctx)
        assert not result["ok"]
        assert "busy" in result["error"]

    def test_ai_no_selection(self, db, project):
        ai_calls = []
        h = SystemCommandHandlers(
            db, project.id,
            get_selected_text=lambda: "",
            run_ai_action=lambda a, t: (ai_calls.append((a, t)) or True),
        )
        ctx = CommandContext(command="ai", args=["rewrite"])
        result = h.handle_ai(ctx)
        assert result["ok"]
        assert ai_calls[0][1] == ""

    def test_ai_case_insensitive(self, db, project):
        ai_calls = []
        h = SystemCommandHandlers(
            db, project.id,
            get_selected_text=lambda: "text",
            run_ai_action=lambda a, t: (ai_calls.append((a, t)) or True),
        )
        ctx = CommandContext(command="ai", args=["Rewrite"])
        result = h.handle_ai(ctx)
        assert result["ok"]


class TestRegistration:
    def test_all_registered(self, registry):
        assert registry.has("create")
        assert registry.has("open")
        assert registry.has("go")
        assert registry.has("goto")
        assert registry.has("ai")
        assert registry.has("ask")

    def test_dispatch_via_registry(self, registry, db, project):
        entry = registry.resolve("create")
        ctx = CommandContext(command="create", args=["character", "Test"])
        result = entry.handler(ctx)
        assert result["ok"]
        assert result["name"] == "Test"


class TestConnectorIntegration:
    """Verify all data operations route through the Connector executor."""

    def test_create_goes_through_connector(self, db, project, callbacks):
        h = SystemCommandHandlers(
            db, project.id,
            open_psyke_entry=callbacks.open_entry,
            on_data_changed=callbacks.on_data_changed,
        )
        ctx = CommandContext(command="create", args=["character", "Via", "Connector"])
        result = h.handle_create(ctx)
        assert result["ok"]
        entry = db.get_psyke_entry_by_id(result["entry_id"])
        assert entry is not None
        assert entry.name == "Via Connector"
        assert entry.entry_type == "character"

    def test_open_scene_validates_via_connector(self, db, project, callbacks):
        scene = db.create_scene(project.id, "Test Scene")
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
        )
        ctx = CommandContext(command="open", args=["scene", str(scene.id)])
        result = h.handle_open(ctx)
        assert result["ok"]
        assert callbacks.opened_scenes == [scene.id]

    def test_open_scene_wrong_project_fails(self, db, callbacks):
        p1 = db.create_project("Project 1")
        p2 = db.create_project("Project 2")
        scene = db.create_scene(p2.id, "Other Scene")
        h = SystemCommandHandlers(
            db, p1.id,
            open_scene=callbacks.open_scene,
        )
        ctx = CommandContext(command="open", args=["scene", str(scene.id)])
        result = h.handle_open(ctx)
        assert not result["ok"]
        assert callbacks.opened_scenes == []

    def test_go_next_uses_connector_list(self, db, project, callbacks):
        s1 = db.create_scene(project.id, "Scene 1")
        s2 = db.create_scene(project.id, "Scene 2")
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
            get_active_scene_id=lambda: s1.id,
        )
        ctx = CommandContext(command="go", args=["scene", "next"])
        result = h.handle_go(ctx)
        assert result["ok"]
        assert result["scene_id"] == s2.id

    def test_go_by_id_validates_via_connector(self, db, project, callbacks):
        scene = db.create_scene(project.id, "Scene 1")
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
        )
        ctx = CommandContext(command="go", args=["scene", str(scene.id)])
        result = h.handle_go(ctx)
        assert result["ok"]
        assert callbacks.opened_scenes == [scene.id]

    def test_go_by_id_nonexistent_fails(self, db, project, callbacks):
        h = SystemCommandHandlers(
            db, project.id,
            open_scene=callbacks.open_scene,
        )
        ctx = CommandContext(command="go", args=["scene", "99999"])
        result = h.handle_go(ctx)
        assert not result["ok"]
        assert callbacks.opened_scenes == []

    def test_open_psyke_validates_via_connector(self, db, project, callbacks):
        db.create_psyke_entry(project.id, "Jean Moreau", "character")
        h = SystemCommandHandlers(
            db, project.id,
            open_psyke_entry=callbacks.open_entry,
        )
        ctx = CommandContext(command="open", args=["psyke", "jean"])
        result = h.handle_open(ctx)
        assert result["ok"]
        assert result["name"] == "Jean Moreau"
        assert len(callbacks.opened_entries) == 1

    def test_create_result_structure(self, db, project, callbacks):
        h = SystemCommandHandlers(
            db, project.id,
            open_psyke_entry=callbacks.open_entry,
            on_data_changed=callbacks.on_data_changed,
        )
        ctx = CommandContext(command="create", args=["place", "The", "Grand", "Palace"])
        result = h.handle_create(ctx)
        assert result["ok"]
        assert "entry_id" in result
        assert result["name"] == "The Grand Palace"
        assert result["type"] == "place"
