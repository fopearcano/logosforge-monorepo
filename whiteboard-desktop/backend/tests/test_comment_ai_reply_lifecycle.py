from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.document_lifecycle as lifecycle
from app.document_lifecycle import DOCUMENT_INCARNATION_HEADER
from app.local_state import (
    CommentAnchor,
    CommentCreate,
    CommentReplyCreate,
    CommentsStore,
    WhiteboardCreate,
    WhiteboardStore,
)
from app.routers import comments as comments_router
from app.routers import littleboy as littleboy_router


class _Core:
    def __init__(self, project_id: int) -> None:
        self.project_id = project_id

    async def request(self, _method: str, _path: str, **_kwargs):
        return SimpleNamespace()


def _request(core: _Core, incarnation: str):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(core=core)),
        headers={DOCUMENT_INCARNATION_HEADER: incarnation},
    )


def test_interrupted_mention_retry_generates_one_deterministic_assistant_reply(
    tmp_path: Path,
    monkeypatch,
) -> None:
    document_id = 992001
    whiteboards = WhiteboardStore(tmp_path)
    document = whiteboards.create(str(document_id), WhiteboardCreate(title="Story"))
    comments = CommentsStore(tmp_path)
    comments.create(
        str(document_id),
        "comment-1",
        CommentCreate(
            anchor=CommentAnchor(block_index=0, from_offset=0, to_offset=4),
            quote="Rain",
            body="Opening note",
        ),
    )
    monkeypatch.setattr(lifecycle, "whiteboard_store", whiteboards)
    monkeypatch.setattr(comments_router, "comments_store", comments)
    monkeypatch.setattr(littleboy_router, "comments_store", comments)

    ai_calls = 0
    generation_started = asyncio.Event()
    finish_generation = asyncio.Event()

    async def controlled_ai_reply(_core, _pid, assistant, _comment) -> str:
        nonlocal ai_calls
        ai_calls += 1
        if ai_calls == 1:
            # The writer reply is already durable when provider work begins.
            raise asyncio.CancelledError
        generation_started.set()
        await finish_generation.wait()
        return f"Reply from {assistant}"

    monkeypatch.setattr(littleboy_router, "ai_reply_to_comment", controlled_ai_reply)
    core = _Core(document_id)
    payload = CommentReplyCreate(
        body="@Billy can you help?",
        client_id="writer-reply-1",
    )

    async def scenario() -> None:
        with pytest.raises(asyncio.CancelledError):
            await comments_router.add_reply(
                _request(core, document.incarnation),
                "comment-1",
                payload,
                document_id,
            )

        after_interruption = comments.get(str(document_id)).comments[0]
        assert [reply.id for reply in after_interruption.replies] == ["writer-reply-1"]

        # Two concurrent delivery retries serialize at the existing lifecycle
        # lock. The first fills the missing AI reply; the second observes it.
        first_retry = asyncio.create_task(
            comments_router.add_reply(
                _request(core, document.incarnation),
                "comment-1",
                payload,
                document_id,
            )
        )
        await generation_started.wait()
        second_retry = asyncio.create_task(
            comments_router.add_reply(
                _request(core, document.incarnation),
                "comment-1",
                payload,
                document_id,
            )
        )
        await asyncio.sleep(0)
        assert not second_retry.done()

        finish_generation.set()
        first, second = await asyncio.gather(first_retry, second_retry)
        expected_ai_id = littleboy_router._assistant_reply_id(
            "comment-1",
            "writer-reply-1",
            "Billy",
        )
        for result in (first, second):
            assert [reply.id for reply in result.replies] == [
                "writer-reply-1",
                expected_ai_id,
            ]

        saved = comments.get(str(document_id)).comments[0]
        assert [reply.id for reply in saved.replies].count(expected_ai_id) == 1
        assert ai_calls == 2  # interrupted attempt + one successful retry

    asyncio.run(scenario())


def test_assistant_reply_id_cannot_be_claimed_as_a_client_id() -> None:
    assistant_id = littleboy_router._assistant_reply_id(
        "comment-1",
        "writer-reply-1",
        "Logos",
    )

    assert assistant_id.startswith("ai:")
    with pytest.raises(ValidationError):
        CommentReplyCreate(body="collision", client_id=assistant_id)
