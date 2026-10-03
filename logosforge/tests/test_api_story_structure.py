"""HTTP contract for the canonical Act -> Chapter -> Scene projection."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from logosforge.api.app import create_api  # noqa: E402
from logosforge.api.config import ApiConfig  # noqa: E402
from logosforge.db import Database  # noqa: E402


def _project(*, engine: str = "novel"):
    db = Database()
    project = db.create_project(
        "Structure",
        narrative_engine=engine,
        default_writing_format=engine,
    )
    client = TestClient(create_api(db=db, config=ApiConfig(mode="desktop")))
    return client, db, project.id


def _flatten(body: dict) -> list[dict]:
    return [
        scene
        for act in body["acts"]
        for chapter in act["chapters"]
        for scene in chapter["scenes"]
    ]


def test_empty_story_structure_is_typed_and_mode_aware():
    client, _db, project_id = _project()

    response = client.get(f"/api/projects/{project_id}/story-structure")

    assert response.status_code == 200
    body = response.json()
    assert len(body.pop("revision")) == 64
    assert body == {
        "project_id": project_id,
        "chapter_level": True,
        "scene_count": 0,
        "orphan_count": 0,
        "acts": [],
    }


def test_story_structure_uses_canonical_order_numbers_and_trimmed_groups():
    client, db, project_id = _project()
    loose = db.create_scene(
        project_id, "Loose", content="private orphan prose", beat="Loose beat",
    )
    first = db.create_scene(
        project_id, "First", act="  Act II  ", chapter=" Chapter B ",
        beat="Opening Image", content="private first prose",
    )
    other_act = db.create_scene(
        project_id, "Other act", act="Act I", chapter="Chapter A",
        content="private other prose",
    )
    other_chapter = db.create_scene(
        project_id, "Other chapter", act="Act II", chapter="Chapter C",
        content="private chapter prose",
    )
    regrouped = db.create_scene(
        project_id, "Regrouped", act=" Act II ", chapter="  Chapter B  ",
        content="private regrouped prose",
    )

    response = client.get(f"/api/projects/{project_id}/story-structure")
    body = response.json()

    assert body["chapter_level"] is True
    assert body["scene_count"] == 5
    assert body["orphan_count"] == 1
    assert [act["name"] for act in body["acts"]] == ["Act II", "Act I", "Unassigned"]
    assert [act["number"] for act in body["acts"]] == ["1", "2", ""]
    assert [chapter["name"] for chapter in body["acts"][0]["chapters"]] == [
        "Chapter B", "Chapter C",
    ]
    assert [chapter["number"] for chapter in body["acts"][0]["chapters"]] == [
        "1.1", "1.2",
    ]
    assert body["acts"][0]["scene_count"] == 3
    assert body["acts"][0]["chapters"][0]["scene_count"] == 2

    flattened = _flatten(body)
    assert [scene["id"] for scene in flattened] == [
        first.id, regrouped.id, other_chapter.id, other_act.id, loose.id,
    ]
    assert [scene["order_index"] for scene in flattened] == [1, 2, 3, 4, 5]
    assert [scene["number"] for scene in flattened] == [
        "1.1.1", "1.1.2", "1.2.1", "2.1.1", "",
    ]
    assert [scene["is_orphan"] for scene in flattened] == [
        False, False, False, False, True,
    ]
    assert body["acts"][-1]["unassigned"] is True
    assert body["acts"][-1]["chapters"][-1]["unassigned"] is True
    assert flattened[0]["beat"] == "Opening Image"

    # Navigation data stays compact: no manuscript body or write revision leaks.
    assert set(flattened[0]) == {
        "id", "title", "beat", "number", "order_index", "is_orphan",
        "episode_id",
    }
    assert "private" not in response.text
    assert all("revision" not in scene for scene in flattened)


def test_non_novel_scene_numbers_flatten_across_canonical_chapter_groups():
    client, db, project_id = _project(engine="screenplay")
    first = db.create_scene(project_id, "A1", act="Act I", chapter="Chapter A")
    later_chapter = db.create_scene(project_id, "B1", act="Act I", chapter="Chapter B")
    regrouped = db.create_scene(project_id, "A2", act="Act I", chapter="Chapter A")

    body = client.get(f"/api/projects/{project_id}/story-structure").json()
    flattened = _flatten(body)

    assert body["chapter_level"] is False
    assert [scene["id"] for scene in flattened] == [
        first.id, regrouped.id, later_chapter.id,
    ]
    assert [scene["number"] for scene in flattened] == ["1.1", "1.2", "1.3"]
    assert [chapter["number"] for chapter in body["acts"][0]["chapters"]] == [
        "1.1", "1.2",
    ]


def test_story_structure_is_independent_from_planning_outline():
    client, db, project_id = _project()
    scene = db.create_scene(
        project_id, "Manuscript scene", act="Manuscript Act", chapter="Manuscript Chapter",
    )
    outline_act = db.create_outline_node(project_id, "Outline-only Act")
    db.create_outline_node(
        project_id, "Outline-only Scene", parent_id=outline_act.id, scene_id=scene.id,
    )

    body = client.get(f"/api/projects/{project_id}/story-structure").json()

    assert [act["name"] for act in body["acts"]] == ["Manuscript Act"]
    assert body["acts"][0]["chapters"][0]["name"] == "Manuscript Chapter"
    assert _flatten(body)[0]["title"] == "Manuscript scene"
    assert "Outline-only" not in str(body)


def test_story_structure_is_project_isolated_and_missing_project_is_404():
    client, db, project_id = _project()
    other_id = db.create_project("Other", narrative_engine="novel").id
    owned = db.create_scene(project_id, "Owned", act="Act I", chapter="Chapter I")
    db.create_scene(other_id, "Foreign", act="Foreign Act", chapter="Foreign Chapter")

    body = client.get(f"/api/projects/{project_id}/story-structure").json()

    assert [scene["id"] for scene in _flatten(body)] == [owned.id]
    assert "Foreign" not in str(body)
    assert client.get("/api/projects/999999/story-structure").status_code == 404


def test_story_structure_reflects_the_next_committed_scene_patch():
    client, _db, project_id = _project()
    created = client.post(
        f"/api/projects/{project_id}/scenes",
        json={
            "title": "Before",
            "act": "Act I",
            "chapter": "Chapter I",
            "beat": "Setup",
            "content": "private prose",
        },
    ).json()

    patched = client.patch(
        f"/api/projects/{project_id}/scenes/{created['id']}",
        json={
            "title": "After",
            "act": "Act II",
            "chapter": "Chapter II",
            "beat": "Midpoint",
            "expected_revision": created["revision"],
        },
    )
    assert patched.status_code == 200

    body = client.get(f"/api/projects/{project_id}/story-structure").json()
    scene = _flatten(body)[0]
    assert body["acts"][0]["name"] == "Act II"
    assert body["acts"][0]["chapters"][0]["name"] == "Chapter II"
    assert scene == {
        "id": created["id"],
        "title": "After",
        "beat": "Midpoint",
        "number": "1.1.1",
        "order_index": 1,
        "is_orphan": False,
        "episode_id": None,
    }
