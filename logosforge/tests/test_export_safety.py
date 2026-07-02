"""Part 5 — Export / backup basic safety.

Export is strictly project-scoped (no other-project data), carries no API
keys, and includes the Outline (Acts/Chapters/Scenes). Backup builders produce
import-compatible, recoverable data for the active project only.
"""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.export import export_json


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def test_export_is_active_project_only_no_cross_leak():
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    b = db.create_project("B", narrative_engine="novel").id
    db.create_scene(a, "A-scene", act="Act I", chapter="Ch1",
                    content="PROJECT_A_BODY_SENTINEL")
    db.create_scene(b, "B-scene", content="PROJECT_B_BODY_SENTINEL")
    db.create_psyke_entry(b, "B_PSYKE_SENTINEL", "character")

    blob = export_json(db, a)

    assert "PROJECT_A_BODY_SENTINEL" in blob
    assert "PROJECT_B_BODY_SENTINEL" not in blob   # no other-project prose
    assert "B_PSYKE_SENTINEL" not in blob          # no other-project PSYKE


def test_export_contains_no_api_keys():
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    db.create_scene(a, "S", content="text")
    # Even if a provider secret is stashed in app settings, project export
    # must never serialize it.
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "sk-SECRET_SHOULD_NOT_EXPORT")

    blob = export_json(db, a)

    assert "sk-SECRET_SHOULD_NOT_EXPORT" not in blob
    assert "ai_api_key" not in blob
    assert "api_key" not in blob


def test_export_includes_outline_acts_chapters_scenes():
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    db.create_scene(a, "Opening", act="Act I", chapter="Chapter One",
                    content="body")

    data = json.loads(export_json(db, a))
    scenes = data.get("scenes", [])

    assert scenes, "export should include scenes"
    s = scenes[0]
    assert s.get("act") == "Act I"
    assert s.get("chapter") == "Chapter One"
    assert s.get("title") == "Opening"


def test_full_project_backup_is_import_compatible():
    from logosforge.data_export import build_full_export
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    db.create_scene(a, "S", act="Act I", content="recover me")
    db.create_psyke_entry(a, "Hero", "character")

    payload = build_full_export(db, a)

    # Recoverable: carries the data needed to reconstruct the project.
    text = json.dumps(payload)
    assert "recover me" in text
    assert "Hero" in text
