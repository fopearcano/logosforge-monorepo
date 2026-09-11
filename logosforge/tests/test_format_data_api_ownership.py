"""Format-data routes must never read or mutate another project's rows."""
from __future__ import annotations

from fastapi.testclient import TestClient

from logosforge.api import create_api
from logosforge.db import Database


def test_cross_project_format_rows_are_rejected() -> None:
    db = Database()
    owner = db.create_project("Owner", narrative_engine="series")
    other = db.create_project("Other", narrative_engine="series")

    page = db.create_gn_page(owner.id)
    panel = db.create_gn_panel(page.id, project_id=owner.id)
    item = db.create_gn_continuity_item(owner.id, "Coat")
    appearance = db.add_gn_continuity_appearance(item.id, page_id=page.id, panel_id=panel.id)
    scene = db.create_scene(owner.id, "Stage scene")
    entrance = db.create_stage_entrance_exit(scene.id)
    cue = db.create_stage_cue(scene.id)
    business = db.create_stage_business(scene.id)
    season = db.create_season(owner.id)
    episode = db.create_episode(season.id, project_id=owner.id)
    arc = db.create_series_arc(owner.id, title="Arc")
    plotline = db.create_episode_plotline(episode.id, title="A story")

    client = TestClient(create_api(db=db))
    root = f"/api/projects/{other.id}"
    attempts = [
        client.get(f"{root}/gn/pages/{page.id}/panels"),
        client.post(f"{root}/gn/pages/{page.id}/panels", json={}),
        client.patch(f"{root}/gn/pages/{page.id}", json={"summary": "stolen"}),
        client.delete(f"{root}/gn/pages/{page.id}"),
        client.patch(f"{root}/gn/panels/{panel.id}", json={"description": "stolen"}),
        client.delete(f"{root}/gn/panels/{panel.id}"),
        client.get(f"{root}/gn/continuity-items/{item.id}/appearances"),
        client.post(f"{root}/gn/continuity-items/{item.id}/appearances", json={}),
        client.patch(f"{root}/gn/continuity-items/{item.id}", json={"name": "stolen"}),
        client.delete(f"{root}/gn/continuity-items/{item.id}"),
        client.patch(f"{root}/gn/continuity-appearances/{appearance.id}", json={}),
        client.delete(f"{root}/gn/continuity-appearances/{appearance.id}"),
        client.get(f"{root}/stage/scenes/{scene.id}/entrances"),
        client.post(f"{root}/stage/scenes/{scene.id}/entrances", json={}),
        client.get(f"{root}/stage/scenes/{scene.id}/cues"),
        client.post(f"{root}/stage/scenes/{scene.id}/cues", json={}),
        client.get(f"{root}/stage/scenes/{scene.id}/business"),
        client.post(f"{root}/stage/scenes/{scene.id}/business", json={}),
        client.patch(f"{root}/stage/entrances/{entrance.id}", json={}),
        client.delete(f"{root}/stage/entrances/{entrance.id}"),
        client.patch(f"{root}/stage/cues/{cue.id}", json={}),
        client.delete(f"{root}/stage/cues/{cue.id}"),
        client.delete(f"{root}/stage/business/{business.id}"),
        client.post(f"{root}/series/seasons/{season.id}/episodes", json={}),
        client.patch(f"{root}/series/seasons/{season.id}", json={}),
        client.delete(f"{root}/series/seasons/{season.id}"),
        client.patch(f"{root}/series/episodes/{episode.id}", json={}),
        client.delete(f"{root}/series/episodes/{episode.id}"),
        client.patch(f"{root}/series/arcs/{arc.id}", json={}),
        client.delete(f"{root}/series/arcs/{arc.id}"),
        client.get(f"{root}/series/episodes/{episode.id}/plotlines"),
        client.post(f"{root}/series/episodes/{episode.id}/plotlines", json={}),
        client.patch(f"{root}/series/plotlines/{plotline.id}", json={}),
        client.delete(f"{root}/series/plotlines/{plotline.id}"),
    ]

    assert all(response.status_code == 404 for response in attempts)
    assert db.get_gn_page_by_id(page.id) is not None
    assert db.get_gn_panel_by_id(panel.id) is not None
    assert db.get_gn_continuity_item_by_id(item.id) is not None
    assert db.get_gn_continuity_appearance_by_id(appearance.id) is not None
    assert db.get_stage_entrance_exit_by_id(entrance.id) is not None
    assert db.get_stage_cue_by_id(cue.id) is not None
    assert db.get_stage_business_by_id(business.id) is not None
    assert db.get_season_by_id(season.id) is not None
    assert db.get_episode_by_id(episode.id) is not None
    assert db.get_series_arc_by_id(arc.id) is not None
    assert db.get_episode_plotline_by_id(plotline.id) is not None


def test_cross_project_foreign_links_are_rejected() -> None:
    db = Database()
    owner = db.create_project("Owner")
    other = db.create_project("Other")
    page = db.create_gn_page(owner.id)
    panel = db.create_gn_panel(page.id, project_id=owner.id)
    entry = db.create_psyke_entry(owner.id, "Foreign", "object")
    character = db.create_character(owner.id, "Foreign character")
    scene = db.create_scene(other.id, "Other scene")
    item = db.create_gn_continuity_item(other.id, "Other item")

    client = TestClient(create_api(db=db))
    root = f"/api/projects/{other.id}"
    attempts = [
        client.post(
            f"{root}/gn/continuity-items",
            json={"name": "Bad", "linked_psyke_entry_id": entry.id},
        ),
        client.post(
            f"{root}/gn/continuity-items/{item.id}/appearances",
            json={"page_id": page.id, "panel_id": panel.id},
        ),
        client.post(
            f"{root}/stage/scenes/{scene.id}/entrances",
            json={"character_id": character.id},
        ),
        client.post(
            f"{root}/stage/scenes/{scene.id}/business",
            json={"prop_psyke_entry_id": entry.id, "character_id": character.id},
        ),
    ]
    assert all(response.status_code == 404 for response in attempts)


def test_nullable_format_links_can_be_cleared_and_panel_page_stays_consistent() -> None:
    db = Database()
    project = db.create_project("Project", narrative_engine="series")
    page_1 = db.create_gn_page(project.id)
    page_2 = db.create_gn_page(project.id)
    panel_1 = db.create_gn_panel(page_1.id, project_id=project.id)
    panel_2 = db.create_gn_panel(page_2.id, project_id=project.id)
    entry = db.create_psyke_entry(project.id, "Prop", "object")
    item = db.create_gn_continuity_item(
        project.id, "Prop", linked_psyke_entry_id=entry.id,
    )
    appearance = db.add_gn_continuity_appearance(
        item.id, page_id=page_1.id, panel_id=panel_1.id,
    )
    scene = db.create_scene(project.id, "Scene")
    character = db.create_character(project.id, "Character")
    entrance = db.create_stage_entrance_exit(scene.id, character_id=character.id)
    season = db.create_season(project.id)
    episode = db.create_episode(season.id, project_id=project.id)
    arc = db.create_series_arc(project.id, title="Arc", setup_episode_id=episode.id)

    client = TestClient(create_api(db=db))
    root = f"/api/projects/{project.id}"

    mismatch = client.patch(
        f"{root}/gn/continuity-appearances/{appearance.id}",
        json={"panel_id": panel_2.id},
    )
    assert mismatch.status_code == 404
    assert db.get_gn_continuity_appearance_by_id(appearance.id).panel_id == panel_1.id

    clears = [
        client.patch(
            f"{root}/gn/continuity-appearances/{appearance.id}",
            json={"panel_id": None},
        ),
        client.patch(
            f"{root}/gn/continuity-items/{item.id}",
            json={"linked_psyke_entry_id": None},
        ),
        client.patch(
            f"{root}/stage/entrances/{entrance.id}",
            json={"character_id": None},
        ),
        client.patch(
            f"{root}/series/arcs/{arc.id}",
            json={"setup_episode_id": None},
        ),
    ]
    assert all(response.status_code == 200 for response in clears)
    assert db.get_gn_continuity_appearance_by_id(appearance.id).panel_id is None
    assert db.get_gn_continuity_item_by_id(item.id).linked_psyke_entry_id is None
    assert db.get_stage_entrance_exit_by_id(entrance.id).character_id is None
    assert db.get_series_arc_by_id(arc.id).setup_episode_id is None
