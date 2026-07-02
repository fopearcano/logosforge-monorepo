"""Graphic Novel review checks — data-driven visual-storytelling feedback.

When the GraphicNovelEngine is active, these checks evaluate the actual
Sequence/Page/Panel data (not prose heuristics) and surface concrete
notes about page turns, dialogue load, panel flow, visual clutter, motif
recurrence, emotional pacing, and splash-page justification.

Pure core/app logic: no UI / Tauri / filesystem / provider imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from logosforge.graphic_novel_plot import (
    _page_text_load,
    classify_page_pacing,
    get_page_turn_map,
    page_rhythm,
)

# Panels-per-page above this reads as visual clutter.
_CLUTTER_PANELS = 9
# Dialogue refs per panel above this reads as balloon overload.
_BALLOON_OVERLOAD_PER_PANEL = 3
# A single balloon longer than this risks overflowing its panel.
_DIALOGUE_OVERFLOW_CHARS = 110
# Fraction of dialogue-bearing panels at/above which a page reads text-heavy.
_TEXT_HEAVY_RATIO = 0.6

# Internal-state words that read as un-drawable (need a visual translation).
_EMOTION_WORDS = (
    "feels", "feeling", "realizes", "realises", "remembers", "thinks",
    "wonders", "hopes", "fears", "loves", "hates", "regrets", "senses",
    "knows", "understands", "wants", "decides", "misses", "dreads",
    "yearns", "despairs", "reflects", "ponders", "believes",
)


@dataclass
class GraphicNovelCheck:
    """One review finding. page_id is None for project-level checks."""

    check_type: str
    message: str
    severity: str = "info"      # "info" | "warning"
    page_id: int | None = None


def review_graphic_novel(
    db: Any, project_id: int, page_id: int | None = None,
) -> list[GraphicNovelCheck]:
    """Run graphic-novel review checks (§2).

    With *page_id*, runs page-scoped checks only; otherwise runs page
    checks for every page plus project-level checks.
    """
    checks: list[GraphicNovelCheck] = []
    pages = db.get_gn_pages(project_id)
    if not pages:
        return checks

    target_pages = (
        [p for p in pages if p.id == page_id] if page_id is not None else pages
    )
    for page in target_pages:
        checks.extend(_page_checks(db, page))

    if page_id is None:
        checks.extend(_project_checks(db, project_id, pages))
    return checks


def _page_checks(db: Any, page: Any) -> list[GraphicNovelCheck]:
    out: list[GraphicNovelCheck] = []
    panels = db.get_gn_panels_for_page(page.id)
    n = len(panels)

    # Too much dialogue / balloon overload.
    text_load = _page_text_load(db, page.id)
    if n and text_load >= _BALLOON_OVERLOAD_PER_PANEL * n:
        out.append(GraphicNovelCheck(
            "too_much_dialogue",
            f"Page {page.page_number}: heavy dialogue load "
            f"({text_load} balloons across {n} panels) — risk of balloon overload",
            "warning", page.id,
        ))

    # Visual clutter.
    if n > _CLUTTER_PANELS:
        out.append(GraphicNovelCheck(
            "visual_clutter",
            f"Page {page.page_number}: {n} panels — visual clutter risk; "
            "consider fewer, stronger panels",
            "warning", page.id,
        ))

    # Panel flow readable — a panel with no description/action reads unclearly.
    if n:
        empty = sum(
            1 for p in panels
            if not (p.description or "").strip() and not (p.action or "").strip()
        )
        if empty:
            out.append(GraphicNovelCheck(
                "panel_flow",
                f"Page {page.page_number}: {empty} panel(s) lack description/action "
                "— panel flow may be unreadable",
                "warning", page.id,
            ))

    # Splash page justified — a splash should land a beat/reveal/high energy.
    if page.splash_page:
        density = (page.density_level or "").lower()
        justified = (
            (page.reveal_type or "").strip()
            or (page.emotional_beat or "").strip()
            or density in ("dense", "explosive")
        )
        if not justified:
            out.append(GraphicNovelCheck(
                "splash_unjustified",
                f"Page {page.page_number}: splash page with no reveal, beat, or "
                "high energy — is the full-page real estate earned?",
                "warning", page.id,
            ))
    return out


def _project_checks(
    db: Any, project_id: int, pages: list,
) -> list[GraphicNovelCheck]:
    out: list[GraphicNovelCheck] = []

    # Page turn effective? — reveal setups should land on a non-empty page.
    turns = get_page_turn_map(db, project_id)
    if not turns and len(pages) >= 4:
        out.append(GraphicNovelCheck(
            "page_turn_effective",
            "No page-turn reveals set up across the book — page turns "
            "are not being leveraged for tension",
            "warning",
        ))
    for turn in turns:
        reveal_panels = db.get_gn_panels_for_page(turn["reveal_page_id"])
        if not reveal_panels:
            out.append(GraphicNovelCheck(
                "page_turn_effective",
                f"Page {turn['setup_page_number']} sets up a "
                f"'{turn['reveal_type']}' but the reveal page "
                f"{turn['reveal_page_number']} is empty",
                "warning", turn["reveal_page_id"],
            ))

    # Motif recurrence — a motif seen once is decor, not theme.
    counts: dict[str, int] = {}
    for page in pages:
        seen: set[str] = set()
        for panel in db.get_gn_panels_for_page(page.id):
            for m in db.csv_split(panel.visual_motifs):
                seen.add(m)
        for m in seen:
            counts[m] = counts.get(m, 0) + 1
    for motif, c in counts.items():
        if c == 1:
            out.append(GraphicNovelCheck(
                "motif_recurrence",
                f"Motif '{motif}' appears once — introduced but never recurs",
                "info",
            ))

    # Emotional pacing balanced — flag a monotonous rhythm across the book.
    rhythms = {page_rhythm(p.density_level) for p in pages if (p.density_level or "")}
    if len(pages) >= 4 and len(rhythms) <= 1:
        out.append(GraphicNovelCheck(
            "emotional_pacing",
            "Emotional pacing is monotonous — every page shares the same "
            "rhythm; vary density to breathe",
            "warning",
        ))
    return out


# ===========================================================================
# Slice 5 — granular page/panel intelligence (heuristic, no LLM calls)
# ===========================================================================

def detect_text_heavy_page(db: Any, page_id: int) -> bool:
    """True if a page leans on text over image (balloon overload or a high
    share of dialogue-bearing panels)."""
    panels = db.get_gn_panels_for_page(page_id)
    n = len(panels)
    if n == 0:
        return False
    balloons = sum(len(db.csv_split(p.dialogue_refs)) for p in panels)
    if balloons >= _BALLOON_OVERLOAD_PER_PANEL * n:
        return True
    dialogue_panels = sum(1 for p in panels if db.csv_split(p.dialogue_refs))
    return (dialogue_panels / n) >= _TEXT_HEAVY_RATIO


def detect_missing_visual_action(db: Any, panel_id: int) -> bool:
    """True if a panel describes an internal/emotional state but gives no
    drawable action — i.e. it can't be staged as an image."""
    panel = db.get_gn_panel_by_id(panel_id)
    if panel is None:
        return False
    desc = (panel.description or "").strip().lower()
    action = (panel.action or "").strip()
    if action or not desc:
        return False
    return any(w in desc for w in _EMOTION_WORDS)


def review_gn_panel(db: Any, panel_id: int) -> list[GraphicNovelCheck]:
    """Panel-level visual-storytelling checks (§3)."""
    panel = db.get_gn_panel_by_id(panel_id)
    if panel is None:
        return []
    out: list[GraphicNovelCheck] = []
    num = panel.panel_number
    page_id = panel.page_id
    desc = (panel.description or "").strip()
    action = (panel.action or "").strip()

    if not desc and not action:
        out.append(GraphicNovelCheck(
            "panel_readable",
            f"Panel {num} is not visually readable — no description or action.",
            "warning", page_id,
        ))
    elif detect_missing_visual_action(db, panel_id):
        out.append(GraphicNovelCheck(
            "drawable_action",
            f"Panel {num} describes emotion but no drawable action.",
            "warning", page_id,
        ))

    if (desc or action) and not (panel.shot_type or "").strip():
        out.append(GraphicNovelCheck(
            "shot_clarity",
            f"Panel {num}: shot/framing not specified — the staging is unclear.",
            "info", page_id,
        ))

    for line in db.csv_split(panel.dialogue_refs):
        if len(line) > _DIALOGUE_OVERFLOW_CHARS:
            out.append(GraphicNovelCheck(
                "dialogue_overflow",
                f"Panel {num}: dialogue may overflow the panel — split or trim.",
                "warning", page_id,
            ))
            break
    return out


def review_gn_page(db: Any, page_id: int) -> list[GraphicNovelCheck]:
    """Page-level review = existing page checks + text/image balance +
    emotional-beat visibility + every panel's checks (§3)."""
    page = db.get_gn_page_by_id(page_id)
    if page is None:
        return []
    out: list[GraphicNovelCheck] = list(_page_checks(db, page))

    if detect_text_heavy_page(db, page_id):
        out.append(GraphicNovelCheck(
            "text_heavy",
            f"Page {page.page_number} is text-heavy — lean on the art to "
            "carry meaning.",
            "warning", page_id,
        ))

    panels = db.get_gn_panels_for_page(page_id)
    if panels and not (page.emotional_beat or "").strip():
        out.append(GraphicNovelCheck(
            "emotional_beat",
            f"Page {page.page_number}: emotional beat not defined — what "
            "should the reader feel here?",
            "info", page_id,
        ))

    for panel in panels:
        out.extend(review_gn_panel(db, panel.id))
    return out


def suggest_page_turn(db: Any, page_id: int) -> list[GraphicNovelCheck]:
    """Page-turn / reveal pressure for a single page (§3, §4)."""
    page = db.get_gn_page_by_id(page_id)
    if page is None:
        return []
    out: list[GraphicNovelCheck] = []
    has_reveal = bool((page.reveal_type or "").strip()
                      and page.reveal_type != "none")
    if not has_reveal:
        out.append(GraphicNovelCheck(
            "page_turn_pressure",
            f"Page {page.page_number} ends without a reveal or hook — the "
            "page turn carries no pressure.",
            "info", page_id,
        ))
    else:
        # Reveal set up but the next page can't land it.
        pages = db.get_gn_pages(db.get_gn_page_by_id(page_id).project_id)
        order = [p.id for p in pages]
        if page_id in order:
            i = order.index(page_id)
            if i + 1 < len(order):
                nxt = pages[i + 1]
                if not db.get_gn_panels_for_page(nxt.id):
                    out.append(GraphicNovelCheck(
                        "page_turn_pressure",
                        f"Page {page.page_number} sets up a "
                        f"'{page.reveal_type}' but the reveal page "
                        f"{nxt.page_number} is empty.",
                        "warning", nxt.id,
                    ))
    return out


def suggest_panel_rewrite(db: Any, panel_id: int) -> str:
    """A compact, GN-vocabulary rewrite suggestion for a panel."""
    panel = db.get_gn_panel_by_id(panel_id)
    if panel is None:
        return ""
    num = panel.panel_number
    desc = (panel.description or "").strip()
    action = (panel.action or "").strip()
    if not desc and not action:
        return (f"Give panel {num} a concrete visual — describe what we SEE "
                "in the frame (subject, staging, expression).")
    if detect_missing_visual_action(db, panel_id):
        return (f"Rewrite panel {num} to show a drawable action or outward "
                "behavior, not an internal state — externalize the emotion.")
    if not (panel.shot_type or "").strip():
        return (f"Specify a shot/framing for panel {num} (wide, close-up, "
                "insert…) so the visual storytelling reads clearly.")
    for line in db.csv_split(panel.dialogue_refs):
        if len(line) > _DIALOGUE_OVERFLOW_CHARS:
            return (f"Panel {num}'s dialogue is long for one balloon — split "
                    "it across panels or trim to a beat.")
    return (f"Panel {num} reads clearly; sharpen the focal action or tighten "
            "the dialogue if you want more punch.")


# ===========================================================================
# Slice 5 — /gn commands: compact, grouped review output (§5, §6, §7)
# ===========================================================================

GN_COMMANDS = ("check", "page", "panel", "rhythm", "page-turn", "motifs",
               "continuity")

# Map a check_type to one of the four report groups (§6).
_GROUP: dict[str, str] = {
    "emotional_pacing": "Page Rhythm",
    "page_turn_effective": "Page Rhythm",
    "page_turn_pressure": "Page Rhythm",
    "splash_unjustified": "Page Rhythm",
    "visual_clutter": "Page Rhythm",
    "emotional_beat": "Page Rhythm",
    "panel_flow": "Panel Readability",
    "panel_readable": "Panel Readability",
    "drawable_action": "Panel Readability",
    "shot_clarity": "Panel Readability",
    "too_much_dialogue": "Text/Image Balance",
    "text_heavy": "Text/Image Balance",
    "dialogue_overflow": "Text/Image Balance",
    "motif_recurrence": "Continuity / Motifs",
    "motif_single_use": "Continuity / Motifs",
    "character_visual_missing": "Continuity / Motifs",
    "location_design_missing": "Continuity / Motifs",
    "object_missing_continuity_state": "Continuity / Motifs",
}

# Short GN-vocabulary fix per check_type.
_FIX: dict[str, str] = {
    "emotional_pacing": "vary page density so the book breathes.",
    "page_turn_effective": "plant reveals on verso pages to pull the turn.",
    "page_turn_pressure": "end the page on a hook or hold the reveal for the turn.",
    "splash_unjustified": "earn the full page with a reveal or peak beat.",
    "visual_clutter": "cut to fewer, stronger panels.",
    "emotional_beat": "name the feeling the page should land.",
    "panel_flow": "give the panel a clear visual subject.",
    "panel_readable": "describe what we see in the frame.",
    "drawable_action": "externalize the emotion as a drawable action.",
    "shot_clarity": "specify the shot/framing.",
    "too_much_dialogue": "move meaning into the art; trim balloons.",
    "text_heavy": "let images carry the page; cut copy.",
    "dialogue_overflow": "split the line across panels.",
    "motif_recurrence": "recur the motif or cut it.",
    "motif_single_use": "make it recur so it reads as intentional.",
    "character_visual_missing": "define the character's visual identity in PSYKE.",
    "location_design_missing": "record the location's visual design.",
    "object_missing_continuity_state": "note the object's continuity state.",
}

_ORDER = ("Page Rhythm", "Panel Readability", "Text/Image Balance",
          "Continuity / Motifs")


def _visual_identity_checks(db: Any, project_id: int) -> list[GraphicNovelCheck]:
    """Characters that appear in panels but lack PSYKE visual identity (§7)."""
    from logosforge.psyke_visual import review_visual_memory
    out: list[GraphicNovelCheck] = []
    for c in review_visual_memory(db, project_id):
        out.append(GraphicNovelCheck(c.check_type, c.message, c.severity,
                                     c.entry_id))
    return out


def _collect_findings(
    db: Any, project_id: int, scope: str,
) -> list[GraphicNovelCheck]:
    pages = db.get_gn_pages(project_id)
    findings: list[GraphicNovelCheck] = []
    if scope in ("check", "page"):
        for page in pages:
            findings.extend(_page_checks(db, page))
            if detect_text_heavy_page(db, page.id):
                findings.append(GraphicNovelCheck(
                    "text_heavy",
                    f"Page {page.page_number} is text-heavy — lean on the art.",
                    "warning", page.id,
                ))
    if scope in ("check", "panel"):
        for page in pages:
            for panel in db.get_gn_panels_for_page(page.id):
                findings.extend(review_gn_panel(db, panel.id))
    if scope in ("check", "rhythm", "page-turn"):
        findings.extend(_project_checks(db, project_id, pages))
        if scope == "page-turn":
            for page in pages:
                findings.extend(suggest_page_turn(db, page.id))
    if scope in ("check", "motifs", "continuity"):
        findings.extend(_visual_identity_checks(db, project_id))
    # Scope-narrowing: keep only the groups relevant to a focused command.
    if scope == "rhythm":
        findings = [f for f in findings if _GROUP.get(f.check_type) == "Page Rhythm"]
    elif scope == "page-turn":
        findings = [f for f in findings if f.check_type in
                    ("page_turn_pressure", "page_turn_effective")]
    elif scope == "motifs":
        findings = [f for f in findings if f.check_type in
                    ("motif_recurrence", "motif_single_use",
                     "character_visual_missing")]
    elif scope == "continuity":
        findings = [f for f in findings
                    if _GROUP.get(f.check_type) == "Continuity / Motifs"]
    return findings


def _format_review(findings: list[GraphicNovelCheck]) -> str:
    if not findings:
        return "Graphic Novel Review\n\nNo issues found."
    grouped: dict[str, list[GraphicNovelCheck]] = {}
    for f in findings:
        grouped.setdefault(_GROUP.get(f.check_type, "Continuity / Motifs"),
                           []).append(f)
    lines = ["Graphic Novel Review"]
    for group in _ORDER:
        items = grouped.get(group)
        if not items:
            continue
        lines.append("")
        lines.append(f"{group}:")
        for f in items[:4]:
            lines.append(f"- issue: {f.message}")
            fix = _FIX.get(f.check_type)
            if fix:
                lines.append(f"  fix: {fix}")
    return "\n".join(lines)


def format_gn_command(db: Any, project_id: int, subcommand: str) -> str:
    """Render a ``/gn <subcommand>`` response (caller gates to GN projects)."""
    sub = (subcommand or "").strip().lower() or "check"
    if sub not in GN_COMMANDS:
        return ("Unknown /gn command. Try: "
                + ", ".join(f"/gn {c}" for c in GN_COMMANDS))
    if not db.get_gn_pages(project_id):
        return "No graphic-novel pages yet — add pages and panels first."
    return _format_review(_collect_findings(db, project_id, sub))
