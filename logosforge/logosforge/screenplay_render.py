"""Screenplay render-preparation layer + title-page / export preferences (10F).

Builds a serializable render document from the parsed screenplay blocks — the
foundation for preview/PDF/FDX in a later phase — plus lightweight title-page
metadata and export preferences stored in existing project settings (no schema
change). Pure logic: no Qt, no LLM, no DB mutation (except the explicit
``set_title_page`` / ``set_export_prefs`` helpers, which write project settings).

Page/minute estimates are explicitly **approximate** (~1 screenplay page/minute,
~55 lines/page) — never presented as professional pagination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb
from logosforge import screenplay as sp

SCHEMA_VERSION = 1
LINES_PER_PAGE = 55

# -- Project-settings keys ----------------------------------------------------
_TITLE_PAGE_KEY = "screenplay_title_page"
_PREFS_KEY = "screenplay_export_prefs"

TITLE_PAGE_FIELDS = ("title", "credit", "author", "source", "draft_date",
                     "contact", "notes")

_DEFAULT_PREFS = {
    "show_notes_in_export": False,        # production export hides notes
    "uppercase_scene_headings": True,
    "uppercase_character_cues": True,
    "include_title_page": True,
    "include_diagnostics_report": False,
    "export_target": "fountain",          # fountain | plain_text | preview_html
    "approximate_page_estimate": True,
}
_VALID_TARGETS = ("fountain", "plain_text", "preview_html")


# ---------------------------------------------------------------------------
# Title page + preferences (project settings; no schema change)
# ---------------------------------------------------------------------------


def default_title_page(db=None, project_id: int | None = None) -> dict:
    meta = {k: "" for k in TITLE_PAGE_FIELDS}
    if db is not None and project_id is not None:
        try:
            project = db.get_project_by_id(project_id)
            if project and not meta["title"]:
                meta["title"] = project.title or ""
        except Exception:
            pass
    return meta


def get_title_page(db, project_id: int) -> dict:
    """Title-page metadata for a project (falls back to project title)."""
    meta = default_title_page(db, project_id)
    try:
        stored = db.get_project_settings(project_id).get(_TITLE_PAGE_KEY)
        if isinstance(stored, dict):
            for k in TITLE_PAGE_FIELDS:
                if stored.get(k):
                    meta[k] = str(stored[k])
    except Exception:
        pass
    return meta


def set_title_page(db, project_id: int, meta: dict) -> dict:
    """Persist title-page metadata (explicit user action)."""
    clean = {k: str(meta.get(k, "") or "") for k in TITLE_PAGE_FIELDS}
    settings = db.get_project_settings(project_id)
    settings[_TITLE_PAGE_KEY] = clean
    db.save_project_settings(project_id, settings)
    return clean


def get_export_prefs(db, project_id: int) -> dict:
    prefs = dict(_DEFAULT_PREFS)
    try:
        stored = db.get_project_settings(project_id).get(_PREFS_KEY)
        if isinstance(stored, dict):
            for k in _DEFAULT_PREFS:
                if k in stored:
                    prefs[k] = stored[k]
    except Exception:
        pass
    if prefs.get("export_target") not in _VALID_TARGETS:
        prefs["export_target"] = "fountain"
    return prefs


def set_export_prefs(db, project_id: int, prefs: dict) -> dict:
    merged = dict(_DEFAULT_PREFS)
    for k in _DEFAULT_PREFS:
        if k in prefs:
            merged[k] = prefs[k]
    if merged.get("export_target") not in _VALID_TARGETS:
        merged["export_target"] = "fountain"
    settings = db.get_project_settings(project_id)
    settings[_PREFS_KEY] = merged
    db.save_project_settings(project_id, settings)
    return merged


# ---------------------------------------------------------------------------
# Render document
# ---------------------------------------------------------------------------


@dataclass
class ScreenplayRenderBlock:
    element_type: str
    text: str
    scene_id: int | None = None
    block_index: int = 0
    page_hint: int | None = None
    style: str = ""
    export_text: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_type": self.element_type, "text": self.text,
            "scene_id": self.scene_id, "block_index": self.block_index,
            "page_hint": self.page_hint, "style": self.style,
            "export_text": self.export_text, "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass
class ScreenplayRenderDocument:
    project_id: int
    title: str = ""
    writing_mode: str = "screenplay"
    title_page: dict = field(default_factory=dict)
    blocks: list[ScreenplayRenderBlock] = field(default_factory=list)
    estimated_pages: float | None = None
    estimated_minutes: float | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id, "title": self.title,
            "writing_mode": self.writing_mode, "title_page": dict(self.title_page),
            "blocks": [b.to_dict() for b in self.blocks],
            "estimated_pages": self.estimated_pages,
            "estimated_minutes": self.estimated_minutes,
            "warnings": list(self.warnings), "metadata": dict(self.metadata),
        }


# Element -> coarse style hint (presentation-agnostic; consumers map to CSS).
_STYLE = {
    "scene_heading": "scene-heading", "action": "action", "character": "character",
    "parenthetical": "parenthetical", "dialogue": "dialogue",
    "transition": "transition", "shot": "shot", "note": "note",
}


def _export_text(element_type: str, text: str, prefs: dict) -> str:
    t = text
    if element_type in ("scene_heading", "transition") and prefs.get(
            "uppercase_scene_headings", True):
        t = t.upper()
    if element_type == "character" and prefs.get("uppercase_character_cues", True):
        t = t.upper()
    if element_type == "parenthetical":
        s = t.strip()
        if not (s.startswith("(") and s.endswith(")")):
            t = f"({s})"
    return t


def build_render_document(db, project_id: int, *, prefs: dict | None = None
                          ) -> ScreenplayRenderDocument:
    """Build a serializable render document from the project's screenplay blocks.

    Read-only; no LLM. Honors export preferences (note inclusion, casing). Pages/
    minutes are approximate and only filled when the pref allows.
    """
    prefs = prefs if prefs is not None else get_export_prefs(db, project_id)
    title_page = get_title_page(db, project_id)
    doc = ScreenplayRenderDocument(
        project_id=project_id, title=title_page.get("title", ""),
        title_page=title_page,
    )
    show_notes = bool(prefs.get("show_notes_in_export", False))

    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        scenes = []
    if not scenes:
        doc.warnings.append("Empty screenplay — no scenes to render.")
        return doc

    line_count = 0
    for scene in scenes:
        blocks = sb.parse_screenplay_text(getattr(scene, "content", "") or "",
                                          scene_id=scene.id)
        # Phase 10I — inject a scene heading from the slug/title when the scene
        # content doesn't already open with one, so render-model exports
        # (DOCX/PDF/preview/FDX) stay consistent with the Fountain path and never
        # drop scene headings.
        if not (blocks and blocks[0].element_type == "scene_heading"):
            heading = (getattr(scene, "slugline", "") or getattr(scene, "title", "")
                       or "").strip()
            if heading:
                doc.blocks.append(ScreenplayRenderBlock(
                    element_type="scene_heading", text=heading, scene_id=scene.id,
                    block_index=-1, style=_STYLE["scene_heading"],
                    export_text=_export_text("scene_heading", heading, prefs)))
        for b in blocks:
            if b.element_type == "note" and not show_notes:
                continue
            warns: list[str] = []
            if b.element_type not in sp.ELEMENT_KEYS:
                warns.append(f"Unsupported block element '{b.element_type}'.")
            rb = ScreenplayRenderBlock(
                element_type=b.element_type, text=b.text, scene_id=scene.id,
                block_index=b.order_index, style=_STYLE.get(b.element_type, "action"),
                export_text=_export_text(b.element_type, b.text, prefs),
                warnings=warns,
            )
            doc.blocks.append(rb)
            line_count += max(1, b.text.count("\n") + 1)

    if prefs.get("approximate_page_estimate", True) and line_count:
        doc.estimated_pages = round(line_count / LINES_PER_PAGE, 2)
        doc.estimated_minutes = doc.estimated_pages  # ~1 page / minute (approx)
    if not doc.title.strip():
        doc.warnings.append("No title set — add a title page before exporting.")
    return doc


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_to_plain_text(doc: ScreenplayRenderDocument) -> str:
    lines: list[str] = []
    if doc.title:
        lines += [doc.title.upper(), ""]
    for b in doc.blocks:
        lines.append(b.export_text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_to_html(doc: ScreenplayRenderDocument) -> str:
    """Conservative screenplay preview HTML (not page-accurate)."""
    css = (
        "body{font-family:'Courier New',monospace;max-width:6in;margin:1in auto;"
        "color:#111;background:#fff;font-size:12pt;line-height:1.25;}"
        ".scene-heading{font-weight:bold;text-transform:uppercase;margin-top:1.5em;}"
        ".action{margin:0.5em 0;}"
        ".character{text-transform:uppercase;margin:0.5em 0 0 2.2in;}"
        ".dialogue{margin:0 1.5in 0 1in;}"
        ".parenthetical{font-style:italic;margin:0 2in 0 1.5in;}"
        ".transition{text-transform:uppercase;text-align:right;margin:0.5em 0;}"
        ".shot{text-transform:uppercase;margin:0.5em 0;}"
        ".note{color:#999;font-style:italic;}"
        ".titlepage{text-align:center;margin-bottom:3em;}"
        ".approx{color:#999;font-size:9pt;}"
    )
    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
             f"<style>{css}</style></head><body>"]
    tp = doc.title_page or {}
    parts.append("<div class='titlepage'>")
    parts.append(f"<h1>{_esc(doc.title or tp.get('title', '') or 'Untitled')}</h1>")
    for label in ("credit", "author", "source", "draft_date", "contact"):
        if tp.get(label):
            parts.append(f"<p>{_esc(str(tp[label]))}</p>")
    parts.append("</div>")
    if doc.estimated_pages is not None:
        parts.append(f"<p class='approx'>~{doc.estimated_pages} pages / "
                     f"~{doc.estimated_minutes} min (approximate)</p>")
    for b in doc.blocks:
        parts.append(f"<div class='{b.style}'>{_esc(b.export_text)}</div>")
    parts.append("</body></html>")
    return "".join(parts)


def title_page_to_fountain(meta: dict) -> list[str]:
    """Fountain title-page key/value lines (omitting empty fields)."""
    lines: list[str] = []
    mapping = [("title", "Title"), ("credit", "Credit"), ("author", "Author"),
               ("source", "Source"), ("draft_date", "Draft date"),
               ("contact", "Contact"), ("notes", "Notes")]
    for key, label in mapping:
        val = (meta or {}).get(key, "")
        if val:
            lines.append(f"{label}: {val}")
    return lines
