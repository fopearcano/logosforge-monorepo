"""Canonical story-structure adapter — the single ordered source of Acts /
Chapters / Scenes shared by Outline, Manuscript, Timeline, Assistant and Export.

There are **no Act/Chapter tables**: a project's structure is derived from the
``Scene`` rows — ``Scene.act`` / ``Scene.chapter`` are string labels and
``Scene.sort_order`` is the single global order. This module is the ONE place
that turns those rows into an ordered tree and the structural numbers
(Act ``1`` · Chapter ``1.2`` · Scene ``1.2.1``). Every view must read order and
numbering from here instead of re-deriving it locally, so Outline, Manuscript
and Timeline always agree.

Ordering rule: named Acts/Chapters keep their first-seen (``sort_order``) order;
scenes with no Act (or no Chapter) collect in an "Unassigned" bucket that always
sorts **last** — so a Scene never appears before a real Act. The Unassigned
bucket is intentionally left unnumbered.
"""

from __future__ import annotations

from logosforge.db import Database

# Display label for the bucket holding scenes with no Act / no Chapter. Kept in
# sync with the rest of the app's "Unassigned" vocabulary (e.g. Story Grid).
UNASSIGNED_ACT = "Unassigned"
UNASSIGNED_CHAPTER = "Unassigned"

# Defaults used when CREATING new structure with no explicit parent.
DEFAULT_ACT = "Act 1"
DEFAULT_CHAPTER = "Chapter 1"

# Labels used when REPAIRING pre-existing orphan data from earlier bugs.
RECOVERED_ACT = "Recovered Act"
RECOVERED_CHAPTER = "Recovered Chapter"

# Canonical Save-the-Cat beat order (structural, non-UI). Used by the Beats
# section and by structural analysis; re-exported from ``ui.structure_view``
# for back-compatibility so the headless API never has to import Qt for it.
BEAT_ORDER = [
    "Opening Image",
    "Setup",
    "Catalyst",
    "Debate",
    "Break into Two",
    "Midpoint",
    "Bad Guys Close In",
    "All Is Lost",
    "Break into Three",
    "Finale",
    "Final Image",
]


def act_key(name: str) -> str:
    """Map the Unassigned display label back to the stored empty string."""
    return "" if name == UNASSIGNED_ACT else name


def chapter_key(name: str) -> str:
    return "" if name == UNASSIGNED_CHAPTER else name


def is_novel_project(db: Database, project_id: int) -> bool:
    """Novel uses Act→Chapter→Scene; other modes use Act→Scene."""
    try:
        from logosforge.project_compat import get_project_narrative_engine
        project = db.get_project_by_id(project_id)
        return (get_project_narrative_engine(project) or "novel") == "novel"
    except Exception:
        return True


def _ordered(names: list[str], unassigned: str) -> list[str]:
    """Named entries in first-seen order, the Unassigned bucket (if any) last."""
    named = [n for n in names if n != unassigned]
    return named + ([unassigned] if unassigned in names else [])


def build_structure_tree(
    db: Database, project_id: int,
) -> list[tuple[str, list[tuple[str, list]]]]:
    """Canonical ``[(act, [(chapter, [scene, ...]), ...]), ...]``.

    Acts/Chapters are grouped by label (deduped) in first-seen ``sort_order``;
    the "Unassigned" bucket for label-less scenes always sorts last.
    """
    scenes = db.get_all_scenes(project_id)
    act_order: list[str] = []
    chapter_order: dict[str, list[str]] = {}
    grouped: dict[str, dict[str, list]] = {}

    for scene in scenes:
        act = (scene.act or "").strip() or UNASSIGNED_ACT
        chapter = (scene.chapter or "").strip() or UNASSIGNED_CHAPTER
        if act not in grouped:
            grouped[act] = {}
            act_order.append(act)
            chapter_order[act] = []
        if chapter not in grouped[act]:
            grouped[act][chapter] = []
            chapter_order[act].append(chapter)
        grouped[act][chapter].append(scene)

    tree: list[tuple[str, list[tuple[str, list]]]] = []
    for act in _ordered(act_order, UNASSIGNED_ACT):
        chapters = _ordered(chapter_order[act], UNASSIGNED_CHAPTER)
        tree.append((act, [(ch, grouped[act][ch]) for ch in chapters]))
    return tree


# Back-compat alias: the Outline planner historically called this build_plan_tree.
build_plan_tree = build_structure_tree


def compute_structural_numbers(
    tree: list[tuple[str, list[tuple[str, list]]]], is_novel: bool,
) -> dict:
    """Structural numbers from a tree.

    Returns ``{"acts": {act: "1"}, "chapters": {(act, ch): "1.2"},
    "scenes": {scene_id: "1.2.3"}}``. Novel → Act.Chapter.Scene (scenes with no
    chapter become Act.Scene); other modes flatten to Act.Scene. The Unassigned
    bucket is left blank ("") so orphans read as unnumbered, never as a fake Act.
    """
    acts: dict[str, str] = {}
    chapters: dict[tuple[str, str], str] = {}
    scenes: dict[int, str] = {}
    act_no = 0
    for act_name, ch_list in tree:
        if act_name == UNASSIGNED_ACT:
            acts[act_name] = ""
            for ch_name, ch_scenes in ch_list:
                chapters[(act_name, ch_name)] = ""
                for s in ch_scenes:
                    scenes[s.id] = ""
            continue
        act_no += 1
        acts[act_name] = str(act_no)
        chap_no = 0
        flat_scene = 0
        for ch_name, ch_scenes in ch_list:
            if ch_name == UNASSIGNED_CHAPTER:
                chapters[(act_name, ch_name)] = ""
            else:
                chap_no += 1
                chapters[(act_name, ch_name)] = f"{act_no}.{chap_no}"
            for si, scene in enumerate(ch_scenes, start=1):
                if is_novel:
                    if ch_name == UNASSIGNED_CHAPTER:
                        scenes[scene.id] = f"{act_no}.{si}"
                    else:
                        scenes[scene.id] = f"{act_no}.{chap_no}.{si}"
                else:
                    flat_scene += 1
                    scenes[scene.id] = f"{act_no}.{flat_scene}"
    return {"acts": acts, "chapters": chapters, "scenes": scenes}


# Back-compat alias used by the Outline planner.
compute_outline_numbering = compute_structural_numbers


def flatten_tree_to_order(
    tree: list[tuple[str, list[tuple[str, list]]]],
) -> tuple[list[int], dict[int, tuple[str, str]]]:
    """Flatten a (possibly reordered) tree into a global scene order plus the
    Act/Chapter label each scene should carry. "Unassigned" placeholders are
    converted back to empty strings so a move never persists the display label.
    """
    order: list[int] = []
    structure: dict[int, tuple[str, str]] = {}
    for act_name, ch_list in tree:
        a = act_key(act_name)
        for ch_name, ch_scenes in ch_list:
            c = chapter_key(ch_name)
            for scene in ch_scenes:
                order.append(scene.id)
                structure[scene.id] = (a, c)
    return order, structure


# ---------------------------------------------------------------------------
# Canonical read API (used by Outline / Manuscript / Timeline / Export)
# ---------------------------------------------------------------------------


def get_ordered_structure(db: Database, project_id: int):
    """The canonical ordered Act→Chapter→Scene tree for a project."""
    return build_structure_tree(db, project_id)


def canonical_scene_order(db: Database, project_id: int) -> list[int]:
    """Flat list of scene ids in canonical structure order (the same order
    Outline and Manuscript render). Timeline's "Structural Order" mode uses this
    so linked scene events line up with the Outline (1.1.1, 1.1.2, 1.1.3, …)."""
    order, _structure = flatten_tree_to_order(build_structure_tree(db, project_id))
    return order


def list_acts(db: Database, project_id: int) -> list[str]:
    return [a for a, _ in build_structure_tree(db, project_id)]


def list_chapters(
    db: Database, project_id: int, act: str | None = None,
) -> list[str]:
    out: list[str] = []
    for a, chs in build_structure_tree(db, project_id):
        if act is not None and a != act:
            continue
        out.extend(c for c, _ in chs if c != UNASSIGNED_CHAPTER)
    return out


def list_scenes(
    db: Database, project_id: int,
    act: str | None = None, chapter: str | None = None,
) -> list:
    out: list = []
    for a, chs in build_structure_tree(db, project_id):
        if act is not None and a != act:
            continue
        for c, scs in chs:
            if chapter is not None and c != chapter:
                continue
            out.extend(scs)
    return out


def get_primary_writing_units(db: Database, project_id: int) -> list:
    """Mode-aware primary writing units in canonical order.

    Novel → one entry per (act, chapter) group; other modes → scenes.
    """
    tree = build_structure_tree(db, project_id)
    if is_novel_project(db, project_id):
        units = []
        for a, chs in tree:
            for c, scs in chs:
                if c != UNASSIGNED_CHAPTER:
                    units.append((a, c, scs))
        return units
    return list_scenes(db, project_id)


def get_unit_path(db: Database, project_id: int, scene_id: int) -> str:
    """Readable canonical path, e.g. ``Act 1 · Chapter 1.2 · Scene 1.2.1``.

    Returns "" if the scene is not found. Safe against missing/renamed nodes.
    """
    tree = build_structure_tree(db, project_id)
    numbers = compute_structural_numbers(tree, is_novel_project(db, project_id))
    for act_name, ch_list in tree:
        for ch_name, ch_scenes in ch_list:
            for s in ch_scenes:
                if s.id != scene_id:
                    continue
                parts: list[str] = []
                an = numbers["acts"].get(act_name, "")
                parts.append(f"Act {an}" if an else act_name)
                if ch_name != UNASSIGNED_CHAPTER:
                    cn = numbers["chapters"].get((act_name, ch_name), "")
                    parts.append(f"Chapter {cn}" if cn else ch_name)
                sn = numbers["scenes"].get(scene_id, "")
                parts.append(f"Scene {sn}" if sn else (s.title or "Scene"))
                return " · ".join(parts)
    return ""


def structure_ref_number(
    db: Database, project_id: int, target_type: str, target_ref: str,
) -> str:
    """Canonical number for a Timeline structure link target.

    ``("act", "Act I") → "1"`` · ``("chapter", "Ch1") → "1.2"``. Returns "" if
    the target no longer exists (safe for stale links).
    """
    tree = build_structure_tree(db, project_id)
    numbers = compute_structural_numbers(tree, is_novel_project(db, project_id))
    if target_type == "act":
        return numbers["acts"].get(target_ref, "")
    if target_type == "chapter":
        for (act_name, ch_name), num in numbers["chapters"].items():
            if ch_name == target_ref:
                return num
    return ""


def note_link_label(
    db: Database, project_id: int, kind: str, ref,
) -> tuple[str, bool]:
    """Canonical display label + ``missing`` flag for a note's structure link.

    ``("act", "Act I") → ("Act 1 — Act I", False)`` ·
    ``("chapter", "Ch1") → ("Chapter 1.2 — Ch1", False)`` ·
    ``("scene", 7) → ("Scene 1.2.3 — Title", False)``.

    Recomputed on each call, so the number/path follows the current Outline order
    automatically while the link itself stays bound to the same act-name / scene
    id. Missing/renamed targets are flagged (never crash) and remain removable.
    """
    kind = (kind or "").lower()
    try:
        tree = build_structure_tree(db, project_id)
        numbers = compute_structural_numbers(tree, is_novel_project(db, project_id))
    except Exception:
        tree, numbers = [], {"acts": {}, "chapters": {}, "scenes": {}}

    if kind == "act":
        present = ref in numbers.get("acts", {})
        num = numbers.get("acts", {}).get(ref, "")
        head = f"Act {num}" if num else "Act"
        return (f"{head} — {ref}", not present)

    if kind == "chapter":
        match = next(((a, c) for a, chs in tree for c, _ in chs if c == ref), None)
        if match is None:
            return (f"Chapter — {ref}", True)
        num = numbers.get("chapters", {}).get(match, "")
        head = f"Chapter {num}" if num else "Chapter"
        return (f"{head} — {ref}", False)

    if kind == "scene":
        scene = None
        try:
            scene = db.get_scene_by_id(int(ref))
        except Exception:
            scene = None
        if scene is None:
            return ("Scene — (missing)", True)
        num = numbers.get("scenes", {}).get(scene.id, "")
        title = (getattr(scene, "title", "") or "Untitled").strip() or "Untitled"
        head = f"Scene {num}" if num else "Scene"
        return (f"{head} — {title}", False)

    return (f"{kind.title()} — {ref}", False)


# ---------------------------------------------------------------------------
# Structural invariant: every Scene under a Chapter, every Chapter under an Act
# ---------------------------------------------------------------------------


def is_orphan_scene(scene) -> bool:
    """A scene is orphan if it has no Act or no Chapter label."""
    return (not (getattr(scene, "act", "") or "").strip()
            or not (getattr(scene, "chapter", "") or "").strip())


def validate_structure(db: Database, project_id: int) -> list[int]:
    """Ids of scenes that violate the Act → Chapter → Scene invariant."""
    return [s.id for s in db.get_all_scenes(project_id) if is_orphan_scene(s)]


def ensure_valid_structure(db: Database, project_id: int) -> dict:
    """Repair orphan structure in place so every Scene has a Chapter and every
    Chapter an Act. Empty labels are filled with "Recovered Act"/"Recovered
    Chapter"; any existing valid label is preserved. Only act/chapter labels are
    touched — never body, summary, tags, links, sort order or ids. Idempotent.
    Returns ``{"repaired": n}``.
    """
    repaired = 0
    for s in db.get_all_scenes(project_id):
        act = (s.act or "").strip()
        chapter = (s.chapter or "").strip()
        if act and chapter:
            continue
        db.set_scene_structure(
            s.id, act or RECOVERED_ACT, chapter or RECOVERED_CHAPTER)
        repaired += 1
    return {"repaired": repaired}


def _named_acts(db: Database, project_id: int) -> list[str]:
    return [a for a in list_acts(db, project_id) if a != UNASSIGNED_ACT]


def default_parent(db: Database, project_id: int) -> tuple[str, str]:
    """The (act, chapter) a parent-less new Scene should adopt: the first valid
    Act/Chapter if any exist, else the project's starter Act 1 / Chapter 1."""
    for act_name, chs in build_structure_tree(db, project_id):
        if act_name == UNASSIGNED_ACT:
            continue
        for ch_name, _scenes in chs:
            if ch_name != UNASSIGNED_CHAPTER:
                return (act_name, ch_name)
        return (act_name, DEFAULT_CHAPTER)
    return (DEFAULT_ACT, DEFAULT_CHAPTER)


def _next_name(existing: set[str], prefix: str) -> str:
    i = 1
    while f"{prefix} {i}" in existing:
        i += 1
    return f"{prefix} {i}"


def create_act(db: Database, project_id: int, name: str | None = None):
    """Create an Act. Because Acts are scene-derived, this seeds a valid starter
    scene (Act → Chapter 1 → Scene) — never an orphan. Returns the seed Scene."""
    act = (name or "").strip() or _next_name(
        set(list_acts(db, project_id)), "Act")
    return db.create_scene(
        project_id, title="Untitled Scene", act=act, chapter=DEFAULT_CHAPTER)


def create_chapter(
    db: Database, project_id: int, act: str | None = None,
    name: str | None = None,
):
    """Create a Chapter under an Act (auto-selecting/creating an Act if none is
    given), seeding a valid placeholder Scene. Returns the seed Scene."""
    act_name = (act or "").strip()
    if not act_name:
        acts = _named_acts(db, project_id)
        act_name = acts[0] if acts else DEFAULT_ACT
    chapter = (name or "").strip() or _next_name(
        set(list_chapters(db, project_id, act_name)), "Chapter")
    return db.create_scene(
        project_id, title="Untitled Scene", act=act_name, chapter=chapter)


def create_scene(
    db: Database, project_id: int,
    act: str | None = None, chapter: str | None = None,
    title: str = "Untitled Scene", **kwargs,
):
    """Create a Scene, guaranteeing an Act + Chapter parent. A missing parent is
    filled from :func:`default_parent` — a Scene is never created orphan."""
    a = (act or "").strip()
    c = (chapter or "").strip()
    if not a or not c:
        da, dc = default_parent(db, project_id)
        a = a or da
        c = c or dc
    return db.create_scene(project_id, title=title, act=a, chapter=c, **kwargs)

