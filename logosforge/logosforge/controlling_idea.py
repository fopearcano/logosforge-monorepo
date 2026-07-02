"""Controlling Idea — McKee-inspired narrative compass.

A Controlling Idea is the story's central meaning: ``VALUE + CAUSE``.
Example: "Justice prevails when the hero sacrifices personal safety for truth."

This module exposes a small, side-effect-free helper layer used by:
- the Assistant context builder (injects a compact CI block)
- the ``/idea`` slash command
- the Idea di Controllo plugin (menu actions + builder UI)

Storage: project-level ``settings_json`` under the key ``controlling_idea``.
No schema migration is required — we reuse the existing project settings store.

PSYKE linking: a normal PSYKE entry of type ``"theme"`` is created on demand
via ``db.create_psyke_entry``; its id is stored in ``theme_psyke_entry_id`` so
subsequent updates reuse the same entry. Per-entry alignment
(supports/opposes/tests/transforms) is kept inside CI settings, **not** on the
PSYKE entry — so we never silently mutate other plugins' data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

CI_KEY = "controlling_idea"

VALID_CHARGES = ("positive", "negative", "ambiguous")
ALIGNMENT_LABELS = ("supports", "opposes", "tests", "transforms")


@dataclass
class ControllingIdea:
    """Project-level narrative compass."""

    enabled: bool = False
    value_charge: str = "positive"  # one of VALID_CHARGES
    value: str = ""
    cause: str = ""
    statement: str = ""
    counter_idea: str = ""
    notes: str = ""
    linked_psyke_entries: list[int] = field(default_factory=list)
    linked_themes: list[int] = field(default_factory=list)
    scene_alignment: dict[str, str] = field(default_factory=dict)
    psyke_alignment: dict[str, str] = field(default_factory=dict)
    theme_psyke_entry_id: int | None = None

    def is_defined(self) -> bool:
        return bool(self.statement or (self.value and self.cause))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ControllingIdea:
        if not isinstance(data, dict):
            return cls()
        # Sanitize/coerce
        charge = data.get("value_charge", "positive")
        if charge not in VALID_CHARGES:
            charge = "positive"

        def _clean_alignment(raw: Any) -> dict[str, str]:
            if not isinstance(raw, dict):
                return {}
            out: dict[str, str] = {}
            for k, v in raw.items():
                if isinstance(v, str) and v in ALIGNMENT_LABELS:
                    out[str(k)] = v
            return out

        return cls(
            enabled=bool(data.get("enabled", False)),
            value_charge=charge,
            value=str(data.get("value", "")),
            cause=str(data.get("cause", "")),
            statement=str(data.get("statement", "")),
            counter_idea=str(data.get("counter_idea", "")),
            notes=str(data.get("notes", "")),
            linked_psyke_entries=[
                int(x) for x in data.get("linked_psyke_entries", [])
                if isinstance(x, (int, float)) and not isinstance(x, bool)
            ],
            linked_themes=[
                int(x) for x in data.get("linked_themes", [])
                if isinstance(x, (int, float)) and not isinstance(x, bool)
            ],
            scene_alignment=_clean_alignment(data.get("scene_alignment")),
            psyke_alignment=_clean_alignment(data.get("psyke_alignment")),
            theme_psyke_entry_id=(
                int(data["theme_psyke_entry_id"])
                if isinstance(data.get("theme_psyke_entry_id"), (int, float))
                and not isinstance(data["theme_psyke_entry_id"], bool)
                else None
            ),
        )


# ---------------------------------------------------------------------------
# Storage (per-project)
# ---------------------------------------------------------------------------

def load(db: Any, project_id: int) -> ControllingIdea:
    settings = db.get_project_settings(project_id) or {}
    return ControllingIdea.from_dict(settings.get(CI_KEY))


def save(db: Any, project_id: int, idea: ControllingIdea) -> None:
    settings = db.get_project_settings(project_id) or {}
    settings = dict(settings)
    settings[CI_KEY] = idea.to_dict()
    db.save_project_settings(project_id, settings)


def clear(db: Any, project_id: int) -> None:
    settings = db.get_project_settings(project_id) or {}
    if CI_KEY in settings:
        settings = dict(settings)
        settings.pop(CI_KEY, None)
        db.save_project_settings(project_id, settings)


# ---------------------------------------------------------------------------
# PSYKE linking
# ---------------------------------------------------------------------------

def _theme_entry_name(idea: ControllingIdea) -> str:
    if idea.value:
        return f"Controlling Idea — {idea.value}"
    return "Controlling Idea"


def ensure_theme_entry(db: Any, project_id: int) -> int | None:
    """Create or update the PSYKE theme entry that mirrors this CI.

    Returns the entry id, or None if no idea is defined.
    """
    idea = load(db, project_id)
    if not idea.is_defined():
        return None

    notes_lines = []
    if idea.statement:
        notes_lines.append(idea.statement)
    if idea.value_charge:
        notes_lines.append(f"Value charge: {idea.value_charge}")
    if idea.counter_idea:
        notes_lines.append(f"Counter-idea: {idea.counter_idea}")
    if idea.notes:
        notes_lines.append(idea.notes)
    notes = "\n".join(notes_lines)

    if idea.theme_psyke_entry_id is not None:
        existing = db.get_psyke_entry_by_id(idea.theme_psyke_entry_id)
        if existing is not None and existing.project_id == project_id:
            db.update_psyke_entry(
                entry_id=existing.id,
                name=_theme_entry_name(idea),
                entry_type="theme",
                aliases=existing.aliases or "",
                notes=notes,
                is_global=existing.is_global,
            )
            return existing.id

    entry = db.create_psyke_entry(
        project_id=project_id,
        name=_theme_entry_name(idea),
        entry_type="theme",
        notes=notes,
    )
    idea.theme_psyke_entry_id = entry.id
    save(db, project_id, idea)
    return entry.id


def set_scene_alignment(
    db: Any, project_id: int, scene_id: int, alignment: str | None,
) -> None:
    """Mark a scene as supports/opposes/tests/transforms (or clear with None)."""
    idea = load(db, project_id)
    key = str(int(scene_id))
    if alignment is None or alignment == "":
        idea.scene_alignment.pop(key, None)
    elif alignment in ALIGNMENT_LABELS:
        idea.scene_alignment[key] = alignment
    else:
        raise ValueError(f"Invalid alignment: {alignment!r}")
    save(db, project_id, idea)


def set_psyke_alignment(
    db: Any, project_id: int, entry_id: int, alignment: str | None,
) -> None:
    idea = load(db, project_id)
    key = str(int(entry_id))
    if alignment is None or alignment == "":
        idea.psyke_alignment.pop(key, None)
    elif alignment in ALIGNMENT_LABELS:
        idea.psyke_alignment[key] = alignment
    else:
        raise ValueError(f"Invalid alignment: {alignment!r}")
    save(db, project_id, idea)


def link_psyke_entry(db: Any, project_id: int, entry_id: int) -> None:
    idea = load(db, project_id)
    if entry_id not in idea.linked_psyke_entries:
        idea.linked_psyke_entries.append(int(entry_id))
        save(db, project_id, idea)


def unlink_psyke_entry(db: Any, project_id: int, entry_id: int) -> None:
    idea = load(db, project_id)
    if entry_id in idea.linked_psyke_entries:
        idea.linked_psyke_entries.remove(int(entry_id))
        save(db, project_id, idea)


# ---------------------------------------------------------------------------
# Assistant context block
# ---------------------------------------------------------------------------

def _gomckee_active() -> bool:
    """Return True iff the Go McKee plugin is ENABLED.

    Uses the real persisted toggle (plugin_states), not mere load state,
    so enabling/disabling Go McKee genuinely changes whether the
    Controlling Idea is treated as the highest-priority constraint.
    """
    try:
        from logosforge.gomckee_bridge import is_gomckee_enabled
        return is_gomckee_enabled()
    except Exception:
        return False


def gather_controlling_idea_context(
    db: Any, project_id: int, scene_id: int | None = None,
) -> str:
    """Return a compact ``[Idea di Controllo]`` block for the Assistant.

    Returns an empty string when no CI is defined — caller should skip
    appending it in that case.
    """
    idea = load(db, project_id)
    if not idea.is_defined():
        return ""

    lines: list[str] = ["[Idea di Controllo]"]
    if idea.statement:
        lines.append(f"Statement: {idea.statement}")
    if idea.value:
        lines.append(f"Value: {idea.value} ({idea.value_charge})")
    if idea.cause:
        lines.append(f"Cause: {idea.cause}")
    if idea.counter_idea:
        lines.append(f"Counter-Idea: {idea.counter_idea}")

    # Relevant PSYKE references — names only, capped to keep the block compact
    relevant_psyke_ids = set(idea.linked_psyke_entries) | set(
        int(k) for k in idea.psyke_alignment
    )
    if relevant_psyke_ids:
        try:
            entries = db.get_all_psyke_entries(project_id)
            id_to_name = {e.id: e.name for e in entries}
        except Exception:
            id_to_name = {}
        names = []
        for pid in list(relevant_psyke_ids)[:6]:
            name = id_to_name.get(pid)
            if not name:
                continue
            alignment = idea.psyke_alignment.get(str(pid))
            if alignment:
                names.append(f"{name} ({alignment})")
            else:
                names.append(name)
        if names:
            lines.append("Relevant PSYKE: " + ", ".join(names))

    # Active-scene alignment
    if scene_id is not None:
        alignment = idea.scene_alignment.get(str(scene_id))
        if alignment:
            lines.append(f"This scene currently: {alignment}")

    if _gomckee_active():
        lines.append(
            "Note: Go McKee is active — treat the Controlling Idea as the "
            "highest-priority story constraint."
        )

    # Operational reminder for the model — keep it short.
    lines.append(
        "Use this idea operationally: evaluate suggestions against it; "
        "do not preach it."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------

@dataclass
class CheckReport:
    statement: str
    aligned_scenes: list[tuple[int, str, str]] = field(default_factory=list)
    opposed_scenes: list[tuple[int, str, str]] = field(default_factory=list)
    tested_scenes: list[tuple[int, str, str]] = field(default_factory=list)
    transformed_scenes: list[tuple[int, str, str]] = field(default_factory=list)
    unmarked_scenes: list[tuple[int, str]] = field(default_factory=list)
    unaligned_psyke: list[tuple[int, str]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def format(self) -> str:
        lines: list[str] = ["[Idea di Controllo — Check]"]
        if self.statement:
            lines.append(f"Statement: {self.statement}")

        def _block(label: str, items: Iterable[tuple[int, str, str]]) -> None:
            items = list(items)
            if items:
                lines.append(f"{label} ({len(items)}):")
                for sid, title, _ in items[:8]:
                    lines.append(f"  • [{sid}] {title}")

        _block("Supports", self.aligned_scenes)
        _block("Opposes", self.opposed_scenes)
        _block("Tests", self.tested_scenes)
        _block("Transforms", self.transformed_scenes)

        if self.unmarked_scenes:
            lines.append(f"Weak (no relation, {len(self.unmarked_scenes)}):")
            for sid, title in self.unmarked_scenes[:8]:
                lines.append(f"  • [{sid}] {title}")

        if self.unaligned_psyke:
            lines.append(f"PSYKE not yet aligned ({len(self.unaligned_psyke)}):")
            for eid, name in self.unaligned_psyke[:6]:
                lines.append(f"  • {name}")

        if self.suggestions:
            lines.append("Suggestions:")
            for s in self.suggestions:
                lines.append(f"  • {s}")
        return "\n".join(lines)


def check(db: Any, project_id: int) -> CheckReport:
    """Run the Controlling Idea checker for the project."""
    idea = load(db, project_id)
    if not idea.is_defined():
        return CheckReport(
            statement="",
            suggestions=[
                "No Controlling Idea defined. Use '/idea set' to begin."
            ],
        )

    report = CheckReport(statement=idea.statement or f"{idea.value} — {idea.cause}")

    scenes = db.get_all_scenes(project_id)
    for sc in scenes:
        alignment = idea.scene_alignment.get(str(sc.id))
        row = (sc.id, sc.title, alignment or "")
        if alignment == "supports":
            report.aligned_scenes.append(row)
        elif alignment == "opposes":
            report.opposed_scenes.append(row)
        elif alignment == "tests":
            report.tested_scenes.append(row)
        elif alignment == "transforms":
            report.transformed_scenes.append(row)
        else:
            report.unmarked_scenes.append((sc.id, sc.title))

    try:
        entries = db.get_all_psyke_entries(project_id)
    except Exception:
        entries = []
    for e in entries:
        if e.id == idea.theme_psyke_entry_id:
            continue
        if (
            e.id not in idea.linked_psyke_entries
            and str(e.id) not in idea.psyke_alignment
        ):
            report.unaligned_psyke.append((e.id, e.name))

    # Operational suggestions — never academic
    total = len(scenes)
    aligned_total = (
        len(report.aligned_scenes)
        + len(report.opposed_scenes)
        + len(report.tested_scenes)
        + len(report.transformed_scenes)
    )
    if total and aligned_total == 0:
        report.suggestions.append(
            "No scenes are yet marked. Tag a turning-point scene with "
            "'supports' or 'opposes' to anchor the arc."
        )
    elif total and aligned_total < total / 3:
        report.suggestions.append(
            "Most scenes have no Controlling Idea relation. Consider marking "
            "the scenes that turn on the value."
        )
    if (
        report.opposed_scenes
        and not report.aligned_scenes
        and not report.transformed_scenes
    ):
        report.suggestions.append(
            "Only opposing scenes are marked. Add at least one supporting or "
            "transforming beat to give the value somewhere to land."
        )
    if not idea.counter_idea:
        report.suggestions.append(
            "No counter-idea defined. A strong opposing worldview sharpens "
            "the Controlling Idea."
        )
    if idea.theme_psyke_entry_id is None:
        report.suggestions.append(
            "Create a PSYKE theme entry for this Controlling Idea via "
            "'/idea link' to surface it in graph and outline contexts."
        )

    return report


# ---------------------------------------------------------------------------
# /idea slash command
# ---------------------------------------------------------------------------

def handle_command(
    db: Any, project_id: int, args: list[str],
) -> dict[str, Any]:
    """Handle the ``/idea`` slash command.

    Returns a dict ``{status: 'ok'|'error', message: str}`` for the caller
    to display. Write actions always return a confirmation message
    describing exactly what was changed.
    """
    if not args:
        idea = load(db, project_id)
        if not idea.is_defined():
            return {
                "status": "ok",
                "message": (
                    "No Controlling Idea defined.\n"
                    "Try: /idea set value=\"justice\" cause=\"when the hero "
                    "sacrifices safety for truth\""
                ),
            }
        return {"status": "ok", "message": gather_controlling_idea_context(db, project_id)}

    sub = args[0].lower()
    rest = args[1:]

    if sub == "explain":
        idea = load(db, project_id)
        if not idea.is_defined():
            return {
                "status": "ok",
                "message": "No Controlling Idea defined.",
            }
        return {
            "status": "ok",
            "message": gather_controlling_idea_context(db, project_id),
        }

    if sub == "check":
        report = check(db, project_id)
        return {"status": "ok", "message": report.format()}

    if sub == "set":
        fields = _parse_kv(rest)
        idea = load(db, project_id)
        for key in (
            "value", "cause", "statement", "counter_idea",
            "value_charge", "notes",
        ):
            if key in fields:
                setattr(idea, key, fields[key])
        if "value_charge" in fields and fields["value_charge"] not in VALID_CHARGES:
            return {
                "status": "error",
                "message": f"value_charge must be one of {VALID_CHARGES}",
            }
        # Auto-compose statement if value+cause present and no explicit statement
        if not idea.statement and idea.value and idea.cause:
            idea.statement = f"{idea.value.capitalize()} prevails {idea.cause}."
        idea.enabled = True
        save(db, project_id, idea)
        return {
            "status": "ok",
            "message": (
                "Controlling Idea updated.\n"
                + (gather_controlling_idea_context(db, project_id) or "")
            ),
        }

    if sub == "link":
        # /idea link            → create/update PSYKE theme entry
        # /idea link <entry_id> [supports|opposes|tests|transforms]
        if not rest:
            new_id = ensure_theme_entry(db, project_id)
            if new_id is None:
                return {
                    "status": "error",
                    "message": "Define a Controlling Idea first with /idea set.",
                }
            return {
                "status": "ok",
                "message": f"PSYKE theme entry ready (id={new_id}).",
            }
        try:
            target_id = int(rest[0])
        except ValueError:
            return {"status": "error", "message": "Expected a PSYKE entry id."}
        alignment = rest[1] if len(rest) > 1 else None
        if alignment is not None and alignment not in ALIGNMENT_LABELS:
            return {
                "status": "error",
                "message": (
                    f"Alignment must be one of "
                    f"{ALIGNMENT_LABELS}."
                ),
            }
        link_psyke_entry(db, project_id, target_id)
        if alignment:
            set_psyke_alignment(db, project_id, target_id, alignment)
        return {
            "status": "ok",
            "message": (
                f"Linked PSYKE #{target_id}"
                + (f" as {alignment}." if alignment else ".")
            ),
        }

    if sub == "scene":
        # /idea scene <scene_id> <alignment>
        if len(rest) < 2:
            return {
                "status": "error",
                "message": "Usage: /idea scene <scene_id> <supports|opposes|tests|transforms|clear>",
            }
        try:
            sid = int(rest[0])
        except ValueError:
            return {"status": "error", "message": "Invalid scene id."}
        alignment = rest[1].lower()
        if alignment == "clear":
            set_scene_alignment(db, project_id, sid, None)
            return {"status": "ok", "message": f"Cleared alignment for scene {sid}."}
        if alignment not in ALIGNMENT_LABELS:
            return {
                "status": "error",
                "message": f"Alignment must be one of {ALIGNMENT_LABELS}.",
            }
        set_scene_alignment(db, project_id, sid, alignment)
        return {
            "status": "ok",
            "message": f"Scene {sid} marked as {alignment}.",
        }

    return {
        "status": "error",
        "message": (
            "Unknown subcommand. Try: /idea set, /idea explain, /idea check, "
            "/idea link, /idea scene"
        ),
    }


def _parse_kv(tokens: list[str]) -> dict[str, str]:
    """Parse ``key=value`` tokens, supporting quoted values.

    Quoted values can span multiple tokens, e.g. ``cause="when the hero acts"``.
    """
    text = " ".join(tokens)
    result: dict[str, str] = {}
    i = 0
    while i < len(text):
        # Skip whitespace
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        # Read key
        start = i
        while i < len(text) and text[i] not in ("=", " ") and text[i] != "\t":
            i += 1
        key = text[start:i].strip()
        if i >= len(text) or text[i] != "=":
            # Standalone token, ignore
            continue
        i += 1  # skip '='
        # Read value: quoted or bare
        if i < len(text) and text[i] in ('"', "'"):
            quote = text[i]
            i += 1
            start = i
            while i < len(text) and text[i] != quote:
                i += 1
            value = text[start:i]
            if i < len(text):
                i += 1  # skip closing quote
        else:
            start = i
            while i < len(text) and not text[i].isspace():
                i += 1
            value = text[start:i]
        if key:
            result[key] = value
    return result
