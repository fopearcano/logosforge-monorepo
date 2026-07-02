"""Collapse Mechanism — choose one branch, archive the rest, update PSYKE."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from logosforge.quantum_outliner.psyke_adapter import apply_collapse
from logosforge.settings import CONFIG_DIR
from logosforge.quantum_outliner.state import (
    Branch,
    Wavefunction,
    get_state,
    serialize,
)

if TYPE_CHECKING:
    from logosforge.db import Database

logger = logging.getLogger(__name__)


class CollapseError(Exception):
    pass


def collapse(
    db: "Database",
    project_id: int,
    wavefunction_id: str,
    branch_id: str,
    *,
    archive: bool = True,
) -> dict:
    """Commit one branch as canonical. Apply its delta to PSYKE.

    Returns a dict with:
      - chosen: the chosen Branch as dict
      - psyke_summary: what was written to PSYKE
      - archived: list of discarded branches (titles)
      - proposals: suggested follow-up actions requiring confirmation
    """
    state = get_state(project_id)
    wf = state.get(wavefunction_id)
    if wf is None:
        raise CollapseError(f"Wavefunction '{wavefunction_id}' not found")
    if wf.is_collapsed():
        raise CollapseError(f"Wavefunction '{wavefunction_id}' already collapsed")

    chosen = wf.get_branch(branch_id)
    if chosen is None:
        raise CollapseError(
            f"Branch '{branch_id}' not in wavefunction '{wavefunction_id}'"
        )

    psyke_summary = apply_collapse(db, project_id, chosen)
    wf.collapsed_branch_id = chosen.id

    archived: list[dict] = []
    for b in wf.branches:
        if b.id != chosen.id:
            archived.append({"id": b.id, "title": b.title})

    proposals = _build_proposals(db, project_id, wf, chosen)

    if archive:
        try:
            _archive_wavefunction(project_id, wf)
        except OSError as exc:
            logger.warning("Failed to archive wavefunction: %s", exc)

    return {
        "chosen": {
            "id": chosen.id,
            "title": chosen.title,
            "description": chosen.description,
            "stakes": chosen.stakes,
            "consequence": chosen.consequence,
        },
        "psyke_summary": psyke_summary,
        "archived": archived,
        "proposals": proposals,
        "source_scene_id": wf.source_scene_id,
        "source_scene_order": wf.source_scene_order,
    }


def _build_proposals(
    db: "Database",
    project_id: int,
    wf: Wavefunction,
    chosen: Branch,
) -> list[dict]:
    """Generate actionable proposals the UI can present for confirmation."""
    proposals: list[dict] = []

    if wf.source_scene_id is not None:
        source = db.get_scene_by_id(wf.source_scene_id)
        if source is not None:
            proposals.append({
                "type": "create_scene",
                "description": (
                    f"Create new scene \"{chosen.title}\" after "
                    f"\"{source.title}\" (position {source.sort_order + 1})"
                ),
                "after_scene_id": wf.source_scene_id,
                "title": chosen.title,
                "summary": chosen.description,
                "content": "",
            })

    if chosen.consequence and wf.source_scene_id is not None:
        proposals.append({
            "type": "update_scene_note",
            "description": f"Add consequence note to source scene",
            "scene_id": wf.source_scene_id,
            "note": f"[quantum] {chosen.consequence}",
        })

    from logosforge.quantum_outliner.psyke_adapter import find_entry_by_name
    for change in chosen.state_delta.character_changes:
        name = (change.get("name") or "").strip()
        note = (change.get("note") or "").strip()
        if not name or not note:
            continue
        entry = find_entry_by_name(db, project_id, name)
        if entry is not None and wf.source_scene_id is not None:
            proposals.append({
                "type": "add_progression",
                "description": f"Add progression for {name}: {note[:60]}",
                "entry_id": entry.id,
                "text": note,
                "scene_id": wf.source_scene_id,
            })

    return proposals


def apply_proposal(db: "Database", project_id: int, proposal: dict) -> dict:
    """Execute a confirmed proposal. Returns result summary."""
    ptype = proposal.get("type")

    if ptype == "create_scene":
        after_id = proposal["after_scene_id"]
        after_scene = db.get_scene_by_id(after_id)
        scene = db.create_scene(
            project_id,
            title=proposal["title"],
            summary=proposal.get("summary", ""),
            content=proposal.get("content", ""),
        )
        if after_scene is not None:
            all_scenes = db.get_all_scenes(project_id)
            after_index = next(
                (i for i, s in enumerate(all_scenes) if s.id == after_id), None,
            )
            if after_index is not None:
                db.reorder_scene(scene.id, after_index + 1)

        state = get_state(project_id)
        for wf in state.wavefunctions.values():
            if wf.source_scene_id == after_id and wf.collapsed_branch_id:
                wf.target_scene_id = scene.id
                break
        return {"type": "create_scene", "scene_id": scene.id, "title": scene.title}

    if ptype == "update_scene_note":
        scene = db.get_scene_by_id(proposal["scene_id"])
        if scene is not None:
            existing = scene.summary or ""
            new_summary = (existing + "\n" + proposal["note"]).strip()
            db.update_scene_summary(proposal["scene_id"], new_summary)
            return {"type": "update_scene_note", "scene_id": proposal["scene_id"]}
        return {"type": "skipped", "reason": "scene not found"}

    if ptype == "add_progression":
        db.create_psyke_progression(
            proposal["entry_id"],
            proposal["text"],
            scene_id=proposal.get("scene_id"),
        )
        return {"type": "add_progression", "entry_id": proposal["entry_id"]}

    return {"type": "unknown", "proposal": proposal}


def _archive_path(project_id: int) -> Path:
    return CONFIG_DIR / "quantum" / f"archive_{project_id}.json"


def _archive_wavefunction(project_id: int, wf: Wavefunction) -> None:
    path = _archive_path(project_id)
    history: list[dict] = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, OSError):
            history = []

    history.append(json.loads(serialize(wf)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def load_archive(project_id: int) -> list[dict]:
    path = _archive_path(project_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []
