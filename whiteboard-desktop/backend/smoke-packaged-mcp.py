"""End-to-end smoke for a packaged LogosForge Whiteboard MCP bridge.

The input is the unpacked application executable on Windows, the AppImage on
Linux, or the DMG on macOS.  The smoke keeps every runtime artifact in an
isolated temporary directory and only terminates processes proven to belong to
the application process tree it launched.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import mcp
from mcp.client.stdio import stdio_client

EXPECTED_SERVER_NAME = "logosforge-whiteboard"
EXPECTED_SERVER_VERSION = "1.4.0"
EXPECTED_TOOL_NAMES = frozenset(
    {
        "logosforge_whiteboard_get_capabilities",
        "logosforge_whiteboard_list_documents",
        "logosforge_whiteboard_select_document",
        "logosforge_whiteboard_get_current_document",
        "logosforge_whiteboard_get_document_snapshot",
        "logosforge_whiteboard_get_outline",
        "logosforge_whiteboard_get_comments",
        "logosforge_whiteboard_get_psyke",
        "logosforge_whiteboard_get_psyke_relations",
        "logosforge_whiteboard_get_psyke_progressions",
        "logosforge_whiteboard_search",
        "logosforge_whiteboard_propose_manuscript_patch",
        "logosforge_whiteboard_propose_outline_replace",
        "logosforge_whiteboard_propose_comment_reply",
        "logosforge_whiteboard_propose_comment_resolution",
        "logosforge_whiteboard_propose_psyke_entry",
        "logosforge_whiteboard_propose_psyke_patch",
        "logosforge_whiteboard_propose_psyke_relation",
        "logosforge_whiteboard_propose_psyke_progression",
        "logosforge_whiteboard_propose_psyke_progression_patch",
        "logosforge_whiteboard_list_proposals",
        "logosforge_whiteboard_get_proposal",
        "logosforge_whiteboard_discard_proposal",
        "logosforge_whiteboard_apply_proposal",
    }
)
DESCRIPTOR_MAX_BYTES = 16 * 1024
HEALTH_MAX_BYTES = 64 * 1024
API_MAX_BYTES = 1024 * 1024


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _structured(result: object) -> dict[str, Any] | None:
    value = getattr(result, "structuredContent", None)
    if value is None:
        value = getattr(result, "structured_content", None)
    return value if isinstance(value, dict) else None


async def _tool_result(session, name: str, arguments: dict, label: str) -> dict:
    called = await session.call_tool(name, arguments)
    value = _structured(called)
    result = value.get("result") if isinstance(value, dict) else None
    if (
        called.isError
        or not isinstance(value, dict)
        or value.get("ok") is not True
        or not isinstance(result, dict)
    ):
        raise RuntimeError(f"Packaged Whiteboard MCP {label} failed")
    return result


async def _propose_and_apply(session, name: str, arguments: dict, label: str) -> dict:
    proposal = await _tool_result(session, name, arguments, f"{label} proposal")
    proposal_id = proposal.get("proposal_id")
    if proposal.get("state") != "pending" or not isinstance(proposal_id, str):
        raise RuntimeError(f"Packaged Whiteboard MCP {label} proposal was invalid")
    applied = await _tool_result(
        session,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal_id},
        f"{label} apply",
    )
    receipt = applied.get("result")
    if applied.get("state") != "applied" or not isinstance(receipt, dict):
        raise RuntimeError(f"Packaged Whiteboard MCP {label} apply was invalid")
    return receipt


async def _exercise_psyke_graph_progression(
    session,
    document_id: int,
    source_entry_id: int,
    expected_revision: str,
    flavor: str,
) -> None:
    target_name = f"{flavor} MCP archive " + secrets.token_hex(4)
    target_receipt = await _propose_and_apply(
        session,
        "logosforge_whiteboard_propose_psyke_entry",
        {
            "document_id": document_id,
            "expected_revision": expected_revision,
            "entry": {
                "name": target_name,
                "entry_type": "place",
                "description": "A disposable story-bible location.",
                "notes": "Created for graph/progression smoke coverage.",
            },
        },
        "second PSYKE entry",
    )
    target_element = target_receipt.get("element")
    if not isinstance(target_element, dict) or not isinstance(
        target_receipt.get("revision"), str
    ):
        raise RuntimeError("Packaged Whiteboard MCP second PSYKE receipt was invalid")
    try:
        target_entry_id = int(target_element["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Packaged Whiteboard MCP second PSYKE id was invalid") from exc

    relations = await _tool_result(
        session,
        "logosforge_whiteboard_get_psyke_relations",
        {"document_id": document_id, "offset": 0, "limit": 200},
        "PSYKE relationship read",
    )
    if relations.get("revision") != target_receipt["revision"]:
        raise RuntimeError("Packaged Whiteboard MCP relationship revision diverged")
    relation_receipt = await _propose_and_apply(
        session,
        "logosforge_whiteboard_propose_psyke_relation",
        {
            "document_id": document_id,
            "source_id": source_entry_id,
            "target_id": target_entry_id,
            "relation_type": "supports_setup",
            "expected_revision": relations["revision"],
        },
        "PSYKE relationship",
    )
    if (
        relation_receipt.get("operation") != "create_relation"
        or relation_receipt.get("source_id") != source_entry_id
        or relation_receipt.get("target_id") != target_entry_id
        or not isinstance(relation_receipt.get("revision"), str)
    ):
        raise RuntimeError("Packaged Whiteboard MCP relationship receipt was invalid")

    progressions = await _tool_result(
        session,
        "logosforge_whiteboard_get_psyke_progressions",
        {"document_id": document_id, "offset": 0, "limit": 200},
        "PSYKE progression read",
    )
    if progressions.get("revision") != relation_receipt["revision"]:
        raise RuntimeError("Packaged Whiteboard MCP progression revision diverged")
    progression_receipt = await _propose_and_apply(
        session,
        "logosforge_whiteboard_propose_psyke_progression",
        {
            "document_id": document_id,
            "entry_id": source_entry_id,
            "text": "The keeper first refuses the archive's call.",
            "scene_id": None,
            "expected_revision": progressions["revision"],
        },
        "PSYKE progression",
    )
    progression_id = progression_receipt.get("progression_id")
    if (
        progression_receipt.get("operation") != "create_progression"
        or not isinstance(progression_id, int)
        or progression_receipt.get("entry_id") != source_entry_id
        or not isinstance(progression_receipt.get("revision"), str)
    ):
        raise RuntimeError("Packaged Whiteboard MCP progression receipt was invalid")

    patched_text = "The keeper accepts the archive's call."
    patch_receipt = await _propose_and_apply(
        session,
        "logosforge_whiteboard_propose_psyke_progression_patch",
        {
            "document_id": document_id,
            "progression_id": progression_id,
            "expected_revision": progression_receipt["revision"],
            "patch": {"text": patched_text},
        },
        "PSYKE progression patch",
    )
    if (
        patch_receipt.get("operation") != "patch_progression"
        or patch_receipt.get("progression_id") != progression_id
        or not isinstance(patch_receipt.get("revision"), str)
    ):
        raise RuntimeError("Packaged Whiteboard MCP progression patch receipt was invalid")

    final_relations = await _tool_result(
        session,
        "logosforge_whiteboard_get_psyke_relations",
        {"document_id": document_id, "offset": 0, "limit": 200},
        "final PSYKE relationship read",
    )
    final_progressions = await _tool_result(
        session,
        "logosforge_whiteboard_get_psyke_progressions",
        {"document_id": document_id, "offset": 0, "limit": 200},
        "final PSYKE progression read",
    )
    final_entries = await _tool_result(
        session,
        "logosforge_whiteboard_get_psyke",
        {"document_id": document_id, "offset": 0, "limit": 200},
        "final aggregate PSYKE read",
    )
    revision = patch_receipt["revision"]
    relation_items = final_relations.get("relations")
    progression_items = final_progressions.get("progressions")
    if (
        final_relations.get("revision") != revision
        or final_progressions.get("revision") != revision
        or final_entries.get("revision") != revision
        or not isinstance(relation_items, list)
        or not any(
            isinstance(item, dict)
            and {item.get("source_id"), item.get("target_id")}
            == {source_entry_id, target_entry_id}
            for item in relation_items
        )
        or not isinstance(progression_items, list)
        or not any(
            isinstance(item, dict)
            and item.get("id") == progression_id
            and item.get("text") == patched_text
            for item in progression_items
        )
    ):
        raise RuntimeError("Packaged Whiteboard MCP PSYKE graph verification failed")


async def _exercise_installed_mcp(
    command: Path,
    env: dict[str, str],
    *,
    allow_writes: bool,
    seed_document_id: int,
    seed_comment_id: str,
) -> None:
    mcp_env = env.copy()
    if allow_writes:
        mcp_env["LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES"] = "1"
    else:
        mcp_env.pop("LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES", None)
    params = mcp.StdioServerParameters(
        command=str(command),
        args=[],
        cwd=str(command.parent),
        env=mcp_env,
    )
    async with (
        stdio_client(params) as streams,
        mcp.ClientSession(*streams) as session,
    ):
        initialized = await session.initialize()
        if (
            initialized.serverInfo.name != EXPECTED_SERVER_NAME
            or initialized.serverInfo.version != EXPECTED_SERVER_VERSION
        ):
            raise RuntimeError(
                "unexpected MCP server identity: "
                f"{initialized.serverInfo.name!r} "
                f"version {initialized.serverInfo.version!r}"
            )

        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        if len(listed.tools) != len(EXPECTED_TOOL_NAMES) or names != EXPECTED_TOOL_NAMES:
            raise RuntimeError(
                "packaged Whiteboard MCP advertised an unexpected tool registry: "
                f"{sorted(names)!r}"
            )
        for tool in listed.tools:
            annotations = tool.annotations
            if not annotations or annotations.openWorldHint is not False:
                raise RuntimeError(f"unsafe MCP annotations on {tool.name}")
            if tool.name == "logosforge_whiteboard_apply_proposal":
                safe = (
                    annotations.readOnlyHint is False
                    and annotations.destructiveHint is True
                    and annotations.idempotentHint is False
                )
            elif tool.name == "logosforge_whiteboard_discard_proposal":
                safe = (
                    annotations.readOnlyHint is False
                    and annotations.destructiveHint is False
                    and annotations.idempotentHint is False
                )
            elif tool.name in {
                "logosforge_whiteboard_propose_manuscript_patch",
                "logosforge_whiteboard_propose_outline_replace",
                "logosforge_whiteboard_propose_comment_reply",
                "logosforge_whiteboard_propose_comment_resolution",
                "logosforge_whiteboard_propose_psyke_entry",
                "logosforge_whiteboard_propose_psyke_patch",
                "logosforge_whiteboard_propose_psyke_relation",
                "logosforge_whiteboard_propose_psyke_progression",
                "logosforge_whiteboard_propose_psyke_progression_patch",
            }:
                safe = (
                    annotations.readOnlyHint is True
                    and annotations.destructiveHint is False
                    and annotations.idempotentHint is False
                )
            else:
                safe = (
                    annotations.readOnlyHint is True
                    and annotations.destructiveHint is False
                    and annotations.idempotentHint is True
                )
            if not safe:
                raise RuntimeError(f"unsafe MCP annotations on {tool.name}")

        capabilities = await session.call_tool(
            "logosforge_whiteboard_get_capabilities", {}
        )
        capabilities_value = _structured(capabilities)
        capabilities_result = (
            capabilities_value.get("result")
            if isinstance(capabilities_value, dict)
            else None
        )
        expected_read_only = not allow_writes
        if (
            capabilities.isError
            or not capabilities_value
            or capabilities_value.get("ok") is not True
            or not isinstance(capabilities_result, dict)
            or capabilities_result.get("server") != EXPECTED_SERVER_NAME
            or capabilities_result.get("version") != EXPECTED_SERVER_VERSION
            or capabilities_result.get("read_only") is not expected_read_only
            or capabilities_result.get("writes_available") is not allow_writes
        ):
            raise RuntimeError("packaged Whiteboard MCP capabilities read failed")

        documents = await session.call_tool(
            "logosforge_whiteboard_list_documents", {"offset": 0, "limit": 10}
        )
        documents_value = _structured(documents)
        documents_result = (
            documents_value.get("result")
            if isinstance(documents_value, dict)
            else None
        )
        if (
            documents.isError
            or not documents_value
            or documents_value.get("ok") is not True
            or not isinstance(documents_result, dict)
            or not isinstance(documents_result.get("documents"), list)
            or not documents_result["documents"]
        ):
            raise RuntimeError("authenticated Whiteboard document-list read failed")
        matching_document = next(
            (
                item
                for item in documents_result["documents"]
                if isinstance(item, dict) and str(item.get("id")) == str(seed_document_id)
            ),
            None,
        )
        if matching_document is None:
            raise RuntimeError("packaged Whiteboard MCP omitted the disposable smoke document")
        document_id = seed_document_id
        snapshot = await session.call_tool(
            "logosforge_whiteboard_get_document_snapshot",
            {
                "document_id": document_id,
                "offset": 0,
                "limit": 1,
                "max_characters": 1_000,
            },
        )
        snapshot_value = _structured(snapshot)
        document = (
            snapshot_value.get("result", {}).get("document")
            if isinstance(snapshot_value, dict)
            else None
        )
        if (
            snapshot.isError
            or not isinstance(document, dict)
            or not isinstance(document.get("revision"), str)
            or not isinstance(document.get("title"), str)
        ):
            raise RuntimeError("packaged Whiteboard MCP manuscript snapshot failed")
        title = (
            "Packaged MCP write-disabled smoke "
            if not allow_writes
            else "Packaged MCP write smoke "
        ) + secrets.token_hex(4)
        proposed = await session.call_tool(
            "logosforge_whiteboard_propose_manuscript_patch",
            {
                "document_id": document_id,
                "expected_revision": document["revision"],
                "patch": {"title": title},
            },
        )
        proposed_value = _structured(proposed)
        proposal = (
            proposed_value.get("result")
            if isinstance(proposed_value, dict)
            else None
        )
        if (
            proposed.isError
            or not isinstance(proposal, dict)
            or proposal.get("state") != "pending"
            or not isinstance(proposal.get("proposal_id"), str)
            or proposal.get("request", {}).get("body_page", {}).get("complete") is not True
        ):
            raise RuntimeError("packaged Whiteboard MCP manuscript proposal failed")
        if not allow_writes:
            denied = await session.call_tool(
                "logosforge_whiteboard_apply_proposal",
                {"proposal_id": proposal["proposal_id"]},
            )
            denied_value = _structured(denied)
            if (
                not denied.isError
                or not isinstance(denied_value, dict)
                or denied_value.get("ok") is not False
                or "Writes are disabled" not in str(denied_value.get("error", ""))
            ):
                raise RuntimeError(
                    "packaged Whiteboard MCP default write gate did not deny apply"
                )
            unchanged = await session.call_tool(
                "logosforge_whiteboard_get_document_snapshot",
                {
                    "document_id": document_id,
                    "offset": 0,
                    "limit": 1,
                    "max_characters": 1_000,
                },
            )
            unchanged_value = _structured(unchanged)
            unchanged_document = (
                unchanged_value.get("result", {}).get("document")
                if isinstance(unchanged_value, dict)
                else None
            )
            if (
                unchanged.isError
                or not isinstance(unchanged_document, dict)
                or unchanged_document.get("revision") != document["revision"]
                or unchanged_document.get("title") != document["title"]
            ):
                raise RuntimeError(
                    "packaged Whiteboard project changed after a write-disabled apply"
                )
            return

        applied = await session.call_tool(
            "logosforge_whiteboard_apply_proposal",
            {"proposal_id": proposal["proposal_id"]},
        )
        applied_value = _structured(applied)
        applied_proposal = (
            applied_value.get("result")
            if isinstance(applied_value, dict)
            else None
        )
        receipt = (
            applied_proposal.get("result")
            if isinstance(applied_proposal, dict)
            else None
        )
        if (
            applied.isError
            or not isinstance(applied_proposal, dict)
            or applied_proposal.get("state") != "applied"
            or not isinstance(receipt, dict)
            or receipt.get("title") != title
        ):
            raise RuntimeError("packaged Whiteboard MCP enabled proposal apply failed")

        comments = await session.call_tool(
            "logosforge_whiteboard_get_comments",
            {
                "document_id": document_id,
                "include_resolved": True,
                "offset": 0,
                "limit": 100,
            },
        )
        comments_value = _structured(comments)
        comments_result = (
            comments_value.get("result")
            if isinstance(comments_value, dict)
            else None
        )
        comment_items = (
            comments_result.get("comments")
            if isinstance(comments_result, dict)
            else None
        )
        root_comment = (
            next(
                (
                    item
                    for item in comment_items
                    if isinstance(item, dict)
                    and item.get("id") == seed_comment_id
                ),
                None,
            )
            if isinstance(comment_items, list)
            else None
        )
        if (
            comments.isError
            or not isinstance(comments_result, dict)
            or not isinstance(comments_result.get("revision"), str)
            or not isinstance(root_comment, dict)
            or root_comment.get("resolved") is not False
            or root_comment.get("replies") != []
        ):
            raise RuntimeError("packaged Whiteboard MCP comments read failed")

        reply_body = "Packaged MCP assistant reply " + secrets.token_hex(4)
        reply_proposed = await session.call_tool(
            "logosforge_whiteboard_propose_comment_reply",
            {
                "document_id": document_id,
                "comment_id": seed_comment_id,
                "expected_revision": comments_result["revision"],
                "body": reply_body,
            },
        )
        reply_proposed_value = _structured(reply_proposed)
        reply_proposal = (
            reply_proposed_value.get("result")
            if isinstance(reply_proposed_value, dict)
            else None
        )
        if (
            reply_proposed.isError
            or not isinstance(reply_proposal, dict)
            or reply_proposal.get("state") != "pending"
            or reply_proposal.get("operation") != "reply_to_comment"
            or not isinstance(reply_proposal.get("proposal_id"), str)
        ):
            raise RuntimeError("packaged Whiteboard MCP comment reply proposal failed")
        reply_applied = await session.call_tool(
            "logosforge_whiteboard_apply_proposal",
            {"proposal_id": reply_proposal["proposal_id"]},
        )
        reply_applied_value = _structured(reply_applied)
        reply_applied_proposal = (
            reply_applied_value.get("result")
            if isinstance(reply_applied_value, dict)
            else None
        )
        reply_receipt = (
            reply_applied_proposal.get("result")
            if isinstance(reply_applied_proposal, dict)
            else None
        )
        expected_reply_receipt_keys = {
            "resource",
            "operation",
            "document_id",
            "revision",
            "comment_id",
            "reply_id",
            "reply_count",
            "resolved",
            "updated_at",
        }
        if (
            reply_applied.isError
            or not isinstance(reply_applied_proposal, dict)
            or reply_applied_proposal.get("state") != "applied"
            or not isinstance(reply_receipt, dict)
            or set(reply_receipt) != expected_reply_receipt_keys
            or reply_receipt.get("resource") != "comments"
            or reply_receipt.get("operation") != "reply"
            or reply_receipt.get("document_id") != document_id
            or reply_receipt.get("comment_id") != seed_comment_id
            or reply_receipt.get("reply_id") != reply_proposal["proposal_id"]
            or reply_receipt.get("reply_count") != 1
            or reply_receipt.get("resolved") is not False
            or not isinstance(reply_receipt.get("revision"), str)
            or reply_receipt["revision"] == comments_result["revision"]
            or not isinstance(reply_receipt.get("updated_at"), str)
        ):
            raise RuntimeError("packaged Whiteboard MCP comment reply apply failed")

        replied_comments = await session.call_tool(
            "logosforge_whiteboard_get_comments",
            {
                "document_id": document_id,
                "include_resolved": True,
                "offset": 0,
                "limit": 100,
            },
        )
        replied_value = _structured(replied_comments)
        replied_result = (
            replied_value.get("result")
            if isinstance(replied_value, dict)
            else None
        )
        replied_items = (
            replied_result.get("comments")
            if isinstance(replied_result, dict)
            else None
        )
        replied_comment = (
            next(
                (
                    item
                    for item in replied_items
                    if isinstance(item, dict)
                    and item.get("id") == seed_comment_id
                ),
                None,
            )
            if isinstance(replied_items, list)
            else None
        )
        replies = (
            replied_comment.get("replies")
            if isinstance(replied_comment, dict)
            else None
        )
        if (
            replied_comments.isError
            or not isinstance(replied_result, dict)
            or replied_result.get("revision") != reply_receipt["revision"]
            or not isinstance(replies, list)
            or len(replies) != 1
            or not isinstance(replies[0], dict)
            or replies[0].get("id") != reply_receipt["reply_id"]
            or replies[0].get("author") != "MCP assistant"
            or replies[0].get("body") != reply_body
        ):
            raise RuntimeError("packaged Whiteboard MCP comment reply verification failed")

        resolution_proposed = await session.call_tool(
            "logosforge_whiteboard_propose_comment_resolution",
            {
                "document_id": document_id,
                "comment_id": seed_comment_id,
                "expected_revision": replied_result["revision"],
                "resolved": True,
            },
        )
        resolution_proposed_value = _structured(resolution_proposed)
        resolution_proposal = (
            resolution_proposed_value.get("result")
            if isinstance(resolution_proposed_value, dict)
            else None
        )
        if (
            resolution_proposed.isError
            or not isinstance(resolution_proposal, dict)
            or resolution_proposal.get("state") != "pending"
            or resolution_proposal.get("operation") != "set_comment_resolution"
            or not isinstance(resolution_proposal.get("proposal_id"), str)
        ):
            raise RuntimeError("packaged Whiteboard MCP comment resolution proposal failed")
        resolution_applied = await session.call_tool(
            "logosforge_whiteboard_apply_proposal",
            {"proposal_id": resolution_proposal["proposal_id"]},
        )
        resolution_applied_value = _structured(resolution_applied)
        resolution_applied_proposal = (
            resolution_applied_value.get("result")
            if isinstance(resolution_applied_value, dict)
            else None
        )
        resolution_receipt = (
            resolution_applied_proposal.get("result")
            if isinstance(resolution_applied_proposal, dict)
            else None
        )
        expected_resolution_receipt_keys = {
            "resource",
            "operation",
            "document_id",
            "revision",
            "comment_id",
            "resolved",
            "reply_count",
            "updated_at",
        }
        if (
            resolution_applied.isError
            or not isinstance(resolution_applied_proposal, dict)
            or resolution_applied_proposal.get("state") != "applied"
            or not isinstance(resolution_receipt, dict)
            or set(resolution_receipt) != expected_resolution_receipt_keys
            or resolution_receipt.get("resource") != "comments"
            or resolution_receipt.get("operation") != "resolve"
            or resolution_receipt.get("document_id") != document_id
            or resolution_receipt.get("comment_id") != seed_comment_id
            or resolution_receipt.get("resolved") is not True
            or resolution_receipt.get("reply_count") != 1
            or not isinstance(resolution_receipt.get("revision"), str)
            or resolution_receipt["revision"] == reply_receipt["revision"]
            or not isinstance(resolution_receipt.get("updated_at"), str)
        ):
            raise RuntimeError("packaged Whiteboard MCP comment resolution apply failed")

        final_comments = await session.call_tool(
            "logosforge_whiteboard_get_comments",
            {
                "document_id": document_id,
                "include_resolved": True,
                "offset": 0,
                "limit": 100,
            },
        )
        final_comments_value = _structured(final_comments)
        final_comments_result = (
            final_comments_value.get("result")
            if isinstance(final_comments_value, dict)
            else None
        )
        final_comment_items = (
            final_comments_result.get("comments")
            if isinstance(final_comments_result, dict)
            else None
        )
        final_comment = (
            next(
                (
                    item
                    for item in final_comment_items
                    if isinstance(item, dict)
                    and item.get("id") == seed_comment_id
                ),
                None,
            )
            if isinstance(final_comment_items, list)
            else None
        )
        final_replies = (
            final_comment.get("replies")
            if isinstance(final_comment, dict)
            else None
        )
        if (
            final_comments.isError
            or not isinstance(final_comments_result, dict)
            or final_comments_result.get("revision") != resolution_receipt["revision"]
            or not isinstance(final_comment, dict)
            or final_comment.get("resolved") is not True
            or not isinstance(final_replies, list)
            or len(final_replies) != 1
            or not isinstance(final_replies[0], dict)
            or final_replies[0].get("id") != reply_receipt["reply_id"]
            or final_replies[0].get("author") != "MCP assistant"
            or final_replies[0].get("body") != reply_body
        ):
            raise RuntimeError("packaged Whiteboard MCP comment resolution verification failed")

        psyke = await session.call_tool(
            "logosforge_whiteboard_get_psyke",
            {"document_id": document_id, "offset": 0, "limit": 200},
        )
        psyke_value = _structured(psyke)
        psyke_result = (
            psyke_value.get("result")
            if isinstance(psyke_value, dict)
            else None
        )
        if (
            psyke.isError
            or not isinstance(psyke_result, dict)
            or not isinstance(psyke_result.get("revision"), str)
            or not isinstance(psyke_result.get("entries"), list)
        ):
            raise RuntimeError("packaged Whiteboard MCP PSYKE read failed")

        entry_name = "Packaged MCP character " + secrets.token_hex(4)
        created = await session.call_tool(
            "logosforge_whiteboard_propose_psyke_entry",
            {
                "document_id": document_id,
                "expected_revision": psyke_result["revision"],
                "entry": {
                    "name": entry_name,
                    "entry_type": "character",
                    "description": "Created by the packaged MCP smoke test.",
                    "notes": "Disposable test entry.",
                },
            },
        )
        created_value = _structured(created)
        create_proposal = (
            created_value.get("result")
            if isinstance(created_value, dict)
            else None
        )
        if (
            created.isError
            or not isinstance(create_proposal, dict)
            or create_proposal.get("state") != "pending"
            or not isinstance(create_proposal.get("proposal_id"), str)
        ):
            raise RuntimeError("packaged Whiteboard MCP PSYKE entry proposal failed")
        create_applied = await session.call_tool(
            "logosforge_whiteboard_apply_proposal",
            {"proposal_id": create_proposal["proposal_id"]},
        )
        create_applied_value = _structured(create_applied)
        create_applied_proposal = (
            create_applied_value.get("result")
            if isinstance(create_applied_value, dict)
            else None
        )
        create_receipt = (
            create_applied_proposal.get("result")
            if isinstance(create_applied_proposal, dict)
            else None
        )
        created_element = (
            create_receipt.get("element")
            if isinstance(create_receipt, dict)
            else None
        )
        if (
            create_applied.isError
            or not isinstance(create_applied_proposal, dict)
            or create_applied_proposal.get("state") != "applied"
            or not isinstance(create_receipt, dict)
            or create_receipt.get("resource") != "psyke"
            or not isinstance(create_receipt.get("revision"), str)
            or not isinstance(created_element, dict)
            or created_element.get("name") != entry_name
        ):
            raise RuntimeError("packaged Whiteboard MCP PSYKE entry apply failed")
        try:
            entry_id = int(created_element["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "packaged Whiteboard MCP returned an invalid PSYKE entry id"
            ) from exc

        refreshed = await session.call_tool(
            "logosforge_whiteboard_get_psyke",
            {
                "document_id": document_id,
                "query": entry_name,
                "offset": 0,
                "limit": 10,
            },
        )
        refreshed_value = _structured(refreshed)
        refreshed_result = (
            refreshed_value.get("result")
            if isinstance(refreshed_value, dict)
            else None
        )
        refreshed_entries = (
            refreshed_result.get("entries")
            if isinstance(refreshed_result, dict)
            else None
        )
        if (
            refreshed.isError
            or not isinstance(refreshed_result, dict)
            or refreshed_result.get("revision") != create_receipt["revision"]
            or not isinstance(refreshed_entries, list)
            or not any(
                isinstance(entry, dict)
                and str(entry.get("id")) == str(entry_id)
                and entry.get("name") == entry_name
                for entry in refreshed_entries
            )
        ):
            raise RuntimeError("packaged Whiteboard MCP PSYKE create verification failed")

        patched_description = "Patched by the packaged MCP smoke test."
        patched = await session.call_tool(
            "logosforge_whiteboard_propose_psyke_patch",
            {
                "document_id": document_id,
                "entry_id": entry_id,
                "expected_revision": refreshed_result["revision"],
                "patch": {"description": patched_description},
            },
        )
        patched_value = _structured(patched)
        patch_proposal = (
            patched_value.get("result")
            if isinstance(patched_value, dict)
            else None
        )
        if (
            patched.isError
            or not isinstance(patch_proposal, dict)
            or patch_proposal.get("state") != "pending"
            or not isinstance(patch_proposal.get("proposal_id"), str)
        ):
            raise RuntimeError("packaged Whiteboard MCP PSYKE patch proposal failed")
        patch_applied = await session.call_tool(
            "logosforge_whiteboard_apply_proposal",
            {"proposal_id": patch_proposal["proposal_id"]},
        )
        patch_applied_value = _structured(patch_applied)
        patch_applied_proposal = (
            patch_applied_value.get("result")
            if isinstance(patch_applied_value, dict)
            else None
        )
        patch_receipt = (
            patch_applied_proposal.get("result")
            if isinstance(patch_applied_proposal, dict)
            else None
        )
        patched_element = (
            patch_receipt.get("element")
            if isinstance(patch_receipt, dict)
            else None
        )
        if (
            patch_applied.isError
            or not isinstance(patch_applied_proposal, dict)
            or patch_applied_proposal.get("state") != "applied"
            or not isinstance(patch_receipt, dict)
            or patch_receipt.get("resource") != "psyke"
            or not isinstance(patch_receipt.get("revision"), str)
            or not isinstance(patched_element, dict)
            or str(patched_element.get("id")) != str(entry_id)
            or patched_element.get("description") != patched_description
        ):
            raise RuntimeError("packaged Whiteboard MCP PSYKE patch apply failed")

        final_psyke = await session.call_tool(
            "logosforge_whiteboard_get_psyke",
            {
                "document_id": document_id,
                "query": entry_name,
                "offset": 0,
                "limit": 10,
            },
        )
        final_value = _structured(final_psyke)
        final_result = (
            final_value.get("result")
            if isinstance(final_value, dict)
            else None
        )
        final_entries = (
            final_result.get("entries")
            if isinstance(final_result, dict)
            else None
        )
        if (
            final_psyke.isError
            or not isinstance(final_result, dict)
            or final_result.get("revision") != patch_receipt["revision"]
            or not isinstance(final_entries, list)
            or not any(
                isinstance(entry, dict)
                and str(entry.get("id")) == str(entry_id)
                and entry.get("name") == entry_name
                and entry.get("description") == patched_description
                for entry in final_entries
            )
        ):
            raise RuntimeError(
                "packaged Whiteboard MCP PSYKE patch verification failed"
            )

        await _exercise_psyke_graph_progression(
            session,
            document_id,
            entry_id,
            patch_receipt["revision"],
            "Packaged",
        )


def _process_is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        from ctypes import wintypes

        query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and (
                exit_code.value == still_active
            )
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_parent_map() -> dict[int, int]:
    """Return live process parentage using Toolhelp; called only on Windows."""
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        present = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            present = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return parents


def _is_descendant(pid: int, ancestor: int, parents: dict[int, int]) -> bool:
    current = pid
    seen: set[int] = set()
    while current > 0 and current not in seen:
        if current == ancestor:
            return True
        seen.add(current)
        current = parents.get(current, 0)
    return False


def _validate_owned_pids(
    process: subprocess.Popen[bytes], app_pid: int, backend_pid: int
) -> set[int]:
    candidates = {app_pid, backend_pid}
    if os.getpid() in candidates:
        raise RuntimeError("packaged app descriptor points at the smoke-test process")
    if any(not _process_is_alive(pid) for pid in candidates):
        raise RuntimeError("packaged app descriptor contains a process that is not alive")
    if os.name == "nt":
        parents = _windows_parent_map()
        if any(not _is_descendant(pid, process.pid, parents) for pid in candidates):
            raise RuntimeError("packaged app descriptor contains a process outside its owned tree")
    else:
        try:
            if any(os.getpgid(pid) != process.pid for pid in candidates):
                raise RuntimeError(
                    "packaged app descriptor contains a process outside its owned group"
                )
        except ProcessLookupError as exc:
            raise RuntimeError("a packaged app process exited during validation") from exc
    return candidates


def _stop_owned_process_tree(
    process: subprocess.Popen[bytes], owned_pids: set[int]
) -> None:
    if os.name == "nt":
        if process.poll() is None:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        # A wrapper may have exited before cleanup. These PIDs were accepted
        # only after proving they descended from our launch root.
        for pid in owned_pids:
            if _process_is_alive(pid):
                subprocess.run(
                    ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        return

    # start_new_session=True makes the launch PID the process-group id. This
    # covers AppImage/xvfb wrappers, Electron helpers, and the backend child.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # The group has been signalled already; use the Popen handle only for
        # the launch process, never a PID learned from untrusted state.
        process.kill()
        process.wait(timeout=5)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_size <= 0
            or info.st_size > DESCRIPTOR_MAX_BYTES
        ):
            return None
        if os.name != "nt" and info.st_mode & 0o077:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return None


def _wait_for_descriptor(
    path: Path, process: subprocess.Popen[bytes], timeout: int
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        candidate = _read_json(path)
        if candidate is not None and candidate.get("schema_version") == 1:
            return candidate
        if process.poll() is not None:
            break
        time.sleep(0.5)
    raise RuntimeError(
        f"packaged app did not publish its MCP descriptor (exit={process.poll()})"
    )


def _validate_descriptor(
    descriptor: dict[str, Any], expected_port: int
) -> tuple[str, str, str, int, int]:
    if type(descriptor.get("schema_version")) is not int or descriptor["schema_version"] != 1:
        raise RuntimeError("packaged app published an unsupported MCP descriptor schema")
    base_url = descriptor.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise RuntimeError("packaged app published an invalid backend URL")
    parsed = urllib.parse.urlparse(base_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("packaged app published an invalid backend port") from exc
    if (
        parsed.scheme != "http"
        or (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or port != expected_port
    ):
        raise RuntimeError("packaged app MCP descriptor is not the expected loopback endpoint")

    auth_token = descriptor.get("auth_token")
    nonce = descriptor.get("instance_nonce")
    if (
        not isinstance(auth_token, str)
        or auth_token != auth_token.strip()
        or len(auth_token) < 32
    ):
        raise RuntimeError("packaged app published an invalid MCP bearer token")
    if not isinstance(nonce, str) or nonce != nonce.strip() or len(nonce) < 16:
        raise RuntimeError("packaged app published an invalid backend nonce")
    created_at = descriptor.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise RuntimeError("packaged app published an invalid descriptor timestamp")
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("packaged app published an invalid descriptor timestamp") from exc
    if parsed_created_at.tzinfo is None or parsed_created_at.utcoffset() != timedelta(0):
        raise RuntimeError("packaged app descriptor timestamp is not UTC")

    def required_pid(name: str) -> int:
        value = descriptor.get(name)
        if type(value) is not int or value <= 0:
            raise RuntimeError(f"packaged app published an invalid {name}")
        return value

    return (
        base_url.rstrip("/"),
        auth_token,
        nonce,
        required_pid("app_pid"),
        required_pid("backend_pid"),
    )


def _fetch_health(base_url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url}/health",
        headers={"Accept": "application/json", "User-Agent": "Whiteboard-Packaged-MCP-Smoke"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        raw = response.read(HEALTH_MAX_BYTES + 1)
    if len(raw) > HEALTH_MAX_BYTES:
        raise RuntimeError("packaged Whiteboard backend returned oversized health data")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("packaged Whiteboard backend returned invalid health data") from exc
    if not isinstance(value, dict):
        raise RuntimeError("packaged Whiteboard backend health response is not an object")
    return value


def _authenticated_json(
    base_url: str,
    auth_token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {auth_token}",
        "User-Agent": "Whiteboard-Packaged-MCP-Smoke",
    }
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(API_MAX_BYTES + 1)
    if len(raw) > API_MAX_BYTES:
        raise RuntimeError("packaged Whiteboard API returned oversized smoke data")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("packaged Whiteboard API returned invalid smoke data") from exc
    if not isinstance(value, dict):
        raise RuntimeError("packaged Whiteboard API smoke response is not an object")
    return value


def _create_smoke_document(base_url: str, auth_token: str) -> tuple[int, str]:
    block_id = "packaged-mcp-block-" + secrets.token_hex(8)
    manuscript = "The lantern burned beside the rain-dark window."
    created = _authenticated_json(
        base_url,
        auth_token,
        "POST",
        "/api/documents",
        {
            "title": "Packaged MCP smoke seed " + secrets.token_hex(4),
            "mode": "novel",
            "blocks": [
                {
                    "id": block_id,
                    "type": "paragraph",
                    "text": manuscript,
                }
            ],
        },
    )
    document = created.get("document")
    if created.get("ok") is not True or not isinstance(document, dict):
        raise RuntimeError("packaged Whiteboard API could not create a disposable smoke document")
    try:
        document_id = int(document["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("packaged Whiteboard API returned an invalid smoke document id") from exc
    incarnation = document.get("incarnation")
    if not isinstance(incarnation, str) or len(incarnation) != 32:
        raise RuntimeError("packaged Whiteboard API returned an invalid smoke incarnation")

    comment = _authenticated_json(
        base_url,
        auth_token,
        "POST",
        f"/api/comments?doc={document_id}",
        {
            "anchor": {
                "block_index": 0,
                "block_id": block_id,
                "from_offset": 4,
                "to_offset": 11,
                "prefix": "The ",
                "suffix": " burned beside the rain-dark window.",
            },
            "quote": "lantern",
            "body": "Track the lantern motif through this revision.",
        },
        {"X-LogosForge-Document-Incarnation": incarnation},
    )
    comment_id = comment.get("id")
    if (
        not isinstance(comment_id, str)
        or not comment_id
        or comment.get("quote") != "lantern"
        or comment.get("resolved") is not False
        or comment.get("replies") != []
    ):
        raise RuntimeError("packaged Whiteboard API could not seed a root comment")
    return document_id, comment_id


def _exercise_codex(
    codex_command: str,
    mcp_command: Path,
    descriptor_path: Path,
    work: Path,
) -> None:
    output_path = work / "codex-result.txt"
    prompt = (
        "Use the MCP server named logosforge-whiteboard. Call "
        "logosforge_whiteboard_get_capabilities once and "
        "logosforge_whiteboard_list_documents once. Do not use shell commands or files. "
        "Reply with exactly PACKAGED_WHITEBOARD_MCP_CODEX_OK only if both tools succeed "
        "with ok=true and the capabilities report read_only=true; otherwise report the failure."
    )
    command = [
        codex_command,
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output_path),
        "-c",
        f"mcp_servers.{EXPECTED_SERVER_NAME}.command={json.dumps(str(mcp_command))}",
        "-c",
        f"mcp_servers.{EXPECTED_SERVER_NAME}.args=[]",
        "-c",
        f"mcp_servers.{EXPECTED_SERVER_NAME}.required=true",
        "-c",
        (
            f"mcp_servers.{EXPECTED_SERVER_NAME}.env."
            "LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE="
            f"{json.dumps(str(descriptor_path))}"
        ),
        prompt,
    ]
    codex_env = os.environ.copy()
    codex_env.pop("LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES", None)
    result = subprocess.run(
        command,
        cwd=work,
        env=codex_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=240,
        check=False,
    )
    final = (
        output_path.read_text(encoding="utf-8", errors="replace")
        if output_path.exists()
        else ""
    )
    if result.returncode != 0 or final.strip() != "PACKAGED_WHITEBOARD_MCP_CODEX_OK":
        raise RuntimeError(
            "Local Codex did not validate the packaged Whiteboard MCP companion.\n"
            + result.stdout[-4000:]
            + "\nFinal response: "
            + final[-1000:]
        )
    print("Local Codex completed default-gated reads through logosforge-whiteboard.")


def _launch_command(app: Path, user_data_dir: Path, env: dict[str, str]) -> list[str]:
    command = [str(app), "--disable-gpu", f"--user-data-dir={user_data_dir}"]
    if sys.platform.startswith("linux"):
        if not os.access(app, os.X_OK):
            raise RuntimeError(f"AppImage is not executable: {app}")
        getuid = getattr(os, "getuid", None)
        if getuid is not None and getuid() == 0:
            command.append("--no-sandbox")
        if not env.get("DISPLAY"):
            xvfb_run = shutil.which("xvfb-run")
            if not xvfb_run:
                raise RuntimeError(
                    "Linux packaged smoke requires DISPLAY or xvfb-run for Electron."
                )
            command = [xvfb_run, "-a", "--server-args=-screen 0 1280x1024x24", *command]
    return command


def _smoke_app(app: Path, timeout: int, codex_command: str | None = None) -> None:
    app = app.resolve()
    if not app.is_file():
        raise RuntimeError(f"packaged application is missing: {app}")
    with tempfile.TemporaryDirectory(
        prefix="logosforge-whiteboard-packaged-mcp-",
        ignore_cleanup_errors=True,
    ) as temp:
        work = Path(temp).resolve()
        descriptor_path = (work / "mcp-runtime-v1.json").resolve()
        installed_mcp_path = (
            work
            / (
                "logosforge-whiteboard-mcp.exe"
                if os.name == "nt"
                else "logosforge-whiteboard-mcp"
            )
        ).resolve()
        port = _available_port()
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(work),
                "USERPROFILE": str(work),
                "APPDATA": str(work / "appdata"),
                "LOCALAPPDATA": str(work / "local-appdata"),
                "XDG_CONFIG_HOME": str(work / "config"),
                "LOGOSFORGE_DATA_DIR": str(work / "data"),
                "LOGOSFORGE_DB_PATH": str(work / "whiteboard.db"),
                "LOGOSFORGE_PORT": str(port),
                "LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE": str(descriptor_path),
                "LOGOSFORGE_WHITEBOARD_MCP_LAUNCHER_PATH": str(installed_mcp_path),
                "APPIMAGE_EXTRACT_AND_RUN": "1",
                "ELECTRON_ENABLE_LOGGING": "1",
            }
        )
        log_path = work / "app.log"
        command = _launch_command(app, work / "electron-user-data", env)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        process: subprocess.Popen[bytes] | None = None
        owned_pids: set[int] = set()
        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
                    command,
                    cwd=app.parent,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                    start_new_session=os.name != "nt",
                )
                descriptor = _wait_for_descriptor(descriptor_path, process, timeout)
                base_url, auth_token, nonce, app_pid, backend_pid = _validate_descriptor(
                    descriptor, port
                )
                owned_pids = _validate_owned_pids(process, app_pid, backend_pid)

                health = _fetch_health(base_url)
                if (
                    health.get("status") != "ok"
                    or health.get("service") != "logosforge-whiteboard-backend"
                    or health.get("instance_nonce") != nonce
                ):
                    raise RuntimeError(
                        "packaged Whiteboard backend identity does not match its MCP descriptor"
                    )
                seed_document_id, seed_comment_id = _create_smoke_document(
                    base_url, auth_token
                )

                try:
                    installed_info = installed_mcp_path.lstat()
                except OSError as exc:
                    raise RuntimeError(
                        f"packaged app did not install its MCP companion: {installed_mcp_path}"
                    ) from exc
                if (
                    not stat.S_ISREG(installed_info.st_mode)
                    or stat.S_ISLNK(installed_info.st_mode)
                    or installed_info.st_size <= 0
                    or (os.name != "nt" and not os.access(installed_mcp_path, os.X_OK))
                ):
                    raise RuntimeError("packaged app installed an invalid MCP companion")

                async def exercise_default_and_enabled() -> None:
                    await _exercise_installed_mcp(
                        installed_mcp_path,
                        env,
                        allow_writes=False,
                        seed_document_id=seed_document_id,
                        seed_comment_id=seed_comment_id,
                    )
                    await _exercise_installed_mcp(
                        installed_mcp_path,
                        env,
                        allow_writes=True,
                        seed_document_id=seed_document_id,
                        seed_comment_id=seed_comment_id,
                    )

                asyncio.run(
                    asyncio.wait_for(exercise_default_and_enabled(), timeout=90)
                )
                if codex_command:
                    _exercise_codex(
                        codex_command, installed_mcp_path, descriptor_path, work
                    )
        except Exception:
            if log_path.exists():
                print(log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            raise
        finally:
            if process is not None:
                _stop_owned_process_tree(process, owned_pids)
        print(
            "Packaged Whiteboard published a verified descriptor and served "
            "authenticated MCP reads with writes disabled by default, then "
            "completed disposable enabled manuscript, comment reply/resolution, "
            "and PSYKE entry/relationship/progression proposal/apply round trips."
        )


def smoke(package: Path, timeout: int, codex_command: str | None = None) -> None:
    package = package.resolve()
    if not package.is_file():
        raise RuntimeError(f"packaged application is missing: {package}")
    if timeout <= 0:
        raise RuntimeError("timeout must be greater than zero")

    if sys.platform == "darwin":
        if package.suffix.lower() != ".dmg":
            raise RuntimeError("macOS packaged smoke expects a Whiteboard DMG.")
        with tempfile.TemporaryDirectory(prefix="logosforge-whiteboard-mcp-dmg-") as mount:
            mount_path = Path(mount).resolve()
            subprocess.run(
                [
                    "hdiutil",
                    "attach",
                    str(package),
                    "-nobrowse",
                    "-readonly",
                    "-mountpoint",
                    str(mount_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            try:
                app = (
                    mount_path
                    / "LogosForge Whiteboard.app"
                    / "Contents"
                    / "MacOS"
                    / "LogosForge Whiteboard"
                )
                _smoke_app(app, timeout, codex_command)
            finally:
                subprocess.run(
                    ["hdiutil", "detach", str(mount_path), "-force"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        return

    if package.suffix.lower() == ".dmg":
        raise RuntimeError("A DMG runtime smoke requires macOS.")
    if os.name == "nt" and package.suffix.lower() != ".exe":
        raise RuntimeError("Windows packaged smoke expects an unpacked .exe application.")
    if sys.platform.startswith("linux") and not package.name.lower().endswith(".appimage"):
        raise RuntimeError("Linux packaged smoke expects a Whiteboard AppImage.")
    _smoke_app(package, timeout, codex_command)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a packaged Whiteboard application and validate its installed, "
            "default-gated MCP companion end to end."
        )
    )
    parser.add_argument(
        "package",
        type=Path,
        help="Windows unpacked app executable, Linux AppImage, or macOS DMG",
    )
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument(
        "--codex-command",
        help="optional local Codex executable for an additional MCP read validation",
    )
    args = parser.parse_args()
    smoke(args.package, args.timeout, args.codex_command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
