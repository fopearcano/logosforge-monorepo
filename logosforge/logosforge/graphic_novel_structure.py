"""Graphic Novel canonical structure — Act → Page → Scene → Panel.

Pre-finalization refactor: the Graphic Novel Outline's visible hierarchy is
**Project → Act → Page → Scene → Panel** and the Manuscript derives from it.
This module is the single adapter that turns the existing storage into that
shape — *without* a storage migration:

* Scene bodies keep the scene-local ``PAGE n`` / ``PANEL n`` script
  (:mod:`graphic_novel_blocks`); ``_renumber`` and the script grammar are
  untouched.
* Each scene gains ONE act-wide coordinate: ``Scene.gn_page_start`` — the
  act-wide page number its local PAGE 1 maps to. ``NULL`` auto-chains the
  scene onto the page after the previous scene ends (first scene → Page 1),
  which exactly reproduces the legacy layout. A pinned value may point into
  an earlier scene's span, which is how **a Page contains Panels from more
  than one Scene** (e.g. Scene A spans Pages 1–2; Scene B pinned to start on
  Page 2 shares Page 2). A scene with several local pages **spans multiple
  act Pages** (its panels are distributed across them).
* Acts own Pages and Scenes; a Panel belongs to exactly one Scene and is
  placed on exactly one Page (its scene-local page → one act-wide page).
* Chapters remain hidden storage labels only (`Scene.chapter` is kept for
  cross-mode compatibility and never shown in Graphic Novel UI).

Pure data logic: no Qt, no LLM, no image/prompt/ComfyUI fields. The legacy
standalone Pages tables/views stay untouched and unmounted.
"""

from __future__ import annotations

from dataclasses import dataclass

from logosforge import graphic_novel_blocks as gnb
from logosforge import story_structure as ss


# ---------------------------------------------------------------------------
# Placement model
# ---------------------------------------------------------------------------


@dataclass
class ScenePlacement:
    """One scene's act-wide page placement (scene + parsed body + offset)."""

    scene: object
    script: gnb.GraphicNovelScript
    start_page: int            # act-wide page number of the scene's local PAGE 1
    explicit: bool             # True when Scene.gn_page_start pinned it

    @property
    def page_count(self) -> int:
        return len(self.script.pages)

    @property
    def end_page(self) -> int:
        """Act-wide number of the scene's last page (start−1 when empty)."""
        return self.start_page + self.page_count - 1

    def global_page(self, local_idx: int) -> int:
        """Act-wide page number for a 0-based scene-local page index."""
        return self.start_page + local_idx


@dataclass
class PageSlice:
    """One scene's contribution to one act-wide Page (one local page)."""

    placement: ScenePlacement
    local_idx: int             # 0-based index into placement.script.pages
    continued: bool            # not the scene's first page → "Scene … continued"

    @property
    def page(self) -> gnb.Page:
        return self.placement.script.pages[self.local_idx]


# ---------------------------------------------------------------------------
# Canonical views (read-only)
# ---------------------------------------------------------------------------


def acts_with_scenes(db, project_id: int) -> list[tuple[str, list]]:
    """Acts in canonical order, each with its scenes in canonical order.

    The hidden chapter grouping is flattened away (order preserved) — in
    Graphic Novel mode an Act owns its Scenes directly."""
    out = []
    for act, chapters in ss.build_structure_tree(db, project_id):
        scenes = [s for _ch, scs in chapters for s in scs]
        out.append((act, scenes))
    return out


def _pinned_start(scene) -> int | None:
    raw = getattr(scene, "gn_page_start", None)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None


def act_placements(db, project_id: int) -> list[tuple[str, list[ScenePlacement]]]:
    """Per act, each scene's act-wide placement in canonical order.

    Auto-chain rule: a scene with no pinned ``gn_page_start`` begins on the
    page after the act's highest used page so far (the act's first scene on
    Page 1). A pinned start may point into an earlier scene's span — that is
    how two scenes share one physical page. Empty scenes occupy no pages and
    never advance the chain."""
    out = []
    for act, scenes in acts_with_scenes(db, project_id):
        placements: list[ScenePlacement] = []
        high = 0
        for s in scenes:
            script = gnb.load_scene_script(db, s.id)
            pinned = _pinned_start(s)
            start = pinned if pinned is not None else high + 1
            placement = ScenePlacement(scene=s, script=script,
                                       start_page=start,
                                       explicit=pinned is not None)
            placements.append(placement)
            high = max(high, placement.end_page)
        out.append((act, placements))
    return out


def act_view(db, project_id: int):
    """The canonical **Act → Page → Scene → Panel** view.

    ``[(act, pages, placements), ...]`` where ``pages`` is
    ``[(page_no, [PageSlice, ...]), ...]`` in ascending physical page order
    (slices keep canonical scene order within a shared page) and
    ``placements`` is the act's full scene list — scenes without pages
    appear only there, so nothing is ever hidden."""
    out = []
    for act, placements in act_placements(db, project_id):
        by_page: dict[int, list[PageSlice]] = {}
        for placement in placements:
            for li in range(placement.page_count):
                by_page.setdefault(placement.global_page(li), []).append(
                    PageSlice(placement=placement, local_idx=li,
                              continued=li > 0))
        pages = [(num, by_page[num]) for num in sorted(by_page)]
        out.append((act, pages, placements))
    return out


def find_placement(db, project_id: int, scene_id: int
                   ) -> tuple[str, ScenePlacement] | tuple[None, None]:
    """(act, placement) for one scene — or ``(None, None)`` if not found."""
    for act, placements in act_placements(db, project_id):
        for placement in placements:
            if placement.scene.id == scene_id:
                return act, placement
    return None, None


def scene_page_range_label(placement: ScenePlacement) -> str:
    """Human label for a scene's act-wide span: ``Page 2`` / ``Pages 2–4`` /
    ``no pages yet``."""
    if placement.page_count == 0:
        return "no pages yet"
    if placement.page_count == 1:
        return f"Page {placement.start_page}"
    return f"Pages {placement.start_page}–{placement.end_page}"


# ---------------------------------------------------------------------------
# Mutation (the ONE new write: pin / release a scene's start page)
# ---------------------------------------------------------------------------


def set_scene_start_page(db, scene_id: int, start: int | None) -> bool:
    """Pin a scene's act-wide start page, or release it back to auto-chain
    with ``None``. Values below 1 are refused. Touches only the offset —
    never the body, so the scene's pages/panels are untouched."""
    if start is not None:
        try:
            start = int(start)
        except (TypeError, ValueError):
            return False
        if start < 1:
            return False
    db.set_scene_gn_page_start(scene_id, start)
    return True


# ---------------------------------------------------------------------------
# Export — Act → Page → Scene → Panel with explicit assignments
# ---------------------------------------------------------------------------


def _panel_fields_markdown(panel: gnb.Panel, indent: str) -> list[str]:
    lines = []
    for label, value in (("Visual", panel.visual_description),
                         ("Caption", panel.caption),
                         ("Dialogue", panel.dialogue),
                         ("SFX", panel.sfx), ("Notes", panel.notes)):
        if (value or "").strip():
            flat = " / ".join(ln.strip() for ln in value.strip().split("\n")
                              if ln.strip())
            lines.append(f"{indent}{label}: {flat}")
    return lines


def export_structure_markdown(db, project_id: int) -> str:
    """Markdown of the canonical **Act → Page → Scene → Panel** structure in
    physical page order, with explicit Panel → Scene and Panel → Page
    assignments and ``continued`` markers for scenes spanning pages.

    Each panel's text appears exactly **once** (no duplicate views). Reads
    only the shared scene bodies — never image data, provider settings or
    API keys."""
    project = db.get_project_by_id(project_id)
    title = (getattr(project, "title", "") or "Graphic Novel").strip() \
        or "Graphic Novel"
    lines: list[str] = [f"# {title}", ""]
    view = act_view(db, project_id)
    if not view:
        lines.append("_No structure yet._")
        return "\n".join(lines) + "\n"
    for act, pages, placements in view:
        lines.append(f"## {act}")
        lines.append("")
        if not pages:
            lines.append("_No pages yet._")
            lines.append("")
        for page_no, slices in pages:
            lines.append(f"### Page {page_no}")
            lines.append("")
            for sl in slices:
                scene = sl.placement.scene
                s_title = (getattr(scene, "title", "") or "Untitled").strip() \
                    or "Untitled"
                marker = " — continued" if sl.continued else ""
                head = f"**Scene: {s_title}{marker}**"
                if (sl.page.title or "").strip():
                    head += f" · {sl.page.title.strip()}"
                lines.append(head)
                if (sl.page.summary or "").strip():
                    lines.append(f"_{sl.page.summary.strip()}_")
                for panel in sl.page.panels:
                    lines.append(f"- Panel {panel.number} "
                                 f"(Scene: {s_title} → Page {page_no})")
                    lines.extend(_panel_fields_markdown(panel, "  - "))
                lines.append("")
        empties = [p for p in placements if p.page_count == 0]
        if empties:
            lines.append("_Scenes without pages:_")
            for placement in empties:
                s_title = (getattr(placement.scene, "title", "")
                           or "Untitled").strip() or "Untitled"
                lines.append(f"- {s_title}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
