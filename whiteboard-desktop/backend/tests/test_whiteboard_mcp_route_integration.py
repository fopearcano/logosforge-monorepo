"""Route-level coverage for Whiteboard MCP conditional writes."""
from __future__ import annotations

import copy
import io
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import app.document_lifecycle as lifecycle
from app.local_state import (
    CommentAnchor,
    CommentCreate,
    CommentsStore,
    OutlineItemsStore,
    PsykeRevisionStore,
    WhiteboardCreate,
    WhiteboardStore,
)
from app.routers import comments as comments_router
from app.routers import outline as outline_router
from app.routers import psyke as psyke_router
from app.routers import whiteboard as whiteboard_router
from app.whiteboard_mcp.client import WhiteboardApiClient


class _Core:
    """Small authoritative-project stub used by the real route lifecycle gate."""

    def __init__(self, project_id: int) -> None:
        self.project_id = project_id
        self.psyke_entries: list[dict] = []
        self.psyke_relations: list[dict] = []
        self.psyke_progressions: list[dict] = []
        self.psyke_write_calls: list[tuple[str, int | None, dict]] = []
        self.psyke_relation_write_calls: list[dict] = []
        self.psyke_progression_write_calls: list[tuple[str, int | None, dict]] = []
        self._next_psyke_id = 1
        self._next_progression_id = 1

    async def request(self, method: str, path: str, **kwargs):
        entries_path = f"/api/projects/{self.project_id}/psyke/entries"
        if method == "GET" and path == entries_path:
            return _JsonResponse(copy.deepcopy(self.psyke_entries))
        relations_path = f"/api/projects/{self.project_id}/psyke/relations"
        progressions_path = f"/api/projects/{self.project_id}/psyke/progressions"
        if method == "GET" and path == relations_path:
            return _JsonResponse(copy.deepcopy(self.psyke_relations))
        if method == "GET" and path == progressions_path:
            return _JsonResponse(copy.deepcopy(self.psyke_progressions))
        if method == "POST" and path == entries_path:
            payload = copy.deepcopy(kwargs["json"])
            details = {"server_only": "preserve-me", **payload.get("details", {})}
            entry = {
                "id": self._next_psyke_id,
                "project_id": self.project_id,
                "name": payload["name"],
                "type": payload.get("type", "other"),
                "aliases": payload.get("aliases", []),
                "notes": payload.get("notes", ""),
                "is_global": payload.get("is_global", False),
                "details": details,
            }
            self._next_psyke_id += 1
            self.psyke_entries.append(entry)
            self.psyke_write_calls.append((method, None, payload))
            return _JsonResponse(copy.deepcopy(entry))
        patch_prefix = f"{entries_path}/"
        if method == "PATCH" and path.startswith(patch_prefix):
            entry_id = int(path.removeprefix(patch_prefix))
            payload = copy.deepcopy(kwargs["json"])
            entry = next(item for item in self.psyke_entries if item["id"] == entry_id)
            entry.update(payload)
            self.psyke_write_calls.append((method, entry_id, payload))
            return _JsonResponse(copy.deepcopy(entry))
        if method == "POST" and path == relations_path:
            payload = copy.deepcopy(kwargs["json"])
            source_id = int(payload["source_id"])
            target_id = int(payload["target_id"])
            source = next(item for item in self.psyke_entries if item["id"] == source_id)
            target = next(item for item in self.psyke_entries if item["id"] == target_id)
            relation = {
                "id": f"{source_id}:{target_id}",
                "source_id": source_id,
                "target_id": target_id,
                "source": source["name"],
                "target": target["name"],
                "relation_type": payload.get("relation_type", ""),
            }
            self.psyke_relations.append(relation)
            self.psyke_relation_write_calls.append(payload)
            return _JsonResponse(copy.deepcopy(relation))
        if method == "POST" and path == progressions_path:
            payload = copy.deepcopy(kwargs["json"])
            progression = {
                "id": self._next_progression_id,
                "entry_id": int(payload["entry_id"]),
                "text": payload["text"],
                "scene_id": payload.get("scene_id"),
                "scene_title": "",
                "sort_order": 1,
            }
            self._next_progression_id += 1
            self.psyke_progressions.append(progression)
            self.psyke_progression_write_calls.append((method, None, payload))
            return _JsonResponse(copy.deepcopy(progression))
        progression_prefix = f"{progressions_path}/"
        if method == "PATCH" and path.startswith(progression_prefix):
            progression_id = int(path.removeprefix(progression_prefix))
            payload = copy.deepcopy(kwargs["json"])
            progression = next(
                item for item in self.psyke_progressions if item["id"] == progression_id
            )
            progression.update(payload)
            self.psyke_progression_write_calls.append(
                (method, progression_id, payload)
            )
            return _JsonResponse(copy.deepcopy(progression))
        return SimpleNamespace()

    async def ensure_project(self) -> int:
        return self.project_id


class _UrlopenResponse:
    def __init__(self, body: bytes, headers=None) -> None:
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]


class _JsonResponse:
    def __init__(self, value) -> None:
        self._value = value

    def json(self):
        return self._value


def test_mcp_client_conditional_puts_satisfy_real_route_preconditions(
    tmp_path,
    monkeypatch,
) -> None:
    """The client must send incarnation, ETag, and mutation id as one contract.

    Explicit ``?doc=`` mutations pass through ``locked_document_request``, which
    rejects a request before its revision is considered unless the document
    incarnation header is present and current. Bridging urllib into TestClient
    keeps the production MCP request builder and the production FastAPI routes
    in the same integration test without opening a real network listener.
    """
    project_id = 920201
    document_id = str(project_id)
    whiteboards = WhiteboardStore(tmp_path)
    outlines = OutlineItemsStore(tmp_path)
    created = whiteboards.create(
        document_id,
        WhiteboardCreate(
            title="Before",
            blocks=[{"id": "b1", "type": "paragraph", "text": "Opening."}],
        ),
    )
    original_outline = outlines.get_document(document_id)

    monkeypatch.setattr(lifecycle, "whiteboard_store", whiteboards)
    monkeypatch.setattr(whiteboard_router, "whiteboard_store", whiteboards)
    monkeypatch.setattr(outline_router, "outline_items_store", outlines)

    route_app = FastAPI()
    route_app.state.core = _Core(project_id)
    route_app.include_router(whiteboard_router.router)
    route_app.include_router(outline_router.router)

    with TestClient(route_app) as route_client:
        seen_headers: list[dict[str, str]] = []

        def urlopen(request, timeout):
            assert timeout == 7.0
            parsed = urlsplit(request.full_url)
            target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            request_headers = {
                key.lower(): value for key, value in request.header_items()
            }
            seen_headers.append(request_headers)
            response = route_client.request(
                request.get_method(),
                target,
                headers=request_headers,
                content=request.data,
            )
            if response.status_code >= 400:
                raise urllib.error.HTTPError(
                    request.full_url,
                    response.status_code,
                    response.reason_phrase,
                    response.headers,
                    io.BytesIO(response.content),
                )
            return _UrlopenResponse(response.content, response.headers)

        monkeypatch.setattr(
            "app.whiteboard_mcp.client.urllib.request.urlopen",
            urlopen,
        )
        api = WhiteboardApiClient("http://whiteboard.test", "s" * 32, 7)

        updated = api.update_document(
            project_id,
            incarnation=created.incarnation,
            expected_revision=created.revision,
            mutation_id="lfwbp-route-manuscript",
            patch={"title": "After"},
        )
        assert updated["title"] == "After"
        assert updated["revision"] != created.revision

        items = [
            {
                "id": "node-1",
                "parentId": None,
                "type": "chapter",
                "title": "Opening",
                "summary": "The story begins.",
                "order": 0,
                "collapsed": False,
                "completed": False,
                "status": "drafting",
                "tags": [],
                "colorLabel": "none",
                "createdAt": "2026-09-25T00:00:00Z",
                "updatedAt": "2026-09-25T00:00:00Z",
            }
        ]
        replaced = api.replace_outline(
            project_id,
            incarnation=created.incarnation,
            expected_revision=original_outline.revision,
            mutation_id="lfwbp-route-outline",
            items=items,
        )
        assert replaced["items"] == items
        assert replaced["revision"] != original_outline.revision

        assert len(seen_headers) == 2
        assert all(
            headers["x-logosforge-document-incarnation"] == created.incarnation
            for headers in seen_headers
        )
        assert seen_headers[0]["x-logosforge-mutation-id"] == (
            "lfwbp-route-manuscript"
        )
        assert seen_headers[1]["x-logosforge-mutation-id"] == "lfwbp-route-outline"
        assert seen_headers[0]["if-match"] == (
            f'"lfwb:whiteboard:{created.incarnation}:{created.revision}"'
        )
        assert seen_headers[1]["if-match"] == (
            f'"lfwb:outline:{created.incarnation}:{original_outline.revision}"'
        )

    stored = whiteboards.get(document_id)
    assert stored.title == "After"
    assert outlines.get_document(document_id).items == items


def test_mcp_client_conditional_psyke_create_and_patch_use_real_routes(
    tmp_path,
    monkeypatch,
) -> None:
    """The named MCP client and PSYKE route share one conditional contract."""
    project_id = 920202
    document_id = str(project_id)
    whiteboards = WhiteboardStore(tmp_path)
    revisions = PsykeRevisionStore(tmp_path)
    document = whiteboards.create(document_id, WhiteboardCreate(title="Story"))
    core = _Core(project_id)

    monkeypatch.setattr(lifecycle, "whiteboard_store", whiteboards)
    monkeypatch.setattr(psyke_router, "psyke_revision_store", revisions)

    route_app = FastAPI()
    route_app.state.core = core
    route_app.include_router(psyke_router.router)

    with TestClient(route_app) as route_client:
        seen_writes: list[tuple[str, dict[str, str]]] = []

        def urlopen(request, timeout):
            assert timeout == 7.0
            parsed = urlsplit(request.full_url)
            target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            request_headers = {
                key.lower(): value for key, value in request.header_items()
            }
            if request.get_method() != "GET":
                seen_writes.append((request.get_method(), request_headers))
            response = route_client.request(
                request.get_method(),
                target,
                headers=request_headers,
                content=request.data,
            )
            if response.status_code >= 400:
                raise urllib.error.HTTPError(
                    request.full_url,
                    response.status_code,
                    response.reason_phrase,
                    response.headers,
                    io.BytesIO(response.content),
                )
            return _UrlopenResponse(response.content, response.headers)

        monkeypatch.setattr(
            "app.whiteboard_mcp.client.urllib.request.urlopen",
            urlopen,
        )
        api = WhiteboardApiClient("http://whiteboard.test", "s" * 32, 7)

        initial = api.get_psyke(project_id)
        assert initial["results"] == []

        created = api.create_psyke_entry(
            project_id,
            incarnation=document.incarnation,
            expected_revision=initial["revision"],
            mutation_id="lfwbp-route-psyke-create",
            entry={
                "name": "Mara",
                "type": "character",
                "description": "Keeper of the drowned archive.",
                "notes": "Introduced in chapter two.",
            },
        )
        entry_id = int(created["element"]["id"])
        assert created["element"]["entry_type"] == "character"
        assert created["revision"] != initial["revision"]

        replayed = api.create_psyke_entry(
            project_id,
            incarnation=document.incarnation,
            expected_revision=initial["revision"],
            mutation_id="lfwbp-route-psyke-create",
            entry={
                "name": "Mara",
                "type": "character",
                "description": "Keeper of the drowned archive.",
                "notes": "Introduced in chapter two.",
            },
        )
        assert replayed == created
        assert len(core.psyke_write_calls) == 1

        patched = api.patch_psyke_entry(
            project_id,
            entry_id,
            incarnation=document.incarnation,
            expected_revision=created["revision"],
            mutation_id="lfwbp-route-psyke-patch",
            patch={"description": "Guardian of the drowned archive."},
        )
        assert patched["element"]["description"] == (
            "Guardian of the drowned archive."
        )
        assert patched["revision"] != created["revision"]
        assert core.psyke_entries[0]["details"]["server_only"] == "preserve-me"
        assert len(core.psyke_write_calls) == 2

        second = api.create_psyke_entry(
            project_id,
            incarnation=document.incarnation,
            expected_revision=patched["revision"],
            mutation_id="lfwbp-route-psyke-create-second",
            entry={
                "name": "The Drowned Archive",
                "type": "place",
                "description": "A library beneath the tide line.",
                "notes": "Mara protects it.",
            },
        )
        second_entry_id = int(second["element"]["id"])

        relation_read = api.get_psyke_relations(project_id)
        assert relation_read == {"relations": [], "revision": second["revision"]}
        related = api.create_psyke_relation(
            project_id,
            incarnation=document.incarnation,
            expected_revision=relation_read["revision"],
            mutation_id="lfwbp-route-psyke-relation",
            relation={
                "source_id": entry_id,
                "target_id": second_entry_id,
                "relation_type": "supports_setup",
            },
        )
        assert related["relation"]["id"] == f"{entry_id}:{second_entry_id}"
        replayed_relation = api.create_psyke_relation(
            project_id,
            incarnation=document.incarnation,
            expected_revision=relation_read["revision"],
            mutation_id="lfwbp-route-psyke-relation",
            relation={
                "source_id": entry_id,
                "target_id": second_entry_id,
                "relation_type": "supports_setup",
            },
        )
        assert replayed_relation == related
        assert len(core.psyke_relation_write_calls) == 1

        progression_read = api.get_psyke_progressions(project_id)
        assert progression_read == {
            "progressions": [],
            "revision": related["revision"],
        }
        progressed = api.create_psyke_progression(
            project_id,
            incarnation=document.incarnation,
            expected_revision=progression_read["revision"],
            mutation_id="lfwbp-route-psyke-progression",
            progression={
                "entry_id": entry_id,
                "text": "Mara first refuses the archive's call.",
                "scene_id": None,
            },
        )
        progression_id = progressed["progression"]["id"]
        replayed_progression = api.create_psyke_progression(
            project_id,
            incarnation=document.incarnation,
            expected_revision=progression_read["revision"],
            mutation_id="lfwbp-route-psyke-progression",
            progression={
                "entry_id": entry_id,
                "text": "Mara first refuses the archive's call.",
                "scene_id": None,
            },
        )
        assert replayed_progression == progressed
        assert len(core.psyke_progression_write_calls) == 1

        progression_patch = api.patch_psyke_progression(
            project_id,
            progression_id,
            incarnation=document.incarnation,
            expected_revision=progressed["revision"],
            mutation_id="lfwbp-route-psyke-progression-patch",
            patch={
                "text": "Mara accepts the archive's call.",
                "scene_id": None,
            },
        )
        assert progression_patch["progression"]["text"] == (
            "Mara accepts the archive's call."
        )
        assert len(core.psyke_progression_write_calls) == 2

        final_entries = api.get_psyke(project_id)
        final_relations = api.get_psyke_relations(project_id)
        final_progressions = api.get_psyke_progressions(project_id)
        assert final_entries["revision"] == progression_patch["revision"]
        assert final_relations["revision"] == progression_patch["revision"]
        assert final_progressions["revision"] == progression_patch["revision"]
        assert final_relations["relations"] == [related["relation"]]
        assert final_progressions["progressions"] == [
            progression_patch["progression"]
        ]

        assert [method for method, _headers in seen_writes] == [
            "POST",
            "POST",
            "PATCH",
            "POST",
            "POST",
            "POST",
            "POST",
            "POST",
            "PATCH",
        ]
        create_headers = seen_writes[0][1]
        patch_headers = seen_writes[2][1]
        assert create_headers["x-logosforge-document-incarnation"] == (
            document.incarnation
        )
        assert create_headers["x-logosforge-mutation-id"] == (
            "lfwbp-route-psyke-create"
        )
        assert create_headers["if-match"] == (
            f'"lfwb:psyke:{document.incarnation}:{initial["revision"]}"'
        )
        assert patch_headers["x-logosforge-mutation-id"] == (
            "lfwbp-route-psyke-patch"
        )
        assert patch_headers["if-match"] == (
            f'"lfwb:psyke:{document.incarnation}:{created["revision"]}"'
        )

    stored = revisions.observe(
        document_id,
        document.incarnation,
        psyke_router._collection_digest(
            psyke_router.PsykeCollectionSnapshot(
                entries=core.psyke_entries,
                relations=core.psyke_relations,
                progressions=core.psyke_progressions,
            )
        ),
    )
    assert stored.revision == progression_patch["revision"]


def test_mcp_client_conditional_comment_reply_and_resolution_use_real_routes(
    tmp_path,
    monkeypatch,
) -> None:
    """Comment review writes stay revision-bound and retry without duplication."""
    project_id = 920203
    document_id = str(project_id)
    whiteboards = WhiteboardStore(tmp_path)
    comments = CommentsStore(tmp_path)
    document = whiteboards.create(
        document_id,
        WhiteboardCreate(
            title="Story",
            blocks=[{"id": "b1", "type": "paragraph", "text": "Opening."}],
        ),
    )
    root_comment = comments.create(
        document_id,
        "root-comment-1",
        CommentCreate(
            anchor=CommentAnchor(
                block_index=0,
                block_id="b1",
                from_offset=0,
                to_offset=7,
            ),
            quote="Opening",
            body="Clarify the opening image.",
        ),
    )

    monkeypatch.setattr(lifecycle, "whiteboard_store", whiteboards)
    monkeypatch.setattr(comments_router, "comments_store", comments)

    route_app = FastAPI()
    route_app.state.core = _Core(project_id)
    route_app.include_router(comments_router.router)

    with TestClient(route_app) as route_client:
        seen_requests: list[
            tuple[str, str, bytes | None, dict[str, str]]
        ] = []

        def urlopen(request, timeout):
            assert timeout == 7.0
            parsed = urlsplit(request.full_url)
            target = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            request_headers = {
                key.lower(): value for key, value in request.header_items()
            }
            seen_requests.append(
                (
                    request.get_method(),
                    target,
                    request.data,
                    request_headers,
                )
            )
            response = route_client.request(
                request.get_method(),
                target,
                headers=request_headers,
                content=request.data,
            )
            if response.status_code >= 400:
                raise urllib.error.HTTPError(
                    request.full_url,
                    response.status_code,
                    response.reason_phrase,
                    response.headers,
                    io.BytesIO(response.content),
                )
            return _UrlopenResponse(response.content, response.headers)

        monkeypatch.setattr(
            "app.whiteboard_mcp.client.urllib.request.urlopen",
            urlopen,
        )
        api = WhiteboardApiClient("http://whiteboard.test", "s" * 32, 7)

        initial = api.get_comments(project_id)
        assert [item["id"] for item in initial["comments"]] == [root_comment.id]

        reply_mutation_id = "lfwbp-route-comment-reply"
        reply_body = "Please sharpen this transition."
        replied = api.reply_to_comment(
            project_id,
            root_comment.id,
            incarnation=document.incarnation,
            expected_revision=initial["revision"],
            mutation_id=reply_mutation_id,
            body=reply_body,
        )
        assert replied["revision"] != initial["revision"]
        assert replied["comment"]["replies"] == [
            {
                "id": reply_mutation_id,
                "body": reply_body,
                "author": "MCP assistant",
                "created_at": replied["comment"]["replies"][0]["created_at"],
            }
        ]

        replayed = api.reply_to_comment(
            project_id,
            root_comment.id,
            incarnation=document.incarnation,
            expected_revision=initial["revision"],
            mutation_id=reply_mutation_id,
            body=reply_body,
        )
        assert replayed == replied
        assert len(replayed["comment"]["replies"]) == 1

        resolution_mutation_id = "lfwbp-route-comment-resolution"
        resolved = api.set_comment_resolution(
            project_id,
            root_comment.id,
            incarnation=document.incarnation,
            expected_revision=replied["revision"],
            mutation_id=resolution_mutation_id,
            resolved=True,
        )
        assert resolved["revision"] != replied["revision"]
        assert resolved["comment"]["resolved"] is True

        final = api.get_comments(project_id)
        assert final["revision"] == resolved["revision"]
        assert final["comments"] == [resolved["comment"]]

        comment_path = f"/api/comments/{root_comment.id}?doc={project_id}"
        reply_path = (
            f"/api/comments/{root_comment.id}/replies?doc={project_id}"
        )
        assert [
            (method, target, body)
            for method, target, body, _headers in seen_requests
        ] == [
            ("GET", f"/api/comments?doc={project_id}", None),
            ("POST", reply_path, b'{"body":"Please sharpen this transition."}'),
            ("POST", reply_path, b'{"body":"Please sharpen this transition."}'),
            ("PUT", comment_path, b'{"resolved":true}'),
            ("GET", f"/api/comments?doc={project_id}", None),
        ]

        conditional_headers = [
            {
                "x-logosforge-document-incarnation": headers[
                    "x-logosforge-document-incarnation"
                ],
                "x-logosforge-mutation-id": headers[
                    "x-logosforge-mutation-id"
                ],
                "if-match": headers["if-match"],
            }
            for method, _target, _body, headers in seen_requests
            if method in {"POST", "PUT"}
        ]
        reply_headers = {
            "x-logosforge-document-incarnation": document.incarnation,
            "x-logosforge-mutation-id": reply_mutation_id,
            "if-match": (
                f'"lfwb:comments:{document.incarnation}:{initial["revision"]}"'
            ),
        }
        assert conditional_headers == [
            reply_headers,
            reply_headers,
            {
                "x-logosforge-document-incarnation": document.incarnation,
                "x-logosforge-mutation-id": resolution_mutation_id,
                "if-match": (
                    f'"lfwb:comments:{document.incarnation}:{replied["revision"]}"'
                ),
            },
        ]

    stored = comments.get(document_id)
    assert stored.revision == resolved["revision"]
    assert len(stored.comments) == 1
    assert stored.comments[0].resolved is True
    assert len(stored.comments[0].replies) == 1
    assert stored.comments[0].replies[0].id == reply_mutation_id
    assert stored.comments[0].replies[0].body == reply_body
    assert stored.comments[0].replies[0].author == "MCP assistant"
