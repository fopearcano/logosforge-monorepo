"""Project imports are all-or-nothing at their project/scene boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from logosforge import manuscript_import, whiteboard_import
from logosforge.api.app import create_api
from logosforge.db import Database


def _fail_on_second_scene(db: Database, monkeypatch) -> None:
    original = db.create_scene
    calls = 0

    def create_scene(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated scene write failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "create_scene", create_scene)


def test_whiteboard_import_removes_partial_project_on_scene_failure(monkeypatch) -> None:
    db = Database()
    existing = db.create_project("Existing project")
    _fail_on_second_scene(db, monkeypatch)

    with pytest.raises(RuntimeError, match="simulated scene write failure"):
        whiteboard_import.import_whiteboard_document(
            db,
            {
                "title": "Broken import",
                "mode": "novel",
                "blocks": [
                    {"id": "b1", "type": "heading", "text": "Chapter One"},
                    {"id": "b2", "type": "paragraph", "text": "Opening."},
                    {"id": "b3", "type": "heading", "text": "Chapter Two"},
                    {"id": "b4", "type": "paragraph", "text": "Later."},
                ],
            },
        )

    projects = db.get_all_projects()
    assert [(project.id, project.title) for project in projects] == [
        (existing.id, "Existing project"),
    ]
    assert db.get_all_scenes(existing.id) == []


def test_manuscript_import_removes_partial_project_on_scene_failure(monkeypatch) -> None:
    db = Database()
    existing = db.create_project("Existing project")
    _fail_on_second_scene(db, monkeypatch)

    with pytest.raises(RuntimeError, match="simulated scene write failure"):
        manuscript_import.import_manuscript_document(
            db,
            title="Broken manuscript",
            mode="novel",
            strategy="smart",
            filename="draft.md",
            data=b"# Chapter One\nOpening.\n\n# Chapter Two\nLater.",
        )

    projects = db.get_all_projects()
    assert [(project.id, project.title) for project in projects] == [
        (existing.id, "Existing project"),
    ]


def test_whiteboard_import_returns_complete_block_to_scene_map() -> None:
    db = Database()
    result = whiteboard_import.import_whiteboard_document(
        db,
        {
            "title": "Mapped import",
            "mode": "novel",
            "blocks": [
                {"id": "b1", "type": "paragraph", "text": "Preface."},
                {"id": "b2", "type": "heading", "text": "Chapter One"},
                {"id": "b3", "type": "paragraph", "text": "Opening."},
            ],
        },
    )

    assert result["scenes_created"] == 2
    assert len(result["scene_ids_by_block"]) == 3
    assert all(scene_id > 0 for scene_id in result["scene_ids_by_block"])
    assert result["scene_ids_by_block"][0] != result["scene_ids_by_block"][1]
    assert result["scene_ids_by_block"][1] == result["scene_ids_by_block"][2]


def test_whiteboard_import_api_returns_the_persisted_project_and_map() -> None:
    db = Database()
    client = TestClient(create_api(db=db))

    response = client.post(
        "/api/import/whiteboard",
        json={
            "title": "API graduation",
            "mode": "screenplay",
            "blocks": [
                {"id": "s1", "type": "paragraph", "text": "INT. LAB - NIGHT"},
                {"id": "s2", "type": "paragraph", "text": "Mara enters."},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    project = db.get_project_by_id(body["project_id"])
    assert project is not None
    assert project.title == "API graduation"
    assert body["mode"] == "screenplay"
    assert body["scenes_created"] == 1
    assert body["scene_ids_by_block"] == [body["scene_ids_by_block"][0]] * 2
    assert db.get_scene_by_id(body["scene_ids_by_block"][0]).project_id == project.id
