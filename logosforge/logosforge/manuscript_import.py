"""Import an already-written, **unformatted** manuscript into a NEW Pro project.

Unlike :mod:`logosforge.whiteboard_import` (which consumes structured Whiteboard
*blocks*), this takes the raw prose a writer already has — a ``.txt`` / ``.md``
file, or a Word ``.docx`` — and segments the flowing text into :class:`Scene`
rows on the markers that actually occur in real manuscripts:

- **chapter / part headings** — ``Chapter 12``, ``CHAPTER TWO``, ``Part One``,
  ``Prologue`` / ``Epilogue``, a lone number or Roman numeral on its own line, or
  a Markdown ``#`` heading (also what a ``.docx`` *Heading* paragraph becomes);
- **scene-break lines** — a line of only separator punctuation (``***``,
  ``* * *``, ``---``, ``# # #``, ``• • •`` …);
- **sluglines** — in screenplay / series mode, an ``INT.`` / ``EXT.`` line starts
  a new scene (and stays in the body).

Segmentation is controlled by ``strategy``:
  ``"smart"`` (default) split on any marker · ``"chapter"`` only headings ·
  ``"scene_break"`` only break lines / sluglines · ``"single"`` one big scene.

Pure logic: no Qt, no LLM, no network. ``.docx`` is read via ``python-docx``
(already a core dependency — the export path uses it).
"""

from __future__ import annotations

import io
import re
from typing import Any

from logosforge import writing_modes

# --- line classification --------------------------------------------------

# A Markdown ATX heading: up to 3 leading spaces, 1-6 '#', a space, then text.
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?P<t>.*\S)\s*$")
# "Chapter 12" / "CHAPTER TWO" / "Part One" / "Book II" / "Act III: The Fall" —
# the keyword MUST be followed by a number, Roman numeral or spelled-out ordinal,
# so a prose line that merely *starts* with "Part…" / "Act…" (e.g. "Part of her
# wanted to stay.") is NOT mistaken for a chapter heading.
_ORDINAL = (
    r"\d{1,4}|[ivxlcdm]{1,7}|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|first|second|third|fourth|fifth"
)
_CHAPTER = re.compile(rf"^\s*(chapter|part|book|act)\s+(?:{_ORDINAL})\b.*$", re.IGNORECASE)
# Front/back-matter headings that stand alone (no number needed). These words
# effectively never open a normal prose sentence.
_STANDALONE = re.compile(
    r"^\s*(prologue|epilogue|interlude|foreword|afterword|preface)\b.{0,40}$",
    re.IGNORECASE,
)
# A bare number / Roman numeral on its own line (a common chapter marker).
_NUMBER_ONLY = re.compile(r"^\s*(\d{1,4}|[IVXLCDM]{1,7})\s*$", re.IGNORECASE)
# A screenplay slug line (INT./EXT./EST./I/E) or a '.'-forced heading.
_SLUGLINE = re.compile(r"^\s*(INT|EXT|EST|INT\.?/EXT|I/E)[.\s]", re.IGNORECASE)
_FORCED_HEADING = re.compile(r"^\s*\.[^.\s]")
# A separator line: only break punctuation (>=3 chars), no letters/digits.
_BREAK_CHARS = set("*-_#=~•·—–.· \t")


def _clean_title(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().strip("#").strip()[:120]


def _is_scene_break_line(line: str) -> bool:
    s = line.strip()
    if len(s) < 3:
        return False
    if any(ch.isalnum() for ch in s):
        return False
    return all(ch in _BREAK_CHARS for ch in s)


def _heading_title(line: str) -> str | None:
    """Return the display title if *line* is a chapter/part heading, else None."""
    m = _MD_HEADING.match(line)
    if m:
        return _clean_title(m.group("t"))
    if _NUMBER_ONLY.match(line):
        return _clean_title(line)
    if _CHAPTER.match(line) or _STANDALONE.match(line):
        # Keep the whole heading ("Chapter 12 — The Return"), collapsed.
        return _clean_title(line)
    return None


# --- document reading -----------------------------------------------------

def _docx_to_text(data: bytes) -> str:
    """Extract text from .docx bytes, one line per paragraph. *Heading*-styled
    paragraphs become Markdown ``#`` lines so the segmenter treats them as
    chapter breaks."""
    try:
        from docx import Document  # python-docx
    except Exception as exc:  # pragma: no cover - dependency wiring
        raise RuntimeError("python-docx is required to import .docx files") from exc
    doc = Document(io.BytesIO(data))
    out: list[str] = []
    for para in doc.paragraphs:
        text = (para.text or "").rstrip()
        style = ""
        try:
            style = (para.style.name or "") if para.style else ""
        except Exception:
            style = ""
        if text and (style.startswith("Heading") or style == "Title"):
            out.append(f"# {text}")
        else:
            out.append(text)
    return "\n".join(out)


def read_document(filename: str, data: bytes) -> str:
    """Decode an uploaded manuscript to plain text. ``.docx`` is parsed with
    python-docx; everything else is treated as UTF-8 text (``.txt`` / ``.md``)."""
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return _docx_to_text(data)
    # .txt / .md / anything else: decode as text, tolerating a stray BOM / bytes.
    text = data.decode("utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


# --- segmentation ---------------------------------------------------------

_STRATEGIES = ("smart", "chapter", "scene_break", "single")


def _normalize_body(lines: list[str]) -> str:
    body = "\n".join(lines)
    body = re.sub(r"\n{3,}", "\n\n", body)  # collapse big gaps
    return body.strip()


def segment_manuscript(
    text: str, mode: str = "novel", strategy: str = "smart"
) -> list[dict[str, str]]:
    """Split raw manuscript *text* into ``[{title, content}]`` scenes.

    See the module docstring for the marker set and *strategy* semantics. Always
    returns at least one scene (possibly empty) so a project can be created.
    """
    mode = writing_modes.normalize_mode(mode or "novel")
    strategy = strategy if strategy in _STRATEGIES else "smart"
    screenplay = mode in ("screenplay", "series")

    split_headings = strategy in ("smart", "chapter")
    split_breaks = strategy in ("smart", "scene_break")

    scenes: list[dict[str, str]] = []
    cur_title: str | None = None
    cur_lines: list[str] = []
    started = False

    def flush() -> None:
        nonlocal cur_title, cur_lines, started
        if not started:
            return
        title = cur_title or f"Scene {len(scenes) + 1}"
        scenes.append({"title": title, "content": _normalize_body(cur_lines)})
        cur_title, cur_lines = None, []

    for raw in (text or "").split("\n"):
        line = raw.rstrip()
        heading = _heading_title(line) if split_headings else None
        slug = bool(split_breaks and screenplay and (_SLUGLINE.match(line) or _FORCED_HEADING.match(line)))
        brk = bool(split_breaks and not screenplay and _is_scene_break_line(line))

        if heading is not None:
            flush()
            started = True
            cur_title = heading
        elif slug:
            flush()
            started = True
            cur_title = _clean_title(line)
            cur_lines.append(line)  # the slug stays in the scene body
        elif brk:
            flush()
            started = True  # a new (as-yet-untitled) scene opens after the break
        else:
            started = True
            cur_lines.append(line)
    flush()

    if not scenes:
        scenes.append({"title": "Scene 1", "content": (text or "").strip()})
    return scenes


def import_manuscript_document(
    db,
    *,
    title: str,
    mode: str,
    strategy: str,
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    """Create a NEW project from a raw manuscript file and populate its scenes.

    Returns ``{project_id, title, mode, scenes_created, scene_titles}``.
    """
    mode = writing_modes.normalize_mode(mode or "novel")
    text = read_document(filename, data)
    proj_title = (title or "").strip() or "Imported Manuscript"
    try:
        default_fmt = writing_modes.default_writing_format(mode)
    except Exception:
        default_fmt = ""
    project = db.create_project(
        proj_title, format_mode=mode, narrative_engine=mode,
        default_writing_format=default_fmt,
    )
    scenes = segment_manuscript(text, mode, strategy)
    titles: list[str] = []
    for i, sc in enumerate(scenes, start=1):
        name = sc["title"] or f"Scene {i}"
        db.create_scene(project.id, title=name, content=sc["content"])
        titles.append(name)
    return {
        "project_id": project.id,
        "title": proj_title,
        "mode": mode,
        "scenes_created": len(titles),
        "scene_titles": titles,
    }
