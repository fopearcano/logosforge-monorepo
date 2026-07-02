"""Experimental Final Draft (.fdx) screenplay export (Phase 10H).

Maps the standard screenplay elements to Final Draft XML paragraph types. This is
**experimental**: the output is well-formed standard FDX, but Final Draft
compatibility is NOT verified in CI, so it is gated behind an explicit
acknowledgement and clearly labelled. Fountain remains the recommended Final
Draft import path. Deterministic; no DB mutation, no LLM.

Unsupported (deferred): notes (omitted + warned), scene/page numbers, dual
dialogue, revisions, sections/synopses.
"""

from __future__ import annotations

import datetime as _dt
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

# Internal element -> FDX paragraph Type.
_FDX_TYPE = {
    "scene_heading": "Scene Heading",
    "action": "Action",
    "character": "Character",
    "dialogue": "Dialogue",
    "parenthetical": "Parenthetical",
    "transition": "Transition",
    "shot": "Shot",
}

EXPERIMENTAL_NOTICE = (
    "Experimental Final Draft FDX export — standard elements only; Final Draft "
    "compatibility is not verified. Use .fountain for reliable interchange."
)


@dataclass
class ScreenplayFdxExportResult:
    text: str = ""
    filename: str = "screenplay.fdx"
    ok: bool = False
    experimental: bool = True
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    exported_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "filename": self.filename, "ok": self.ok,
            "experimental": self.experimental, "warnings": list(self.warnings),
            "metadata": dict(self.metadata), "exported_at": self.exported_at,
        }


def export_screenplay_to_fdx(
    render_document, *, options: dict | None = None,
) -> ScreenplayFdxExportResult:
    """Export a screenplay render document to experimental FDX XML.

    Requires ``options['experimental_export_acknowledged'] is True`` to produce
    output; otherwise returns a gated result (no text) with a warning.
    """
    options = options or {}
    result = ScreenplayFdxExportResult(
        exported_at=_dt.datetime.now().isoformat(timespec="seconds"))
    result.warnings.append(EXPERIMENTAL_NOTICE)

    if not options.get("experimental_export_acknowledged"):
        result.warnings.append(
            "FDX export is gated: set experimental_export_acknowledged=True to enable.")
        return result

    root = ET.Element("FinalDraft", DocumentType="Script", Template="No", Version="1")
    content = ET.SubElement(root, "Content")

    notes_omitted = 0
    for b in render_document.blocks:
        et = b.element_type
        text = (b.export_text or b.text or "").strip()
        if not text:
            continue
        if et == "note":
            notes_omitted += 1
            continue
        fdx_type = _FDX_TYPE.get(et)
        if fdx_type is None:
            result.warnings.append(f"Unsupported element '{et}' exported as Action.")
            fdx_type = "Action"
        para = ET.SubElement(content, "Paragraph", Type=fdx_type)
        t = ET.SubElement(para, "Text")
        t.text = text

    # Title page (basic).
    tp = getattr(render_document, "title_page", {}) or {}
    title = (tp.get("title") or render_document.title or "").strip()
    if title:
        tp_el = ET.SubElement(root, "TitlePage")
        tp_content = ET.SubElement(tp_el, "Content")
        for key in ("title", "credit", "author", "source", "draft_date", "contact"):
            val = tp.get(key) or (title if key == "title" else "")
            if val:
                para = ET.SubElement(tp_content, "Paragraph", Type="Action")
                te = ET.SubElement(para, "Text")
                te.text = str(val)

    if notes_omitted:
        result.warnings.append(f"{notes_omitted} note(s) omitted (FDX notes deferred).")

    try:
        buf = io.BytesIO()
        ET.ElementTree(root).write(buf, encoding="utf-8", xml_declaration=True)
        result.text = buf.getvalue().decode("utf-8")
        result.ok = True
    except Exception as exc:
        result.warnings.append(f"FDX serialization failed: {exc}")
        return result

    project_title = title or "screenplay"
    safe = "".join(c for c in project_title if c.isalnum() or c in " -_").strip()
    result.filename = f"{safe or 'screenplay'}.fdx"
    result.metadata = {"experimental": True, "notes_omitted": notes_omitted}
    return result
