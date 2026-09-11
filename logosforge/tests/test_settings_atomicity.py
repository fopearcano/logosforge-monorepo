from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os

from logosforge import settings


def test_group_update_is_persisted_as_one_valid_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    manager = settings.SettingsManager()

    assert manager.update({"ai_provider": "OpenRouter", "ai_model": "openrouter/auto"})
    stored = json.loads(settings.SETTINGS_FILE.read_text(encoding="utf-8"))
    assert stored["ai_provider"] == "OpenRouter"
    assert stored["ai_model"] == "openrouter/auto"


def test_concurrent_updates_do_not_lose_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    manager = settings.SettingsManager()

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(
            lambda index: manager.set(f"concurrent_{index}", index),
            range(36),
        ))

    assert all(results)
    stored = json.loads(settings.SETTINGS_FILE.read_text(encoding="utf-8"))
    assert {f"concurrent_{index}": stored[f"concurrent_{index}"] for index in range(36)} == {
        f"concurrent_{index}": index for index in range(36)
    }


def test_failed_replace_rolls_back_memory_and_leaves_valid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    manager = settings.SettingsManager()
    assert manager.set("ai_model", "stable-model")
    before = settings.SETTINGS_FILE.read_bytes()
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk full")))

    assert manager.set("ai_model", "lost-model") is False
    assert manager.get("ai_model") == "stable-model"
    assert settings.SETTINGS_FILE.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_get_returns_a_copy_of_mutable_values(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    manager = settings.SettingsManager()
    assert manager.set("connector_disabled_actions", ["delete_scene"])

    returned = manager.get("connector_disabled_actions")
    assert isinstance(returned, list)
    returned.append("delete_project")
    assert manager.get("connector_disabled_actions") == ["delete_scene"]
    snapshot = manager.snapshot()
    snapshot["connector_disabled_actions"].append("delete_project")
    assert manager.get("connector_disabled_actions") == ["delete_scene"]
