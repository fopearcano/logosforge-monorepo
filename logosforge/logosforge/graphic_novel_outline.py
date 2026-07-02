"""Graphic Novel Outline data layer — scene-scoped Page/Panel editing helpers.

The editing primitives behind the Graphic Novel Outline (the standalone Pages
section stays disabled for fullscreen safety). Everything reads/writes the
**shared** per-scene GN body (`Scene.content` via :mod:`graphic_novel_blocks`):
helpers here load the scene script, mutate it, and save it back (single source
of truth) — no separate Pages storage, no body-format change, no migration.
Pure data logic: no Qt. No image / prompt / ComfyUI fields.

The canonical **visible** hierarchy — ``Act → Page → Scene → Panel``, where an
Act owns act-wide Pages, a Scene can span several Pages and one Page can hold
Panels from several Scenes — is computed by :mod:`graphic_novel_structure`
(act-wide page coordinates over these same scene-local bodies). Chapters
remain hidden storage labels for cross-mode compatibility; the legacy
chapter-grouped read views below (:func:`scene_view`, :func:`chapter_page_view`)
are retained as data-layer compatibility helpers.

Storage note (Alpha): pages are physically **scene-scoped** (each scene owns
its Pages/Panels in its own body); the act-wide page numbers are a computed
coordinate (`Scene.gn_page_start` + canonical order), which is the anchor
point for later visual-production integrations.
"""

from __future__ import annotations

from logosforge import graphic_novel_blocks as gnb
from logosforge import story_structure as ss


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def is_graphic_novel(db, project_id: int) -> bool:
    try:
        from logosforge.writing_modes import (
            GRAPHIC_NOVEL, get_project_writing_mode_by_id)
        return get_project_writing_mode_by_id(db, project_id) == GRAPHIC_NOVEL
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Read views (no mutation)
# ---------------------------------------------------------------------------


def scene_view(db, project_id: int):
    """``[(act, [(chapter, [(scene, script), ...]), ...]), ...]`` in canonical
    order — the editable Scene View (Act -> Chapter -> Scene -> Page -> Panel)."""
    try:
        tree = ss.build_structure_tree(db, project_id)
    except Exception:
        return []
    out = []
    for act, chapters in tree:
        ch_out = []
        for chapter, scenes in chapters:
            sc_out = [(s, gnb.load_scene_script(db, s.id)) for s in scenes]
            ch_out.append((chapter, sc_out))
        out.append((act, ch_out))
    return out


def chapter_page_view(db, scenes):
    """Group panels across *scenes* by page number (the chapter-level Page View).

    Returns an ordered ``[(page_number, [(scene, page_idx, panel_idx, panel), ...]),
    ...]`` so a chapter page lists panels from every scene assigned to that page —
    this is how a page "spans" multiple scenes.
    """
    pages: dict[int, list] = {}
    for s in scenes:
        script = gnb.load_scene_script(db, s.id)
        for pi, page in enumerate(script.pages):
            for ci, panel in enumerate(page.panels):
                pages.setdefault(page.number, []).append((s, pi, ci, panel))
    return [(num, pages[num]) for num in sorted(pages)]


def scenes_in_chapter(db, project_id: int, act: str, chapter: str) -> list:
    """The scenes (rows) under one (act, chapter), in canonical order."""
    for a, chapters in scene_view(db, project_id):
        if a != act:
            continue
        for c, sc_out in chapters:
            if c == chapter:
                return [s for s, _script in sc_out]
    return []


def panel_snippet(panel: gnb.Panel) -> str:
    vis = (panel.visual_description or "").strip().replace("\n", " ")
    snippet = (vis[:40] + "…") if len(vis) > 40 else (vis or "(empty)")
    flags = []
    if (panel.dialogue or "").strip():
        flags.append("💬")
    if (panel.caption or "").strip():
        flags.append("▤")
    if (panel.sfx or "").strip():
        flags.append("✺")
    tag = ("  " + " ".join(flags)) if flags else ""
    return f"{snippet}{tag}"


# ---------------------------------------------------------------------------
# Editing helpers (load -> mutate -> save the shared Scene.content body)
# ---------------------------------------------------------------------------


def add_page(db, scene_id: int, *, title: str = "") -> int:
    """Add a page to a scene. Returns the new page index."""
    script = gnb.load_scene_script(db, scene_id)
    gnb.add_page(script, title=title)
    gnb.save_scene_script(db, scene_id, script)
    return len(script.pages) - 1


def add_panel(db, scene_id: int, page_idx: int | None = None, **fields) -> bool:
    """Add a panel to a scene's page (seeds a page if none). Defaults to the last
    page when *page_idx* is None."""
    script = gnb.load_scene_script(db, scene_id)
    if not script.pages:
        gnb.add_page(script)
        page_idx = 0
    if page_idx is None:
        page_idx = len(script.pages) - 1
    if not (0 <= page_idx < len(script.pages)):
        return False
    gnb.add_panel(script.pages[page_idx], **fields)
    gnb._renumber(script)
    gnb.save_scene_script(db, scene_id, script)
    return True


def set_panel_field(db, scene_id: int, page_idx: int, panel_idx: int,
                    field: str, value: str) -> bool:
    script = gnb.load_scene_script(db, scene_id)
    try:
        panel = script.pages[page_idx].panels[panel_idx]
    except (IndexError, TypeError):
        return False
    if getattr(panel, field, None) == value:
        return False
    setattr(panel, field, value)
    gnb.save_scene_script(db, scene_id, script)
    return True


def set_page_field(db, scene_id: int, page_idx: int, field: str,
                   value: str) -> bool:
    script = gnb.load_scene_script(db, scene_id)
    try:
        page = script.pages[page_idx]
    except (IndexError, TypeError):
        return False
    if getattr(page, field, None) == value:
        return False
    setattr(page, field, value)
    gnb.save_scene_script(db, scene_id, script)
    return True


def move_panel(db, scene_id: int, page_idx: int, panel_idx: int,
               delta: int) -> bool:
    script = gnb.load_scene_script(db, scene_id)
    try:
        page = script.pages[page_idx]
    except (IndexError, TypeError):
        return False
    j = panel_idx + delta
    if not (0 <= panel_idx < len(page.panels) and 0 <= j < len(page.panels)):
        return False
    gnb.move_panel(page, panel_idx, delta)
    gnb.save_scene_script(db, scene_id, script)
    return True


def move_panel_to_page(db, scene_id: int, from_page_idx: int, panel_idx: int,
                       to_page_idx: int) -> bool:
    script = gnb.load_scene_script(db, scene_id)
    ok = gnb.move_panel_to_page(script, from_page_idx, panel_idx, to_page_idx)
    if ok:
        gnb.save_scene_script(db, scene_id, script)
    return ok


def delete_panel(db, scene_id: int, page_idx: int, panel_idx: int) -> bool:
    script = gnb.load_scene_script(db, scene_id)
    try:
        page = script.pages[page_idx]
    except (IndexError, TypeError):
        return False
    if not (0 <= panel_idx < len(page.panels)):
        return False
    gnb.delete_panel(page, panel_idx)
    gnb.save_scene_script(db, scene_id, script)
    return True


def delete_page(db, scene_id: int, page_idx: int) -> bool:
    script = gnb.load_scene_script(db, scene_id)
    if not (0 <= page_idx < len(script.pages)):
        return False
    gnb.delete_page(script, page_idx)
    gnb.save_scene_script(db, scene_id, script)
    return True


# ---------------------------------------------------------------------------
# Export (canonical Act → Page → Scene → Panel)
# ---------------------------------------------------------------------------


def export_outline_markdown(db, project_id: int) -> str:
    """Canonical **Act → Page → Scene → Panel** structural export (delegates
    to :func:`graphic_novel_structure.export_structure_markdown`): physical
    page order, explicit Panel → Scene and Panel → Page assignments,
    ``continued`` markers, each panel's text exactly once. Reads only the
    shared body — never settings / API keys / image data."""
    from logosforge import graphic_novel_structure as gns
    return gns.export_structure_markdown(db, project_id)
