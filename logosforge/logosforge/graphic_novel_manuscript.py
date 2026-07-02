"""Graphic Novel — one-way manuscript draft generation.

Pure, deterministic helpers that turn structured GraphicNovelPage /
GraphicNovelPanel data into a clean, editable manuscript *scaffold*.

This is the model -> manuscript direction ONLY. Nothing here parses prose
back into panels, mutates panel/page rows, or synchronizes. The caller
inserts the returned text into Scene.content as ordinary editable text.

Captions and SFX are intentionally NOT emitted: there is no panel column
backing them yet (they would require the deferred manuscript-binding /
schema work). Per "omit empty fields", absent data produces no section.

No UI / Tauri / filesystem imports.
"""

from __future__ import annotations

from typing import Any


def _csv_list(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def generate_page_draft(db: Any, page: Any) -> str:
    """Scaffold text for one page and its panels, in panel order.

    Empty fields are omitted; page/panel order is preserved.
    """
    lines: list[str] = [f"PAGE {page.page_number}"]
    if page.density_level:
        lines.append(f"Density: {page.density_level}")
    if page.reveal_type and page.reveal_type != "none":
        lines.append(f"Reveal: {page.reveal_type}")
    if page.splash_page:
        lines.append("Splash: yes")
    if (page.emotional_beat or "").strip():
        lines.append(f"Emotional beat: {page.emotional_beat.strip()}")
    if (page.summary or "").strip():
        lines.append(f"Summary: {page.summary.strip()}")
    lines.append("")

    panels = db.get_gn_panels_for_page(page.id)
    if not panels:
        lines.append("(no panels yet)")
        lines.append("")

    for panel in panels:
        lines.append(f"PANEL {panel.panel_number}")
        if panel.shot_type:
            lines.append(f"Shot: {panel.shot_type}")
        if panel.camera_angle:
            lines.append(f"Camera: {panel.camera_angle}")
        if panel.transition_type:
            lines.append(f"Transition: {panel.transition_type}")
        if panel.reading_priority:
            lines.append(f"Priority: {panel.reading_priority}")
        if (panel.emotional_tone or "").strip():
            lines.append(f"Tone: {panel.emotional_tone.strip()}")
        if (panel.description or "").strip():
            lines.append(f"Description: {panel.description.strip()}")
        if (panel.action or "").strip():
            lines.append(f"Action: {panel.action.strip()}")
        chars = _csv_list(panel.characters_present)
        if chars:
            lines.append("Characters: " + ", ".join(chars))
        dialogue = _csv_list(panel.dialogue_refs)
        if dialogue:
            lines.append("")
            lines.append("Dialogue:")
            lines.extend(f"  {d}" for d in dialogue)
        motifs = _csv_list(panel.visual_motifs)
        if motifs:
            lines.append("")
            lines.append("Motifs: " + ", ".join(motifs))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_draft(
    db: Any, project_id: int, *, scope: str = "all",
    page_id: int | None = None, issue_id: int | None = None,
) -> str:
    """Generate a manuscript scaffold for *scope*.

    scope:
      - "page"  : the single page *page_id*.
      - "all"   : every page in the project (page_number / sort_order order).
      - "issue" : every page assigned to *issue_id* (in page order).

    Returns "" when there is nothing to generate (unknown page, empty
    project, or an issue with no pages). The caller decides how to insert it.
    """
    if scope == "page":
        if page_id is None:
            return ""
        page = db.get_gn_page_by_id(page_id)
        if page is None or page.project_id != project_id:
            return ""
        pages = [page]
    elif scope == "issue":
        if issue_id is None:
            return ""
        pages = db.get_gn_pages_for_issue(issue_id)
    else:  # "all"
        pages = db.get_gn_pages(project_id)

    if not pages:
        return ""

    return "\n".join(generate_page_draft(db, p) for p in pages).rstrip() + "\n"
