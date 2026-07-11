"""Parse an Assistant outline response into structured outline operations.

Outline Mode asks the model for a structured outline (acts / chapters /
scenes / beats). This module turns that free text into a hierarchy of
proposed nodes so the Assistant can PROPOSE the structure and then apply it
additively through the existing outline services — instead of only showing
text.

The Outline data model is a single ``OutlineNode`` table whose hierarchy is
pure parent/child nesting (no node_type column). We infer depth from
Markdown headers (``#`` levels), list indentation, and act/chapter/scene/
beat keywords, then emit nodes with parent links + sort order.

Pure logic: no UI, no DB writes here — the caller applies the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class OutlineOp:
    """One proposed outline node (a create operation)."""

    title: str
    description: str = ""
    level: int = 0                     # 0 = top (act/part), deeper = nested
    kind: str = ""                     # act|chapter|scene|beat|section (label)
    children: list["OutlineOp"] = field(default_factory=list)

    def count(self) -> int:
        return 1 + sum(c.count() for c in self.children)


# Keyword → canonical level (used to normalise mixed inputs).
_KIND_LEVEL = {"act": 0, "part": 0, "chapter": 1, "sequence": 1,
               "scene": 2, "beat": 3}
# Leading whitespace AND Markdown emphasis/decoration (``**``, ``*``, ``_``,
# `` ` ``, ``~``) may precede the keyword — models routinely emit headings as
# ``**Chapter 1: …**`` or ``*Scene 1:*``.  Without tolerating those markers the
# line falls through to the prose branch, the chapter is lost, and its scenes
# orphan into an "Unassigned" bucket.
_KIND_RE = re.compile(
    r"^[\s*_`~]*(act|part|chapter|sequence|scene|beat)\b[\s:.\-)]*",
    re.IGNORECASE,
)
# "1.", "1)", "- ", "* ", "1.2", "•"
_LIST_RE = re.compile(r"^(\s*)(?:[-*•]|\d+[.)](?:\d+[.)])*)\s+(.*)$")
_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")

# A bullet that is dialogue (``ADA — "…"``) or a craft/shot annotation
# (``Visuals: …``, ``Action: …``) is scene *content*, not a structural node.
# Folding it into the current node's description (instead of minting a node)
# stops screenplay/GN outlines from exploding into dozens of dialogue "scenes".
_DIALOGUE_RE = re.compile(r"""^[A-Z][A-Z0-9 .()'’\-]{0,28}\s*[:—–\-]\s*["'“”]""")
_CRAFT_RE = re.compile(
    r"^\s*(visuals?|action|subtext|blocking|page\s*turn|art\s*direction|"
    r"camera|angle|shot|sfx|lighting|sound|mood|tone)\b\s*[:.\-—–]",
    re.IGNORECASE,
)


def _is_content_bullet(body: str) -> bool:
    """True if a list item is dialogue or a craft annotation (not structure)."""
    return bool(_DIALOGUE_RE.match(body) or _CRAFT_RE.match(body))


def _split_title_desc(text: str) -> tuple[str, str]:
    """Split "Title: description" / "Title — description" into parts."""
    text = text.strip().strip("*_`").strip()
    for sep in (" — ", " – ", " - ", ": "):
        if sep in text:
            head, tail = text.split(sep, 1)
            if head.strip():
                return head.strip().rstrip(":").strip(), tail.strip()
    return text.rstrip(":").strip(), ""


def _classify(raw: str) -> tuple[str, int | None]:
    """Return (kind, forced_level) from a leading act/chapter/... keyword."""
    m = _KIND_RE.match(raw)
    if not m:
        return "", None
    kw = m.group(1).lower()
    kind = ("act" if kw in ("act", "part") else
            "chapter" if kw in ("chapter", "sequence") else kw)
    return kind, _KIND_LEVEL[kw]


def _titled(kind: str, raw: str) -> tuple[str, str]:
    """Split a keyword-led line into (title, description).

    Keeps the numbered identity ("Act 1", "Chapter 2") but drops a bare type
    label ("Scene:", "Beat -") so the title is the meaningful text.
    """
    rest = _KIND_RE.sub("", raw).strip()
    head, desc = _split_title_desc(rest)
    label = kind.capitalize()
    if head[:1].isdigit():
        # Keep the numbered identity ("Act 1"); drop any punctuation.
        num = re.match(r"[\d.]+", head)
        num = num.group(0).rstrip(".") if num else ""
        return f"{label} {num}".strip(), desc
    # Bare label like "Scene: title" — title is the remainder.
    return (head or label), desc


def parse_outline_response(text: str) -> list[OutlineOp]:
    """Parse outline text into a tree of OutlineOp (top-level list).

    Robust to: Markdown headers, numbered/bulleted lists with indentation,
    and explicit Act/Chapter/Scene/Beat labels. Lines that look like prose
    (no list/header marker) attach as description to the current node.
    """
    roots: list[OutlineOp] = []
    # stack of (level, op) for the current open ancestry.
    stack: list[tuple[int, OutlineOp]] = []
    last: OutlineOp | None = None
    # Level of the most recent header/keyword section — list items nest
    # beneath it. Reset whenever a header opens a new section.
    section_level = -1
    # (physical_indent, logical_level) frames for the current list, mapping
    # indentation to nesting depth. Reset by headers / bare section keywords.
    indent_stack: list[tuple[int, int]] = []

    def _attach(level: int, op: OutlineOp) -> None:
        nonlocal last
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            stack[-1][1].children.append(op)
        else:
            roots.append(op)
        stack.append((level, op))
        last = op

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        header = _HEADER_RE.match(line)
        listm = _LIST_RE.match(line)

        if header:
            depth = len(header.group(1)) - 1   # "#"=0, "##"=1, ...
            kind, forced = _classify(header.group(2))
            if kind:
                title, desc = _titled(kind, header.group(2))
            else:
                title, desc = _split_title_desc(header.group(2))
            level = forced if forced is not None else depth
            section_level = level
            indent_stack = []
            _attach(level, OutlineOp(title=title or header.group(2).strip(),
                                     description=desc, level=level, kind=kind))
            continue

        if listm:
            indent = len(listm.group(1).replace("\t", "  "))
            body = listm.group(2)
            if last is not None and _is_content_bullet(body):
                # Dialogue / craft annotation → fold into the current node's
                # description rather than minting a bogus structural node.
                extra = body.strip()
                last.description = (
                    (last.description + " " + extra).strip()
                    if last.description else extra
                )
                continue
            kind, _forced = _classify(body)
            if kind:
                title, desc = _titled(kind, body)
            else:
                title, desc = _split_title_desc(body)
            # Nesting follows INDENTATION (the keyword only labels the kind),
            # so same-indent items are siblings — e.g. "- Scene" then "- Beat"
            # at the same indent both sit under the section, not under each
            # other. Drop frames at >= this indent, then nest one deeper than
            # the surviving parent (or the section if none).
            while indent_stack and indent_stack[-1][0] >= indent:
                indent_stack.pop()
            level = (indent_stack[-1][1] + 1) if indent_stack else (
                section_level + 1
            )
            indent_stack.append((indent, level))
            _attach(level, OutlineOp(title=title or body.strip(),
                                     description=desc, level=level, kind=kind))
            continue

        # Bare line: a labelled heading (e.g. "Act 1: ...") or prose desc.
        kind, forced = _classify(line)
        if kind:
            title, desc = _titled(kind, line)
            level = forced if forced is not None else 0
            if kind in ("act", "chapter"):
                section_level = level
                indent_stack = []
            _attach(level, OutlineOp(title=title or line.strip(),
                                     description=desc, level=level, kind=kind))
        elif last is not None:
            # Continuation prose → append to the current node's description.
            extra = line.strip()
            last.description = (
                (last.description + " " + extra).strip()
                if last.description else extra
            )
        else:
            # Leading prose with no structure yet → a top-level section.
            title, desc = _split_title_desc(line)
            _attach(0, OutlineOp(title=title, description=desc, level=0))

    return roots


def _renumber(ops: list[OutlineOp]) -> list[OutlineOp]:
    return ops


def count_ops(ops: list[OutlineOp]) -> int:
    return sum(o.count() for o in ops)


def format_outline_preview(ops: list[OutlineOp]) -> str:
    """Human-readable preview of the proposed structure (for confirmation)."""
    lines: list[str] = []

    def _walk(op: OutlineOp, depth: int) -> None:
        bullet = "  " * depth + "• "
        label = f"[{op.kind}] " if op.kind else ""
        line = f"{bullet}{label}{op.title}"
        if op.description:
            line += f" — {op.description[:60]}"
        lines.append(line)
        for child in op.children:
            _walk(child, depth + 1)

    for op in ops:
        _walk(op, 0)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Repair & validation — keep generated outlines structured and complete
# ---------------------------------------------------------------------------
#
# Generation can return nodes with no description, or (when the model ignores
# the "no prose" instruction) a wall of prose masquerading as an outline.  The
# Outline must never contain empty placeholder blocks, and prose must never be
# applied as structure.  ``repair_outline_ops`` fills missing descriptions with
# a concise, useful placeholder and trims prose-like ones; ``validate_outline_ops``
# rejects output that is not a usable outline.  Neither adds or removes nodes,
# so node counts are preserved for the caller's confirmation/preview.

_MAX_DESC = 400          # a description longer than this reads like prose
_DESC_TRIM = 300         # trim an over-long description to this many chars
_MAX_TITLE = 200         # a title longer than this is prose, not a heading

# A leading meta/preamble line the model sometimes emits before the real
# structure — e.g. "A Complete Outline for Your Novel", "Here is your outline".
# Such prose, when parsed, becomes a bogus top-level structural node (and then a
# placeholder scene that surfaces in the Manuscript canvas). We drop these so
# they never become structure. Kept conservative: only a top-level, kind-less,
# childless node whose title mentions "outline" qualifies — real acts/scenes
# don't look like that.
_PREAMBLE_RE = re.compile(r"\boutlines?\b", re.IGNORECASE)


def _is_preamble_node(op: "OutlineOp") -> bool:
    return (
        not op.kind
        and not op.children
        and bool(_PREAMBLE_RE.search(op.title or ""))
    )


# Section headers the model appends that are NOT narrative structure — they must
# not become chapters/scenes. Matched only when the node is KIND-LESS (an
# explicit "Act 2: …" / "Chapter: …" is never dropped) and the title is
# essentially just the label.
_NON_STRUCTURAL_RE = re.compile(
    r"^\s*(?:key\s+)?(?:"
    r"characters?|character\s+arcs?|cast(?:\s+of\s+characters)?|dramatis\s+personae|"
    r"themes?|thematic[\w\s/&-]*|motifs?|recurring\s+motifs?|visual\s+motifs?|"
    r"symbolism|world\s*building|settings?|locations?|geography|glossary|"
    r"terminology|author'?s?\s+notes?|notes?|synopsis|logline|premise|"
    r"controlling\s+idea|tone(?:\s+and\s+style)?|style|mood|pacing(?:\s+notes?)?|"
    r"structure\s+notes?"
    r")\s*[:.\-—–]?\s*$",
    re.IGNORECASE,
)


def _is_non_structural(op: "OutlineOp") -> bool:
    """A kind-less meta-section ("Key Characters", "Themes", an outline intro)."""
    if op.kind:
        return False
    if _NON_STRUCTURAL_RE.match((op.title or "").strip()):
        return True
    return _is_preamble_node(op)


def _prune_non_structural(
    ops: list["OutlineOp"],
) -> tuple[list["OutlineOp"], list["OutlineOp"]]:
    """Drop kind-less meta-section nodes (and their subtrees) at any depth.

    Returns ``(kept_ops, dropped_roots)``. Acts/chapters/scenes (explicit kind)
    and any node not matching a meta-section label are preserved.
    """
    kept: list[OutlineOp] = []
    dropped: list[OutlineOp] = []
    for op in ops:
        if _is_non_structural(op):
            dropped.append(op)
            continue
        op.children, sub = _prune_non_structural(op.children)
        dropped.extend(sub)
        kept.append(op)
    return kept, dropped


def _fallback_description(op: "OutlineOp") -> str:
    """A concise, useful planning placeholder for a node missing a description."""
    kind = _effective_kind(op)
    title = (op.title or "").strip() or kind.capitalize()
    if kind in ("act", "part"):
        return f"{title}: the dramatic purpose and stakes of this part."
    if kind in ("chapter", "sequence"):
        return (f"{title}: what this chapter accomplishes and how it moves the "
                "story forward.")
    if kind == "beat":
        return f"{title}: the turning point this beat delivers."
    return f"{title}: the goal, conflict, and narrative movement of this scene."


def repair_outline_ops(ops: list[OutlineOp]) -> tuple[list[OutlineOp], list[str]]:
    """Fill empty descriptions, trim prose, and prune non-structural sections.

    Repairs the tree in place (and returns it). Non-structural meta-sections
    ("Key Characters", "Themes", outline intros) are dropped with their
    subtrees; otherwise no nodes are added/removed. *warnings* summarise what
    was repaired/removed so the caller can surface it before applying.
    """
    counters = {"missing": 0, "trimmed": 0}

    # Drop non-structural sections the model appends ("KEY CHARACTERS",
    # "THEMATIC PAYOFF", an outline intro line, …) — and their subtrees — so they
    # never become bogus chapters/scenes. Anything with an explicit act/chapter/
    # scene/beat kind is always kept.
    ops, dropped = _prune_non_structural(ops)
    dropped_count = sum(d.count() for d in dropped)

    def _walk(nodes: list[OutlineOp]) -> None:
        for op in nodes:
            desc = (op.description or "").strip()
            if not desc:
                op.description = _fallback_description(op)
                counters["missing"] += 1
            elif len(desc) > _MAX_DESC:
                cut = desc[:_DESC_TRIM].rsplit(" ", 1)[0].rstrip()
                op.description = (cut or desc[:_DESC_TRIM]).rstrip() + "…"
                counters["trimmed"] += 1
            _walk(op.children)

    _walk(ops)
    warnings: list[str] = []
    if dropped:
        warnings.append(
            f"Removed {dropped_count} non-structural item(s) (e.g. "
            f"“{(dropped[0].title or '')[:40]}”) that aren't part of the "
            "act/chapter/scene structure."
        )
    if counters["missing"]:
        warnings.append(
            f"{counters['missing']} item(s) had no description — added a "
            "concise placeholder you can refine."
        )
    if counters["trimmed"]:
        warnings.append(
            f"{counters['trimmed']} description(s) looked like prose and were "
            "shortened to a one-line summary."
        )
    return ops, warnings


def validate_outline_ops(ops: list[OutlineOp]) -> tuple[bool, list[str]]:
    """Return (ok, errors). Rejects empty output or prose masquerading as outline."""
    if not ops:
        return False, ["No outline structure was found in the response."]

    errors: list[str] = []

    def _walk(nodes: list[OutlineOp]) -> None:
        for op in nodes:
            if not (op.title or "").strip():
                errors.append("An outline item has no title.")
            elif len(op.title) > _MAX_TITLE:
                errors.append(
                    "The response looks like prose, not a structured outline."
                )
            _walk(op.children)

    _walk(ops)
    # De-duplicate, preserving order.
    seen: set[str] = set()
    unique = [e for e in errors if not (e in seen or seen.add(e))]
    return (not unique), unique


# ---------------------------------------------------------------------------
# AI generation prompt builder (scope-aware, engine-aware, PSYKE-aware)
# ---------------------------------------------------------------------------

# Render a raw structural-unit token as a human label.
_UNIT_LABELS = {
    "entrance_exit": "Entrance/Exit",
    "plotline": "A/B/C Plot",
    "cue": "Cue",
}

# Internal scope keys map to a tier (depth) in the engine's structural units.
_SCOPE_TIER = {"act": 0, "chapter": 1, "scene": 2}


def _unit_label(unit: str) -> str:
    return _UNIT_LABELS.get(unit, unit.replace("_", " ").title())


def engine_structural_units(engine: str) -> tuple[str, ...]:
    """The current NarrativeEngine's structural units (Novel fallback)."""
    from logosforge.narrative_engines import get_engine
    return get_engine(engine).get_structural_units()


def _structure_guide(units: tuple[str, ...]) -> str:
    labels = [_unit_label(u) for u in units]
    return "Structure as " + " → ".join(labels) + "."


def build_outline_generation_prompt(
    scope: str = "full", *, engine: str = "novel", template_name: str = "",
    template_beats: list[str] | None = None, psyke_context: str = "",
    target_title: str = "", instructions: str = "",
) -> str:
    """Build the user prompt for an AI outline generation request.

    The structural vocabulary is asked from the current NarrativeEngine
    (``engine``) — Novel: Part/Chapter/Scene; Screenplay: Act/Sequence/
    Scene/Beat; Graphic Novel: Issue/Chapter/Page/Panel; etc. *scope*
    selects a tier (full / act=tier0 / chapter=tier1 / scene=tier2);
    template_*/psyke_context/target_title are folded in when present. Pure
    text — the caller sends it to the model.
    """
    units = engine_structural_units(engine)
    labels = [_unit_label(u) for u in units]
    parts: list[str] = []

    tier = _SCOPE_TIER.get(scope)
    if scope == "full" or tier is None:
        parts.append("Generate a complete story outline.")
    else:
        unit = labels[tier] if tier < len(labels) else labels[-1]
        children = labels[tier + 1:tier + 3]
        if children:
            parts.append(
                f"Generate ONE {unit} for the story outline, with its "
                + " and ".join(children) + "."
            )
        else:
            parts.append(f"Generate the {unit}-level structure here.")

    if target_title:
        parts.append(f"This continues under: {target_title}.")

    parts.append(_structure_guide(units))
    parts.append(
        "Format as a Markdown outline using '#'/'##'/'###' headers and/or "
        "'- ' bullets. Prefix items with the structural unit ("
        + ", ".join(labels) + ") where appropriate. For EVERY node give a "
        "short title, then on the same line after ' — ' a one-line planning "
        "description stating its purpose, and for scenes the central "
        "conflict/tension or narrative movement. Output planning structure "
        "ONLY: no prose, no dialogue, no full paragraphs, no commentary."
    )

    if template_name:
        parts.append(f"Follow the '{template_name}' structure.")
    if template_beats:
        parts.append("Template beats to honour: " + "; ".join(template_beats))
    if psyke_context:
        parts.append(psyke_context)
    if instructions:
        parts.append(instructions)

    return "\n\n".join(parts)


def outline_messages(prompt: str) -> list[dict]:
    """System+user message pair for an outline-generation request.

    Qt-free so the API route and the desktop UI share one definition (the Qt
    worker in ``ui/outline_ai.py`` re-exports this).
    """
    return [
        {"role": "system",
         "content": "You are a story-structure assistant. Produce a clean, "
                    "structured outline only — no prose."},
        {"role": "user", "content": prompt},
    ]


# ---------------------------------------------------------------------------
# Scene-based application (the model the Outline / Plot / Timeline UI reads)
# ---------------------------------------------------------------------------
#
# The visible Outline section (PlanView) — and Plot, Timeline and the
# Dashboard — are all derived from ``Scene`` rows grouped by ``Scene.act`` /
# ``Scene.chapter``.  Applying a generated outline therefore has to create
# *scenes* carrying act/chapter/beat labels, not the parallel ``OutlineNode``
# table.  ``outline_scene_rows`` flattens the proposed op tree into scene rows;
# ``apply_outline_as_scenes`` writes them through the normal scene service.


def _effective_kind(op: "OutlineOp") -> str:
    """The act/chapter/scene/beat role of an op (explicit kind wins)."""
    if op.kind:
        return op.kind
    return {0: "act", 1: "chapter", 2: "scene"}.get(
        op.level, "beat" if op.level >= 3 else "scene",
    )


def outline_scene_rows(
    ops: list[OutlineOp], act: str = "", chapter: str = "",
) -> list[dict]:
    """Flatten a proposed outline tree into scene rows.

    Each row is ``{"act", "chapter", "title", "summary", "beat"}``.  Acts and
    chapters propagate down to their descendant scenes; an act/chapter with no
    scene descendants becomes a single placeholder scene so it stays visible in
    the (scene-derived) Outline.
    """
    rows: list[dict] = []
    for op in ops:
        kind = _effective_kind(op)
        if kind in ("act", "part"):
            sub = outline_scene_rows(op.children, act=op.title, chapter="")
            rows.extend(sub if sub else [
                {"act": op.title, "chapter": "", "title": op.title,
                 "summary": op.description, "beat": ""},
            ])
        elif kind in ("chapter", "sequence"):
            sub = outline_scene_rows(op.children, act=act, chapter=op.title)
            rows.extend(sub if sub else [
                {"act": act, "chapter": op.title, "title": op.title,
                 "summary": op.description, "beat": ""},
            ])
        else:  # scene / beat / section
            beat = op.title if kind == "beat" else ""
            rows.append({
                "act": act, "chapter": chapter, "title": op.title,
                "summary": op.description, "beat": beat,
            })
            # Anything nested under a scene becomes further scenes in context.
            rows.extend(outline_scene_rows(op.children, act=act, chapter=chapter))
    return rows


def apply_outline_as_scenes(
    db, project_id: int, ops: list[OutlineOp], *,
    base_act: str = "", base_chapter: str = "",
) -> list[int]:
    """Apply a proposed outline as Scenes (act/chapter/scene/beat) additively.

    Scenes are appended (``create_scene`` auto-assigns the next sort order) so
    nothing is overwritten.  *base_act* / *base_chapter* scope the result under
    an existing act/chapter (used by the per-item "AI Generate" actions).
    Returns the created scene ids in creation order.
    """
    rows = outline_scene_rows(ops, act=base_act, chapter=base_chapter)
    created: list[int] = []
    for row in rows:
        act = base_act or row["act"]
        chapter = base_chapter or row["chapter"]
        scene = db.create_scene(
            project_id,
            title=row["title"] or "(untitled)",
            summary=row["summary"],
            act=act,
            chapter=chapter,
            beat=row["beat"],
        )
        created.append(scene.id)
    return created


# ---------------------------------------------------------------------------
# Mode-aware outline: Novel = Act → Chapter, others = Act → Scene
# ---------------------------------------------------------------------------


def outline_unit_labels(mode: str) -> tuple[str, str]:
    """Return (container_label, unit_label) for an outline in *mode*.

    Novel → ("Act", "Chapter"); every other mode → ("Act", "Scene").
    """
    from logosforge.writing_modes import NOVEL
    return ("Act", "Chapter") if mode == NOVEL else ("Act", "Scene")


def build_mode_outline_prompt(
    mode: str, *, template_name: str = "", template_beats: list[str] | None = None,
    psyke_context: str = "", instructions: str = "",
) -> str:
    """Two-level outline prompt for the mode's primary unit.

    Novel asks for Acts → Chapters (no scene layer); other modes ask for
    Acts → Scenes (no chapter layer). Each unit must carry a one-line
    description; output is planning structure only (never prose/manuscript).
    """
    container, unit = outline_unit_labels(mode)
    parts = [
        f"Generate a complete story outline as a two-level hierarchy: "
        f"{container} → {unit}. Do NOT add any other structural layer.",
        f"Format as Markdown: '# {container} N: title' for each {container}, "
        f"then '- {unit}: title — one-line description' for each {unit} under it.",
        f"Every {unit} MUST have a concise one-line description stating its "
        f"purpose / what happens. Output planning structure ONLY — no prose, no "
        f"dialogue, no manuscript text, no commentary.",
    ]
    if template_name:
        parts.append(f"Follow the '{template_name}' structure.")
    if template_beats:
        parts.append("Template beats to honour: " + "; ".join(template_beats))
    if psyke_context:
        parts.append(psyke_context)
    if instructions:
        parts.append(instructions)
    return "\n\n".join(parts)


def validate_mode_outline(mode: str, ops: list[OutlineOp]) -> tuple[bool, list[str]]:
    """Validate a generated outline for *mode*.

    Builds on :func:`validate_outline_ops` (rejects empty / prose) and requires
    at least one applicable primary unit so we never silently apply an empty or
    structureless result.
    """
    ok, errors = validate_outline_ops(ops)
    if not ok:
        return ok, errors
    _, unit = outline_unit_labels(mode)
    if mode_outline_rows(mode, ops):
        return True, []
    return False, [f"No {unit.lower()}s were found in the generated outline."]


def outline_chapter_rows(ops: list[OutlineOp], act: str = "") -> list[dict]:
    """Flatten a proposed outline into chapter rows ``{act, title, summary}``.

    Acts propagate their label down; any leaf under an act (whatever the AI
    labelled it) becomes a Chapter — so Novel generation is robust even if the
    model emits scenes. Deeper nesting under a chapter is folded away (Novel has
    no scene layer).
    """
    rows: list[dict] = []
    for op in ops:
        kind = _effective_kind(op)
        if kind in ("act", "part"):
            sub = outline_chapter_rows(op.children, act=op.title)
            rows.extend(sub if sub else [
                {"act": op.title, "title": op.title, "summary": op.description},
            ])
        else:
            rows.append({"act": act, "title": op.title, "summary": op.description})
    return rows


def mode_outline_rows(mode: str, ops: list[OutlineOp]) -> list[dict]:
    """Rows for the mode's primary unit (chapters for Novel, scenes otherwise)."""
    from logosforge.writing_modes import NOVEL
    if mode == NOVEL:
        return outline_chapter_rows(ops)
    return outline_scene_rows(ops)


def apply_outline_as_chapters(
    db, project_id: int, ops: list[OutlineOp],
) -> list[int]:
    """Apply a proposed outline as Chapters (Act → Chapter) additively.

    Writes ONLY to the Chapter planning store (title/summary/act) — never to any
    manuscript body. Returns created chapter ids.
    """
    created: list[int] = []
    for row in outline_chapter_rows(ops):
        chapter = db.create_chapter(
            project_id,
            title=row["title"] or "(untitled)",
            summary=row["summary"],
            act=row["act"],
        )
        created.append(chapter.id)
    return created


def apply_outline_ops(
    db, project_id: int, ops: list[OutlineOp], parent_id: int | None = None,
) -> list[int]:
    """Apply parsed ops ADDITIVELY under *parent_id* via outline services.

    Appends after existing siblings (never deletes / overwrites). Returns the
    flat list of created node ids in creation order.
    """
    created: list[int] = []
    existing = db.get_outline_children(project_id, parent_id)
    base = len(existing)
    for i, op in enumerate(ops):
        node = db.create_outline_node(
            project_id, op.title or "(untitled)", description=op.description,
            parent_id=parent_id, sort_order=base + i,
        )
        created.append(node.id)
        if op.children:
            created.extend(
                apply_outline_ops(db, project_id, op.children, parent_id=node.id)
            )
    return created
