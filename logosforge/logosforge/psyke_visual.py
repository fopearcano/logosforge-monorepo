"""PSYKE visual-memory layer for the Graphic Novel Engine.

Graphic novels need PSYKE to remember how things LOOK and how those
looks RECUR. This module stores visual storytelling metadata on PSYKE
entries (under details_json["visual"]) and derives recurrence/callback
information from the page/panel/continuity tables — without duplicating
PSYKE or adding a second codex.

Pure core/app logic: no UI, no Tauri, no filesystem, no providers.
"""

from __future__ import annotations

from typing import Any


# Visual fields for a character PSYKE entry (entry_type == "character").
CHARACTER_VISUAL_FIELDS: tuple[str, ...] = (
    "silhouette",
    "shape_language",
    "color_identity",
    "costume_state",
    "pose_language",
    "gesture_vocabulary",
    "facial_expression_range",
    "visual_symbolism",
)

# Visual fields for a place/location PSYKE entry (entry_type == "place").
LOCATION_VISUAL_FIELDS: tuple[str, ...] = (
    "architecture",
    "lighting_mood",
    "color_palette",
    "environmental_motifs",
    "recurring_camera_angles",
    "spatial_continuity_notes",
    "recurring_objects",
)

# Visual fields for an object/prop PSYKE entry (entry_type == "object").
OBJECT_VISUAL_FIELDS: tuple[str, ...] = (
    "appearance",
    "scale",
    "owner",
    "continuity_state",
    "symbolic_meaning",
    "first_appearance",
    "recurring_use",
)

# Visual fields for a theme PSYKE entry (entry_type == "theme").
THEME_VISUAL_FIELDS: tuple[str, ...] = (
    "visual_manifestations",
    "symbolic_colors",
    "recurring_shapes",
    "motif_family",
)

# Visual fields for a lore PSYKE entry (entry_type == "lore").
LORE_VISUAL_FIELDS: tuple[str, ...] = (
    "visual_rules",
    "design_constraints",
    "world_style_notes",
)

# Kinds of recurring motif (for a motif tracked as a theme/object entry).
MOTIF_KINDS: tuple[str, ...] = (
    "symbol",
    "object",
    "color",
    "pose",
    "framing",
    "composition",
)


def visual_fields_for_type(entry_type: str) -> tuple[str, ...]:
    """Return the relevant visual field names for a PSYKE entry type."""
    et = (entry_type or "").lower()
    if et == "character":
        return CHARACTER_VISUAL_FIELDS
    if et == "place":
        return LOCATION_VISUAL_FIELDS
    if et == "object":
        return OBJECT_VISUAL_FIELDS
    if et == "theme":
        return THEME_VISUAL_FIELDS
    if et == "lore":
        return LORE_VISUAL_FIELDS
    return ()


def get_visual_memory(db: Any, entry_id: int) -> dict:
    """Visual metadata stored on a PSYKE entry (may be empty)."""
    return db.get_psyke_visual_memory(entry_id)


def set_visual_memory(db: Any, entry_id: int, **fields: Any) -> None:
    """Merge visual metadata onto a PSYKE entry. Empty values clear a key."""
    db.set_psyke_visual_memory(entry_id, dict(fields))


# ---------------------------------------------------------------------------
# Panel context — where motifs appeared, where objects reappear, callbacks.
# ---------------------------------------------------------------------------

def get_motif_recurrences(db: Any, project_id: int) -> dict[str, list[int]]:
    """Map each visual-motif token to the panel ids it appears in.

    Reads GraphicNovelPanel.visual_motifs (CSV). A motif appearing in more
    than one panel is a genuine recurrence/callback.
    """
    recurrences: dict[str, list[int]] = {}
    for page in db.get_gn_pages(project_id):
        for panel in db.get_gn_panels_for_page(page.id):
            for motif in db.csv_split(panel.visual_motifs):
                recurrences.setdefault(motif, []).append(panel.id)
    return recurrences


def get_object_reappearances(db: Any, project_id: int) -> dict[str, list[dict]]:
    """Map each continuity item to its ordered appearances (page/panel/state).

    Captures object persistence and visual callbacks across the book.
    """
    result: dict[str, list[dict]] = {}
    for item in db.get_gn_continuity_items(project_id):
        appearances = db.get_gn_continuity_appearances(item.id)
        result[item.name] = [
            {
                "page_id": a.page_id,
                "panel_id": a.panel_id,
                "state": a.state_description,
                "status": a.continuity_status,
            }
            for a in appearances
        ]
    return result


def get_visual_callbacks(db: Any, project_id: int) -> dict[str, list[int]]:
    """Motifs that recur (appear in 2+ panels) — i.e. visual callbacks."""
    return {
        motif: panels
        for motif, panels in get_motif_recurrences(db, project_id).items()
        if len(panels) >= 2
    }


# ---------------------------------------------------------------------------
# Appearance matching — connect a PSYKE entry to pages/panels by name (§4).
# ---------------------------------------------------------------------------

def _entry_names(db: Any, entry: Any) -> set[str]:
    names = {(entry.name or "").strip().lower()}
    for alias in db.csv_split(entry.aliases or ""):
        names.add(alias.strip().lower())
    names.discard("")
    return names


def get_visual_appearances_for_psyke_entry(
    db: Any, project_id: int, entry_id: int,
) -> list[dict]:
    """Pages/panels where a PSYKE entry appears, matched by name/alias.

    Characters are matched against ``panel.characters_present``; every other
    entry type (themes/objects/motifs) is matched against
    ``panel.visual_motifs``. No hard foreign keys are required — matching is
    by name first. Returns appearances in reading order.
    """
    entry = db.get_psyke_entry_by_id(entry_id)
    if entry is None:
        return []
    names = _entry_names(db, entry)
    if not names:
        return []
    is_character = (entry.entry_type or "").lower() == "character"

    out: list[dict] = []
    for page in db.get_gn_pages(project_id):
        for panel in db.get_gn_panels_for_page(page.id):
            field = panel.characters_present if is_character else panel.visual_motifs
            tokens = {t.strip().lower() for t in db.csv_split(field)}
            if names & tokens:
                out.append({
                    "page_id": page.id,
                    "page_number": page.page_number,
                    "panel_id": panel.id,
                    "panel_number": panel.panel_number,
                })
    return out


def _format_appearances(appearances: list[dict], limit: int = 6) -> str:
    bits = [
        f"Page {a['page_number']} Panel {a['panel_number']}"
        for a in appearances[:limit]
    ]
    return ", ".join(bits)


# ---------------------------------------------------------------------------
# Assistant context block
# ---------------------------------------------------------------------------

_MAX_ENTRIES = 8
_MAX_MOTIFS = 10


def build_visual_memory_context(
    db: Any, project_id: int, entry_id: int | None = None,
) -> str:
    """Compact ``[Visual Memory]`` block for the Assistant.

    With *entry_id*, focuses on that entry's visual identity. Otherwise it
    summarizes character/location visual identity plus tracked motifs and
    recurring objects across the project. Returns "" when there is nothing
    visual to report.
    """
    lines: list[str] = []

    if entry_id is not None:
        entry = db.get_psyke_entry_by_id(entry_id)
        if entry is not None:
            visual = db.get_psyke_visual_memory(entry_id)
            if visual:
                lines.append(f"{entry.name} ({entry.entry_type}):")
                for key, value in visual.items():
                    lines.append(f"- {key.replace('_', ' ')}: {value}")
                appearances = get_visual_appearances_for_psyke_entry(
                    db, project_id, entry_id,
                )
                if appearances:
                    lines.append(
                        "- appears in: " + _format_appearances(appearances)
                    )
    else:
        entries = db.get_all_psyke_entries(project_id)
        shown = 0
        for entry in entries:
            visual = db.get_psyke_visual_memory(entry.id)
            if not visual:
                continue
            bits = ", ".join(
                f"{k.replace('_', ' ')}: {v}" for k, v in list(visual.items())[:4]
            )
            line = f"- {entry.name} ({entry.entry_type}): {bits}"
            appearances = get_visual_appearances_for_psyke_entry(
                db, project_id, entry.id,
            )
            if appearances:
                line += "; appears in: " + _format_appearances(appearances, 3)
            lines.append(line)
            shown += 1
            if shown >= _MAX_ENTRIES:
                break

        callbacks = get_visual_callbacks(db, project_id)
        if callbacks:
            motif_bits = ", ".join(
                f"{m} (×{len(p)})" for m, p in list(callbacks.items())[:_MAX_MOTIFS]
            )
            lines.append(f"Recurring motifs: {motif_bits}")

        objects = get_object_reappearances(db, project_id)
        recurring_objs = [
            f"{name} (×{len(apps)})"
            for name, apps in objects.items() if len(apps) >= 2
        ]
        if recurring_objs:
            lines.append("Recurring objects: " + ", ".join(recurring_objs[:_MAX_MOTIFS]))

    if not lines:
        return ""
    return "[Visual Memory]\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Lightweight visual-continuity review helpers (§7)
# ---------------------------------------------------------------------------

from dataclasses import dataclass  # noqa: E402


@dataclass
class VisualReviewCheck:
    """One visual-memory finding. entry_id is None for project-level checks."""

    check_type: str
    message: str
    severity: str = "info"      # "info" | "warning"
    entry_id: int | None = None


def review_visual_memory(db: Any, project_id: int) -> list[VisualReviewCheck]:
    """Surface gaps in visual storytelling memory (data-driven, no UI).

    Checks: character visual identity missing (for characters that appear),
    location design missing, motif appears only once, object appears without
    a continuity state.
    """
    checks: list[VisualReviewCheck] = []

    for entry in db.get_all_psyke_entries(project_id):
        etype = (entry.entry_type or "").lower()
        if etype not in ("character", "place"):
            continue
        if db.get_psyke_visual_memory(entry.id):
            continue
        if etype == "character":
            # Only nag about characters that actually appear on the page.
            if get_visual_appearances_for_psyke_entry(db, project_id, entry.id):
                checks.append(VisualReviewCheck(
                    "character_visual_missing",
                    f"“{entry.name}” appears in panels but has no visual "
                    "identity (silhouette / color / shape).",
                    "warning", entry.id,
                ))
        else:  # place
            checks.append(VisualReviewCheck(
                "location_design_missing",
                f"Location “{entry.name}” has no visual design recorded.",
                "info", entry.id,
            ))

    # Motif appears only once — establish a recurrence or pay it off.
    for motif, panels in get_motif_recurrences(db, project_id).items():
        if len(panels) == 1:
            checks.append(VisualReviewCheck(
                "motif_single_use",
                f"Motif “{motif}” appears only once — it does not yet recur.",
                "info",
            ))

    # Object appears without a continuity state.
    for name, appearances in get_object_reappearances(db, project_id).items():
        if any(not (a.get("state") or "").strip() for a in appearances):
            checks.append(VisualReviewCheck(
                "object_missing_continuity_state",
                f"Object “{name}” appears without a continuity state noted.",
                "info",
            ))

    return checks
