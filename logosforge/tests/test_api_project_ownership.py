"""Project-scoped API routes must reject foreign resources and link targets."""
from __future__ import annotations

from fastapi.testclient import TestClient

from logosforge.api import create_api
from logosforge.db import Database


def test_cross_project_links_and_nested_resources_are_rejected() -> None:
    db = Database()
    owner = db.create_project("Owner")
    other = db.create_project("Other")

    owner_scene = db.create_scene(owner.id, "Owner scene")
    owner_character = db.create_character(owner.id, "Owner character")
    owner_place = db.create_place(owner.id, "Owner place")
    owner_entry = db.create_psyke_entry(owner.id, "Owner entry", "object")
    owner_progression = db.create_psyke_progression(
        owner_entry.id, "Owner beat", scene_id=owner_scene.id,
    )
    owner_memory = db.add_memory(
        owner.id, owner_scene.id, "continuity_prop", "Key", "Pocket",
    )
    owner_parent = db.create_outline_node(owner.id, "Owner parent")

    other_scene = db.create_scene(other.id, "Other scene")
    other_note = db.create_note(other.id, "Other note")
    other_entry = db.create_psyke_entry(other.id, "Other entry", "object")
    other_theme = db.create_psyke_entry(other.id, "Other theme", "theme")
    other_node = db.create_outline_node(other.id, "Other node")
    other_progression = db.create_psyke_progression(other_entry.id, "Other beat")
    db.set_theme_scenes(other_theme.id, [other_scene.id])

    client = TestClient(create_api(db=db))
    root = f"/api/projects/{other.id}"
    attempts = [
        client.post(
            f"{root}/notes/{other_note.id}/scene-links/{owner_scene.id}",
        ),
        client.delete(
            f"{root}/notes/{other_note.id}/scene-links/{owner_scene.id}",
        ),
        client.post(
            f"{root}/notes/{other_note.id}/psyke-links/{owner_entry.id}",
        ),
        client.delete(
            f"{root}/notes/{other_note.id}/psyke-links/{owner_entry.id}",
        ),
        client.post(
            f"{root}/outline/nodes",
            json={"title": "Bad child", "parent_id": owner_parent.id},
        ),
        client.post(
            f"{root}/outline/nodes",
            json={"title": "Bad link", "scene_id": owner_scene.id},
        ),
        client.patch(
            f"{root}/outline/nodes/{other_node.id}",
            json={"scene_id": owner_scene.id},
        ),
        client.post(
            f"{root}/scenes",
            json={"title": "Bad cast", "character_ids": [owner_character.id]},
        ),
        client.post(
            f"{root}/scenes",
            json={"title": "Bad place", "place_ids": [owner_place.id]},
        ),
        client.patch(
            f"{root}/scenes/{other_scene.id}/continuity/{owner_memory.id}",
            json={"target": "Stolen", "value": "Changed"},
        ),
        client.delete(
            f"{root}/scenes/{other_scene.id}/continuity/{owner_memory.id}",
        ),
        client.post(
            f"{root}/psyke/progressions",
            json={
                "entry_id": other_entry.id,
                "text": "Bad scene",
                "scene_id": owner_scene.id,
            },
        ),
        client.patch(
            f"{root}/psyke/progressions/{owner_progression.id}",
            json={"text": "Stolen"},
        ),
        client.delete(
            f"{root}/psyke/progressions/{owner_progression.id}",
        ),
        client.patch(
            f"{root}/psyke/progressions/{other_progression.id}",
            json={"text": "Bad scene", "scene_id": owner_scene.id},
        ),
        client.put(
            f"{root}/themes/{other_theme.id}/scenes",
            json={"scene_ids": [owner_scene.id]},
        ),
    ]

    assert all(response.status_code == 404 for response in attempts)
    assert db.get_note_scene_links(other_note.id) == []
    assert db.get_note_psyke_links(other_note.id) == []
    assert db.get_outline_node_by_id(other_node.id).scene_id is None
    assert db.get_story_memory_by_id(owner_memory.id).target == "Key"
    assert db.get_psyke_progression_by_id(owner_progression.id) is not None
    assert db.get_psyke_progression_by_id(other_progression.id).scene_id is None
    assert db.get_theme_scene_ids(other_theme.id) == [other_scene.id]


def test_same_project_links_and_nested_resources_still_work() -> None:
    db = Database()
    project = db.create_project("Project")
    scene = db.create_scene(project.id, "Scene")
    character = db.create_character(project.id, "Character")
    place = db.create_place(project.id, "Place")
    entry = db.create_psyke_entry(project.id, "Object", "object")
    theme = db.create_psyke_entry(project.id, "Theme", "theme")
    note = db.create_note(project.id, "Note")
    parent = db.create_outline_node(project.id, "Parent")

    client = TestClient(create_api(db=db))
    root = f"/api/projects/{project.id}"

    responses = [
        client.post(f"{root}/notes/{note.id}/scene-links/{scene.id}"),
        client.post(f"{root}/notes/{note.id}/psyke-links/{entry.id}"),
        client.post(
            f"{root}/outline/nodes",
            json={"title": "Child", "parent_id": parent.id, "scene_id": scene.id},
        ),
        client.post(
            f"{root}/scenes",
            json={
                "title": "Linked scene",
                "character_ids": [character.id],
                "place_ids": [place.id],
            },
        ),
        client.post(
            f"{root}/psyke/progressions",
            json={"entry_id": entry.id, "text": "Beat", "scene_id": scene.id},
        ),
        client.put(
            f"{root}/themes/{theme.id}/scenes",
            json={"scene_ids": [scene.id]},
        ),
    ]

    assert [response.status_code for response in responses] == [200, 200, 201, 201, 201, 200]


def test_ai_context_and_extraction_are_project_scoped() -> None:
    db = Database()
    owner = db.create_project("Owner")
    other = db.create_project("Other")
    owner_scene = db.create_scene(owner.id, "Private scene")
    owner_character = db.create_character(owner.id, "Private character")
    owner_entry = db.create_psyke_entry(owner.id, "Private entry", "object")
    owner_entry_2 = db.create_psyke_entry(owner.id, "Private entry 2", "object")
    owner_node = db.create_outline_node(owner.id, "Private node")

    client = TestClient(create_api(db=db))
    root = f"/api/projects/{other.id}"
    attempts = [
        client.post(
            f"{root}/assistant/chat",
            json={"message": "Read it", "active_scene_id": owner_scene.id},
        ),
        client.post(
            f"{root}/logos/run",
            json={"action": "sp_scene_health", "current_scene_id": owner_scene.id},
        ),
        client.post(
            f"{root}/logos/run",
            json={"action": "sp_scene_health", "current_timeline_event_id": owner_scene.id},
        ),
        client.post(
            f"{root}/logos/run",
            json={"action": "sp_scene_health", "current_outline_node_id": owner_node.id},
        ),
        client.post(
            f"{root}/logos/run",
            json={"action": "sp_scene_health", "current_psyke_entry_id": owner_entry.id},
        ),
        client.post(
            f"{root}/quantum/outline",
            json={"premise": "Read it", "source_scene_id": owner_scene.id},
        ),
        client.post(
            f"{root}/quantum/branches",
            json={"situation": "Read it", "source_scene_id": owner_scene.id},
        ),
        client.post(
            f"{root}/extract/apply",
            json={"scenes": [{"scene_id": owner_scene.id}]},
        ),
        client.post(
            f"{root}/extract/revert",
            json={"character_ids": [owner_character.id]},
        ),
        client.post(
            f"{root}/extract/revert",
            json={"links": [[owner_scene.id, owner_character.id]]},
        ),
        client.post(
            f"{root}/extract/revert",
            json={"wkw_scene_ids": [owner_scene.id]},
        ),
        client.post(
            f"{root}/extract/revert",
            json={"psyke_ids": [owner_entry.id]},
        ),
        client.post(
            f"{root}/extract/revert",
            json={
                "relations": [{
                    "source_id": owner_entry.id,
                    "target_id": owner_entry_2.id,
                    "rel_type": "thematic_echo",
                }],
            },
        ),
    ]
    assert all(response.status_code == 404 for response in attempts)

    started = client.post(f"/api/projects/{owner.id}/extract?use_llm=false")
    assert started.status_code == 200
    job_id = started.json()["job_id"]
    assert client.get(f"{root}/extract/jobs/{job_id}").status_code == 404
    assert client.delete(f"{root}/extract/jobs/{job_id}").status_code == 404

    assert db.get_scene_by_id(owner_scene.id) is not None
    assert db.get_character_by_id(owner_character.id) is not None
    assert db.get_psyke_entry_by_id(owner_entry.id) is not None


def test_legacy_cross_project_links_are_not_exposed() -> None:
    """Defensive serializers hide malformed links written by older builds."""
    db = Database()
    owner = db.create_project("Owner")
    other = db.create_project("Other")
    foreign_scene = db.create_scene(other.id, "Foreign scene")
    foreign_character = db.create_character(other.id, "Foreign character")
    foreign_place = db.create_place(other.id, "Foreign place")
    foreign_entry = db.create_psyke_entry(other.id, "Foreign entry", "object")
    foreign_parent = db.create_outline_node(other.id, "Foreign parent")

    scene = db.create_scene(
        owner.id, "Owner scene",
        character_ids=[foreign_character.id], place_ids=[foreign_place.id],
    )
    note = db.create_note(owner.id, "Owner note")
    db.link_note_to_scene(note.id, foreign_scene.id)
    db.link_note_to_psyke(note.id, foreign_entry.id)
    db.create_outline_node(
        owner.id, "Owner orphan", parent_id=foreign_parent.id,
        scene_id=foreign_scene.id,
    )
    owner_entry = db.create_psyke_entry(owner.id, "Owner entry", "object")
    db.create_psyke_progression(owner_entry.id, "Beat", scene_id=foreign_scene.id)
    db.add_psyke_relation(owner_entry.id, foreign_entry.id, "thematic_echo")
    character = db.create_character(owner.id, "Owner character")
    db.set_character_psyke_entry(character.id, foreign_entry.id)
    theme = db.create_psyke_entry(owner.id, "Owner theme", "theme")
    db.set_theme_scenes(theme.id, [foreign_scene.id])

    client = TestClient(create_api(db=db))
    root = f"/api/projects/{owner.id}"

    scene_dto = client.get(f"{root}/scenes/{scene.id}").json()
    assert scene_dto["character_ids"] == []
    assert scene_dto["place_ids"] == []

    note_dto = client.get(f"{root}/notes").json()[0]
    assert note_dto["scene_links"] == []
    assert note_dto["psyke_links"] == []

    outline = client.get(f"{root}/outline").json()
    assert len(outline) == 1
    assert outline[0]["parent_id"] is None
    assert outline[0]["scene_id"] is None

    progression = client.get(f"{root}/psyke/progressions").json()[0]
    assert progression["scene_id"] is None
    assert client.get(f"{root}/psyke/relations").json() == []

    characters = client.get(f"{root}/characters").json()
    owner_character_dto = next(row for row in characters if row["id"] == character.id)
    assert owner_character_dto["psyke_entry_id"] is None
    assert client.get(f"{root}/themes/{theme.id}/scenes").json()["scene_ids"] == []
