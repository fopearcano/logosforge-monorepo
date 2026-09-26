"""First-class Pro inline comments and Whiteboard anchor migration."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from logosforge.api.app import create_api
from logosforge.api.config import ApiConfig
from logosforge.db import Database
from sqlalchemy.exc import StatementError

from logosforge import whiteboard_import


def _client(db: Database) -> TestClient:
    return TestClient(create_api(db=db, config=ApiConfig(mode="desktop")))


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def test_comment_rest_surface_openapi_and_project_isolated_roundtrip() -> None:
    """The documented Comments API supports one complete editor roundtrip."""
    db = Database()
    project = db.create_project("REST comments")
    content = "Before 😀 comet, then moon🌙 after."
    scene = db.create_scene(project.id, "Unicode", content=content)
    foreign_project = db.create_project("Other project")
    db.create_scene(foreign_project.id, "Other", content="Nothing shared")
    client = _client(db)

    schema = client.get("/openapi.json").json()
    expected_methods = {
        "/api/projects/{project_id}/comments": {"get", "post"},
        "/api/projects/{project_id}/comments/{comment_id}": {
            "get", "patch", "delete",
        },
        "/api/projects/{project_id}/comments/{comment_id}/replies": {"post"},
        (
            "/api/projects/{project_id}/comments/{comment_id}"
            "/replies/{reply_id}"
        ): {"delete"},
    }
    for path, methods in expected_methods.items():
        assert path in schema["paths"]
        assert methods <= set(schema["paths"][path])

    update_schema = schema["components"]["schemas"]["InlineCommentUpdateDTO"]
    assert {"anchor", "quote", "body", "resolved", "expected_revision"} <= set(
        update_schema["properties"]
    )
    reply_create_schema = schema["components"]["schemas"]["CommentReplyCreateDTO"]
    assert "expected_revision" in reply_create_schema["properties"]
    assert "revision" in schema["components"]["schemas"]["InlineCommentDTO"][
        "properties"
    ]

    initial_quote = "😀 comet"
    initial_start = _utf16_units(content[:content.index(initial_quote)])
    initial_end = initial_start + _utf16_units(initial_quote)
    assert (initial_start, initial_end) == (7, 15)
    created_response = client.post(
        f"/api/projects/{project.id}/comments",
        json={
            "source_id": "desktop-native",
            "anchor": {
                "start_scene_id": scene.id,
                "start_field": "content",
                "from_offset": initial_start,
                "end_scene_id": scene.id,
                "end_field": "content",
                "to_offset": initial_end,
                "prefix": "Before ",
                "suffix": ", then",
            },
            "quote": initial_quote,
            "body": "Track the comet 🌠 motif",
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    comment_id = created["id"]
    assert len(created["revision"]) == 64
    assert client.get(
        f"/api/projects/{project.id}/comments/{comment_id}"
    ).json() == created
    assert created["anchor"]["from_offset"] == 7
    assert created["anchor"]["to_offset"] == 15

    # An ID from another project is not an alternate route to the thread.
    assert client.get(
        f"/api/projects/{foreign_project.id}/comments"
    ).json() == []
    assert client.post(
        f"/api/projects/{foreign_project.id}/comments/{comment_id}/replies",
        json={"body": "Must not cross projects"},
    ).status_code == 404
    assert client.get(
        f"/api/projects/{foreign_project.id}/comments/{comment_id}"
    ).status_code == 404

    replied_response = client.post(
        f"/api/projects/{project.id}/comments/{comment_id}/replies",
        json={"body": "Keep the 🌙 echo", "author": "editor"},
    )
    assert replied_response.status_code == 201
    reply = replied_response.json()["replies"][0]
    assert reply["body"] == "Keep the 🌙 echo"

    moved_quote = "moon🌙"
    moved_start = _utf16_units(content[:content.index(moved_quote)])
    moved_end = moved_start + _utf16_units(moved_quote)
    patched_response = client.patch(
        f"/api/projects/{project.id}/comments/{comment_id}",
        json={
            "anchor": {
                "start_scene_id": scene.id,
                "start_field": "content",
                "from_offset": moved_start,
                "end_scene_id": scene.id,
                "end_field": "content",
                "to_offset": moved_end,
                "prefix": "comet, then ",
                "suffix": " after.",
            },
            "quote": moved_quote,
            "body": "Follow the lunar echo instead",
            "resolved": True,
        },
    )
    assert patched_response.status_code == 200
    patched = patched_response.json()
    assert patched["quote"] == moved_quote
    assert patched["body"] == "Follow the lunar echo instead"
    assert patched["resolved"] is True
    assert patched["anchor"]["from_offset"] == moved_start
    assert patched["anchor"]["to_offset"] == moved_end

    listed = client.get(f"/api/projects/{project.id}/comments").json()
    assert [comment["id"] for comment in listed] == [comment_id]
    assert listed[0]["replies"] == [reply]

    assert client.delete(
        f"/api/projects/{foreign_project.id}/comments/{comment_id}"
        f"/replies/{reply['id']}"
    ).status_code == 404
    assert client.delete(
        f"/api/projects/{foreign_project.id}/comments/{comment_id}"
    ).status_code == 404
    assert client.get(f"/api/projects/{project.id}/comments").json()

    deleted_reply = client.delete(
        f"/api/projects/{project.id}/comments/{comment_id}"
        f"/replies/{reply['id']}"
    )
    assert deleted_reply.json() == {"ok": True, "deleted": reply["id"]}
    assert client.get(f"/api/projects/{project.id}/comments").json()[0][
        "replies"
    ] == []

    deleted_thread = client.delete(
        f"/api/projects/{project.id}/comments/{comment_id}"
    )
    assert deleted_thread.json() == {"ok": True, "deleted": comment_id}
    assert client.get(f"/api/projects/{project.id}/comments").json() == []


def test_comment_revisions_guard_reply_and_resolution_without_breaking_ui() -> None:
    db = Database()
    project = db.create_project("Revisioned comments")
    scene = db.create_scene(project.id, "Opening", content="A quiet warning")
    client = _client(db)
    path = f"/api/projects/{project.id}/comments"
    created = client.post(
        path,
        json={
            "anchor": {
                "start_scene_id": scene.id,
                "start_field": "content",
                "from_offset": 2,
                "end_scene_id": scene.id,
                "end_field": "content",
                "to_offset": 7,
            },
            "quote": "quiet",
            "body": "First note",
        },
    ).json()
    comment_path = f"{path}/{created['id']}"
    assert len(created["revision"]) == 64
    assert set(created["revision"]) <= set("0123456789abcdef")

    # Native UI callers remain compatible when they omit a revision.
    native = client.patch(comment_path, json={"body": "Native edit"})
    assert native.status_code == 200
    assert native.json()["revision"] != created["revision"]

    current = native.json()
    reply = client.post(
        f"{comment_path}/replies",
        json={
            "body": "Revision-bound reply",
            "author": "MCP assistant",
            "expected_revision": current["revision"],
        },
    )
    assert reply.status_code == 201
    replied = reply.json()
    assert replied["revision"] != current["revision"]
    assert replied["replies"][-1]["author"] == "MCP assistant"

    stale_resolution = client.patch(
        comment_path,
        json={"resolved": True, "expected_revision": current["revision"]},
    )
    assert stale_resolution.status_code == 409
    assert stale_resolution.json()["error"]["code"] == "comment_conflict"
    assert client.get(comment_path).json()["resolved"] is False

    resolved = client.patch(
        comment_path,
        json={"resolved": True, "expected_revision": replied["revision"]},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved"] is True
    assert resolved.json()["revision"] != replied["revision"]

    stale_reply = client.post(
        f"{comment_path}/replies",
        json={"body": "Must not land", "expected_revision": replied["revision"]},
    )
    assert stale_reply.status_code == 409
    latest = client.get(comment_path).json()
    assert [item["body"] for item in latest["replies"]] == [
        "Revision-bound reply",
    ]

    before_delete = latest["revision"]
    reply_id = latest["replies"][0]["id"]
    assert client.delete(f"{comment_path}/replies/{reply_id}").status_code == 200
    after_delete = client.get(comment_path).json()
    assert after_delete["replies"] == []
    assert after_delete["revision"] != before_delete


def test_same_comment_revision_has_one_winner_across_database_instances(
    tmp_path,
) -> None:
    database_path = tmp_path / "comment-race.db"
    first_db = Database(str(database_path))
    project = first_db.create_project("Comment race")
    scene = first_db.create_scene(project.id, "Scene", content="Race")
    first_client = _client(first_db)
    created = first_client.post(
        f"/api/projects/{project.id}/comments",
        json={
            "anchor": {
                "start_scene_id": scene.id,
                "start_field": "content",
                "from_offset": 0,
                "end_scene_id": scene.id,
                "end_field": "content",
                "to_offset": 4,
            },
            "quote": "Race",
        },
    ).json()
    second_db = Database(str(database_path))
    second_client = _client(second_db)
    barrier = Barrier(2)
    reply_path = (
        f"/api/projects/{project.id}/comments/{created['id']}/replies"
    )

    def append(client: TestClient, body: str):
        barrier.wait()
        return client.post(
            reply_path,
            json={"body": body, "expected_revision": created["revision"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(
            lambda pair: append(*pair),
            [(first_client, "first"), (second_client, "second")],
        ))

    assert sorted(response.status_code for response in responses) == [201, 409]
    conflict_response = next(
        response for response in responses if response.status_code == 409
    )
    assert conflict_response.json()["error"]["code"] == "comment_conflict"
    final = first_client.get(
        f"/api/projects/{project.id}/comments/{created['id']}"
    ).json()
    assert len(final["replies"]) == 1
    assert final["replies"][0]["body"] in {"first", "second"}

    # Reply and Resolve share the same transaction boundary as well.
    second_barrier = Barrier(2)

    def append_again():
        second_barrier.wait()
        return first_client.post(
            reply_path,
            json={"body": "another", "expected_revision": final["revision"]},
        )

    def resolve():
        second_barrier.wait()
        return second_client.patch(
            f"/api/projects/{project.id}/comments/{created['id']}",
            json={"resolved": True, "expected_revision": final["revision"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        reply_future = pool.submit(append_again)
        resolve_future = pool.submit(resolve)
        mixed_responses = [reply_future.result(), resolve_future.result()]

    assert sorted(response.status_code for response in mixed_responses) in (
        [200, 409],
        [201, 409],
    )
    mixed_final = first_client.get(
        f"/api/projects/{project.id}/comments/{created['id']}"
    ).json()
    if mixed_final["resolved"]:
        assert len(mixed_final["replies"]) == 1
    else:
        assert [reply["body"] for reply in mixed_final["replies"]][-1] == "another"


def test_comment_routes_enforce_ownership_order_replies_and_scene_cascade() -> None:
    db = Database()
    project = db.create_project("Commented")
    first = db.create_scene(project.id, "First", content="Alpha")
    second = db.create_scene(project.id, "Beta", content="Omega")
    foreign_project = db.create_project("Foreign")
    foreign_scene = db.create_scene(foreign_project.id, "Elsewhere", content="No")
    client = _client(db)

    created_response = client.post(
        f"/api/projects/{project.id}/comments",
        json={
            "source_id": "wb-root",
            "anchor": {
                "start_scene_id": first.id,
                "start_field": "content",
                "from_offset": 0,
                "end_scene_id": second.id,
                "end_field": "title",
                "to_offset": 4,
                "prefix": "",
                "suffix": "",
            },
            "quote": "Alpha\nBeta",
            "body": "Bridge these beats",
            "replies": [
                {"source_id": "later", "body": "Later", "sort_order": 3},
                {"source_id": "earlier", "body": "Earlier", "sort_order": 1},
            ],
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["source_id"] == "wb-root"
    assert [reply["source_id"] for reply in created["replies"]] == [
        "earlier", "later",
    ]

    rejected = client.post(
        f"/api/projects/{project.id}/comments",
        json={
            "anchor": {
                "start_scene_id": first.id,
                "start_field": "content",
                "from_offset": 0,
                "end_scene_id": foreign_scene.id,
                "end_field": "content",
                "to_offset": 1,
                "prefix": "",
                "suffix": "",
            },
            "quote": "A",
        },
    )
    assert rejected.status_code == 400

    emoji_scene = db.create_scene(project.id, "Emoji", content="😀x")
    split_surrogate = client.post(
        f"/api/projects/{project.id}/comments",
        json={
            "anchor": {
                "start_scene_id": emoji_scene.id,
                "start_field": "content",
                "from_offset": 1,
                "end_scene_id": emoji_scene.id,
                "end_field": "content",
                "to_offset": 2,
                "prefix": "",
                "suffix": "",
            },
            "quote": "😀",
        },
    )
    assert split_surrogate.status_code == 400

    patched = client.patch(
        f"/api/projects/{project.id}/comments/{created['id']}",
        json={"quote": "Alpha revised", "resolved": True},
    )
    assert patched.status_code == 200
    assert patched.json()["quote"] == "Alpha revised"
    assert patched.json()["resolved"] is True

    invalid_quote_patch = client.patch(
        f"/api/projects/{project.id}/comments/{created['id']}",
        content=json.dumps({"quote": "\ud83d"}).encode("ascii"),
        headers={"content-type": "application/json"},
    )
    assert invalid_quote_patch.status_code in {400, 422}

    replied = client.post(
        f"/api/projects/{project.id}/comments/{created['id']}/replies",
        json={"body": "Native reply", "author": "writer"},
    )
    assert replied.status_code == 201
    assert len(replied.json()["replies"]) == 3
    reply_id = next(
        reply["id"] for reply in replied.json()["replies"]
        if reply["body"] == "Native reply"
    )
    deleted_reply = client.delete(
        f"/api/projects/{project.id}/comments/{created['id']}/replies/{reply_id}",
    )
    assert deleted_reply.json() == {"ok": True, "deleted": reply_id}

    # Legal JSON may carry a lone surrogate (for example when a JS context
    # window slices through an emoji). Never let it reach SQLite or a response
    # encoder as a server error.
    invalid_context_payload = {
        "anchor": {
            "start_scene_id": first.id,
            "start_field": "content",
            "from_offset": 0,
            "end_scene_id": first.id,
            "end_field": "content",
            "to_offset": 1,
            "prefix": "\ud800",
            "suffix": "",
        },
        "quote": "A",
    }
    invalid_context = client.post(
        f"/api/projects/{project.id}/comments",
        content=json.dumps(invalid_context_payload).encode("ascii"),
        headers={"content-type": "application/json"},
    )
    assert invalid_context.status_code == 400

    zero_width = client.post(
        f"/api/projects/{project.id}/comments",
        json={
            "anchor": {
                "start_scene_id": first.id,
                "start_field": "content",
                "from_offset": 4,
                "end_scene_id": first.id,
                "end_field": "content",
                "to_offset": 4,
                "prefix": "Alph",
                "suffix": "a",
            },
            "quote": "deleted text",
            "body": "Retain this editorial thread",
        },
    )
    assert zero_width.status_code == 201
    assert zero_width.json()["anchor"]["from_offset"] == 4
    assert zero_width.json()["anchor"]["to_offset"] == 4
    assert client.delete(
        f"/api/projects/{project.id}/comments/{zero_width.json()['id']}"
    ).status_code == 200

    # Removing either edge scene removes the complete range/thread and emits a
    # comment invalidation event in addition to the ordinary scenes event.
    deleted_scene = client.delete(f"/api/projects/{project.id}/scenes/{second.id}")
    assert deleted_scene.status_code == 200
    assert client.get(f"/api/projects/{project.id}/comments").json() == []
    names = [
        event["event"]
        for event in client.app.state.broker.events_since(0, project.id)
    ]
    assert "comments_changed" in names


def test_comment_root_and_nested_replies_are_one_transaction() -> None:
    db = Database()
    project = db.create_project("Atomic")
    scene = db.create_scene(project.id, "Scene", content="Text")

    with pytest.raises((StatementError, TypeError, ValueError)):
        db.create_comment_with_replies(
            project.id,
            start_scene_id=scene.id,
            start_field="content",
            from_offset=0,
            end_scene_id=scene.id,
            end_field="content",
            to_offset=4,
            quote="Text",
            replies=[{"body": "bad timestamp", "created_at": object()}],
        )

    assert db.get_all_comments(project.id) == []


def test_whiteboard_import_maps_utf16_marks_trim_and_cross_field_replies() -> None:
    db = Database()
    timestamp = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc).isoformat()
    result = whiteboard_import.import_whiteboard_document(
        db,
        {
            "title": "Mapped comments",
            "mode": "novel",
            "blocks": [
                {"id": "h1", "type": "heading", "text": "  Chapter One  "},
                {
                    "id": "p1",
                    "type": "paragraph",
                    "text": "  A😀bold tail  ",
                    # JavaScript offsets: two spaces + A + the two-unit emoji.
                    "marks": [{"type": "bold", "from": 5, "to": 9}],
                },
                {"id": "h2", "type": "heading", "text": "Second"},
                {"id": "p2", "type": "paragraph", "text": "Omega end"},
                {"id": "p3", "type": "paragraph", "text": "cat dog cat"},
                {"id": "p4", "type": "paragraph", "text": "before storm after"},
            ],
            "comments": [
                {
                    "id": "title",
                    "anchor": {
                        "block_index": 0,
                        "block_id": "h1",
                        "from_offset": 2,
                        "to_offset": 9,
                    },
                    "quote": "Chapter",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                {
                    "id": "marked",
                    "anchor": {
                        # Stable id is authoritative even when the legacy index
                        # is stale/out of range.
                        "block_index": 99,
                        "block_id": "p1",
                        "from_offset": 5,
                        "to_offset": 9,
                    },
                    "quote": "bold",
                    "body": "Keep the emphasis",
                    "replies": [
                        {"id": "r1", "body": "First", "created_at": timestamp},
                        {"id": "r2", "body": "Second", "created_at": timestamp},
                    ],
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                {
                    "id": "cross-scene",
                    "anchor": {
                        "block_index": 1,
                        "block_id": "p1",
                        "from_offset": 10,
                        "end_block_index": 3,
                        "end_block_id": "p2",
                        "to_offset": 5,
                    },
                    "quote": "tail  \nSecond\nOmega",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                {
                    "id": "cross-field",
                    "anchor": {
                        "block_index": 2,
                        "block_id": "h2",
                        "from_offset": 0,
                        "end_block_index": 3,
                        "end_block_id": "p2",
                        "to_offset": 5,
                    },
                    "quote": "Second\nOmega",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                {
                    "id": "relocated",
                    "anchor": {
                        "block_index": 4,
                        "block_id": "p3",
                        "from_offset": 0,
                        "to_offset": 3,
                        "prefix": "dog ",
                    },
                    "quote": "cat",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                {
                    "id": "moved-block",
                    "anchor": {
                        "block_index": 0,
                        "from_offset": 0,
                        "to_offset": 5,
                    },
                    "quote": "Omega",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                {
                    "id": "edited-quote",
                    "anchor": {
                        "block_index": 5,
                        "block_id": "p4",
                        "from_offset": 7,
                        "to_offset": 11,
                        "prefix": "before ",
                        "suffix": " after",
                    },
                    "quote": "rain",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                {
                    "id": "surviving-edge",
                    "anchor": {
                        "block_index": 99,
                        "from_offset": 0,
                        "end_block_index": 3,
                        "end_block_id": "p2",
                        "to_offset": 5,
                    },
                    "quote": "deleted edge\nOmega",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
                {
                    "id": "orphan",
                    "anchor": {
                        "block_index": 99,
                        "from_offset": 0,
                        "to_offset": 1,
                    },
                    "quote": "x",
                    "replies": [
                        {"id": "lost", "body": "Lost", "created_at": timestamp},
                    ],
                    "created_at": timestamp,
                    "updated_at": timestamp,
                },
            ],
        },
    )

    assert result["comments_created"] == 8
    assert result["comments_skipped"] == 1
    assert result["comment_replies_created"] == 2
    assert result["comment_replies_skipped"] == 1
    comments = {
        comment.source_id: comment
        for comment in db.get_all_comments(result["project_id"])
    }
    title = comments["title"]
    assert (title.start_field, title.from_offset, title.to_offset) == (
        "title", 0, 7,
    )
    marked = comments["marked"]
    assert (marked.start_field, marked.from_offset, marked.to_offset) == (
        "content", 5, 9,
    )
    assert marked.quote == "bold"
    assert [reply.source_id for reply in db.get_comment_replies(marked.id)] == [
        "r1", "r2",
    ]
    cross = comments["cross-field"]
    assert cross.start_field == "title"
    assert cross.end_field == "content"
    assert cross.start_scene_id == cross.end_scene_id
    cross_scene = comments["cross-scene"]
    assert cross_scene.start_field == cross_scene.end_field == "content"
    assert cross_scene.start_scene_id != cross_scene.end_scene_id
    relocated = comments["relocated"]
    # "Omega end\n\n" is 11 UTF-16 units; the context selector chooses the
    # second "cat" at local offset 8 rather than trusting the stale zero hint.
    assert (relocated.from_offset, relocated.to_offset) == (19, 22)
    moved = comments["moved-block"]
    assert (moved.from_offset, moved.to_offset) == (0, 5)
    edited = comments["edited-quote"]
    assert edited.quote == "storm"
    assert (edited.from_offset, edited.to_offset) == (31, 36)
    surviving = comments["surviving-edge"]
    assert surviving.start_scene_id == surviving.end_scene_id
    assert (surviving.from_offset, surviving.to_offset) == (0, 5)

    db.delete_project(result["project_id"])
    assert db.get_all_comments(result["project_id"]) == []


def test_whiteboard_import_honours_explicit_end_index_without_end_id() -> None:
    """A legacy multi-block anchor may predate stable end-block IDs."""
    db = Database()
    result = whiteboard_import.import_whiteboard_document(
        db,
        {
            "title": "Legacy range",
            "mode": "novel",
            "blocks": [
                {"id": "heading", "type": "heading", "text": "Chapter"},
                {"id": "start", "type": "paragraph", "text": "Alpha"},
                {"id": "end", "type": "paragraph", "text": "Omega"},
            ],
            "comments": [{
                "id": "legacy-cross-block",
                "anchor": {
                    "block_index": 1,
                    "block_id": "start",
                    "from_offset": 0,
                    "end_block_index": 2,
                    "to_offset": 5,
                    # JS context capture can split an emoji at its fixed UTF-16
                    # window boundary. It remains advisory and is regenerated
                    # from the mapped Pro text instead of being persisted.
                    "prefix": "\ud800",
                },
                "quote": "Alpha\nOmega",
            }],
        },
    )

    assert result["comments_created"] == 1
    assert result["comments_skipped"] == 0
    comment = db.get_all_comments(result["project_id"])[0]
    assert comment.source_id == "legacy-cross-block"
    assert comment.start_scene_id == comment.end_scene_id
    assert (comment.from_offset, comment.to_offset) == (0, 12)


def test_screenplay_slug_titles_survive_comment_anchor_mapping() -> None:
    db = Database()
    first_slug = "INT. HOUSE - DAY"
    second_slug = "EXT. ROAD - NIGHT"
    result = whiteboard_import.import_whiteboard_document(
        db,
        {
            "title": "Screenplay import",
            "mode": "screenplay",
            "blocks": [
                {"id": "slug-1", "type": "paragraph", "text": first_slug},
                {"id": "action-1", "type": "paragraph", "text": "Action."},
                {"id": "slug-2", "type": "paragraph", "text": second_slug},
                {"id": "action-2", "type": "paragraph", "text": "More."},
            ],
            "comments": [{
                "id": "slug-comment",
                "anchor": {
                    "block_index": 0,
                    "block_id": "slug-1",
                    "from_offset": 0,
                    "to_offset": len(first_slug),
                },
                "quote": first_slug,
            }],
        },
    )

    scenes = db.get_all_scenes(result["project_id"])
    assert [scene.title for scene in scenes] == [first_slug, second_slug]
    assert [scene.content for scene in scenes] == [
        f"{first_slug}\nAction.",
        f"{second_slug}\nMore.",
    ]
    comment = db.get_all_comments(result["project_id"])[0]
    assert comment.start_scene_id == comment.end_scene_id == scenes[0].id
    assert comment.start_field == comment.end_field == "content"
    assert (comment.from_offset, comment.to_offset) == (0, len(first_slug))


def test_whiteboard_import_preserves_deleted_quote_between_context_edges() -> None:
    db = Database()
    result = whiteboard_import.import_whiteboard_document(
        db,
        {
            "title": "Edited quote",
            "mode": "novel",
            "blocks": [{
                "id": "edited",
                "type": "paragraph",
                "text": "The  had not stopped",
            }],
            "comments": [{
                "id": "deleted-quote",
                "anchor": {
                    "block_index": 0,
                    "block_id": "edited",
                    "from_offset": 4,
                    "to_offset": 8,
                    "prefix": "The ",
                    "suffix": " had not",
                },
                "quote": "rain",
                "body": "The deletion itself still needs review",
            }],
        },
    )

    assert result["comments_created"] == 1
    assert result["comments_skipped"] == 0
    comment = db.get_all_comments(result["project_id"])[0]
    assert comment.quote == "rain"
    assert (comment.from_offset, comment.to_offset) == (4, 4)
