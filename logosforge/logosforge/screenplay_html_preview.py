"""Screenplay HTML print preview (Phase 10H).

Readable, self-contained HTML from a ScreenplayRenderDocument (no remote assets,
no Qt, no LLM, no DB). Light/dark + print CSS. This is the recommended
"print to PDF" path where native PDF is approximate.
"""

from __future__ import annotations


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_screenplay_preview_html(render_document, *, dark: bool = False,
                                  print_css: bool = True) -> str:
    bg, fg, muted = ("#1e1e1e", "#eee", "#888") if dark else ("#fff", "#111", "#999")
    css = (
        f"body{{font-family:'Courier Prime','Courier New',Courier,monospace;"
        f"max-width:6in;margin:1in auto;color:{fg};background:{bg};"
        "font-size:12pt;line-height:1.25;}}"
        ".scene-heading{font-weight:bold;text-transform:uppercase;margin-top:1.5em;}"
        ".action{margin:0.5em 0;}"
        ".character{text-transform:uppercase;margin:0.5em 0 0 2.2in;}"
        ".dialogue{margin:0 1.5in 0 1in;}"
        ".parenthetical{font-style:italic;margin:0 2in 0 1.6in;}"
        ".transition{text-transform:uppercase;text-align:right;margin:0.5em 0;}"
        ".shot{text-transform:uppercase;margin:0.5em 0;}"
        f".note{{color:{muted};font-style:italic;}}"
        ".titlepage{text-align:center;margin-bottom:3em;}"
        f".approx{{color:{muted};font-size:9pt;}}"
        f".warnings{{color:{muted};font-size:9pt;border-top:1px solid {muted};"
        "margin-top:2em;padding-top:0.5em;}}"
    )
    if print_css:
        css += "@media print{.approx,.warnings{display:none;}body{margin:1in;}}"

    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
             f"<title>Screenplay Preview</title><style>{css}</style></head><body>"]
    tp = getattr(render_document, "title_page", {}) or {}
    parts.append("<div class='titlepage'>")
    parts.append(f"<h1>{_esc(render_document.title or tp.get('title','') or 'Untitled')}</h1>")
    for key in ("credit", "author", "source", "draft_date", "contact"):
        if tp.get(key):
            parts.append(f"<p>{_esc(str(tp[key]))}</p>")
    parts.append("</div>")
    if getattr(render_document, "estimated_pages", None) is not None:
        parts.append(f"<p class='approx'>~{render_document.estimated_pages} pages / "
                     f"~{render_document.estimated_minutes} min (approximate)</p>")
    for b in render_document.blocks:
        style = getattr(b, "style", "action") or "action"
        text = (getattr(b, "export_text", "") or b.text or "")
        parts.append(f"<div class='{style}'>{_esc(text)}</div>")
    if render_document.warnings:
        parts.append("<div class='warnings'>Warnings: "
                     + _esc("; ".join(render_document.warnings)) + "</div>")
    parts.append("</body></html>")
    return "".join(parts)
