"""Tests for PSYKE natural language intent detection."""

import pytest

from logosforge.psyke_intents import Intent, detect_intent


class TestOpenIntents:
    def test_open_scene_by_id(self):
        intent = detect_intent("open scene 3")
        assert intent == Intent("open_scene", {"id": 3})

    def test_open_scene_by_id_large(self):
        intent = detect_intent("open scene 142")
        assert intent == Intent("open_scene", {"id": 142})

    def test_open_entry_by_name(self):
        intent = detect_intent("open entry John")
        assert intent == Intent("open_entry", {"name": "John"})

    def test_open_psyke_entry(self):
        intent = detect_intent("open psyke Sword of Light")
        assert intent == Intent("open_entry", {"name": "Sword of Light"})

    def test_show_entry(self):
        intent = detect_intent("show entry Mary")
        assert intent == Intent("open_entry", {"name": "Mary"})

    def test_view_entry(self):
        intent = detect_intent("view psyke Palazzo")
        assert intent == Intent("open_entry", {"name": "Palazzo"})

    def test_open_generic_number(self):
        intent = detect_intent("open 5")
        assert intent == Intent("open_scene", {"id": 5})

    def test_open_generic_name(self):
        intent = detect_intent("open John")
        assert intent == Intent("open_entry", {"name": "John"})

    def test_case_insensitive(self):
        intent = detect_intent("OPEN SCENE 7")
        assert intent == Intent("open_scene", {"id": 7})


class TestCreateIntents:
    def test_create_character(self):
        intent = detect_intent("create character john")
        assert intent == Intent("create_entry", {"entry_type": "character", "name": "john"})

    def test_create_place(self):
        intent = detect_intent("create place The Dark Forest")
        assert intent == Intent("create_entry", {"entry_type": "place", "name": "The Dark Forest"})

    def test_new_object(self):
        intent = detect_intent("new object Sword of Light")
        assert intent == Intent("create_entry", {"entry_type": "object", "name": "Sword of Light"})

    def test_add_theme(self):
        intent = detect_intent("add theme Redemption")
        assert intent == Intent("create_entry", {"entry_type": "theme", "name": "Redemption"})

    def test_create_type_no_name(self):
        intent = detect_intent("create character")
        assert intent == Intent("create_entry", {"entry_type": "character", "name": ""})

    def test_create_generic_falls_back(self):
        intent = detect_intent("create something weird")
        assert intent is not None
        assert intent.action == "create_entry"
        assert intent.args["entry_type"] == "other"
        assert intent.args["name"] == "something weird"
        assert intent.confidence < 1.0

    def test_create_lore(self):
        intent = detect_intent("new lore Ancient Prophecy")
        assert intent == Intent("create_entry", {"entry_type": "lore", "name": "Ancient Prophecy"})


class TestNavigationIntents:
    def test_go_to_next_scene(self):
        intent = detect_intent("go to next scene")
        assert intent == Intent("go_scene", {"direction": "next"})

    def test_goto_previous(self):
        intent = detect_intent("goto previous scene")
        assert intent == Intent("go_scene", {"direction": "previous"})

    def test_go_scene_next(self):
        intent = detect_intent("go scene next")
        assert intent == Intent("go_scene", {"direction": "next"})

    def test_go_prev(self):
        intent = detect_intent("go to prev")
        assert intent == Intent("go_scene", {"direction": "previous"})

    def test_go_to_scene_id(self):
        intent = detect_intent("go to scene 5")
        assert intent == Intent("go_scene", {"id": 5})

    def test_goto_scene_id(self):
        intent = detect_intent("goto scene 12")
        assert intent == Intent("go_scene", {"id": 12})

    def test_next_scene_shorthand(self):
        intent = detect_intent("next scene")
        assert intent == Intent("go_scene", {"direction": "next"})

    def test_previous_scene_shorthand(self):
        intent = detect_intent("previous scene")
        assert intent == Intent("go_scene", {"direction": "previous"})

    def test_prev_scene_shorthand(self):
        intent = detect_intent("prev scene")
        assert intent == Intent("go_scene", {"direction": "previous"})


class TestInsertIntents:
    def test_insert_entity(self):
        intent = detect_intent("insert john")
        assert intent == Intent("insert_entity", {"name": "john"})

    def test_insert_multi_word(self):
        intent = detect_intent("insert Sword of Light")
        assert intent == Intent("insert_entity", {"name": "Sword of Light"})

    def test_mention_entity(self):
        intent = detect_intent("mention Mary")
        assert intent is not None
        assert intent.action == "insert_entity"
        assert intent.args["name"] == "Mary"

    def test_use_entity_here(self):
        intent = detect_intent("use john here")
        assert intent is not None
        assert intent.action == "insert_entity"
        assert intent.args["name"] == "john"


class TestAiIntents:
    def test_rewrite(self):
        intent = detect_intent("rewrite")
        assert intent is not None
        assert intent.action == "ai_action"
        assert intent.args["action"] == "rewrite"

    def test_expand(self):
        intent = detect_intent("expand")
        assert intent is not None
        assert intent.action == "ai_action"
        assert intent.args["action"] == "expand"

    def test_summarize(self):
        intent = detect_intent("summarize")
        assert intent is not None
        assert intent.action == "ai_action"
        assert intent.args["action"] == "summarize"

    def test_ai_prefix(self):
        intent = detect_intent("ai rewrite")
        assert intent is not None
        assert intent.action == "ai_action"
        assert intent.args["action"] == "rewrite"

    def test_make_shorter(self):
        intent = detect_intent("make it shorter")
        assert intent is not None
        assert intent.action == "ai_action"
        assert intent.args["action"] == "condense"

    def test_make_longer(self):
        intent = detect_intent("make this longer")
        assert intent is not None
        assert intent.action == "ai_action"
        assert intent.args["action"] == "expand"

    def test_make_clearer(self):
        intent = detect_intent("make it clearer")
        assert intent is not None
        assert intent.action == "ai_action"
        assert intent.args["action"] == "rewrite"


class TestDeleteRenameIntents:
    def test_delete_entity(self):
        intent = detect_intent("delete John")
        assert intent == Intent("delete_entry", {"name": "John"})

    def test_remove_entity(self):
        intent = detect_intent("remove entry Old Character")
        assert intent == Intent("delete_entry", {"name": "Old Character"})

    def test_rename_entity(self):
        intent = detect_intent("rename John to Jonathan")
        assert intent == Intent("rename_entry", {"name": "John", "new_name": "Jonathan"})

    def test_rename_with_as(self):
        intent = detect_intent("rename Old Name as New Name")
        assert intent == Intent("rename_entry", {"name": "Old Name", "new_name": "New Name"})


class TestEdgeCases:
    def test_empty_string(self):
        assert detect_intent("") is None

    def test_whitespace_only(self):
        assert detect_intent("   ") is None

    def test_no_match(self):
        assert detect_intent("hello world") is None

    def test_random_text(self):
        assert detect_intent("the weather is nice") is None

    def test_partial_keyword(self):
        assert detect_intent("ope scene 3") is None

    def test_preserves_whitespace_in_names(self):
        intent = detect_intent("create character  John Doe")
        assert intent is not None
        assert intent.args["name"] == "John Doe"

    def test_confidence_on_ambiguous(self):
        intent = detect_intent("add something")
        assert intent is not None
        assert intent.confidence < 1.0
