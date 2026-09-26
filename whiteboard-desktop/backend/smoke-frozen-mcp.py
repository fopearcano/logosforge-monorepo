"""Exercise the frozen Whiteboard backend and MCP companion together.

Usage::

    python smoke-frozen-mcp.py <backend-executable> <mcp-executable>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

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
API_MAX_BYTES = 1024 * 1024


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _health(base_url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
            value = json.load(response)
            return value if isinstance(value, dict) else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _authenticated_json(
    base_url: str,
    auth_token: str,
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    extra_headers: dict[str, str] | None = None,
) -> dict:
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {auth_token}",
        "User-Agent": "Whiteboard-Frozen-MCP-Smoke",
    }
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(API_MAX_BYTES + 1)
    if len(raw) > API_MAX_BYTES:
        raise RuntimeError("frozen Whiteboard API returned oversized smoke data")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("frozen Whiteboard API returned invalid smoke data") from exc
    if not isinstance(value, dict):
        raise RuntimeError("frozen Whiteboard API smoke response is not an object")
    return value


def _seed_comment_document(base_url: str, auth_token: str) -> tuple[int, str]:
    seed_text = "A lantern burned beside the rain-dark window."
    created = _authenticated_json(
        base_url,
        auth_token,
        "POST",
        "/api/documents",
        {
            "title": "Frozen MCP comment smoke seed",
            "mode": "novel",
            "blocks": [
                {"id": "smoke-block-1", "type": "paragraph", "text": seed_text}
            ],
        },
    )
    document = created.get("document")
    if created.get("ok") is not True or not isinstance(document, dict):
        raise RuntimeError("frozen Whiteboard API could not create a smoke document")
    try:
        document_id = int(document["id"])
        incarnation = str(document["incarnation"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("frozen Whiteboard API returned an invalid smoke document") from exc
    if len(incarnation) != 32:
        raise RuntimeError("frozen Whiteboard API returned an invalid incarnation")

    root = _authenticated_json(
        base_url,
        auth_token,
        "POST",
        f"/api/comments?doc={document_id}",
        {
            "anchor": {
                "block_index": 0,
                "block_id": "smoke-block-1",
                "from_offset": 0,
                "to_offset": len(seed_text),
                "prefix": "",
                "suffix": "",
            },
            "quote": seed_text,
            "body": "Review this disposable opening image.",
        },
        extra_headers={
            "X-LogosForge-Document-Incarnation": incarnation,
        },
    )
    comment_id = root.get("id")
    if not isinstance(comment_id, str) or not comment_id:
        raise RuntimeError("frozen Whiteboard API could not create a root comment")
    return document_id, comment_id


def _structured(result: object) -> dict | None:
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
        raise RuntimeError(f"Frozen Whiteboard MCP {label} failed")
    return result


async def _propose_and_apply(session, name: str, arguments: dict, label: str) -> dict:
    proposal = await _tool_result(session, name, arguments, f"{label} proposal")
    proposal_id = proposal.get("proposal_id")
    if proposal.get("state") != "pending" or not isinstance(proposal_id, str):
        raise RuntimeError(f"Frozen Whiteboard MCP {label} proposal was invalid")
    applied = await _tool_result(
        session,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal_id},
        f"{label} apply",
    )
    receipt = applied.get("result")
    if applied.get("state") != "applied" or not isinstance(receipt, dict):
        raise RuntimeError(f"Frozen Whiteboard MCP {label} apply was invalid")
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
        raise RuntimeError("Frozen Whiteboard MCP second PSYKE receipt was invalid")
    try:
        target_entry_id = int(target_element["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Frozen Whiteboard MCP second PSYKE id was invalid") from exc

    relations = await _tool_result(
        session,
        "logosforge_whiteboard_get_psyke_relations",
        {"document_id": document_id, "offset": 0, "limit": 200},
        "PSYKE relationship read",
    )
    if relations.get("revision") != target_receipt["revision"]:
        raise RuntimeError("Frozen Whiteboard MCP relationship revision diverged")
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
        raise RuntimeError("Frozen Whiteboard MCP relationship receipt was invalid")

    progressions = await _tool_result(
        session,
        "logosforge_whiteboard_get_psyke_progressions",
        {"document_id": document_id, "offset": 0, "limit": 200},
        "PSYKE progression read",
    )
    if progressions.get("revision") != relation_receipt["revision"]:
        raise RuntimeError("Frozen Whiteboard MCP progression revision diverged")
    initial_text = "The keeper first refuses the archive's call."
    progression_receipt = await _propose_and_apply(
        session,
        "logosforge_whiteboard_propose_psyke_progression",
        {
            "document_id": document_id,
            "entry_id": source_entry_id,
            "text": initial_text,
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
        raise RuntimeError("Frozen Whiteboard MCP progression receipt was invalid")

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
        raise RuntimeError("Frozen Whiteboard MCP progression patch receipt was invalid")

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
        raise RuntimeError("Frozen Whiteboard MCP PSYKE graph verification failed")


async def _exercise_mcp(
    executable: Path,
    descriptor: Path,
    *,
    allow_writes: bool,
    expected_document_id: int,
    comment_id: str,
) -> None:
    env = os.environ.copy()
    env["LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE"] = str(descriptor)
    if allow_writes:
        env["LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES"] = "1"
    else:
        env.pop("LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES", None)
    params = mcp.StdioServerParameters(
        command=str(executable),
        args=[],
        cwd=str(executable.parent),
        env=env,
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
                "frozen Whiteboard MCP advertised an unexpected tool registry: "
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
            raise RuntimeError("Whiteboard MCP capabilities read failed")

        documents = await session.call_tool(
            "logosforge_whiteboard_list_documents", {"limit": 10}
        )
        documents_value = _structured(documents)
        if (
            documents.isError
            or not documents_value
            or documents_value.get("ok") is not True
            or not documents_value.get("result", {}).get("documents")
        ):
            raise RuntimeError("authenticated Whiteboard document read failed")
        selected_document = next(
            (
                item
                for item in documents_value["result"]["documents"]
                if str(item.get("id")) == str(expected_document_id)
            ),
            None,
        )
        if not isinstance(selected_document, dict):
            raise RuntimeError("frozen Whiteboard MCP omitted the smoke document")
        try:
            document_id = int(selected_document["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Whiteboard MCP returned an invalid document id") from exc
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
            raise RuntimeError("Whiteboard MCP manuscript snapshot failed")

        comments = await session.call_tool(
            "logosforge_whiteboard_get_comments",
            {
                "document_id": document_id,
                "offset": 0,
                "limit": 20,
                "include_resolved": True,
            },
        )
        comments_value = _structured(comments)
        comments_result = (
            comments_value.get("result")
            if isinstance(comments_value, dict)
            else None
        )
        initial_comments = (
            comments_result.get("comments")
            if isinstance(comments_result, dict)
            else None
        )
        root_comment = next(
            (
                item
                for item in initial_comments or []
                if isinstance(item, dict) and item.get("id") == comment_id
            ),
            None,
        )
        if (
            comments.isError
            or not isinstance(comments_result, dict)
            or not isinstance(comments_result.get("revision"), str)
            or not isinstance(initial_comments, list)
            or not isinstance(root_comment, dict)
            or root_comment.get("resolved") is not False
            or root_comment.get("replies") != []
        ):
            raise RuntimeError("Whiteboard MCP comments read failed")
        title = (
            "Frozen MCP write-disabled smoke "
            if not allow_writes
            else "Frozen MCP write smoke "
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
        ):
            raise RuntimeError("Whiteboard MCP manuscript proposal failed")
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
                raise RuntimeError("Whiteboard MCP default write gate did not deny apply")
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
                    "Whiteboard project changed after a write-disabled apply"
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
            raise RuntimeError("Whiteboard MCP enabled proposal apply failed")

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
            raise RuntimeError("Whiteboard MCP PSYKE read failed")

        entry_name = "Frozen MCP character " + secrets.token_hex(4)
        created = await session.call_tool(
            "logosforge_whiteboard_propose_psyke_entry",
            {
                "document_id": document_id,
                "expected_revision": psyke_result["revision"],
                "entry": {
                    "name": entry_name,
                    "entry_type": "character",
                    "description": "Created by the frozen MCP smoke test.",
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
            raise RuntimeError("Whiteboard MCP PSYKE entry proposal failed")
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
            raise RuntimeError("Whiteboard MCP PSYKE entry apply failed")
        try:
            entry_id = int(created_element["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Whiteboard MCP returned an invalid PSYKE entry id") from exc

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
            raise RuntimeError("Whiteboard MCP PSYKE create verification failed")

        patched_description = "Patched by the frozen MCP smoke test."
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
            raise RuntimeError("Whiteboard MCP PSYKE patch proposal failed")
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
            raise RuntimeError("Whiteboard MCP PSYKE patch apply failed")

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
            raise RuntimeError("Whiteboard MCP PSYKE patch verification failed")

        await _exercise_psyke_graph_progression(
            session,
            document_id,
            entry_id,
            patch_receipt["revision"],
            "Frozen",
        )

        reply_body = "Sharpen the image and keep the rain motif."
        reply = await session.call_tool(
            "logosforge_whiteboard_propose_comment_reply",
            {
                "document_id": document_id,
                "comment_id": comment_id,
                "expected_revision": comments_result["revision"],
                "body": reply_body,
            },
        )
        reply_value = _structured(reply)
        reply_proposal = (
            reply_value.get("result") if isinstance(reply_value, dict) else None
        )
        if (
            reply.isError
            or not isinstance(reply_proposal, dict)
            or reply_proposal.get("state") != "pending"
            or reply_proposal.get("request", {}).get("method") != "POST"
            or reply_proposal.get("request", {}).get("body_page", {}).get("complete")
            is not True
            or reply_proposal.get("review", {}).get("author") != "MCP assistant"
        ):
            raise RuntimeError("Whiteboard MCP comment reply proposal failed")
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
        if (
            reply_applied.isError
            or not isinstance(reply_applied_proposal, dict)
            or reply_applied_proposal.get("state") != "applied"
            or not isinstance(reply_receipt, dict)
            or reply_receipt.get("resource") != "comments"
            or reply_receipt.get("operation") != "reply"
            or reply_receipt.get("comment_id") != comment_id
            or not isinstance(reply_receipt.get("reply_id"), str)
            or not isinstance(reply_receipt.get("revision"), str)
            or reply_receipt.get("reply_count") != 1
        ):
            raise RuntimeError("Whiteboard MCP comment reply apply failed")

        replied = await session.call_tool(
            "logosforge_whiteboard_get_comments",
            {
                "document_id": document_id,
                "offset": 0,
                "limit": 20,
                "include_resolved": True,
            },
        )
        replied_value = _structured(replied)
        replied_result = (
            replied_value.get("result")
            if isinstance(replied_value, dict)
            else None
        )
        replied_comment = next(
            (
                item
                for item in (
                    replied_result.get("comments", [])
                    if isinstance(replied_result, dict)
                    else []
                )
                if isinstance(item, dict) and item.get("id") == comment_id
            ),
            None,
        )
        expected_reply = (
            replied_comment.get("replies", [None])[0]
            if isinstance(replied_comment, dict)
            and len(replied_comment.get("replies", [])) == 1
            else None
        )
        if (
            replied.isError
            or not isinstance(replied_result, dict)
            or replied_result.get("revision") != reply_receipt["revision"]
            or not isinstance(replied_comment, dict)
            or replied_comment.get("resolved") is not False
            or not isinstance(expected_reply, dict)
            or expected_reply.get("id") != reply_receipt["reply_id"]
            or expected_reply.get("body") != reply_body
            or expected_reply.get("author") != "MCP assistant"
        ):
            raise RuntimeError("Whiteboard MCP comment reply verification failed")

        resolution = await session.call_tool(
            "logosforge_whiteboard_propose_comment_resolution",
            {
                "document_id": document_id,
                "comment_id": comment_id,
                "expected_revision": replied_result["revision"],
                "resolved": True,
            },
        )
        resolution_value = _structured(resolution)
        resolution_proposal = (
            resolution_value.get("result")
            if isinstance(resolution_value, dict)
            else None
        )
        if (
            resolution.isError
            or not isinstance(resolution_proposal, dict)
            or resolution_proposal.get("state") != "pending"
            or resolution_proposal.get("request", {}).get("method") != "PUT"
            or resolution_proposal.get("review", {}).get("after_resolved") is not True
        ):
            raise RuntimeError("Whiteboard MCP comment resolution proposal failed")
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
        if (
            resolution_applied.isError
            or not isinstance(resolution_applied_proposal, dict)
            or resolution_applied_proposal.get("state") != "applied"
            or not isinstance(resolution_receipt, dict)
            or resolution_receipt.get("resource") != "comments"
            or resolution_receipt.get("operation") != "resolve"
            or resolution_receipt.get("comment_id") != comment_id
            or resolution_receipt.get("resolved") is not True
            or resolution_receipt.get("reply_count") != 1
            or not isinstance(resolution_receipt.get("revision"), str)
            or resolution_receipt.get("revision") == reply_receipt["revision"]
        ):
            raise RuntimeError("Whiteboard MCP comment resolution apply failed")

        final_comments = await session.call_tool(
            "logosforge_whiteboard_get_comments",
            {
                "document_id": document_id,
                "offset": 0,
                "limit": 20,
                "include_resolved": True,
            },
        )
        final_comments_value = _structured(final_comments)
        final_comments_result = (
            final_comments_value.get("result")
            if isinstance(final_comments_value, dict)
            else None
        )
        final_comment = next(
            (
                item
                for item in (
                    final_comments_result.get("comments", [])
                    if isinstance(final_comments_result, dict)
                    else []
                )
                if isinstance(item, dict) and item.get("id") == comment_id
            ),
            None,
        )
        final_replies = (
            final_comment.get("replies") if isinstance(final_comment, dict) else None
        )
        final_reply = (
            final_replies[0]
            if isinstance(final_replies, list)
            and len(final_replies) == 1
            and isinstance(final_replies[0], dict)
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
            or not isinstance(final_reply, dict)
            or final_reply.get("id") != reply_receipt["reply_id"]
            or final_reply.get("body") != reply_body
            or final_reply.get("author") != "MCP assistant"
        ):
            raise RuntimeError("Whiteboard MCP comment resolution verification failed")


def smoke(backend_executable: Path, mcp_executable: Path) -> None:
    backend_executable = backend_executable.resolve()
    mcp_executable = mcp_executable.resolve()
    if not backend_executable.is_file():
        raise RuntimeError(f"frozen Whiteboard backend is missing: {backend_executable}")
    if not mcp_executable.is_file():
        raise RuntimeError(f"frozen Whiteboard MCP companion is missing: {mcp_executable}")

    with tempfile.TemporaryDirectory(prefix="logosforge-whiteboard-mcp-") as temp:
        work = Path(temp).resolve()
        port = _available_port()
        base_url = f"http://127.0.0.1:{port}"
        token = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(24)
        descriptor_path = work / "mcp-runtime-v1.json"
        log_path = work / "whiteboard-backend.log"
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(work),
                "USERPROFILE": str(work),
                "LOGOSFORGE_DATA_DIR": str(work / "data"),
                "LOGOSFORGE_DB_PATH": str(work / "whiteboard.db"),
                "LOGOSFORGE_WHITEBOARD_AUTH_TOKEN": token,
                "LOGOSFORGE_WHITEBOARD_INSTANCE_NONCE": nonce,
            }
        )
        command = [
            str(backend_executable),
            "--host", "127.0.0.1",
            "--port", str(port),
        ]
        process: subprocess.Popen | None = None
        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
                    command,
                    cwd=backend_executable.parent,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                health = None
                for _attempt in range(60):
                    if process.poll() is not None:
                        break
                    health = _health(base_url)
                    if health is not None:
                        break
                    time.sleep(1)
                if (
                    not health
                    or health.get("status") != "ok"
                    or health.get("service") != "logosforge-whiteboard-backend"
                    or health.get("instance_nonce") != nonce
                ):
                    raise RuntimeError(
                        "frozen Whiteboard backend did not present the expected identity "
                        f"(exit={process.poll()})"
                    )
                document_id, comment_id = _seed_comment_document(base_url, token)
                descriptor = {
                    "schema_version": 1,
                    "base_url": base_url,
                    "auth_token": token,
                    "instance_nonce": nonce,
                    "app_pid": os.getpid(),
                    "backend_pid": process.pid,
                    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
                if os.name != "nt":
                    descriptor_path.chmod(0o600)
                async def exercise_default_and_enabled() -> None:
                    await _exercise_mcp(
                        mcp_executable,
                        descriptor_path,
                        allow_writes=False,
                        expected_document_id=document_id,
                        comment_id=comment_id,
                    )
                    await _exercise_mcp(
                        mcp_executable,
                        descriptor_path,
                        allow_writes=True,
                        expected_document_id=document_id,
                        comment_id=comment_id,
                    )

                asyncio.run(
                    asyncio.wait_for(exercise_default_and_enabled(), timeout=90)
                )
        except Exception:
            if log_path.exists():
                print(log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            raise
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)

    print(
        "Frozen Whiteboard MCP initialized, advertised 24 read/proposal tools, "
        "kept writes disabled by default, and completed a disposable enabled "
        "manuscript, PSYKE entry/relationship/progression, and comment collaboration "
        "proposal/apply round trip."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backend_executable", type=Path)
    parser.add_argument("mcp_executable", type=Path)
    args = parser.parse_args()
    smoke(args.backend_executable, args.mcp_executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
