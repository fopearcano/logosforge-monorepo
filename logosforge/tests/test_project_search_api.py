"""Typed project search: relevance, isolation, validation, and wire shape."""

from __future__ import annotations

from fastapi.testclient import TestClient

from logosforge.api import create_api
from logosforge.api.config import ApiConfig
from logosforge.db import Database
from logosforge.project_search import MAX_EXCERPT_LENGTH


def _client(db: Database, *, token: str = "") -> TestClient:
    return TestClient(create_api(
        db=db,
        config=ApiConfig(mode="desktop", auth_token=token),
    ))


def _comment(db: Database, project_id: int, scene_id: int):
    return db.create_comment_with_replies(
        project_id,
        start_scene_id=scene_id,
        start_field="content",
        from_offset=0,
        end_scene_id=scene_id,
        end_field="content",
        to_offset=6,
        quote="Dragon",
        body="Track the fire motif",
        resolved=True,
        replies=[{"author": "Editor", "body": "Dragon continuity is deliberate"}],
    )


def test_search_returns_ranked_typed_matches_and_comment_metadata() -> None:
    db = Database()
    project = db.create_project("Search")
    scene = db.create_scene(
        project.id,
        "Dragon",
        content="The creature wakes.",
        offstage_events="A distant bell",
    )
    note = db.create_note(
        project.id,
        "Dragon ledger",
        content="Research notes",
        tags="creature, fire",
    )
    psyke = db.create_psyke_entry(
        project.id,
        "Wyrm",
        "character",
        aliases="Dragon",
        details={"motif": "fire"},
    )
    comment = _comment(db, project.id, scene.id)

    response = _client(db).get(
        f"/api/projects/{project.id}/search",
        params={"q": "  DRAGON  "},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "DRAGON"
    assert body["limit"] == 100
    assert [(row["kind"], row["id"]) for row in body["matches"]] == [
        ("scene", scene.id),
        ("comment", comment.id),
        ("psyke", psyke.id),
        ("note", note.id),
    ]

    comment_match = body["matches"][1]
    assert comment_match["resolved"] is True
    assert len(comment_match["revision"]) == 64
    for match in (body["matches"][0], body["matches"][2], body["matches"][3]):
        assert "revision" not in match
        assert "resolved" not in match


def test_search_repeated_kind_filter_is_strictly_project_scoped() -> None:
    db = Database()
    owner = db.create_project("Owner")
    other = db.create_project("Other")
    owner_scene = db.create_scene(owner.id, "Shared needle")
    owner_psyke = db.create_psyke_entry(owner.id, "Needle lore", "lore")
    owner_note = db.create_note(owner.id, "Needle note")
    owner_comment = db.create_comment_with_replies(
        owner.id,
        start_scene_id=owner_scene.id,
        start_field="content",
        from_offset=0,
        end_scene_id=owner_scene.id,
        end_field="content",
        to_offset=0,
        quote="Needle quote",
        body="Needle comment",
        resolved=False,
        replies=[],
    )
    other_scene = db.create_scene(other.id, "Foreign needle")
    db.create_psyke_entry(other.id, "Foreign needle", "lore")
    db.create_note(other.id, "Foreign needle")
    db.create_comment_with_replies(
        other.id,
        start_scene_id=other_scene.id,
        start_field="content",
        from_offset=0,
        end_scene_id=other_scene.id,
        end_field="content",
        to_offset=0,
        quote="Foreign needle",
        body="Foreign needle",
        resolved=False,
        replies=[],
    )

    response = _client(db).get(
        f"/api/projects/{owner.id}/search",
        params=[
            ("q", "needle"),
            ("kinds", "scene"),
            ("kinds", "note"),
            ("kinds", "psyke"),
            ("kinds", "comment"),
        ],
    )
    assert response.status_code == 200
    matches = response.json()["matches"]
    assert {(row["kind"], row["id"]) for row in matches} == {
        ("scene", owner_scene.id),
        ("note", owner_note.id),
        ("psyke", owner_psyke.id),
        ("comment", owner_comment.id),
    }
    assert {row["kind"] for row in matches} == {"scene", "note", "psyke", "comment"}
    assert all("Foreign" not in row["title"] for row in matches)


def test_search_ranking_limit_and_order_are_deterministic() -> None:
    db = Database()
    project = db.create_project("Ranking")
    exact = db.create_note(project.id, "needle")
    prefix = db.create_note(project.id, "needle prefix")
    db.create_note(project.id, "a needle inside")
    exact_content = db.create_note(project.id, "unrelated", content="needle")
    client = _client(db)
    params = [("q", "needle"), ("kinds", "note"), ("limit", "3")]

    first = client.get(f"/api/projects/{project.id}/search", params=params).json()
    second = client.get(f"/api/projects/{project.id}/search", params=params).json()
    # Exact matches outrank prefixes regardless of field; within the same
    # match class, a title match outranks a body match.
    expected = [exact.id, exact_content.id, prefix.id]
    assert [row["id"] for row in first["matches"]] == expected
    assert [row["id"] for row in second["matches"]] == expected
    assert first["limit"] == 3


def test_search_is_unicode_casefolded_and_excerpts_are_bounded_single_lines() -> None:
    db = Database()
    project = db.create_project("Unicode")
    scene = db.create_scene(
        project.id,
        "Long scene",
        content=("before " * 80) + "\nStraße\n" + ("after " * 80),
    )
    cjk = db.create_scene(project.id, "教堂场景")
    client = _client(db)

    folded = client.get(
        f"/api/projects/{project.id}/search",
        params=[("q", "STRASSE"), ("kinds", "scene")],
    ).json()["matches"]
    assert [row["id"] for row in folded] == [scene.id]
    assert "Straße" in folded[0]["excerpt"]
    assert "\n" not in folded[0]["excerpt"]
    assert len(folded[0]["excerpt"]) <= MAX_EXCERPT_LENGTH

    cjk_matches = client.get(
        f"/api/projects/{project.id}/search",
        params=[("q", "教堂"), ("kinds", "scene")],
    ).json()["matches"]
    assert [row["id"] for row in cjk_matches] == [cjk.id]


def test_search_normalizes_internal_query_whitespace_like_indexed_fields() -> None:
    db = Database()
    project = db.create_project("Whitespace")
    scene = db.create_scene(project.id, "Alpha\t  Beta", content="Elsewhere")

    response = _client(db).get(
        f"/api/projects/{project.id}/search",
        params=[("q", "Alpha\t  Beta"), ("kinds", "scene")],
    )

    assert response.status_code == 200
    assert [(row["kind"], row["id"]) for row in response.json()["matches"]] == [
        ("scene", scene.id),
    ]


def test_search_matches_canonically_equivalent_unicode() -> None:
    db = Database()
    project = db.create_project("Canonical Unicode")
    scene = db.create_scene(project.id, "Caf\u00e9 rendezvous")

    response = _client(db).get(
        f"/api/projects/{project.id}/search",
        params=[("q", "Cafe\u0301"), ("kinds", "scene")],
    )

    assert response.status_code == 200
    matches = response.json()["matches"]
    assert [(row["kind"], row["id"]) for row in matches] == [("scene", scene.id)]
    assert "Caf\u00e9" in matches[0]["excerpt"]


def test_search_matches_ids_and_generated_fallback_titles() -> None:
    db = Database()
    project = db.create_project("Identifiers")
    scene = db.create_scene(project.id, "")
    psyke = db.create_psyke_entry(project.id, "", "character")
    client = _client(db)

    scene_matches = client.get(
        f"/api/projects/{project.id}/search",
        params=[("q", str(scene.id)), ("kinds", "scene")],
    ).json()["matches"]
    psyke_matches = client.get(
        f"/api/projects/{project.id}/search",
        params=[("q", f"PSYKE entry {psyke.id}"), ("kinds", "psyke")],
    ).json()["matches"]

    assert [(row["id"], row["title"]) for row in scene_matches] == [
        (scene.id, f"Scene {scene.id}"),
    ]
    assert [(row["id"], row["title"]) for row in psyke_matches] == [
        (psyke.id, f"PSYKE entry {psyke.id}"),
    ]


def test_search_covers_structured_scene_and_psyke_details_fields() -> None:
    db = Database()
    project = db.create_project("Structured")
    scene = db.create_scene(
        project.id,
        "Stage scene",
        audience_visibility_notes="Lantern reveal",
    )
    psyke = db.create_psyke_entry(
        project.id,
        "Artifact",
        "object",
        details={"origin": "Obsidian archive"},
    )
    client = _client(db)

    scene_match = client.get(
        f"/api/projects/{project.id}/search",
        params=[("q", "lantern"), ("kinds", "scene")],
    ).json()["matches"]
    assert [(row["kind"], row["id"]) for row in scene_match] == [("scene", scene.id)]

    psyke_match = client.get(
        f"/api/projects/{project.id}/search",
        params=[("q", "obsidian"), ("kinds", "psyke")],
    ).json()["matches"]
    assert [(row["kind"], row["id"]) for row in psyke_match] == [("psyke", psyke.id)]


def test_search_validates_query_limit_kind_project_and_auth() -> None:
    db = Database()
    project = db.create_project("Validation")
    client = _client(db)
    path = f"/api/projects/{project.id}/search"

    blank = client.get(path, params={"q": "   "})
    assert blank.status_code == 400
    assert blank.json()["error"]["code"] == "bad_request"
    assert client.get(path).status_code == 422
    assert client.get(path, params={"q": "x" * 501}).status_code == 422
    assert client.get(path, params={"q": "x", "limit": 0}).status_code == 422
    assert client.get(path, params={"q": "x", "limit": 101}).status_code == 422
    assert client.get(path, params={"q": "x", "kinds": "project"}).status_code == 422
    assert client.get("/api/projects/99999/search", params={"q": "x"}).status_code == 404

    secured = _client(db, token="secret")
    assert secured.get(path, params={"q": "x"}).status_code == 403
    assert secured.get(
        path,
        params={"q": "x"},
        headers={"Authorization": "Bearer secret"},
    ).status_code == 200
