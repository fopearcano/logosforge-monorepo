"""Controlled-apply target adapters (Phase 10M).

Each adapter knows how to *read* a target's current text and *apply* normalized
text to it through the Database service layer — never raw SQL, never broad object
mutation, and only the allowed apply modes. Adapters validate the target exists
and the mode is permitted. No Qt, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

# Apply modes shared across adapters (subset per adapter).
_REPLACE_MODES = ("replace", "replace_selection", "append", "insert_after",
                  "insert_before", "manual_copy")


@dataclass
class TargetState:
    exists: bool
    text: str = ""
    writing_mode: str = ""


def _writing_mode(db, project_id: int) -> str:
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        return get_project_writing_mode_by_id(db, project_id)
    except Exception:
        return "novel"


def _compose(current: str, proposed: str, mode: str) -> str:
    if mode == "append":
        return (current + "\n\n" + proposed) if current else proposed
    if mode == "insert_before":
        return (proposed + "\n\n" + current) if current else proposed
    # replace / replace_selection / insert_after / manual_copy -> full replace of
    # the target field (selection-level replace is a UI concern; the field-level
    # adapter replaces the whole field text).
    return proposed


class BaseTargetAdapter:
    target_type = "base"
    allowed_modes = _REPLACE_MODES

    def __init__(self, db, project_id: int, target_id):
        self.db = db
        self.project_id = project_id
        self.target_id = target_id

    def read(self) -> TargetState:
        raise NotImplementedError

    def validate_mode(self, mode: str) -> str | None:
        if mode not in self.allowed_modes:
            return f"Apply mode '{mode}' not allowed for {self.target_type}."
        return None

    def apply(self, proposed_text: str, mode: str) -> None:
        raise NotImplementedError


class SceneTargetAdapter(BaseTargetAdapter):
    target_type = "scene"

    def read(self) -> TargetState:
        scene = self.db.get_scene_by_id(self.target_id)
        if scene is None:
            return TargetState(exists=False,
                               writing_mode=_writing_mode(self.db, self.project_id))
        return TargetState(exists=True, text=getattr(scene, "content", "") or "",
                           writing_mode=_writing_mode(self.db, self.project_id))

    def apply(self, proposed_text: str, mode: str) -> None:
        cur = self.read().text
        self.db.update_scene_content(self.target_id, _compose(cur, proposed_text, mode))


# Manuscript / screenplay_block apply at scene granularity (field-level replace).
class ManuscriptTargetAdapter(SceneTargetAdapter):
    target_type = "manuscript"


class ScreenplayBlockTargetAdapter(SceneTargetAdapter):
    target_type = "screenplay_block"


class OutlineTargetAdapter(BaseTargetAdapter):
    target_type = "outline_node"
    allowed_modes = ("replace", "append", "manual_copy")

    def read(self) -> TargetState:
        node = self.db.get_outline_node_by_id(self.target_id)
        if node is None:
            return TargetState(exists=False)
        return TargetState(exists=True, text=getattr(node, "description", "") or "",
                           writing_mode=_writing_mode(self.db, self.project_id))

    def apply(self, proposed_text: str, mode: str) -> None:
        cur = self.read().text
        # Outline structural (multi-node) apply goes through the outline parser
        # elsewhere; the adapter only updates a single node's description text.
        self.db.update_outline_node(self.target_id,
                                    description=_compose(cur, proposed_text, mode))


class PsykeTargetAdapter(BaseTargetAdapter):
    target_type = "psyke_entry"
    allowed_modes = ("replace", "append", "manual_copy")

    def read(self) -> TargetState:
        entry = self.db.get_psyke_entry_by_id(self.target_id)
        if entry is None:
            return TargetState(exists=False)
        return TargetState(exists=True, text=getattr(entry, "notes", "") or "",
                           writing_mode=_writing_mode(self.db, self.project_id))

    def apply(self, proposed_text: str, mode: str) -> None:
        entry = self.db.get_psyke_entry_by_id(self.target_id)
        if entry is None:
            return
        cur = getattr(entry, "notes", "") or ""
        # Update ONLY the notes field; name/type/aliases/relations are preserved.
        details = None
        try:
            details = self.db.get_psyke_entry_details(self.target_id)
        except Exception:
            details = None
        self.db.update_psyke_entry(
            self.target_id, name=getattr(entry, "name", "") or "",
            entry_type=getattr(entry, "entry_type", "other") or "other",
            aliases=getattr(entry, "aliases", "") or "",
            notes=_compose(cur, proposed_text, mode),
            is_global=bool(getattr(entry, "is_global", False)), details=details)


class NoteTargetAdapter(BaseTargetAdapter):
    target_type = "note"
    allowed_modes = ("replace", "append", "manual_copy")

    def read(self) -> TargetState:
        note = self.db.get_note_by_id(self.target_id)
        if note is None:
            return TargetState(exists=False)
        return TargetState(exists=True, text=getattr(note, "content", "") or "",
                           writing_mode=_writing_mode(self.db, self.project_id))

    def apply(self, proposed_text: str, mode: str) -> None:
        note = self.db.get_note_by_id(self.target_id)
        if note is None:
            return
        cur = getattr(note, "content", "") or ""
        # Update ONLY the body; title/tags/pinned preserved.
        self.db.update_note(
            self.target_id, getattr(note, "title", "") or "",
            content=_compose(cur, proposed_text, mode),
            tags=getattr(note, "tags", "") or "",
            pinned=bool(getattr(note, "pinned", False)))


_ADAPTERS = {
    "scene": SceneTargetAdapter,
    "manuscript": ManuscriptTargetAdapter,
    "screenplay_block": ScreenplayBlockTargetAdapter,
    "outline_node": OutlineTargetAdapter,
    "psyke_entry": PsykeTargetAdapter,
    "note": NoteTargetAdapter,
}


def get_adapter(db, project_id: int, target_type: str, target_id):
    """Return a target adapter, or None for unsupported/deferred target types."""
    cls = _ADAPTERS.get(target_type)
    if cls is None:
        return None
    return cls(db, project_id, target_id)


def supported_target_types() -> tuple[str, ...]:
    return tuple(_ADAPTERS.keys())
