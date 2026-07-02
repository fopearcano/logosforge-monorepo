"""Fountain — the canonical plain-text screenplay interchange format (Phase 10G).

Fountain is screenplay-specific markup (NOT generic Markdown). This module is the
dedicated serializer / parser / validator that maps the internal screenplay
:class:`~logosforge.screenplay_blocks.ScreenplayBlock` list to and from
``.fountain`` text.

Deterministic, no Qt, no LLM, no DB mutation, no ORM leakage. Conservative:
forcing syntax (``.`` ``@`` ``!`` ``>``) is used only when needed, ambiguous
lines degrade to action with a warning, and no text is lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay as sp
from logosforge import screenplay_blocks as sb

SCHEMA_VERSION = 1

# Fountain title-page keys (order preserved on export).
_TITLE_KEYS = [("title", "Title"), ("credit", "Credit"), ("author", "Author"),
               ("source", "Source"), ("draft_date", "Draft date"),
               ("contact", "Contact"), ("notes", "Notes")]
_TITLE_KEY_LOOKUP = {label.lower(): key for key, label in _TITLE_KEYS}


@dataclass
class FountainExportOptions:
    include_title_page: bool = True
    include_notes: bool = False
    include_sections: bool = False
    include_synopses: bool = False
    uppercase_scene_headings: bool = True
    uppercase_character_cues: bool = True
    force_ambiguous_elements: bool = True
    include_export_warnings_comment: bool = False
    filename_pattern: str = "{project_title}.fountain"


@dataclass
class FountainExportResult:
    text: str = ""
    filename: str = "screenplay.fountain"
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "filename": self.filename,
            "warnings": list(self.warnings), "metadata": dict(self.metadata),
            "schema_version": self.schema_version,
        }


@dataclass
class FountainParseResult:
    blocks: list[sb.ScreenplayBlock] = field(default_factory=list)
    title_page: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    ambiguous_lines: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocks": [b.to_dict() for b in self.blocks],
            "title_page": dict(self.title_page),
            "warnings": list(self.warnings),
            "ambiguous_lines": list(self.ambiguous_lines),
            "metadata": dict(self.metadata),
        }


@dataclass
class FountainValidationReport:
    is_valid: bool = True
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    unsupported_elements: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid, "blocking_errors": list(self.blocking_errors),
            "warnings": list(self.warnings), "suggestions": list(self.suggestions),
            "unsupported_elements": list(self.unsupported_elements),
            "summary": self.summary,
        }


def _filename(options: FountainExportOptions, project_title: str) -> str:
    safe = re.sub(r"[^\w\- ]+", "", project_title or "screenplay").strip() or "screenplay"
    try:
        name = options.filename_pattern.format(project_title=safe)
    except Exception:
        name = f"{safe}.fountain"
    return name if name.endswith(".fountain") else f"{name}.fountain"


def title_page_to_fountain(meta: dict) -> list[str]:
    lines: list[str] = []
    for key, label in _TITLE_KEYS:
        val = (meta or {}).get(key, "")
        if val:
            text = str(val)
            if "\n" in text:                       # multi-line indented value
                lines.append(f"{label}:")
                lines += [f"\t{ln}" for ln in text.splitlines()]
            else:
                lines.append(f"{label}: {text}")
    return lines


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


def _looks_like_character(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 35:
        return False
    core = re.sub(r"\(.*?\)", "", s).strip()
    return bool(core) and bool(re.search(r"[A-Za-z]", core)) and core == core.upper()


def serialize_screenplay_to_fountain(
    blocks: list[sb.ScreenplayBlock], *, title_page: dict | None = None,
    options: FountainExportOptions | None = None, project_title: str = "",
) -> FountainExportResult:
    """Serialize screenplay blocks to canonical ``.fountain`` text."""
    options = options or FountainExportOptions()
    result = FountainExportResult(filename=_filename(options, project_title))
    out: list[str] = []

    if options.include_title_page:
        tp = title_page_to_fountain(title_page or {})
        if tp:
            out.extend(tp)
            out.append("")  # blank line terminates title page
        else:
            result.warnings.append("No title page metadata — exported without one.")

    # Build "paragraphs": a dialogue group (character + parentheticals + dialogue)
    # is ONE paragraph (single newlines inside) so Fountain keeps it grouped;
    # paragraphs are blank-line separated.
    paras: list[str] = []
    cur_dialogue: list[str] | None = None  # open dialogue group lines
    notes_omitted = 0

    def flush() -> None:
        nonlocal cur_dialogue
        if cur_dialogue:
            paras.append("\n".join(cur_dialogue))
            cur_dialogue = None

    for b in blocks:
        et = b.element_type
        text = b.text.strip()
        if not text:
            continue
        if et == "character":
            flush()
            if options.uppercase_character_cues:
                cur_dialogue = [text.upper()]
            elif text != text.upper() and options.force_ambiguous_elements:
                cur_dialogue = ["@" + text]      # forced (preserve mixed case)
            else:
                cur_dialogue = [text]
            continue
        if et in ("parenthetical", "dialogue") and cur_dialogue is not None:
            if et == "parenthetical":
                cur_dialogue.append(text if text.startswith("(") else f"({text})")
            else:
                cur_dialogue.append(text)
            continue
        # Any non-dialogue element ends an open group.
        flush()
        if et == "scene_heading":
            up = text.upper() if options.uppercase_scene_headings else text
            paras.append(up if any(up.upper().startswith(p)
                                   for p in sp.SCENE_HEADING_PREFIXES) else "." + up)
        elif et == "transition":
            up = text.upper()
            paras.append(up if up.endswith("TO:") else f"> {up}")
        elif et == "parenthetical":          # orphan parenthetical (no cue)
            paras.append(text if text.startswith("(") else f"({text})")
            result.warnings.append("Parenthetical without a preceding character cue.")
        elif et == "dialogue":               # orphan dialogue (no cue)
            paras.append(text)
            result.warnings.append("Dialogue without a preceding character cue.")
        elif et == "note":
            if options.include_notes:
                paras.append(f"[[{text}]]")
            else:
                notes_omitted += 1
        elif et == "shot":
            paras.append(text.upper())
        else:  # action (and any unknown -> action)
            if options.force_ambiguous_elements and _looks_like_character(text):
                paras.append("!" + text)
                result.warnings.append(
                    f"Ambiguous uppercase action forced with '!': {text[:40]}")
            else:
                paras.append(text)
    flush()

    if notes_omitted:
        result.warnings.append(
            f"{notes_omitted} note block(s) omitted from export (include_notes=off).")
    if not paras:
        result.warnings.append("Empty screenplay — no body content exported.")

    out.extend("\n\n".join(paras).split("\n") if paras else [])
    if options.include_export_warnings_comment and result.warnings:
        out = ["/*", "Export warnings:"] + [f"- {w}" for w in result.warnings] + ["*/", ""] + out

    result.text = "\n".join(out).rstrip() + "\n"
    result.metadata = {"block_count": len(blocks), "notes_omitted": notes_omitted}
    return result


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_TRANSITION_LITERALS = {
    "FADE IN:", "FADE OUT.", "FADE OUT", "CUT TO:", "SMASH CUT TO:",
    "DISSOLVE TO:", "MATCH CUT TO:", "JUMP CUT TO:",
}


def _parse_title_page(lines: list[str]) -> tuple[dict, int]:
    """Parse a leading Fountain title page; return (meta, lines_consumed)."""
    meta: dict = {}
    if not lines:
        return meta, 0
    first = lines[0].split(":", 1)
    if len(first) != 2 or first[0].strip().lower() not in _TITLE_KEY_LOOKUP:
        return meta, 0  # no title page
    i = 0
    cur_key = None
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            break
        if ":" in line and not line.startswith((" ", "\t")):
            label, _, val = line.partition(":")
            key = _TITLE_KEY_LOOKUP.get(label.strip().lower())
            if key:
                cur_key = key
                meta[key] = val.strip()
            else:
                break
        elif cur_key and line.startswith((" ", "\t")):
            meta[cur_key] = (meta[cur_key] + "\n" + line.strip()).strip()
        else:
            break
        i += 1
    return meta, i


def parse_fountain_to_screenplay_blocks(
    text: str, *, options: FountainExportOptions | None = None,
) -> FountainParseResult:
    """Parse ``.fountain`` text into screenplay blocks (conservative, no loss)."""
    result = FountainParseResult()
    if not text or not text.strip():
        result.warnings.append("Empty Fountain input.")
        return result

    raw = text.replace("\r\n", "\n").replace("\r", "\n")
    # Boneyard /* ... */ — strip but record.
    boneyard = re.findall(r"/\*.*?\*/", raw, flags=re.DOTALL)
    if boneyard:
        raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
        result.warnings.append(f"{len(boneyard)} boneyard comment(s) removed on import.")
        result.metadata["boneyard"] = boneyard

    all_lines = raw.split("\n")
    title_page, consumed = _parse_title_page(all_lines)
    result.title_page = title_page
    body_text = "\n".join(all_lines[consumed:])

    order = 0

    def add(et: str, t: str) -> None:
        nonlocal order
        if t == "":
            return
        result.blocks.append(sb.ScreenplayBlock(element_type=et, text=t,
                                                order_index=order))
        order += 1

    chunks = re.split(r"\n[ \t]*\n", body_text)
    for chunk in chunks:
        lines = [ln for ln in chunk.split("\n")]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            continue
        first = lines[0].rstrip()
        fs = first.strip()

        # --- Single-line forced / structural ---
        if len(lines) == 1:
            if fs.startswith("===") or re.fullmatch(r"=+", fs):
                result.warnings.append("Page break (===) dropped on import.")
                continue
            if fs.startswith("##"):
                result.warnings.append("Section (##) preserved as note on import.")
                add("note", fs.lstrip("#").strip()); continue
            if fs.startswith("#"):
                result.warnings.append("Section (#) preserved as note on import.")
                add("note", fs.lstrip("#").strip()); continue
            if fs.startswith("="):
                result.warnings.append("Synopsis (=) preserved as note on import.")
                add("note", fs.lstrip("=").strip()); continue
            if fs.startswith("~"):
                result.warnings.append("Lyric (~) imported as action.")
                add("action", fs[1:].strip()); continue
            if fs.startswith("[[") and fs.endswith("]]"):
                add("note", fs[2:-2].strip()); continue
            if fs.startswith(">") and fs.endswith("<"):
                result.warnings.append("Centered text (>...<) imported as action.")
                add("action", fs[1:-1].strip()); continue
            if fs.startswith("."):                      # forced scene heading
                if not fs.startswith(".."):
                    add("scene_heading", fs[1:].strip()); continue
            if fs.startswith(">"):                       # forced transition
                add("transition", fs[1:].strip().upper()); continue
            if fs.startswith("!"):                       # forced action
                add("action", fs[1:]); continue
            if fs.startswith("@"):                        # forced character (alone)
                add("character", fs[1:].strip())
                result.warnings.append("Forced character cue (@) with no dialogue.")
                continue
            # Standard heuristics.
            up = fs.upper()
            if any(up.startswith(p) for p in sp.SCENE_HEADING_PREFIXES):
                add("scene_heading", fs); continue
            if up == fs and (fs in _TRANSITION_LITERALS or fs.endswith("TO:")
                             or fs.startswith("FADE ")):
                add("transition", fs); continue
            add("action", first); continue

        # --- Multi-line chunk ---
        # Forced or standard character cue leads a dialogue group.
        cue = None
        if fs.startswith("@"):
            cue = fs[1:].strip()
        elif _looks_like_character(fs) and not fs.startswith("."):
            cue = fs
        if cue is not None:
            add("character", cue)
            for ln in lines[1:]:
                s = ln.strip()
                if not s:
                    continue
                if s.startswith("(") and s.endswith(")"):
                    add("parenthetical", s)
                else:
                    add("dialogue", ln.rstrip())
            continue
        if fs.startswith(".") and not fs.startswith(".."):
            add("scene_heading", fs[1:].strip())
            rest = "\n".join(lines[1:]).strip()
            if rest:
                add("action", rest)
            continue
        up = fs.upper()
        if any(up.startswith(p) for p in sp.SCENE_HEADING_PREFIXES):
            add("scene_heading", fs)
            rest = "\n".join(lines[1:]).strip()
            if rest:
                add("action", rest)
            continue
        # Whole chunk is one action paragraph.
        add("action", "\n".join(ln.rstrip() for ln in lines))

    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_fountain_export(
    text: str, *, source_document=None,
) -> FountainValidationReport:
    """Validate generated Fountain text (deterministic, read-only)."""
    report = FountainValidationReport()
    if not text or not text.strip():
        report.blocking_errors.append("Empty Fountain output.")
        report.is_valid = False
        report.summary = "Invalid: empty Fountain output."
        return report

    parsed = parse_fountain_to_screenplay_blocks(text)
    blocks = parsed.blocks
    if not blocks:
        report.warnings.append("No screenplay body content detected.")

    if not any(b.element_type == "scene_heading" for b in blocks):
        report.warnings.append("No scene heading found.")
    if not (parsed.title_page.get("title") or "").strip():
        report.warnings.append("No title page / title.")

    prev = None
    orphan_dlg = orphan_paren = 0
    for b in blocks:
        if b.element_type == "dialogue" and prev not in (
                "character", "parenthetical", "dialogue"):
            orphan_dlg += 1
        if b.element_type == "parenthetical" and prev not in ("character", "dialogue"):
            orphan_paren += 1
        prev = b.element_type
    if orphan_dlg:
        report.warnings.append(f"{orphan_dlg} dialogue block(s) without a character cue.")
    if orphan_paren:
        report.warnings.append(f"{orphan_paren} parenthetical(s) without dialogue context.")

    report.warnings.extend(w for w in parsed.warnings if "import" in w.lower())
    report.is_valid = not report.blocking_errors
    report.summary = (
        ("Valid Fountain" if report.is_valid else "Invalid Fountain")
        + f": {len(report.blocking_errors)} error(s), {len(report.warnings)} warning(s)."
    )
    return report
