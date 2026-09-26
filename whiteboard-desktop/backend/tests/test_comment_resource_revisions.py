from __future__ import annotations

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from starlette.datastructures import Headers

import app.document_lifecycle as lifecycle
from app.local_state import (
    CommentAnchor,
    CommentCreate,
    CommentReplyCreate,
    CommentsStore,
    CommentUpdate,
    MutationIdConflict,
    ResourceRevisionConflict,
    WhiteboardCreate,
    WhiteboardStore,
)
from app.resource_revision import resource_etag
from app.routers import comments as comments_router


_REVISION_RE = re.compile(r"^[0-9a-f]{32}$")


class _Core:
    def __init__(self, project_id: int) -> None:
        self.project_id = project_id

    async def request(self, method: str, path: str, **_kwargs):
        assert method == "GET"
        assert path == f"/api/projects/{self.project_id}"
        return SimpleNamespace(json=lambda: {"id": self.project_id})

    async def ensure_project_with_status(self) -> tuple[int, bool]:
        return self.project_id, False

    async def ensure_project(self) -> int:
        return self.project_id


class _Request:
    def __init__(
        self,
        core: _Core,
        headers: dict[str, str] | None = None,
        body: dict | None = None,
    ) -> None:
        self.app = SimpleNamespace(state=SimpleNamespace(core=core))
        self.headers = Headers(headers or {})
        self._body = body

    async def json(self):
        return self._body


def _headers(
    incarnation: str | None,
    *,
    etag: str | None = None,
    mutation_id: str | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if incarnation is not None:
        headers["X-LogosForge-Document-Incarnation"] = incarnation
    if etag is not None:
        headers["If-Match"] = etag
    if mutation_id is not None:
        headers["X-LogosForge-Mutation-Id"] = mutation_id
    return headers


def _install(
    tmp_path: Path,
    monkeypatch,
    project_id: int,
) -> tuple[_Core, WhiteboardStore, CommentsStore, str]:
    core = _Core(project_id)
    whiteboards = WhiteboardStore(tmp_path)
    document = whiteboards.create(
        str(project_id), WhiteboardCreate(title="Comment revisions")
    )
    comments = CommentsStore(tmp_path)
    monkeypatch.setattr(lifecycle, "whiteboard_store", whiteboards)
    monkeypatch.setattr(comments_router, "comments_store", comments)
    return core, whiteboards, comments, document.incarnation


def _seed_comment(store: CommentsStore, document_id: int, comment_id: str = "comment-1"):
    return store.create(
        str(document_id),
        comment_id,
        CommentCreate(
            anchor=CommentAnchor(
                block_index=0,
                block_id="block-1",
                from_offset=0,
                to_offset=4,
                prefix="",
                suffix=" fell",
            ),
            quote="Rain",
            body="Opening note",
        ),
    )


def _get_comments(
    core: _Core,
    incarnation: str,
) -> tuple[object, Response]:
    response = Response()
    result = asyncio.run(
        comments_router.list_comments(
            _Request(core, _headers(incarnation)),
            core.project_id,
            response,
        )
    )
    return result, response


def _resolve(
    core: _Core,
    incarnation: str | None,
    comment_id: str,
    expected_revision: str,
    mutation_id: str,
    resolved: bool,
) -> tuple[object, Response]:
    response = Response()
    raw = {"resolved": resolved}
    result = asyncio.run(
        comments_router.update_comment(
            _Request(
                core,
                _headers(
                    incarnation,
                    etag=(
                        resource_etag("comments", incarnation, expected_revision)
                        if incarnation is not None
                        else resource_etag("comments", "a" * 32, expected_revision)
                    ),
                    mutation_id=mutation_id,
                ),
                raw,
            ),
            comment_id,
            CommentUpdate(**raw),
            core.project_id,
            response,
        )
    )
    return result, response


def _reply(
    core: _Core,
    incarnation: str,
    comment_id: str,
    expected_revision: str,
    mutation_id: str,
    body: str,
) -> tuple[object, Response]:
    response = Response()
    raw = {"body": body}
    result = asyncio.run(
        comments_router.add_reply(
            _Request(
                core,
                _headers(
                    incarnation,
                    etag=resource_etag(
                        "comments", incarnation, expected_revision
                    ),
                    mutation_id=mutation_id,
                ),
                raw,
            ),
            comment_id,
            CommentReplyCreate(**raw),
            core.project_id,
            response,
        )
    )
    return result, response


def test_legacy_file_gets_one_stable_revision_and_empty_state_is_persisted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "comments" / "7.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "comments": [
                    {
                        "id": "legacy",
                        "anchor": {
                            "block_index": 0,
                            "from_offset": 0,
                            "to_offset": 4,
                        },
                        "quote": "Rain",
                        "body": "Keep this",
                        "resolved": False,
                        "replies": [],
                        "created_at": "2025-01-02T03:04:05+00:00",
                        "updated_at": "2025-01-02T03:04:05+00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = CommentsStore(tmp_path)

    first = store.get("7")
    second = store.get("7")

    assert _REVISION_RE.fullmatch(first.revision)
    assert second.revision == first.revision
    assert second.comments[0].body == "Keep this"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["revision"] == first.revision
    assert stored["last_mutation_id"] == ""

    empty = store.get("8")
    assert _REVISION_RE.fullmatch(empty.revision)
    assert store.get("8").revision == empty.revision
    assert (tmp_path / "comments" / "8.json").exists()


def test_get_and_legacy_update_keep_raw_comment_body_and_publish_collection_etag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 940101
    core, _whiteboards, comments, incarnation = _install(
        tmp_path, monkeypatch, project_id
    )
    _seed_comment(comments, project_id)

    loaded, get_response = _get_comments(core, incarnation)
    assert get_response.headers["etag"] == resource_etag(
        "comments", incarnation, loaded.revision
    )

    response = Response()
    updated = asyncio.run(
        comments_router.update_comment(
            _Request(core, _headers(incarnation), {"body": "Edited by the writer"}),
            "comment-1",
            CommentUpdate(body="Edited by the writer"),
            project_id,
            response,
        )
    )

    assert updated.id == "comment-1"
    assert updated.body == "Edited by the writer"
    assert not hasattr(updated, "comment")
    current = comments.get(str(project_id))
    assert current.revision != loaded.revision
    assert response.headers["etag"] == resource_etag(
        "comments", incarnation, current.revision
    )


def test_conditional_routes_require_the_complete_header_triplet(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 940102
    core, _whiteboards, comments, incarnation = _install(
        tmp_path, monkeypatch, project_id
    )
    _seed_comment(comments, project_id)
    current = comments.get(str(project_id))
    etag = resource_etag("comments", incarnation, current.revision)

    attempts = [
        (
            _Request(core, _headers(incarnation, etag=etag), {"resolved": True}),
            "mutation_id_required",
        ),
        (
            _Request(
                core,
                _headers(incarnation, mutation_id="comment-resolution-1"),
                {"resolved": True},
            ),
            "revision_precondition_required",
        ),
    ]
    for request, code in attempts:
        with pytest.raises(HTTPException) as caught:
            asyncio.run(
                comments_router.update_comment(
                    request,
                    "comment-1",
                    CommentUpdate(resolved=True),
                    project_id,
                    Response(),
                )
            )
        assert caught.value.status_code == 428
        assert caught.value.detail["code"] == code

    with pytest.raises(HTTPException) as missing_incarnation:
        asyncio.run(
            comments_router.add_reply(
                _Request(
                    core,
                    _headers(
                        None,
                        etag=resource_etag(
                            "comments", "a" * 32, current.revision
                        ),
                        mutation_id="comment-reply-1",
                    ),
                    {"body": "A reply"},
                ),
                "comment-1",
                CommentReplyCreate(body="A reply"),
                project_id,
                Response(),
            )
        )
    assert missing_incarnation.value.status_code == 428
    assert comments.get(str(project_id)).revision == current.revision


def test_conditional_resolution_rejects_stale_and_wrong_resource_etags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 940103
    core, _whiteboards, comments, incarnation = _install(
        tmp_path, monkeypatch, project_id
    )
    _seed_comment(comments, project_id)
    initial = comments.get(str(project_id))

    resolved, response = _resolve(
        core,
        incarnation,
        "comment-1",
        initial.revision,
        "comment-resolution-1",
        True,
    )
    current = comments.get(str(project_id))
    assert resolved.resolved is True
    assert current.revision != initial.revision
    assert response.headers["etag"] == resource_etag(
        "comments", incarnation, current.revision
    )

    retried, retry_response = _resolve(
        core,
        incarnation,
        "comment-1",
        initial.revision,
        "comment-resolution-1",
        True,
    )
    assert retried.resolved is True
    assert comments.get(str(project_id)).revision == current.revision
    assert retry_response.headers["etag"] == response.headers["etag"]

    with pytest.raises(HTTPException) as reused:
        _resolve(
            core,
            incarnation,
            "comment-1",
            initial.revision,
            "comment-resolution-1",
            False,
        )
    assert reused.value.status_code == 409
    assert reused.value.detail["code"] == "mutation_id_conflict"

    with pytest.raises(HTTPException) as stale:
        _resolve(
            core,
            incarnation,
            "comment-1",
            initial.revision,
            "comment-resolution-2",
            False,
        )
    assert stale.value.status_code == 409
    assert stale.value.detail["code"] == "revision_conflict"
    assert stale.value.detail["current_revision"] == current.revision

    wrong_headers = _headers(
        incarnation,
        etag=resource_etag("outline", incarnation, current.revision),
        mutation_id="comment-resolution-3",
    )
    with pytest.raises(HTTPException) as wrong_kind:
        asyncio.run(
            comments_router.update_comment(
                _Request(core, wrong_headers, {"resolved": False}),
                "comment-1",
                CommentUpdate(resolved=False),
                project_id,
                Response(),
            )
        )
    assert wrong_kind.value.status_code == 409
    assert wrong_kind.value.detail["code"] == "revision_conflict"
    assert comments.get(str(project_id)).comments[0].resolved is True


def test_conditional_reply_has_durable_exact_retry_and_reuse_conflicts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 940104
    core, _whiteboards, comments, incarnation = _install(
        tmp_path, monkeypatch, project_id
    )
    _seed_comment(comments, project_id)
    initial = comments.get(str(project_id))

    first, first_response = _reply(
        core,
        incarnation,
        "comment-1",
        initial.revision,
        "comment-reply-1",
        "Clarify this image.",
    )
    first_revision = comments.get(str(project_id)).revision
    assert [(reply.id, reply.author, reply.body) for reply in first.replies] == [
        ("comment-reply-1", "MCP assistant", "Clarify this image.")
    ]
    assert first_response.headers["etag"] == resource_etag(
        "comments", incarnation, first_revision
    )

    # A fresh store proves the receipt was persisted rather than cached in the
    # route or process-local proposal state.
    durable = CommentsStore(tmp_path)
    monkeypatch.setattr(comments_router, "comments_store", durable)
    retried, retry_response = _reply(
        core,
        incarnation,
        "comment-1",
        initial.revision,
        "comment-reply-1",
        "Clarify this image.",
    )
    assert len(retried.replies) == 1
    assert durable.get(str(project_id)).revision == first_revision
    assert retry_response.headers["etag"] == first_response.headers["etag"]

    with pytest.raises(HTTPException) as changed_body:
        _reply(
            core,
            incarnation,
            "comment-1",
            initial.revision,
            "comment-reply-1",
            "Different content.",
        )
    assert changed_body.value.status_code == 409
    assert changed_body.value.detail["code"] == "mutation_id_conflict"

    with pytest.raises(HTTPException) as changed_revision:
        _reply(
            core,
            incarnation,
            "comment-1",
            first_revision,
            "comment-reply-1",
            "Clarify this image.",
        )
    assert changed_revision.value.status_code == 409
    assert changed_revision.value.detail["code"] == "mutation_id_conflict"

    raw = json.loads(
        (tmp_path / "comments" / f"{project_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert raw["last_mutation_id"] == "comment-reply-1"
    assert raw["last_mutation_comment_id"] == "comment-1"
    assert "last_mutation_id" not in durable.get(str(project_id)).model_dump()


def test_only_one_concurrent_comment_writer_from_a_revision_commits(
    tmp_path: Path,
) -> None:
    store = CommentsStore(tmp_path)
    _seed_comment(store, 940105)
    initial = store.get("940105")

    def resolve(entry: tuple[str, bool]) -> str:
        mutation_id, value = entry
        try:
            result = store.update(
                "940105",
                "comment-1",
                CommentUpdate(resolved=value),
                expected_revision=initial.revision,
                mutation_id=mutation_id,
            )
            assert result is not None
            return "saved"
        except ResourceRevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(
            executor.map(
                resolve,
                [("comment-resolution-alpha", True), ("comment-resolution-beta", False)],
            )
        )
    assert sorted(outcomes) == ["conflict", "saved"]


def test_legacy_mutation_invalidates_conditional_retry_receipt(
    tmp_path: Path,
) -> None:
    store = CommentsStore(tmp_path)
    _seed_comment(store, 940106)
    initial = store.get("940106")
    payload = CommentReplyCreate(body="Conditional", author="MCP assistant")
    first = store.add_reply(
        "940106",
        "comment-1",
        "comment-reply-legacy-invalidation",
        payload,
        expected_revision=initial.revision,
        mutation_id="comment-reply-legacy-invalidation",
    )
    assert first is not None
    conditional_revision = store.get("940106").revision

    legacy = store.update(
        "940106", "comment-1", CommentUpdate(body="Writer changed this")
    )
    assert legacy is not None
    current = store.get("940106")
    assert current.revision != conditional_revision
    raw = json.loads(
        (tmp_path / "comments" / "940106.json").read_text(encoding="utf-8")
    )
    assert raw["last_mutation_id"] == ""
    assert raw["last_mutation_fingerprint"] == ""
    assert raw["last_mutation_comment_id"] == ""

    with pytest.raises(ResourceRevisionConflict):
        store.add_reply(
            "940106",
            "comment-1",
            "comment-reply-legacy-invalidation",
            payload,
            expected_revision=initial.revision,
            mutation_id="comment-reply-legacy-invalidation",
        )


def test_recovery_rotates_revision_and_clears_conditional_receipt(
    tmp_path: Path,
) -> None:
    store = CommentsStore(tmp_path)
    _seed_comment(store, 940107)
    initial = store.get("940107")
    reply_payload = CommentReplyCreate(body="Durable", author="MCP assistant")
    replied = store.add_reply(
        "940107",
        "comment-1",
        "comment-reply-recovery",
        reply_payload,
        expected_revision=initial.revision,
        mutation_id="comment-reply-recovery",
    )
    assert replied is not None
    reply_revision = store.get("940107").revision
    resolved = store.update(
        "940107",
        "comment-1",
        CommentUpdate(resolved=True),
        expected_revision=reply_revision,
        mutation_id="comment-resolution-recovery",
    )
    assert resolved is not None
    current_revision = store.get("940107").revision
    path = tmp_path / "comments" / "940107.json"
    backup = json.loads(path.with_name(path.name + ".bak").read_text(encoding="utf-8"))
    assert backup["revision"] == reply_revision
    assert backup["last_mutation_id"] == "comment-reply-recovery"
    path.write_text("{broken", encoding="utf-8")

    recovered = store.get("940107")
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert recovered.comments[0].resolved is False
    assert len(recovered.comments[0].replies) == 1
    assert recovered.revision not in {reply_revision, current_revision}
    assert persisted["last_mutation_id"] == ""
    assert persisted["last_mutation_fingerprint"] == ""
    assert persisted["last_mutation_comment_id"] == ""

    with pytest.raises(ResourceRevisionConflict):
        store.add_reply(
            "940107",
            "comment-1",
            "comment-reply-recovery",
            reply_payload,
            expected_revision=initial.revision,
            mutation_id="comment-reply-recovery",
        )


def test_every_successful_legacy_mutation_rotates_and_clears_receipt(
    tmp_path: Path,
) -> None:
    store = CommentsStore(tmp_path)
    revisions = [store.get("940108").revision]
    _seed_comment(store, 940108)
    revisions.append(store.get("940108").revision)
    assert store.update(
        "940108", "comment-1", CommentUpdate(resolved=True)
    ) is not None
    revisions.append(store.get("940108").revision)
    assert store.add_reply(
        "940108",
        "comment-1",
        "writer-reply",
        CommentReplyCreate(body="Writer reply", client_id="writer-reply"),
    ) is not None
    revisions.append(store.get("940108").revision)
    assert store.delete_reply("940108", "comment-1", "writer-reply") is not None
    revisions.append(store.get("940108").revision)
    assert store.delete_comment("940108", "comment-1")
    revisions.append(store.get("940108").revision)

    assert len(set(revisions)) == len(revisions)
    raw = json.loads(
        (tmp_path / "comments" / "940108.json").read_text(encoding="utf-8")
    )
    assert raw["last_mutation_id"] == ""
    assert raw["last_mutation_fingerprint"] == ""
    assert raw["last_mutation_comment_id"] == ""


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"resolved": True, "body": "not allowed"},
        {"resolved": "true"},
        {"body": "not a resolution"},
    ],
)
def test_conditional_update_accepts_only_one_boolean_resolved_field(
    tmp_path: Path,
    monkeypatch,
    raw: dict,
) -> None:
    project_id = 940109
    core, _whiteboards, comments, incarnation = _install(
        tmp_path, monkeypatch, project_id
    )
    _seed_comment(comments, project_id)
    current = comments.get(str(project_id))
    payload = CommentUpdate.model_validate(raw)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            comments_router.update_comment(
                _Request(
                    core,
                    _headers(
                        incarnation,
                        etag=resource_etag(
                            "comments", incarnation, current.revision
                        ),
                        mutation_id="comment-resolution-invalid",
                    ),
                    raw,
                ),
                "comment-1",
                payload,
                project_id,
                Response(),
            )
        )
    assert caught.value.status_code == 422
    assert comments.get(str(project_id)).revision == current.revision


@pytest.mark.parametrize(
    "body",
    ["", "   ", " leading", "trailing ", "@Billy revise this", "Ask @LOGOS now"],
)
def test_conditional_reply_rejects_blank_untrimmed_and_ai_mentions(
    tmp_path: Path,
    monkeypatch,
    body: str,
) -> None:
    project_id = 940110
    core, _whiteboards, comments, incarnation = _install(
        tmp_path, monkeypatch, project_id
    )
    _seed_comment(comments, project_id)
    current = comments.get(str(project_id))

    with pytest.raises(HTTPException) as caught:
        _reply(
            core,
            incarnation,
            "comment-1",
            current.revision,
            "comment-reply-invalid",
            body,
        )
    assert caught.value.status_code == 422
    assert comments.get(str(project_id)).revision == current.revision


def test_conditional_reply_is_bounded_and_never_calls_ai_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = 940111
    core, _whiteboards, comments, incarnation = _install(
        tmp_path, monkeypatch, project_id
    )
    _seed_comment(comments, project_id)
    initial = comments.get(str(project_id))
    ai_calls = 0

    async def forbidden_ai(*_args, **_kwargs):
        nonlocal ai_calls
        ai_calls += 1
        raise AssertionError("conditional comments must not call an AI provider")

    monkeypatch.setattr(comments_router, "maybe_ai_reply", forbidden_ai)
    updated, _response = _reply(
        core,
        incarnation,
        "comment-1",
        initial.revision,
        "comment-reply-no-provider",
        "A" * comments_router.MAX_CONDITIONAL_REPLY_CHARACTERS,
    )
    assert len(updated.replies[0].body) == comments_router.MAX_CONDITIONAL_REPLY_CHARACTERS
    assert updated.replies[0].author == "MCP assistant"
    assert ai_calls == 0

    current = comments.get(str(project_id))
    with pytest.raises(HTTPException) as oversized:
        _reply(
            core,
            incarnation,
            "comment-1",
            current.revision,
            "comment-reply-too-large",
            "B" * (comments_router.MAX_CONDITIONAL_REPLY_CHARACTERS + 1),
        )
    assert oversized.value.status_code == 422
    assert ai_calls == 0


def test_mutation_id_reuse_with_different_comment_or_operation_is_rejected(
    tmp_path: Path,
) -> None:
    store = CommentsStore(tmp_path)
    _seed_comment(store, 940112, "comment-1")
    _seed_comment(store, 940112, "comment-2")
    initial = store.get("940112")
    first = store.update(
        "940112",
        "comment-1",
        CommentUpdate(resolved=True),
        expected_revision=initial.revision,
        mutation_id="comment-shared-mutation",
    )
    assert first is not None

    with pytest.raises(MutationIdConflict):
        store.update(
            "940112",
            "comment-2",
            CommentUpdate(resolved=True),
            expected_revision=initial.revision,
            mutation_id="comment-shared-mutation",
        )
    with pytest.raises(MutationIdConflict):
        store.add_reply(
            "940112",
            "comment-1",
            "comment-shared-mutation",
            CommentReplyCreate(body="Different operation", author="MCP assistant"),
            expected_revision=initial.revision,
            mutation_id="comment-shared-mutation",
        )
