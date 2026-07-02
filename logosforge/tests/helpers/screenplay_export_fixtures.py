"""Reusable screenplay export-integrity fixtures + extractors (Phase 10I).

Builds a representative screenplay project covering every element type plus
tricky cases (ambiguous uppercase action, character extensions, multiline
dialogue, accented/special characters, notes), and provides normalized-text
extractors for each export format so tests can assert *no text loss* without
requiring exact cross-format formatting equality.
"""

from __future__ import annotations

import re

from logosforge.db import Database
from logosforge.screenplay_render import set_title_page


# Text tokens that MUST survive into every (text-bearing) export.
REQUIRED_TOKENS = (
    "INT. WAREHOUSE - NIGHT",      # scene heading
    "Rain hammers the tin roof.",  # action
    "THE LIGHTS DIE",              # ambiguous uppercase action (not a character)
    "MARÍA",                       # character cue with accent
    "We can still make the train.",   # dialogue (line 1)
    "If we run.",                  # dialogue (line 2, multiline)
    "She checks the café receipt — 3€.",  # special / accented chars
    "EXT. PLATFORM - CONTINUOUS",  # second scene heading
)

# Character extension that must be preserved on the cue.
CUE_EXTENSION = "(V.O.)"


def build_screenplay_fixture(db: Database | None = None):
    """Create a screenplay project exercising all element types.

    Returns (db, project_id). Title page is set.
    """
    db = db or Database()
    pid = db.create_project("The Last Train", narrative_engine="screenplay").id
    set_title_page(db, pid, {
        "title": "The Last Train", "author": "J. Tester",
        "credit": "Written by", "draft_date": "2026-05-31",
    })
    # Scene 1 — headings, action, ambiguous caps action, cue+ext, multiline
    # dialogue, parenthetical, note, special chars.
    db.create_scene(
        pid, "Warehouse",
        content=(
            "INT. WAREHOUSE - NIGHT\n\n"
            "Rain hammers the tin roof.\n\n"
            "THE LIGHTS DIE\n\n"
            "MARÍA (V.O.)\n"
            "(breathless)\n"
            "We can still make the train.\n"
            "If we run.\n\n"
            "She checks the café receipt — 3€.\n\n"
            "[[note: confirm the receipt prop]]"
        ),
        summary="x",
    )
    # Scene 2 — second heading + transition.
    db.create_scene(
        pid, "Platform",
        content=(
            "EXT. PLATFORM - CONTINUOUS\n\n"
            "The train doors hiss shut.\n\n"
            "CUT TO:"
        ),
        summary="x",
    )
    return db, pid


# -- Normalized-text extractors ----------------------------------------------


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def fountain_text(db, pid: str) -> str:
    from logosforge.export import export_screenplay_fountain
    return export_screenplay_fountain(db, pid)


def fountain_parsed_text(text: str) -> str:
    from logosforge.screenplay_fountain import parse_fountain_to_screenplay_blocks
    res = parse_fountain_to_screenplay_blocks(text)
    parts = [b.text for b in res.blocks]
    parts += [str(v) for v in res.title_page.values()]
    return " ".join(parts)


def docx_text(path: str) -> str:
    from docx import Document
    return "\n".join(p.text for p in Document(path).paragraphs)


def html_text(html: str) -> str:
    # Strip tags for token checks.
    return re.sub(r"<[^>]+>", " ", html)


def fdx_text(xml: str) -> str:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    return " ".join(t.text or "" for t in root.iter("Text"))


def assert_tokens_present(haystack: str, tokens=REQUIRED_TOKENS, *,
                          missing_ok=()) -> list[str]:
    """Return the list of required tokens missing from *haystack* (excluding
    explicitly allowed-missing ones)."""
    missing = [t for t in tokens if t not in haystack and t not in missing_ok]
    return missing
