"""Bridge: persist GN-script page/panel structure (parsed from each Scene's body
text) into the structured GraphicNovelPage / GraphicNovelPanel tables.

Real graphic-novel scripts are authored as flat ``Scene.content`` text and parsed
on the fly into an in-memory script; nothing persists them as rows, so the GN graph
enricher (which reads ``get_gn_pages``) sees an empty project and emits no edges.
This sync closes that gap deterministically: parse each GN scene -> create page +
panel rows, deriving ``visual_motifs`` from tokens that recur across the scene's
panels (so motif + symbol-echo edges form) and ``characters_present`` from ALLCAPS
dialogue cues. Qt-free; reuses the existing parser, no LLM.
"""

from __future__ import annotations

import re
from collections import defaultdict

from logosforge.graphic_novel_blocks import parse_graphic_novel_text

# Words too common to be a meaningful recurring visual motif.
_STOP = {
    "the", "and", "a", "an", "of", "to", "in", "on", "at", "is", "are", "was",
    "were", "with", "from", "into", "over", "under", "as", "by", "for", "his",
    "her", "its", "their", "they", "she", "he", "it", "we", "you", "this", "that",
    "there", "here", "then", "than", "but", "not", "all", "one", "two", "out",
    "up", "down", "off", "back", "face", "hand", "eyes", "looks", "looking",
    "stands", "sits", "walks", "panel", "page", "shot", "close", "wide", "frame",
}
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")
# An ALLCAPS speaker cue at the head of a Dialogue line, e.g. "MARA: ..." / "DR. ELI: ...".
_DLG_CUE_RE = re.compile(r"^\s*([A-Z][A-Z0-9 .'\-]{0,30}?)\s*(?:\([^)]*\))?\s*:")


def _recurring_motifs(panels) -> dict[int, list[str]]:
    """Map each panel (by object id) to the significant tokens it shares with at
    least one other panel in the same scene — its recurring visual motifs."""
    occ: dict[str, set[int]] = defaultdict(set)
    toks_by_panel: dict[int, set[str]] = {}
    for pn in panels:
        text = f"{pn.visual_description} {pn.caption}".lower()
        toks = {t for t in _TOKEN_RE.findall(text) if t not in _STOP}
        toks_by_panel[id(pn)] = toks
        for t in toks:
            occ[t].add(id(pn))
    recurring = {t for t, ids in occ.items() if len(ids) >= 2}
    return {pid: sorted(toks & recurring) for pid, toks in toks_by_panel.items()}


def _panel_characters(panel) -> list[str]:
    out: list[str] = []
    for line in (panel.dialogue or "").splitlines():
        m = _DLG_CUE_RE.match(line)
        if m:
            name = m.group(1).strip().rstrip(".").strip()
            if name and name not in out:
                out.append(name)
    return out


def sync_gn_pages_from_scenes(db, project_id: int, *, replace: bool = False) -> dict:
    """Parse every scene's GN-script body into structured page/panel rows.

    Returns ``{"pages", "panels", "skipped"}``. To stay idempotent it SKIPS when the
    project already has pages (unless ``replace`` and the db exposes ``delete_gn_page``),
    so re-running never duplicates the structure.
    """
    existing = db.get_gn_pages(project_id)
    if existing:
        if not (replace and hasattr(db, "delete_gn_page")):
            return {"pages": 0, "panels": 0, "skipped": True}
        for p in existing:
            db.delete_gn_page(p.id)

    pages_made = panels_made = 0
    for scene in db.get_all_scenes(project_id):
        script = parse_graphic_novel_text(scene.content or "")
        all_panels = [pn for pg in script.pages for pn in pg.panels]
        motif_by_panel = _recurring_motifs(all_panels)
        for pg in script.pages:
            page = db.create_gn_page(project_id, summary=(pg.title or pg.summary or "").strip())
            pages_made += 1
            for pn in pg.panels:
                db.create_gn_panel(
                    page.id, project_id=project_id,
                    description=(pn.visual_description or pn.caption or "").strip(),
                    characters_present=_panel_characters(pn),
                    visual_motifs=motif_by_panel.get(id(pn), []),
                )
                panels_made += 1
    return {"pages": pages_made, "panels": panels_made, "skipped": False}
