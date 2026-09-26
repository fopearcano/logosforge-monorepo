"""Tests for the project-bundle export (GET /api/export/project).

Runnable standalone (no pytest needed):
    cd whiteboard-desktop/backend && .venv/Scripts/python tests/test_export.py

Checks include:
  1. build_project_bundle() — the pure assembler shapes the bundle correctly.
  2. GET /api/export/project — an integration smoke against a TEMP data dir + DB
     (never touches the real ~/.logosforge): seed one doc with blocks, outline,
     a comment, PSYKE entries, a relation, and a progression, then export and
     assert every section.
  3. malformed or unavailable relation/progression collections abort instead of
     producing a bundle that silently loses story-bible data.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

# Make `app` importable regardless of CWD, and point ALL state at a throwaway
# dir BEFORE importing anything that reads it (stores + core DB path).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="lf-export-test-"))
os.environ["LOGOSFORGE_DATA_DIR"] = str(_TMP)
os.environ["LOGOSFORGE_DB_PATH"] = str(_TMP / "whiteboard.db")

passed = 0
failures: list[str] = []


def check(label: str, cond: bool) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


# -- 1. pure assembler -------------------------------------------------------
def test_build_bundle_pure() -> None:
    from app.local_state import Comment, CommentAnchor, CommentsDocument, WhiteboardBlock, WhiteboardDocument
    from app.routers.export import BUNDLE_FORMAT, build_project_bundle

    wb = WhiteboardDocument(
        id="7", title="The Sounding", mode="novel", updated_at="2026-01-01T00:00:00Z",
        settings={"narrativePerson": "first", "narrativeStyle": "literary"},
        blocks=[
            WhiteboardBlock(id="b0", type="heading", text="Chapter One", level=1),
            WhiteboardBlock(id="b1", type="paragraph", text="The hull settled."),
        ],
    )
    outline = [{"id": "o1", "parentId": None, "type": "act", "title": "Act I", "order": 0}]
    comments = CommentsDocument(comments=[
        Comment(
            id="c1", anchor=CommentAnchor(
                block_index=1, block_id="block-body", from_offset=0, to_offset=3,
            ),
            quote="The", body="opening?", resolved=False,
            created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        )
    ])
    psyke = [{"id": "1", "name": "Mara", "entry_type": "character", "description": "sonar tech", "notes": "", "aliases": []}]
    relations = [{
        "id": "1:2",
        "source_id": 1,
        "target_id": 2,
        "source": "Mara",
        "target": "Bex",
        "relation_type": "rivals",
    }]
    progressions = [{
        "id": 4,
        "entry_id": 1,
        "text": "Mara stops hiding the signal.",
        "scene_id": None,
        "scene_title": "",
        "sort_order": 1,
    }]

    b = build_project_bundle(
        "7",
        wb,
        outline,
        comments,
        psyke,
        "2026-01-01T00:00:00Z",
        psyke_relations=relations,
        psyke_progressions=progressions,
    )

    check("format tag", b["format"] == BUNDLE_FORMAT)
    check("version present", isinstance(b.get("version"), str))
    check("project id stringified", b["project"]["id"] == "7")
    check("title + mode carried", b["project"]["title"] == "The Sounding" and b["project"]["mode"] == "novel")
    check("document settings carried", b["project"]["settings"]["narrativePerson"] == "first")
    blocks = b["project"]["manuscript"]["blocks"]
    check("all blocks carried", len(blocks) == 2 and blocks[0]["type"] == "heading" and blocks[0]["level"] == 1)
    check("None fields dropped from blocks", "level" not in blocks[1])  # paragraph has no level
    check("outline carried", b["project"]["outline"] == outline)
    cm = b["project"]["comments"]
    check(
        "comment carried with stable anchor",
        len(cm) == 1
        and cm[0]["anchor"]["block_index"] == 1
        and cm[0]["anchor"]["block_id"] == "block-body"
        and cm[0]["quote"] == "The",
    )
    ps = b["project"]["psyke"]["elements"]
    check("psyke carried", len(ps) == 1 and ps[0]["name"] == "Mara" and ps[0]["entry_type"] == "character")
    check("psyke relations carried", b["project"]["psyke"]["relations"] == relations)
    check(
        "psyke progressions carried",
        b["project"]["psyke"]["progressions"] == progressions,
    )
    assert not failures, "\n".join(failures)


# -- 2. integration smoke (temp DB, real route) ------------------------------
def test_export_route_integration() -> None:
    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except Exception as exc:  # pragma: no cover
        raise AssertionError(f"integration import failed: {exc!r}") from exc

    with TestClient(app) as client:
        # Seed the DEFAULT document (doc omitted → default project).
        client.put("/api/whiteboard", json={
            "title": "Bundle Demo", "mode": "novel",
            "settings": {"narrativePerson": "third-limited"},
            "blocks": [
                {"id": "b0", "type": "heading", "text": "Act I", "level": 1},
                {"id": "b1", "type": "paragraph", "text": "It began with a knock."},
            ],
        })
        client.put("/api/outline/items", json={"items": [
            {"id": "o1", "parentId": None, "type": "act", "title": "Act I", "order": 0},
        ]})
        client.post("/api/comments", json={
            "anchor": {
                "block_index": 1, "block_id": "b1", "from_offset": 0, "to_offset": 2,
            },
            "quote": "It", "body": "hook",
        })
        mara_response = client.post("/api/psyke/elements", json={
            "type": "character", "name": "Mara", "description": "sonar tech", "notes": "",
        })
        bex_response = client.post("/api/psyke/elements", json={
            "type": "character", "name": "Bex", "description": "navigator", "notes": "",
        })
        mara_id = int(mara_response.json()["element"]["id"])
        bex_id = int(bex_response.json()["element"]["id"])

        # Seed core-owned PSYKE features through the core's public API.  The
        # Whiteboard export must include them even though the visible Free-tier
        # panel only edits the flat entry list.
        document_id = int(client.get("/api/whiteboard").json()["id"])
        with TestClient(app.state.core.app) as core_client:
            relation_response = core_client.post(
                f"/api/projects/{document_id}/psyke/relations",
                json={
                    "source_id": mara_id,
                    "target_id": bex_id,
                    "relation_type": "rivals",
                },
            )
            progression_response = core_client.post(
                f"/api/projects/{document_id}/psyke/progressions",
                json={
                    "entry_id": mara_id,
                    "text": "Mara stops hiding the signal.",
                },
            )
        check("route seed: relation created", relation_response.status_code == 201)
        check("route seed: progression created", progression_response.status_code == 201)

        resp = client.get("/api/export/project")
        check("route 200", resp.status_code == 200)
        b = resp.json()
        proj = b.get("project", {})
        check("route: format tag", b.get("format") == "logosforge-project-bundle")
        check("route: blocks present", len(proj.get("manuscript", {}).get("blocks", [])) == 2)
        check("route: settings present", proj.get("settings", {}).get("narrativePerson") == "third-limited")
        check("route: outline present", len(proj.get("outline", [])) == 1)
        comments = proj.get("comments", [])
        check(
            "route: stable comment anchor present",
            len(comments) == 1 and comments[0]["anchor"].get("block_id") == "b1",
        )
        exported_psyke = proj.get("psyke", {})
        check("route: psyke present", any(e.get("name") == "Mara" for e in exported_psyke.get("elements", [])))
        exported_relations = exported_psyke.get("relations", [])
        exported_relation = (
            exported_relations[0]
            if isinstance(exported_relations, list) and len(exported_relations) == 1
            else {}
        )
        check(
            "route: psyke relation present",
            {
                exported_relation.get("source_id"),
                exported_relation.get("target_id"),
            }
            == {mara_id, bex_id}
            and exported_relation.get("id")
            == (
                f'{exported_relation.get("source_id")}:'
                f'{exported_relation.get("target_id")}'
            )
            and {
                exported_relation.get("source"),
                exported_relation.get("target"),
            }
            == {"Mara", "Bex"}
            and exported_relation.get("relation_type") == "rivals",
        )
        exported_progressions = exported_psyke.get("progressions", [])
        check(
            "route: psyke progression present",
            len(exported_progressions) == 1
            and exported_progressions[0]["entry_id"] == mara_id
            and exported_progressions[0]["text"]
            == "Mara stops hiding the signal."
            and exported_progressions[0]["scene_id"] is None
            and exported_progressions[0]["sort_order"] == 1,
        )
    assert not failures, "\n".join(failures)


class _CollectionCore:
    def __init__(
        self,
        payloads: dict[str, object],
        *,
        failing_resource: str | None = None,
    ) -> None:
        self.payloads = payloads
        self.failing_resource = failing_resource

    async def request(self, method: str, path: str):
        assert method == "GET"
        resource = path.rsplit("/", 1)[-1]
        if resource == self.failing_resource:
            request = httpx.Request(method, "http://logosforge-core" + path)
            response = httpx.Response(
                503,
                request=request,
                json={"error": {"message": f"{resource} unavailable"}},
            )
            raise httpx.HTTPStatusError(
                "failed", request=request, response=response
            )
        return SimpleNamespace(json=lambda: self.payloads[resource])


@pytest.mark.parametrize(
    ("helper_name", "resource", "payload"),
    [
        (
            "_list_psyke_relations",
            "relations",
            [{"id": "1:1", "source_id": 1, "target_id": 1}],
        ),
        (
            "_list_psyke_progressions",
            "progressions",
            [{"id": True, "entry_id": 1, "text": "invalid"}],
        ),
    ],
)
def test_export_rejects_invalid_psyke_graph_collections(
    helper_name: str,
    resource: str,
    payload: object,
) -> None:
    from app.routers import export as export_router

    helper = getattr(export_router, helper_name)
    core = _CollectionCore({resource: payload})
    with pytest.raises(HTTPException) as caught:
        asyncio.run(helper(core, 7))
    assert caught.value.status_code == 502
    assert "export aborted" in str(caught.value.detail).lower()
    assert resource in str(caught.value.detail).lower()


@pytest.mark.parametrize("resource", ["relations", "progressions"])
def test_export_aborts_when_psyke_graph_collection_is_unavailable(
    resource: str,
) -> None:
    from app.routers import export as export_router

    helper = getattr(export_router, f"_list_psyke_{resource}")
    core = _CollectionCore({resource: []}, failing_resource=resource)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(helper(core, 7))
    assert caught.value.status_code == 502
    assert f"{resource} unavailable" in str(caught.value.detail)


if __name__ == "__main__":
    test_build_bundle_pure()
    test_export_route_integration()
    print(f"Export bundle tests: {passed} passed, {len(failures)} failed")
    for f in failures:
        print("  FAIL:", f)
    # Best-effort temp cleanup.
    try:
        import shutil
        shutil.rmtree(_TMP, ignore_errors=True)
    except Exception:
        pass
    if failures:
        sys.exit(1)
    print("EXPORT TESTS: PASS")
