"""Logos structured operations — Phase 2 controlled apply layer.

Logos generates *suggestions* (Phase 1). Phase 2 turns a confirmed suggestion
into a small, validated, structured operation and applies it through the
existing write paths — never via raw SQL, arbitrary code, or silent overwrite.

Operation shape (plain dicts, serializable / debuggable)::

    {"operation": "replace_selection", "target": "manuscript",
     "payload": {"replacement_text": "..."}}

    {"operation": "create_outline_node", "target": "outline",
     "payload": {"act": "Act I", "chapter": "Ch1", "title": "...",
                 "summary": "...", "beat": ""}}

Safety:
* unknown operations are rejected;
* missing target ids / empty required text are rejected;
* manuscript ops act on the editor's QTextCursor (undo-safe, auto-persisting);
* outline ops use the scene service (create/update), never destructive deletes;
* nothing here is applied without the caller having confirmed via the preview.
"""

from __future__ import annotations

from typing import Any

TARGET_MANUSCRIPT = "manuscript"
TARGET_OUTLINE = "outline"
TARGET_PSYKE = "psyke"

# Manuscript operations
OP_REPLACE_SELECTION = "replace_selection"
OP_INSERT_AFTER = "insert_after_selection"
# Outline operations
OP_CREATE_OUTLINE_NODE = "create_outline_node"
OP_UPDATE_OUTLINE_SUMMARY = "update_outline_summary"
OP_UPDATE_OUTLINE_TITLE = "update_outline_title"
# PSYKE operations (Phase 3) — write through existing PSYKE APIs.
OP_APPEND_PSYKE_NOTES = "append_psyke_notes"
OP_CREATE_PSYKE_PROGRESSION = "create_psyke_progression"
OP_CREATE_PSYKE_RELATION = "create_psyke_relation"

_MANUSCRIPT_OPS = {OP_REPLACE_SELECTION, OP_INSERT_AFTER}
_OUTLINE_OPS = {OP_CREATE_OUTLINE_NODE, OP_UPDATE_OUTLINE_SUMMARY, OP_UPDATE_OUTLINE_TITLE}
_PSYKE_OPS = {OP_APPEND_PSYKE_NOTES, OP_CREATE_PSYKE_PROGRESSION, OP_CREATE_PSYKE_RELATION}
KNOWN_OPERATIONS = _MANUSCRIPT_OPS | _OUTLINE_OPS | _PSYKE_OPS


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_operation(op: dict) -> str | None:
    """Static validation (no DB). Returns an error string, or None if valid."""
    if not isinstance(op, dict):
        return "Operation must be a mapping."
    name = op.get("operation")
    if name not in KNOWN_OPERATIONS:
        return f"Unknown operation: {name!r}"
    target = op.get("target")
    if name in _MANUSCRIPT_OPS and target != TARGET_MANUSCRIPT:
        return "Manuscript operation must target 'manuscript'."
    if name in _OUTLINE_OPS and target != TARGET_OUTLINE:
        return "Outline operation must target 'outline'."
    if name in _PSYKE_OPS and target != TARGET_PSYKE:
        return "PSYKE operation must target 'psyke'."
    payload = op.get("payload")
    if not isinstance(payload, dict):
        return "Operation payload must be a mapping."

    if name == OP_REPLACE_SELECTION:
        if not str(payload.get("replacement_text", "")).strip():
            return "Replacement text is empty."
    elif name == OP_INSERT_AFTER:
        if not str(payload.get("text", "")).strip():
            return "Insert text is empty."
    elif name == OP_CREATE_OUTLINE_NODE:
        if not str(payload.get("title", "")).strip():
            return "A new outline node needs a title."
    elif name == OP_UPDATE_OUTLINE_SUMMARY:
        if payload.get("scene_id") is None:
            return "Update summary requires a target node id."
        if not str(payload.get("summary", "")).strip():
            return "Summary is empty."
    elif name == OP_UPDATE_OUTLINE_TITLE:
        if payload.get("scene_id") is None:
            return "Update title requires a target node id."
        if not str(payload.get("title", "")).strip():
            return "Title is empty."
    elif name == OP_APPEND_PSYKE_NOTES:
        if payload.get("entry_id") is None:
            return "A target PSYKE entry id is required."
        if not str(payload.get("note", "")).strip():
            return "Note text is empty."
    elif name == OP_CREATE_PSYKE_PROGRESSION:
        if payload.get("entry_id") is None:
            return "A target PSYKE entry id is required."
        if not str(payload.get("text", "")).strip():
            return "Progression text is empty."
    elif name == OP_CREATE_PSYKE_RELATION:
        if payload.get("entry_id") is None or payload.get("related_entry_id") is None:
            return "Both PSYKE entry ids are required for a relation."
        if payload["entry_id"] == payload["related_entry_id"]:
            return "A relation needs two different entries."
    return None


def validate_operation_against_db(db, project_id: int, op: dict) -> str | None:
    """Validate target ids still exist / belong to the project."""
    err = validate_operation(op)
    if err:
        return err
    name = op["operation"]
    payload = op["payload"]
    if name in (OP_UPDATE_OUTLINE_SUMMARY, OP_UPDATE_OUTLINE_TITLE):
        scene = db.get_scene_by_id(payload["scene_id"])
        if scene is None or scene.project_id != project_id:
            return f"Target outline node {payload['scene_id']} no longer exists."
    elif name in (OP_APPEND_PSYKE_NOTES, OP_CREATE_PSYKE_PROGRESSION):
        entry = db.get_psyke_entry_by_id(payload["entry_id"])
        if entry is None or entry.project_id != project_id:
            return f"PSYKE entry {payload['entry_id']} no longer exists."
    elif name == OP_CREATE_PSYKE_RELATION:
        for key in ("entry_id", "related_entry_id"):
            entry = db.get_psyke_entry_by_id(payload[key])
            if entry is None or entry.project_id != project_id:
                return f"PSYKE entry {payload[key]} no longer exists."
    return None


# ---------------------------------------------------------------------------
# Build proposed operations from a generated reply
# ---------------------------------------------------------------------------


def build_proposed_operations(db, context, action, reply: str) -> list[dict]:
    """Derive the *available* operations for a result (preview-only payloads).

    The preview UI lets the user edit the text and pick which operation to
    apply, so payloads here are suggested starting points — nothing is applied.
    """
    reply = (reply or "").strip()
    if not reply:
        return []
    section = getattr(context, "section_name", "")
    category = getattr(action, "category", "")

    if section == "Manuscript":
        # Only generative actions on a real selection can replace/insert.
        if category == "generative" and getattr(context, "selected_text", "").strip():
            return [
                {"operation": OP_REPLACE_SELECTION, "target": TARGET_MANUSCRIPT,
                 "payload": {"replacement_text": reply}},
                {"operation": OP_INSERT_AFTER, "target": TARGET_MANUSCRIPT,
                 "payload": {"text": reply}},
            ]
        return []

    if section == "Outline":
        scene_id = getattr(context, "current_scene_id", None)
        act, chapter = _node_act_chapter(db, context)
        ops: list[dict] = []
        # Create is always offered (new beat/child/sibling scene).
        ops.append({
            "operation": OP_CREATE_OUTLINE_NODE, "target": TARGET_OUTLINE,
            "payload": {
                "act": act, "chapter": chapter,
                "title": _suggested_title(context, action),
                "summary": reply, "beat": "",
            },
        })
        # Update is offered only when a concrete scene node is selected.
        if scene_id is not None:
            ops.append({
                "operation": OP_UPDATE_OUTLINE_SUMMARY, "target": TARGET_OUTLINE,
                "payload": {"scene_id": scene_id, "summary": reply},
            })
        return ops

    if section == "PSYKE":
        return _psyke_proposed_operations(context, action, reply)

    # Plot / Timeline / Graph: Phase 3 keeps generated results suggestion-only.
    # Their write paths (scene metadata, PSYKE relations) require a reliable
    # target the model's prose does not provide, so nothing is auto-proposed —
    # the result UI shows "Suggestion only" with no Apply button. PSYKE relation
    # / scene-summary writes remain available through their own sections.
    return []


def _psyke_proposed_operations(context, action, reply: str) -> list[dict]:
    """PSYKE is the one Phase 3 section with safe, entry-targeted writes."""
    entry_id = (
        getattr(context, "selected_psyke_entry_id", None)
        or getattr(context, "current_psyke_entry_id", None)
    )
    if entry_id is None:
        return []  # no concrete target -> suggestion only
    name = getattr(action, "name", "")
    if name == "suggest_progression":
        return [{
            "operation": OP_CREATE_PSYKE_PROGRESSION, "target": TARGET_PSYKE,
            "payload": {"entry_id": entry_id, "text": reply,
                        "scene_id": getattr(context, "current_scene_id", None)},
        }]
    # Generative entry actions that enrich the entry append to its notes.
    if getattr(action, "category", "") == "generative":
        return [{
            "operation": OP_APPEND_PSYKE_NOTES, "target": TARGET_PSYKE,
            "payload": {"entry_id": entry_id, "note": reply},
        }]
    return []


def _node_act_chapter(db, context) -> tuple[str, str]:
    scene_id = getattr(context, "current_scene_id", None)
    if scene_id is not None:
        scene = db.get_scene_by_id(scene_id)
        if scene is not None:
            return (scene.act or ""), (scene.chapter or "")
    kind = getattr(context, "outline_node_kind", "")
    label = getattr(context, "outline_node_label", "")
    if kind == "act":
        return label, ""
    if kind == "chapter":
        return "", label
    return "", ""


def _suggested_title(context, action) -> str:
    label = getattr(context, "outline_node_label", "") or "New beat"
    name = getattr(action, "name", "")
    if name == "suggest_next_beat":
        return "New beat"
    if name == "strengthen_conflict":
        return f"{label} — heightened"
    return label


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def apply_logos_operation(db, project_id: int, op: dict, *, editor=None) -> dict:
    """Apply a *validated* operation. Returns a dict with ``ok``, ``events``
    (bus signals the caller should emit) and a human ``detail``.

    Manuscript ops mutate the editor document (undo-safe, autosaves); outline
    ops use the scene service. Raises nothing — errors come back as ``ok=False``.
    """
    err = validate_operation_against_db(db, project_id, op)
    if err:
        return {"ok": False, "events": [], "detail": err}

    name = op["operation"]
    payload = op["payload"]

    if name == OP_REPLACE_SELECTION:
        return _apply_manuscript(editor, replace=True, text=payload["replacement_text"])
    if name == OP_INSERT_AFTER:
        return _apply_manuscript(editor, replace=False, text=payload["text"])

    if name == OP_CREATE_OUTLINE_NODE:
        scene = db.create_scene(
            project_id,
            title=payload["title"],
            summary=payload.get("summary", ""),
            act=payload.get("act", ""),
            chapter=payload.get("chapter", ""),
            beat=payload.get("beat", ""),
        )
        return {
            "ok": True,
            "events": ["scenes_changed", "outline_changed", "plot_changed",
                       "project_data_changed"],
            "detail": f"Created outline node '{payload['title']}'.",
            "scene_id": scene.id,
        }
    if name == OP_UPDATE_OUTLINE_SUMMARY:
        db.update_scene_summary(payload["scene_id"], payload["summary"])
        return {
            "ok": True,
            "events": ["scene_changed", "outline_changed", "project_data_changed"],
            "detail": "Updated outline node summary.",
            "scene_id": payload["scene_id"],
        }
    if name == OP_UPDATE_OUTLINE_TITLE:
        db.update_scene_title(payload["scene_id"], payload["title"])
        return {
            "ok": True,
            "events": ["scene_changed", "outline_changed", "project_data_changed"],
            "detail": "Updated outline node title.",
            "scene_id": payload["scene_id"],
        }

    if name == OP_APPEND_PSYKE_NOTES:
        entry = db.get_psyke_entry_by_id(payload["entry_id"])
        existing = (entry.notes or "").rstrip()
        addition = payload["note"].strip()
        merged = f"{existing}\n\n{addition}" if existing else addition
        db.update_psyke_entry(
            entry.id, name=entry.name, entry_type=entry.entry_type,
            aliases=entry.aliases, notes=merged, is_global=entry.is_global,
            details=db.get_psyke_entry_details(entry.id),
        )
        return {
            "ok": True,
            "events": ["psyke_changed", "project_data_changed"],
            "detail": "Appended to PSYKE entry notes.",
            "entry_id": entry.id,
        }
    if name == OP_CREATE_PSYKE_PROGRESSION:
        db.create_psyke_progression(
            payload["entry_id"], payload["text"],
            scene_id=payload.get("scene_id"),
        )
        return {
            "ok": True,
            "events": ["psyke_changed", "project_data_changed"],
            "detail": "Added PSYKE progression.",
            "entry_id": payload["entry_id"],
        }
    if name == OP_CREATE_PSYKE_RELATION:
        db.add_psyke_relation(
            payload["entry_id"], payload["related_entry_id"],
            relation_type=payload.get("relation_type", ""),
        )
        return {
            "ok": True,
            "events": ["psyke_changed", "project_data_changed"],
            "detail": "Created PSYKE relation.",
            "entry_id": payload["entry_id"],
        }

    return {"ok": False, "events": [], "detail": f"Unknown operation: {name!r}"}


def _apply_manuscript(editor, *, replace: bool, text: str) -> dict[str, Any]:
    if editor is None:
        return {"ok": False, "events": [], "detail": "No active manuscript editor."}
    cursor = editor.textCursor()
    if replace:
        if not cursor.hasSelection():
            return {
                "ok": False, "events": [],
                "detail": "The selection has changed — reselect the text and try again.",
            }
        cursor.insertText(text)  # replaces the current selection (undo-safe)
    else:
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionEnd())
        cursor.insertText("\n\n" + text if text else "")
    editor.setTextCursor(cursor)
    return {
        "ok": True,
        "events": ["scene_changed", "project_data_changed"],
        "detail": "Applied to manuscript." if replace else "Inserted after selection.",
    }
