"""Tests for the project-bundle export (GET /api/export/project).

Runnable standalone (no pytest needed):
    cd whiteboard-desktop/backend && .venv/Scripts/python tests/test_export.py

Two checks:
  1. build_project_bundle() — the pure assembler shapes the bundle correctly.
  2. GET /api/export/project — an integration smoke against a TEMP data dir + DB
     (never touches the real ~/.logosforge): seed one doc with blocks, outline,
     a comment, and a PSYKE character, then export and assert all four sections.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

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
        blocks=[
            WhiteboardBlock(id="b0", type="heading", text="Chapter One", level=1),
            WhiteboardBlock(id="b1", type="paragraph", text="The hull settled."),
        ],
    )
    outline = [{"id": "o1", "parentId": None, "type": "act", "title": "Act I", "order": 0}]
    comments = CommentsDocument(comments=[
        Comment(
            id="c1", anchor=CommentAnchor(block_index=1, from_offset=0, to_offset=3),
            quote="The", body="opening?", resolved=False,
            created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
        )
    ])
    psyke = [{"id": "1", "name": "Mara", "entry_type": "character", "description": "sonar tech", "notes": "", "aliases": []}]

    b = build_project_bundle("7", wb, outline, comments, psyke, "2026-01-01T00:00:00Z")

    check("format tag", b["format"] == BUNDLE_FORMAT)
    check("version present", isinstance(b.get("version"), str))
    check("project id stringified", b["project"]["id"] == "7")
    check("title + mode carried", b["project"]["title"] == "The Sounding" and b["project"]["mode"] == "novel")
    blocks = b["project"]["manuscript"]["blocks"]
    check("all blocks carried", len(blocks) == 2 and blocks[0]["type"] == "heading" and blocks[0]["level"] == 1)
    check("None fields dropped from blocks", "level" not in blocks[1])  # paragraph has no level
    check("outline carried", b["project"]["outline"] == outline)
    cm = b["project"]["comments"]
    check("comment carried with anchor", len(cm) == 1 and cm[0]["anchor"]["block_index"] == 1 and cm[0]["quote"] == "The")
    ps = b["project"]["psyke"]["elements"]
    check("psyke carried", len(ps) == 1 and ps[0]["name"] == "Mara" and ps[0]["entry_type"] == "character")


# -- 2. integration smoke (temp DB, real route) ------------------------------
def test_export_route_integration() -> None:
    try:
        from fastapi.testclient import TestClient
        from app.main import app
    except Exception as exc:  # pragma: no cover
        failures.append(f"integration import failed: {exc!r}")
        return

    with TestClient(app) as client:
        # Seed the DEFAULT document (doc omitted → default project).
        client.put("/api/whiteboard", json={
            "title": "Bundle Demo", "mode": "novel",
            "blocks": [
                {"id": "b0", "type": "heading", "text": "Act I", "level": 1},
                {"id": "b1", "type": "paragraph", "text": "It began with a knock."},
            ],
        })
        client.put("/api/outline/items", json={"items": [
            {"id": "o1", "parentId": None, "type": "act", "title": "Act I", "order": 0},
        ]})
        client.post("/api/comments", json={
            "anchor": {"block_index": 1, "from_offset": 0, "to_offset": 2},
            "quote": "It", "body": "hook",
        })
        client.post("/api/psyke/elements", json={
            "type": "character", "name": "Mara", "description": "sonar tech", "notes": "",
        })

        resp = client.get("/api/export/project")
        check("route 200", resp.status_code == 200)
        b = resp.json()
        proj = b.get("project", {})
        check("route: format tag", b.get("format") == "logosforge-project-bundle")
        check("route: blocks present", len(proj.get("manuscript", {}).get("blocks", [])) == 2)
        check("route: outline present", len(proj.get("outline", [])) == 1)
        check("route: comment present", len(proj.get("comments", [])) == 1)
        check("route: psyke present", any(e.get("name") == "Mara" for e in proj.get("psyke", {}).get("elements", [])))


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
