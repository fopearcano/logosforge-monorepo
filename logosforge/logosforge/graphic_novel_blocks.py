"""Graphic Novel scene-body page/panel adapter (Phase 1).

The foundation for Graphic Novel mode *inside the universal Manuscript section*:
a Scene's body (flat ``Scene.content`` text) is parsed into a structured
Page/Panel script and serialized back — no schema change, no parallel storage, no
separate Manuscript section. This mirrors how ``screenplay_blocks`` adapts a
screenplay Scene body; the editor already styles the GN block grammar via
``writing_formats.GRAPHIC_NOVEL``.

A Graphic Novel Scene body is:

    PAGE 1: Optional title
    Summary: optional page summary

    PANEL 1
    Visual: what the panel shows
    Caption: narration / caption
    Dialogue: NAME: spoken line
    SFX: KRAKOOM
    Notes: artist / framing notes

    PANEL 2
    ...

Pure logic: parse / serialize / script operations / Markdown export / rule-based
validation / a small Assistant context block. No Qt, no LLM, no provider/API keys.
Outline summary (``Scene.summary``) is never read or written here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Canonical field labels (round-trippable). "Visual"/"Description" both parse to
# visual_description; "Notes"/"Art" both parse to notes.
_FIELD_ALIASES = {
    "visual": "visual_description", "description": "visual_description",
    "caption": "caption", "dialogue": "dialogue", "sfx": "sfx",
    "notes": "notes", "art": "notes",
}

# Validation thresholds (documented; conservative).
DIALOGUE_HEAVY_WORDS = 35     # one panel's dialogue this long reads as talky
SFX_LONG_CHARS = 30
CAPTION_LONG_WORDS = 40


@dataclass
class Panel:
    number: int = 0
    visual_description: str = ""
    caption: str = ""
    dialogue: str = ""
    sfx: str = ""
    notes: str = ""

    def is_empty(self) -> bool:
        return not any((self.visual_description.strip(), self.caption.strip(),
                        self.dialogue.strip(), self.sfx.strip(),
                        self.notes.strip()))

    def to_dict(self) -> dict[str, Any]:
        return {"number": self.number,
                "visual_description": self.visual_description,
                "caption": self.caption, "dialogue": self.dialogue,
                "sfx": self.sfx, "notes": self.notes}

    @classmethod
    def from_dict(cls, d: dict) -> "Panel":
        d = d or {}
        return cls(
            number=int(d.get("number", 0) or 0),
            visual_description=d.get("visual_description", "") or "",
            caption=d.get("caption", "") or "", dialogue=d.get("dialogue", "") or "",
            sfx=d.get("sfx", "") or "", notes=d.get("notes", "") or "")


@dataclass
class Page:
    number: int = 0
    title: str = ""
    summary: str = ""
    panels: list[Panel] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"number": self.number, "title": self.title,
                "summary": self.summary, "panels": [p.to_dict() for p in self.panels]}

    @classmethod
    def from_dict(cls, d: dict) -> "Page":
        d = d or {}
        return cls(number=int(d.get("number", 0) or 0),
                   title=d.get("title", "") or "", summary=d.get("summary", "") or "",
                   panels=[Panel.from_dict(p) for p in (d.get("panels") or [])])


@dataclass
class GraphicNovelScript:
    pages: list[Page] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(p.panels or p.summary.strip() or p.title.strip()
                       for p in self.pages)

    def panel_count(self) -> int:
        return sum(len(p.panels) for p in self.pages)

    def to_dict(self) -> dict[str, Any]:
        return {"pages": [p.to_dict() for p in self.pages]}

    @classmethod
    def from_dict(cls, d: dict) -> "GraphicNovelScript":
        return cls(pages=[Page.from_dict(p) for p in ((d or {}).get("pages") or [])])


# ===========================================================================
# Parse  (Scene body text -> structured script)
# ===========================================================================

_PAGE_RE = re.compile(r"^\s*PAGE\s+(\d+)\s*[:.\-]?\s*(.*)$", re.IGNORECASE)
_PANEL_RE = re.compile(r"^\s*PANEL\s+(\d+)\s*[:.\-]?\s*(.*)$", re.IGNORECASE)
_FIELD_RE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.*)$")
_SUMMARY_RE = re.compile(r"^\s*Summary\s*:\s*(.*)$", re.IGNORECASE)


def parse_graphic_novel_text(text: str) -> GraphicNovelScript:
    """Parse a GN Scene body into a Page/Panel script. Conservative and lossless:
    text before any PAGE/PANEL marker is preserved as Page 1 / Panel 1 visual, so
    legacy plain-text bodies are never dropped."""
    script = GraphicNovelScript()
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return script

    cur_page: Page | None = None
    cur_panel: Panel | None = None
    cur_field: str | None = None       # field currently accumulating wrapped text

    def new_page(num: int, title: str) -> None:
        nonlocal cur_page, cur_panel, cur_field
        cur_page = Page(number=num, title=title.strip())
        script.pages.append(cur_page)
        cur_panel = None
        cur_field = None

    def new_panel(num: int) -> None:
        nonlocal cur_panel, cur_field, cur_page
        if cur_page is None:
            new_page(1, "")
        cur_panel = Panel(number=num)
        cur_page.panels.append(cur_panel)
        cur_field = None

    for line in raw.split("\n"):
        pm = _PAGE_RE.match(line)
        if pm:
            new_page(int(pm.group(1)), pm.group(2))
            continue
        panel_m = _PANEL_RE.match(line)
        if panel_m:
            new_panel(int(panel_m.group(1)))
            continue
        sm = _SUMMARY_RE.match(line)
        if sm and cur_page is not None and cur_panel is None:
            cur_page.summary = (cur_page.summary + " " + sm.group(1)).strip()
            cur_field = "summary"
            continue

        fm = _FIELD_RE.match(line)
        if fm and fm.group(1).lower() in _FIELD_ALIASES:
            if cur_panel is None:
                new_panel(1)
            cur_field = _FIELD_ALIASES[fm.group(1).lower()]
            setattr(cur_panel, cur_field, fm.group(2).strip())
            continue

        stripped = line.strip()
        if not stripped:
            cur_field = None
            continue

        # Continuation / unlabeled text.
        if cur_field == "summary" and cur_page is not None:
            cur_page.summary = (cur_page.summary + " " + stripped).strip()
        elif cur_panel is not None and cur_field is not None:
            # Keep the writer's line breaks inside a field (script-first
            # editing): continuation lines join with a newline, not a space.
            prev = getattr(cur_panel, cur_field)
            setattr(cur_panel, cur_field, (prev + "\n" + stripped)
                    if prev else stripped)
        else:
            # Unlabeled body with no field context -> treat as visual (preserve).
            if cur_panel is None:
                new_panel(1)
            cur_panel.visual_description = (
                cur_panel.visual_description + "\n" + stripped) \
                if cur_panel.visual_description else stripped
            cur_field = "visual_description"

    return script


# ===========================================================================
# Serialize  (structured script -> Scene body text, round-trip safe)
# ===========================================================================


def _ambiguous_line(line: str) -> bool:
    """Would *line*, on its own, re-parse as structure or a field label?"""
    if _PAGE_RE.match(line) or _PANEL_RE.match(line) or _SUMMARY_RE.match(line):
        return True
    fm = _FIELD_RE.match(line)
    return bool(fm and fm.group(1).lower() in _FIELD_ALIASES)


def _field_lines(label: str, value: str) -> list[str]:
    """Serialize one field, keeping the writer's line breaks. Interior blank
    lines are dropped (a blank line ends a field on parse) and a continuation
    line that would re-parse as a PAGE/PANEL marker or field label is folded
    into the previous line (content preserved; structure cannot drift), so
    the result round-trips exactly."""
    lines = [ln.rstrip() for ln in value.split("\n") if ln.strip()]
    if not lines:
        return []
    out = [f"{label}: {lines[0]}"]
    for ln in lines[1:]:
        if _ambiguous_line(ln):
            out[-1] = f"{out[-1]} {ln}"
        else:
            out.append(ln)
    return out


def _panel_text(panel: Panel) -> list[str]:
    lines = [f"PANEL {panel.number}"]
    lines.extend(_field_lines("Visual", panel.visual_description))
    lines.extend(_field_lines("Caption", panel.caption))
    lines.extend(_field_lines("Dialogue", panel.dialogue))
    lines.extend(_field_lines("SFX", panel.sfx))
    lines.extend(_field_lines("Notes", panel.notes))
    return lines


# Display order + labels for the Manuscript's panel script blocks.
_PANEL_FIELD_ORDER = (
    ("visual_description", "Visual"),
    ("caption", "Caption"),
    ("dialogue", "Dialogue"),
    ("sfx", "SFX"),
    ("notes", "Notes"),
)


def panel_script_text(panel: Panel) -> str:
    """One panel's text for the Manuscript script block: labeled sections,
    line breaks preserved, empty fields omitted (the writer types labels)."""
    chunks = []
    for key, label in _PANEL_FIELD_ORDER:
        value = (getattr(panel, key, "") or "").strip()
        if value:
            chunks.append(f"{label}:\n{value}")
    return "\n\n".join(chunks)


def parse_panel_text(text: str) -> dict[str, str]:
    """Parse ONE panel script block back into the five fields.

    Same conservative rules as the scene parser: a known label line
    (``Visual:`` / ``Caption:`` / ``Dialogue:`` / ``SFX:`` / ``Notes:`` +
    aliases) switches the current field; anything else — including speaker
    lines like ``NAME: …``, unknown labels and PAGE/PANEL-looking lines — is
    plain content appended to the current field (leading unlabeled text goes
    to Visual). Nothing is ever dropped; a repeated label appends."""
    fields = {key: "" for key, _label in _PANEL_FIELD_ORDER}
    cur: str | None = None
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in raw.split("\n"):
        fm = _FIELD_RE.match(line)
        if fm and fm.group(1).lower() in _FIELD_ALIASES:
            cur = _FIELD_ALIASES[fm.group(1).lower()]
            inline = fm.group(2).strip()
            if inline:
                fields[cur] = (fields[cur] + "\n" + inline) \
                    if fields[cur] else inline
            continue
        stripped = line.strip()
        if not stripped:
            cur = None
            continue
        if cur is None:
            cur = "visual_description"
        fields[cur] = (fields[cur] + "\n" + stripped) \
            if fields[cur] else stripped
    return fields


def serialize_graphic_novel_script(script: GraphicNovelScript) -> str:
    out: list[str] = []
    for page in script.pages:
        head = f"PAGE {page.number}"
        if page.title.strip():
            head += f": {page.title.strip()}"
        out.append(head)
        if page.summary.strip():
            out.append(f"Summary: {page.summary.strip()}")
        for panel in page.panels:
            out.append("")
            out.extend(_panel_text(panel))
        out.append("")
    return "\n".join(out).strip() + ("\n" if out else "")


# ===========================================================================
# Script operations (pure; return the modified script)
# ===========================================================================


def _renumber(script: GraphicNovelScript) -> GraphicNovelScript:
    for pi, page in enumerate(script.pages, start=1):
        page.number = pi
        for ci, panel in enumerate(page.panels, start=1):
            panel.number = ci
    return script


def add_page(script: GraphicNovelScript, *, title: str = "") -> Page:
    page = Page(number=len(script.pages) + 1, title=title)
    script.pages.append(page)
    _renumber(script)
    return page


def add_panel(page: Page, **fields) -> Panel:
    panel = Panel(number=len(page.panels) + 1,
                  visual_description=fields.get("visual_description", ""),
                  caption=fields.get("caption", ""),
                  dialogue=fields.get("dialogue", ""),
                  sfx=fields.get("sfx", ""), notes=fields.get("notes", ""))
    page.panels.append(panel)
    return panel


def move_panel(page: Page, index: int, delta: int) -> None:
    """Swap a panel with its neighbour within the same page."""
    j = index + delta
    if 0 <= index < len(page.panels) and 0 <= j < len(page.panels):
        page.panels[index], page.panels[j] = page.panels[j], page.panels[index]
        for ci, panel in enumerate(page.panels, start=1):
            panel.number = ci


def move_panel_to_page(script: GraphicNovelScript, from_page_idx: int,
                       panel_idx: int, to_page_idx: int) -> bool:
    pages = script.pages
    if not (0 <= from_page_idx < len(pages) and 0 <= to_page_idx < len(pages)):
        return False
    src = pages[from_page_idx]
    if not (0 <= panel_idx < len(src.panels)):
        return False
    panel = src.panels.pop(panel_idx)
    pages[to_page_idx].panels.append(panel)
    for page in pages:
        for ci, p in enumerate(page.panels, start=1):
            p.number = ci
    return True


def delete_panel(page: Page, index: int) -> None:
    if 0 <= index < len(page.panels):
        page.panels.pop(index)
        for ci, panel in enumerate(page.panels, start=1):
            panel.number = ci


def delete_page(script: GraphicNovelScript, index: int) -> None:
    if 0 <= index < len(script.pages):
        script.pages.pop(index)
        _renumber(script)


# ===========================================================================
# Cursor <-> panel mapping (shared editor + Dexter panel targeting)
# ===========================================================================


def panel_at_offset(text: str, pos: int) -> tuple[int, int] | None:
    """(page_idx, panel_idx) of the panel containing character *pos* in a GN
    scene body — None before the first PANEL line. Lets the SHARED text
    editor (and the Voice Commit Router) resolve "the selected Panel" from
    the cursor position alone."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    pos = max(0, min(pos, len(raw)))
    page_idx, panel_idx = -1, -1
    offset = 0
    current: tuple[int, int] | None = None
    for line in raw.split("\n"):
        end = offset + len(line)
        if offset > pos:
            break
        if _PAGE_RE.match(line):
            page_idx += 1
            panel_idx = -1
        elif _PANEL_RE.match(line):
            if page_idx < 0:
                page_idx = 0
            panel_idx += 1
            current = None              # set below once pos check passes
        if pos >= offset and (panel_idx >= 0):
            current = (max(page_idx, 0), panel_idx)
        offset = end + 1
    return current


def panel_offset(text: str, page_idx: int, panel_idx: int) -> int | None:
    """Character offset of the line FOLLOWING the requested PANEL heading
    (i.e. where its script content starts) — None if it does not exist."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    pi, ci = -1, -1
    offset = 0
    for line in raw.split("\n"):
        if _PAGE_RE.match(line):
            pi += 1
            ci = -1
        elif _PANEL_RE.match(line):
            if pi < 0:
                pi = 0
            ci += 1
            if pi == page_idx and ci == panel_idx:
                return offset + len(line) + 1
        offset += len(line) + 1
    return None


# ===========================================================================
# Scene-body DB adapter (the Scene body IS the storage — no schema change)
# ===========================================================================


def load_scene_script(db, scene_id: int) -> GraphicNovelScript:
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return GraphicNovelScript()
    return parse_graphic_novel_text(getattr(scene, "content", "") or "")


def save_scene_script(db, scene_id: int, script: GraphicNovelScript) -> None:
    """Write the page/panel script to the Scene *body* only. Never touches the
    Outline summary, PSYKE, Timeline, or any other field."""
    db.update_scene_content(scene_id, serialize_graphic_novel_script(script))


# ===========================================================================
# Markdown export
# ===========================================================================


def scene_markdown(script: GraphicNovelScript, *, title: str = "") -> str:
    out: list[str] = [f"# {title or 'Untitled Scene'}", ""]
    if not script.pages:
        out.append("_(no pages)_")
        return "\n".join(out)
    for page in script.pages:
        head = f"## Page {page.number}"
        if page.title.strip():
            head += f" — {page.title.strip()}"
        out.append(head)
        if page.summary.strip():
            out.append("")
            out.append(f"_{page.summary.strip()}_")
        for panel in page.panels:
            out.append("")
            out.append(f"### Panel {panel.number}")
            out.append("")
            for label, value in (("Visual", panel.visual_description),
                                 ("Caption", panel.caption),
                                 ("Dialogue", panel.dialogue),
                                 ("SFX", panel.sfx), ("Notes", panel.notes)):
                if value.strip():
                    out.append(f"{label}: {value.strip()}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def export_scene_markdown(db, project_id: int, scene_id: int) -> str:
    scene = db.get_scene_by_id(scene_id)
    title = (getattr(scene, "title", "") or "Untitled Scene") if scene else "Scene"
    return scene_markdown(load_scene_script(db, scene_id), title=title)


def export_project_markdown(db, project_id: int) -> str:
    """Full project GN script in canonical Act->Chapter->Scene order. Body only —
    never Outline summaries, Timeline notes, or provider settings."""
    from logosforge import story_structure as ss
    project = db.get_project_by_id(project_id)
    out: list[str] = [f"# {getattr(project, 'title', 'Graphic Novel')}", ""]
    try:
        order = ss.canonical_scene_order(db, project_id)
    except Exception:
        order = [s.id for s in db.get_all_scenes(project_id)]
    for sid in order:
        out.append(export_scene_markdown(db, project_id, sid).rstrip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ===========================================================================
# Deterministic validation
# ===========================================================================


@dataclass
class GNValidation:
    warnings: list[str] = field(default_factory=list)
    is_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"warnings": list(self.warnings), "is_valid": self.is_valid}


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def validate_graphic_novel_script(script: GraphicNovelScript) -> GNValidation:
    """Rule-based GN script warnings (no LLM). Warnings are advisory; an empty
    script is the only thing flagged as not-valid-for-export."""
    report = GNValidation()
    if script.is_empty():
        report.warnings.append("Empty graphic novel script — add a page and panel.")
        report.is_valid = False
        return report

    consecutive_no_visual = 0
    for page in script.pages:
        if not page.panels:
            report.warnings.append(f"Page {page.number} has no panels.")
        for panel in page.panels:
            where = f"Page {page.number} · Panel {panel.number}"
            if panel.is_empty():
                report.warnings.append(f"{where}: empty panel.")
            if not panel.visual_description.strip():
                report.warnings.append(f"{where}: no visual description.")
                consecutive_no_visual += 1
            else:
                consecutive_no_visual = 0
            if consecutive_no_visual >= 3:
                report.warnings.append(
                    "Several consecutive panels have no visual action.")
                consecutive_no_visual = 0
            if _words(panel.dialogue) >= DIALOGUE_HEAVY_WORDS:
                report.warnings.append(f"{where}: dialogue-heavy panel.")
            if (panel.dialogue.strip() and ":" not in panel.dialogue):
                report.warnings.append(
                    f"{where}: dialogue without a character name (use 'NAME: line').")
            if len(panel.sfx.strip()) >= SFX_LONG_CHARS:
                report.warnings.append(f"{where}: SFX is long.")
            if _words(panel.caption) >= CAPTION_LONG_WORDS:
                report.warnings.append(f"{where}: caption is long.")

    report.warnings = list(dict.fromkeys(report.warnings))
    return report


# ===========================================================================
# Assistant / Logos context (minimal)
# ===========================================================================


def graphic_novel_context(db, project_id: int, scene_id: int | None) -> str:
    """A short, labelled ``[Graphic Novel Script]`` block for Assistant context.

    Empty for non-graphic-novel projects or scenes without page/panel content."""
    if scene_id is None:
        return ""
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id, GRAPHIC_NOVEL,
        )
        if get_project_writing_mode_by_id(db, project_id) != GRAPHIC_NOVEL:
            return ""
    except Exception:
        return ""
    script = load_scene_script(db, scene_id)
    if script.is_empty():
        return ""
    return (f"[Graphic Novel Script]\n{len(script.pages)} page(s), "
            f"{script.panel_count()} panel(s).")
