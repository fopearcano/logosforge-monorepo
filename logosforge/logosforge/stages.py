"""Stages — narrative versioning capture, restore, and diff logic.

This module implements the *content* side of the STAGES feature.
Database persistence is handled by the Database CRUD methods; this
module orchestrates capturing scope-specific data into a snapshot
JSON, restoring it back, and producing diffs between snapshots
or the current state.

No Qt code lives here. The UI calls these functions and renders the
results.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass

SCOPE_PROJECT = "project"
SCOPE_SCENE = "scene"
SCOPE_CHAPTER = "chapter"
SCOPE_OUTLINE = "outline"
SCOPE_PSYKE = "psyke"

SAFETY_STAGE_NAME = "Safety (auto)"


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SnapshotPayload:
    """The deserialized payload of a StageSnapshot.data_json field."""

    scope_type: str
    scope_id: int | None
    data: dict


@dataclass(slots=True)
class DiffResult:
    """Unified-diff style result of comparing two payloads."""

    added: list[str]
    removed: list[str]
    changed: list[tuple[str, str, str]]  # (key, before, after)
    unified: str


# ---------------------------------------------------------------------------
# Capture — read project state and produce a JSON-serializable dict
# ---------------------------------------------------------------------------


def capture_scope(db, project_id: int, scope_type: str, scope_id: int | None) -> dict:
    """Capture the current state of a scope into a serializable dict."""
    if scope_type == SCOPE_SCENE:
        if scope_id is None:
            return {"scope_type": scope_type, "scope_id": None, "data": {}}
        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "data": _capture_scene(db, scope_id),
        }
    if scope_type == SCOPE_OUTLINE:
        return {
            "scope_type": scope_type,
            "scope_id": None,
            "data": _capture_outline(db, project_id),
        }
    if scope_type == SCOPE_PSYKE:
        return {
            "scope_type": scope_type,
            "scope_id": None,
            "data": _capture_psyke(db, project_id),
        }
    if scope_type == SCOPE_CHAPTER:
        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "data": _capture_chapter(db, project_id, scope_id),
        }
    if scope_type == SCOPE_PROJECT:
        return {
            "scope_type": scope_type,
            "scope_id": None,
            "data": _capture_project(db, project_id),
        }
    return {"scope_type": scope_type, "scope_id": scope_id, "data": {}}


def _capture_scene(db, scene_id: int) -> dict:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {}
    char_ids = list(db.get_scene_character_ids(scene_id))
    char_states = list(db.get_scene_character_states(scene_id))
    return {
        "title": scene.title,
        "content": scene.content or "",
        "summary": scene.summary or "",
        "synopsis": scene.synopsis or "",
        "goal": getattr(scene, "goal", "") or "",
        "conflict": getattr(scene, "conflict", "") or "",
        "outcome": getattr(scene, "outcome", "") or "",
        "beat": getattr(scene, "beat", "") or "",
        "tags": getattr(scene, "tags", "") or "",
        "act": getattr(scene, "act", "") or "",
        "chapter": getattr(scene, "chapter", "") or "",
        "plotline": getattr(scene, "plotline", "") or "",
        "character_ids": char_ids,
        "character_states": [
            {"character_id": cid, "state": state} for cid, state in char_states
        ],
    }


def _capture_outline(db, project_id: int) -> dict:
    nodes = db.get_outline_nodes(project_id)
    return {
        "nodes": [
            {
                "id": n.id,
                "parent_id": n.parent_id,
                "title": n.title,
                "description": n.description,
                "sort_order": n.sort_order,
            }
            for n in nodes
        ]
    }


def _capture_psyke(db, project_id: int) -> dict:
    entries = db.get_all_psyke_entries(project_id)
    return {
        "entries": [
            {
                "id": e.id,
                "name": e.name,
                "entry_type": e.entry_type,
                "aliases": e.aliases,
                "notes": e.notes,
                "is_global": e.is_global,
                "details": db.get_psyke_entry_details(e.id),
            }
            for e in entries
        ]
    }


def _capture_chapter(db, project_id: int, chapter_id: int | None) -> dict:
    scenes = db.get_all_scenes(project_id)
    if chapter_id is None:
        chapter_scenes = scenes
    else:
        chapter_scenes = [
            s for s in scenes
            if str(getattr(s, "chapter", "")) == str(chapter_id)
        ]
    return {
        "chapter_id": chapter_id,
        "scenes": [_capture_scene(db, s.id) | {"id": s.id} for s in chapter_scenes],
    }


def _capture_project(db, project_id: int) -> dict:
    scenes = db.get_all_scenes(project_id)
    return {
        "scenes": [_capture_scene(db, s.id) | {"id": s.id} for s in scenes],
        "outline": _capture_outline(db, project_id),
        "psyke": _capture_psyke(db, project_id),
    }


# ---------------------------------------------------------------------------
# Snapshot summary — short human-readable string
# ---------------------------------------------------------------------------


def snapshot_summary(captured: dict) -> str:
    scope = captured.get("scope_type", "?")
    data = captured.get("data") or {}
    if scope == SCOPE_SCENE:
        title = data.get("title", "?")
        words = len((data.get("content") or "").split())
        return f"Scene '{title}' · {words} words"
    if scope == SCOPE_OUTLINE:
        return f"Outline · {len(data.get('nodes', []))} nodes"
    if scope == SCOPE_PSYKE:
        return f"PSYKE · {len(data.get('entries', []))} entries"
    if scope == SCOPE_CHAPTER:
        return f"Chapter · {len(data.get('scenes', []))} scenes"
    if scope == SCOPE_PROJECT:
        return (
            f"Project · {len(data.get('scenes', []))} scenes, "
            f"{len(data.get('psyke', {}).get('entries', []))} PSYKE"
        )
    return "(empty)"


# ---------------------------------------------------------------------------
# Persistence helpers (orchestrate DB writes)
# ---------------------------------------------------------------------------


def save_snapshot(
    db, stage_id: int, captured: dict, *, label: str = "", reason: str = "",
):
    """Serialize *captured* and store it under the given stage."""
    summary = snapshot_summary(captured)
    return db.create_stage_snapshot(
        stage_id,
        json.dumps(captured),
        label=label,
        reason=reason,
        summary=summary,
    )


def load_snapshot(db, snapshot_id: int) -> SnapshotPayload | None:
    snap = db.get_snapshot(snapshot_id)
    if snap is None:
        return None
    try:
        raw = json.loads(snap.data_json) if snap.data_json else {}
    except (json.JSONDecodeError, TypeError):
        raw = {}
    return SnapshotPayload(
        scope_type=raw.get("scope_type", "project"),
        scope_id=raw.get("scope_id"),
        data=raw.get("data") or {},
    )


# ---------------------------------------------------------------------------
# Restore — write captured data back into the project
# ---------------------------------------------------------------------------


def restore_snapshot(
    db, project_id: int, snapshot_id: int, *, take_safety: bool = True,
) -> dict:
    """Restore a snapshot's data into the project.

    Always returns a dict ``{"ok": bool, "safety_snapshot_id": int|None,
    "error": str|None}``. When *take_safety* is True (default), the
    current state in the snapshot's scope is captured as a safety
    snapshot under a system-managed "Safety" stage before the restore.
    """
    payload = load_snapshot(db, snapshot_id)
    if payload is None:
        return {"ok": False, "safety_snapshot_id": None, "error": "Snapshot not found"}

    safety_id: int | None = None
    if take_safety:
        safety_stage = _ensure_safety_stage(db, project_id)
        current = capture_scope(
            db, project_id, payload.scope_type, payload.scope_id,
        )
        safety_snap = save_snapshot(
            db, safety_stage.id, current,
            label=f"Pre-restore safety ({payload.scope_type})",
            reason=f"Auto-captured before restoring snapshot #{snapshot_id}",
        )
        safety_id = safety_snap.id

    try:
        if payload.scope_type == SCOPE_SCENE and payload.scope_id is not None:
            _restore_scene(db, payload.scope_id, payload.data)
        elif payload.scope_type == SCOPE_OUTLINE:
            _restore_outline(db, project_id, payload.data)
        elif payload.scope_type == SCOPE_CHAPTER:
            _restore_chapter(db, project_id, payload.data)
        elif payload.scope_type == SCOPE_PROJECT:
            _restore_project(db, project_id, payload.data)
        elif payload.scope_type == SCOPE_PSYKE:
            _restore_psyke(db, project_id, payload.data)
        else:
            return {"ok": False, "safety_snapshot_id": safety_id, "error": f"Unsupported scope: {payload.scope_type}"}
    except Exception as e:
        return {"ok": False, "safety_snapshot_id": safety_id, "error": str(e)}
    return {"ok": True, "safety_snapshot_id": safety_id, "error": None}


def _restore_scene(db, scene_id: int, data: dict) -> None:
    db.update_scene(
        scene_id,
        title=data.get("title", ""),
        summary=data.get("summary", ""),
        synopsis=data.get("synopsis", ""),
        goal=data.get("goal", ""),
        conflict=data.get("conflict", ""),
        outcome=data.get("outcome", ""),
        beat=data.get("beat", ""),
        tags=data.get("tags", ""),
        act=data.get("act", ""),
        content=data.get("content", ""),
        chapter=data.get("chapter", ""),
        plotline=data.get("plotline", ""),
        character_ids=list(data.get("character_ids") or []),
        character_states=[
            (s.get("character_id"), s.get("state", ""))
            for s in (data.get("character_states") or [])
            if s.get("character_id") is not None
        ],
    )


def _restore_outline(db, project_id: int, data: dict) -> None:
    db.delete_all_outline_nodes(project_id)
    id_remap: dict[int, int] = {}
    nodes = sorted(
        data.get("nodes", []),
        key=lambda n: (n.get("parent_id") is not None, n.get("sort_order", 0)),
    )
    for n in nodes:
        old_parent = n.get("parent_id")
        new_parent = id_remap.get(old_parent) if old_parent is not None else None
        created = db.create_outline_node(
            project_id,
            title=n.get("title", ""),
            description=n.get("description", ""),
            parent_id=new_parent,
            sort_order=n.get("sort_order", 0),
        )
        if n.get("id") is not None:
            id_remap[n["id"]] = created.id


def _restore_chapter(db, project_id: int, data: dict) -> None:
    for s in data.get("scenes", []):
        sid = s.get("id")
        if sid is None:
            continue
        _restore_scene(db, sid, s)


def _restore_project(db, project_id: int, data: dict) -> None:
    for s in data.get("scenes", []):
        sid = s.get("id")
        if sid is None:
            continue
        _restore_scene(db, sid, s)
    if "outline" in data:
        _restore_outline(db, project_id, data["outline"])
    if "psyke" in data:
        _restore_psyke(db, project_id, data["psyke"])


def _restore_psyke(db, project_id: int, data: dict) -> None:
    entries = data.get("entries", [])
    existing = {e.id: e for e in db.get_all_psyke_entries(project_id)}
    for entry_data in entries:
        eid = entry_data.get("id")
        if eid is not None and eid in existing:
            db.update_psyke_entry(
                eid,
                name=entry_data.get("name", ""),
                entry_type=entry_data.get("entry_type", "other"),
                aliases=entry_data.get("aliases", ""),
                notes=entry_data.get("notes", ""),
                is_global=entry_data.get("is_global", False),
                details=entry_data.get("details") or {},
            )


# ---------------------------------------------------------------------------
# Safety stage
# ---------------------------------------------------------------------------


def _ensure_safety_stage(db, project_id: int):
    for stage in db.get_all_stages(project_id):
        if stage.name == SAFETY_STAGE_NAME:
            return stage
    return db.create_stage(
        project_id,
        SAFETY_STAGE_NAME,
        description="Auto-captured snapshots taken before each restore.",
        status="archived",
        scope_type="project",
    )


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def _payload_to_text(payload: SnapshotPayload | dict) -> str:
    """Render a payload as deterministic text for diffing."""
    if isinstance(payload, SnapshotPayload):
        scope = payload.scope_type
        data = payload.data
    else:
        scope = payload.get("scope_type", "?")
        data = payload.get("data") or {}
    if scope == SCOPE_SCENE:
        return _scene_data_to_text(data)
    if scope == SCOPE_OUTLINE:
        return _outline_data_to_text(data)
    if scope == SCOPE_PSYKE:
        return _psyke_data_to_text(data)
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)


def _scene_data_to_text(data: dict) -> str:
    return (
        f"# {data.get('title', '')}\n"
        f"summary: {data.get('summary', '')}\n"
        f"synopsis: {data.get('synopsis', '')}\n"
        f"goal: {data.get('goal', '')}\n"
        f"conflict: {data.get('conflict', '')}\n"
        f"outcome: {data.get('outcome', '')}\n"
        f"beat: {data.get('beat', '')}\n"
        f"act: {data.get('act', '')}\n"
        f"chapter: {data.get('chapter', '')}\n"
        f"plotline: {data.get('plotline', '')}\n"
        f"---\n"
        f"{data.get('content', '')}"
    )


def _outline_data_to_text(data: dict) -> str:
    lines = []
    nodes = sorted(
        data.get("nodes", []),
        key=lambda n: (n.get("parent_id") is None, n.get("sort_order", 0), n.get("id", 0)),
    )
    for n in nodes:
        depth = 0 if n.get("parent_id") is None else 1
        prefix = "  " * depth + "- "
        lines.append(f"{prefix}{n.get('title', '')}")
        if n.get("description"):
            lines.append(f"{'  ' * (depth + 1)}{n['description']}")
    return "\n".join(lines)


def _psyke_data_to_text(data: dict) -> str:
    lines = []
    for entry in sorted(data.get("entries", []), key=lambda e: (e.get("entry_type", ""), e.get("name", ""))):
        lines.append(f"[{entry.get('entry_type', '?')}] {entry.get('name', '')}")
        if entry.get("aliases"):
            lines.append(f"  aliases: {entry['aliases']}")
        if entry.get("notes"):
            lines.append(f"  notes: {entry['notes']}")
    return "\n".join(lines)


def diff_payloads(
    before: SnapshotPayload | dict, after: SnapshotPayload | dict,
) -> DiffResult:
    """Produce a unified-diff text plus structured added/removed/changed."""
    before_text = _payload_to_text(before)
    after_text = _payload_to_text(after)
    unified = "\n".join(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )

    before_data = before.data if isinstance(before, SnapshotPayload) else (before.get("data") or {})
    after_data = after.data if isinstance(after, SnapshotPayload) else (after.get("data") or {})

    added: list[str] = []
    removed: list[str] = []
    changed: list[tuple[str, str, str]] = []
    keys = set(before_data.keys()) | set(after_data.keys())
    for k in sorted(keys):
        b = before_data.get(k)
        a = after_data.get(k)
        if k not in before_data:
            added.append(k)
        elif k not in after_data:
            removed.append(k)
        elif b != a:
            changed.append((k, str(b)[:200], str(a)[:200]))

    return DiffResult(
        added=added, removed=removed, changed=changed, unified=unified,
    )


# ---------------------------------------------------------------------------
# Branching
# ---------------------------------------------------------------------------


def branch_from(
    db,
    source_stage_id: int,
    *,
    name: str,
    description: str = "",
    branch_reason: str = "",
    copy_data: bool = True,
):
    """Create a new alternate stage branched from *source_stage_id*.

    When *copy_data* is True and the source has at least one snapshot,
    the most recent snapshot is copied into the new stage so the user
    starts from a known state.
    """
    source = db.get_stage(source_stage_id)
    if source is None:
        return None
    new_stage = db.create_stage(
        source.project_id,
        name=name,
        description=description,
        parent_stage_id=source.id,
        scope_type=source.scope_type,
        scope_id=source.scope_id,
        status="alternate",
    )
    db.create_stage_branch(
        source_stage_id=source.id,
        target_stage_id=new_stage.id,
        branch_reason=branch_reason,
    )
    if copy_data:
        snaps = db.get_stage_snapshots(source.id)
        if snaps:
            latest = snaps[-1]
            db.create_stage_snapshot(
                new_stage.id,
                latest.data_json,
                label=f"Copied from {source.name}",
                reason=branch_reason or "Branch initialization",
                summary=latest.summary,
            )
    return new_stage


# ---------------------------------------------------------------------------
# Quantum integration helper (optional, not auto-wired)
# ---------------------------------------------------------------------------


def create_from_quantum_collapse(
    db,
    project_id: int,
    *,
    wavefunction_id: str,
    branch_id: str,
    branch_title: str,
    reason: str = "",
    captured: dict | None = None,
):
    """Record a Quantum collapse as a Stage + initial snapshot.

    Optional helper. Not auto-wired into Quantum's collapse flow yet.
    Call this from Quantum-side code if/when desired.
    """
    metadata = {
        "quantum_wavefunction_id": wavefunction_id,
        "quantum_branch_id": branch_id,
        "collapse_reason": reason,
    }
    stage = db.create_stage(
        project_id,
        name=f"Quantum: {branch_title}",
        description=reason,
        scope_type="project",
        status="alternate",
        metadata=metadata,
    )
    if captured is not None:
        save_snapshot(
            db, stage.id, captured,
            label="Quantum collapse",
            reason=reason,
        )
    return stage
