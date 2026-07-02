"""Series hierarchy data layer — the corrected serial structure.

    Series Project -> Season -> Episode -> Act -> Chapter -> Scene

Seasons and Episodes are **real rows** (the ``Season`` / ``Episode`` tables);
each Series scene links to its Episode via ``Scene.episode_id``. WITHIN an
episode the Act -> Chapter -> Scene outline is derived from the scene string
labels (``Scene.act`` / ``Scene.chapter`` / ``Scene.sort_order``) **scoped to
that episode** — the same canonical algorithm as :mod:`story_structure`, just
filtered by ``episode_id``. So Acts/Chapters stay scene-derived (no new tables
for them); only Season/Episode are stored.

Design contract (Phase 1 foundation):

* **Series-only.** Every entry point is a no-op / empty for non-Series projects.
  ``Scene.episode_id`` is ``NULL`` everywhere else, so this module never changes
  Novel / Screenplay / Graphic Novel / Stage behaviour.
* **The global Outline / Manuscript / Timeline are not rewritten.** They keep
  reading the episode-agnostic :mod:`story_structure`. The Series Navigator (this
  module's consumer) is the canonical Season/Episode structural surface. A
  Season/Episode-aware *global* Outline is deferred to a later phase.
* **No data is silently destroyed.** Deleting a Season/Episode unlinks its scenes
  (``episode_id`` -> NULL) instead of deleting them; the one-time legacy
  migration only *adds* Season/Episode rows and sets ``episode_id`` — it never
  edits a scene's body, labels or order.
* **No LLM, no image generation, no Qt.** Pure data logic.
"""

from __future__ import annotations

from logosforge import story_structure as ss
from logosforge.db import Database


# ---------------------------------------------------------------------------
# Mode / hierarchy detection
# ---------------------------------------------------------------------------


def is_series_project(db: Database, project_id: int) -> bool:
    """True only for projects whose writing mode is Series."""
    try:
        from logosforge.writing_modes import (
            SERIES, get_project_writing_mode_by_id)
        return get_project_writing_mode_by_id(db, project_id) == SERIES
    except Exception:
        return False


def has_series_hierarchy(db: Database, project_id: int) -> bool:
    """True if the project has at least one real Season row (new model)."""
    try:
        return bool(db.get_seasons(project_id))
    except Exception:
        return False


def is_legacy_series(db: Database, project_id: int) -> bool:
    """A Series project still on the Alpha shortcut: it has scenes but no Season
    rows (Act/Chapter were used as Season/Episode). These can be migrated."""
    if not is_series_project(db, project_id):
        return False
    if has_series_hierarchy(db, project_id):
        return False
    try:
        return bool(db.get_all_scenes(project_id))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Season / Episode CRUD (thin, validated wrappers over the DB)
# ---------------------------------------------------------------------------


def list_seasons(db: Database, project_id: int) -> list:
    try:
        return list(db.get_seasons(project_id))
    except Exception:
        return []


def list_episodes(db: Database, season_id: int) -> list:
    try:
        return list(db.get_episodes_for_season(season_id))
    except Exception:
        return []


def create_season(db: Database, project_id: int, title: str = ""):
    """Create a Season at the end of the project's season list."""
    title = (title or "").strip()
    existing = list_seasons(db, project_id)
    season = db.create_season(
        project_id, season_number=len(existing) + 1,
        title=title or f"Season {len(existing) + 1}",
    )
    return season


def rename_season(db: Database, season_id: int, title: str) -> None:
    db.update_season(season_id, title=(title or "").strip())


def delete_season(db: Database, season_id: int) -> None:
    """Delete a Season (cascades to its Episodes); scenes are unlinked, not
    deleted — their bodies survive as unassigned Series scenes."""
    db.delete_season(season_id)


def move_season(db: Database, project_id: int, season_id: int, delta: int) -> bool:
    """Move a Season up (delta=-1) or down (delta=+1). Returns False at an edge."""
    ids = [s.id for s in list_seasons(db, project_id)]
    if season_id not in ids:
        return False
    i = ids.index(season_id)
    j = i + delta
    if j < 0 or j >= len(ids):
        return False
    ids[i], ids[j] = ids[j], ids[i]
    db.reorder_seasons(project_id, ids)
    # Keep the human-facing season_number aligned with the new order.
    for n, sid in enumerate(ids, start=1):
        db.update_season(sid, season_number=n)
    return True


def create_episode(db: Database, season_id: int, title: str = "",
                   *, project_id: int | None = None):
    """Create an Episode at the end of a Season's episode list."""
    title = (title or "").strip()
    existing = list_episodes(db, season_id)
    return db.create_episode(
        season_id, project_id=project_id,
        episode_number=len(existing) + 1,
        title=title or f"Episode {len(existing) + 1}",
    )


def rename_episode(db: Database, episode_id: int, title: str) -> None:
    db.update_episode(episode_id, title=(title or "").strip())


def delete_episode(db: Database, episode_id: int) -> None:
    """Delete an Episode; its scenes are unlinked (``episode_id`` -> NULL)."""
    db.delete_episode(episode_id)


def move_episode(db: Database, season_id: int, episode_id: int, delta: int) -> bool:
    ids = [e.id for e in list_episodes(db, season_id)]
    if episode_id not in ids:
        return False
    i = ids.index(episode_id)
    j = i + delta
    if j < 0 or j >= len(ids):
        return False
    ids[i], ids[j] = ids[j], ids[i]
    db.reorder_episodes(season_id, ids)
    return True


# ---------------------------------------------------------------------------
# Scene <-> Episode linking
# ---------------------------------------------------------------------------


def scenes_in_episode(db: Database, episode_id: int) -> list:
    try:
        return list(db.get_scenes_for_episode(episode_id))
    except Exception:
        return []


def unassigned_scenes(db: Database, project_id: int) -> list:
    """Series scenes not yet placed in any Episode (``episode_id`` IS NULL)."""
    try:
        return list(db.get_unassigned_series_scenes(project_id))
    except Exception:
        return []


def assign_scene_to_episode(db: Database, scene_id: int,
                            episode_id: int | None) -> None:
    """Move a scene into an Episode (or unassign it with ``None``)."""
    db.set_scene_episode(scene_id, episode_id)


def _default_internal_labels(db: Database, episode_id: int,
                             act: str | None, chapter: str | None
                             ) -> tuple[str, str]:
    """Pick the (act, chapter) a new episode scene should adopt.

    Explicit values win; otherwise inherit the last existing scene's labels so a
    new scene lands in the same internal chapter, falling back to the canonical
    starter Act 1 / Chapter 1 for an empty episode.
    """
    a = (act or "").strip()
    c = (chapter or "").strip()
    if a and c:
        return a, c
    existing = scenes_in_episode(db, episode_id)
    if existing:
        last = existing[-1]
        a = a or (getattr(last, "act", "") or "").strip() or ss.DEFAULT_ACT
        c = c or (getattr(last, "chapter", "") or "").strip() or ss.DEFAULT_CHAPTER
    else:
        a = a or ss.DEFAULT_ACT
        c = c or ss.DEFAULT_CHAPTER
    return a, c


def create_episode_scene(db: Database, project_id: int, episode_id: int, *,
                         title: str = "Untitled Scene",
                         act: str | None = None, chapter: str | None = None):
    """Create a Scene linked to an Episode with valid internal Act/Chapter.

    The scene is never created orphan: missing internal labels default to the
    last sibling's labels or the canonical Act 1 / Chapter 1.
    """
    a, c = _default_internal_labels(db, episode_id, act, chapter)
    return db.create_scene(
        project_id, title=title, act=a, chapter=c, episode_id=episode_id)


def create_episode_act(db: Database, project_id: int, episode_id: int,
                       name: str | None = None):
    """Add an internal Act to an Episode (seeds a placeholder scene under
    Chapter 1, so the Act is non-empty and valid)."""
    existing = {(getattr(s, "act", "") or "").strip()
                for s in scenes_in_episode(db, episode_id)}
    act = (name or "").strip() or _next_name(existing, "Act")
    return create_episode_scene(
        db, project_id, episode_id, act=act, chapter=ss.DEFAULT_CHAPTER)


def create_episode_chapter(db: Database, project_id: int, episode_id: int,
                           act: str, name: str | None = None):
    """Add an internal Chapter under an Act inside an Episode (seeds a scene)."""
    act = (act or "").strip() or ss.DEFAULT_ACT
    existing = {(getattr(s, "chapter", "") or "").strip()
                for s in scenes_in_episode(db, episode_id)
                if (getattr(s, "act", "") or "").strip() == act}
    chapter = (name or "").strip() or _next_name(existing, "Chapter")
    return create_episode_scene(db, project_id, episode_id, act=act,
                                chapter=chapter)


def rename_episode_act(db: Database, episode_id: int, old: str, new: str) -> int:
    """Rename an internal Act across an Episode's scenes. Returns count touched.
    Only the Act label is changed (chapter / body / order untouched)."""
    new = (new or "").strip()
    if not new:
        return 0
    n = 0
    for s in scenes_in_episode(db, episode_id):
        if (getattr(s, "act", "") or "").strip() == old:
            db.set_scene_structure(s.id, new, (getattr(s, "chapter", "") or ""))
            n += 1
    return n


def rename_episode_chapter(db: Database, episode_id: int, act: str,
                           old: str, new: str) -> int:
    """Rename an internal Chapter (within one Act) across an Episode's scenes."""
    new = (new or "").strip()
    if not new:
        return 0
    n = 0
    for s in scenes_in_episode(db, episode_id):
        if ((getattr(s, "act", "") or "").strip() == act
                and (getattr(s, "chapter", "") or "").strip() == old):
            db.set_scene_structure(s.id, act, new)
            n += 1
    return n


def move_episode_scene(db: Database, project_id: int, scene_id: int,
                       delta: int) -> bool:
    """Move a scene up/down among its siblings in the same Episode + Act +
    Chapter by swapping global ``sort_order`` with the adjacent sibling."""
    scene = db.get_scene_by_id(scene_id)
    if scene is None or getattr(scene, "episode_id", None) is None:
        return False
    a = (getattr(scene, "act", "") or "").strip()
    c = (getattr(scene, "chapter", "") or "").strip()
    sibs = [s for s in scenes_in_episode(db, scene.episode_id)
            if (getattr(s, "act", "") or "").strip() == a
            and (getattr(s, "chapter", "") or "").strip() == c]
    ids = [s.id for s in sibs]
    if scene_id not in ids:
        return False
    i = ids.index(scene_id)
    j = i + delta
    if j < 0 or j >= len(ids):
        return False
    order = ss.canonical_scene_order(db, project_id)
    try:
        pa, pb = order.index(scene_id), order.index(ids[j])
    except ValueError:
        return False
    order[pa], order[pb] = order[pb], order[pa]
    db.reorder_scenes(project_id, order)
    return True


# ---------------------------------------------------------------------------
# Episode-scoped Act -> Chapter -> Scene tree (reuses the canonical algorithm)
# ---------------------------------------------------------------------------


def _ordered(names: list[str], unassigned: str) -> list[str]:
    named = [n for n in names if n != unassigned]
    return named + ([unassigned] if unassigned in names else [])


def _group_scenes(scenes: list) -> list[tuple[str, list[tuple[str, list]]]]:
    """Group a scene list into ``[(act, [(chapter, [scene, ...]), ...]), ...]``
    in first-seen order, Unassigned bucket last — the same shape and rule as
    :func:`story_structure.build_structure_tree`, but for an arbitrary list."""
    act_order: list[str] = []
    chapter_order: dict[str, list[str]] = {}
    grouped: dict[str, dict[str, list]] = {}
    for scene in scenes:
        act = (getattr(scene, "act", "") or "").strip() or ss.UNASSIGNED_ACT
        chapter = (getattr(scene, "chapter", "") or "").strip() or ss.UNASSIGNED_CHAPTER
        if act not in grouped:
            grouped[act] = {}
            act_order.append(act)
            chapter_order[act] = []
        if chapter not in grouped[act]:
            grouped[act][chapter] = []
            chapter_order[act].append(chapter)
        grouped[act][chapter].append(scene)
    tree: list[tuple[str, list[tuple[str, list]]]] = []
    for act in _ordered(act_order, ss.UNASSIGNED_ACT):
        chapters = _ordered(chapter_order[act], ss.UNASSIGNED_CHAPTER)
        tree.append((act, [(ch, grouped[act][ch]) for ch in chapters]))
    return tree


def build_episode_tree(db: Database, episode_id: int):
    """Episode-scoped ``[(act, [(chapter, [scene, ...]), ...]), ...]``."""
    return _group_scenes(scenes_in_episode(db, episode_id))


def episode_scene_numbers(db: Database, episode_id: int) -> dict:
    """Episode-internal structural numbers (flat Act.Scene — Series is not
    Novel), as ``story_structure.compute_structural_numbers`` would produce."""
    return ss.compute_structural_numbers(build_episode_tree(db, episode_id), False)


def episode_has_internal_structure(tree) -> bool:
    """True if the episode tree has more than a single trivial Act/Chapter — i.e.
    it is worth showing the Act/Chapter nodes (a migrated single-act/single-
    chapter echo is collapsed in the Navigator for readability)."""
    named_acts = [a for a, _ in tree if a != ss.UNASSIGNED_ACT]
    if len(named_acts) > 1:
        return True
    if not named_acts and tree:
        return False
    for act, chs in tree:
        if act == ss.UNASSIGNED_ACT:
            continue
        named_ch = [c for c, _ in chs if c != ss.UNASSIGNED_CHAPTER]
        if len(named_ch) > 1:
            return True
    return False


def build_series_tree(db: Database, project_id: int):
    """The full ``[(season, [(episode, episode_tree), ...]), ...]`` for a project.

    ``episode_tree`` is the episode-scoped Act/Chapter/Scene tree. Empty for a
    project with no Season rows (legacy / brand-new).
    """
    out = []
    for season in list_seasons(db, project_id):
        episodes = []
        for ep in list_episodes(db, season.id):
            episodes.append((ep, build_episode_tree(db, ep.id)))
        out.append((season, episodes))
    return out


# ---------------------------------------------------------------------------
# Labels + readable path
# ---------------------------------------------------------------------------


def season_label(season) -> str:
    num = getattr(season, "season_number", 0) or 0
    title = (getattr(season, "title", "") or "").strip()
    head = f"Season {num}" if num else "Season"
    return f"{head} — {title}" if title else head


def episode_label(episode) -> str:
    num = getattr(episode, "episode_number", 0) or 0
    title = (getattr(episode, "title", "") or "").strip()
    head = f"Episode {num}" if num else "Episode"
    return f"{head} — {title}" if title else head


def scene_series_path(db: Database, project_id: int, scene_id: int) -> str:
    """Readable Series path, e.g.
    ``Season 1 — Pilot · Episode 1 — Cold Open · Act 1 · Scene 1.1``.

    Returns "" if the scene is not linked to an Episode (legacy / unassigned).
    Act/Chapter are omitted when the episode has only a trivial single
    Act/Chapter (so a migrated echo stays clean).
    """
    scene = db.get_scene_by_id(scene_id)
    if scene is None or getattr(scene, "episode_id", None) is None:
        return ""
    ep = db.get_episode_by_id(scene.episode_id)
    if ep is None:
        return ""
    parts: list[str] = []
    season = db.get_season_by_id(ep.season_id)
    if season is not None:
        parts.append(season_label(season))
    parts.append(episode_label(ep))

    tree = build_episode_tree(db, ep.id)
    numbers = ss.compute_structural_numbers(tree, False)
    show_struct = episode_has_internal_structure(tree)
    for act_name, ch_list in tree:
        for ch_name, scs in ch_list:
            if not any(s.id == scene_id for s in scs):
                continue
            if show_struct and act_name != ss.UNASSIGNED_ACT:
                an = numbers["acts"].get(act_name, "")
                parts.append(f"Act {an}" if an else act_name)
            if show_struct and ch_name != ss.UNASSIGNED_CHAPTER:
                cn = numbers["chapters"].get((act_name, ch_name), "")
                parts.append(f"Chapter {cn}" if cn else ch_name)
            sn = numbers["scenes"].get(scene_id, "")
            title = (getattr(scene, "title", "") or "Scene").strip() or "Scene"
            parts.append(f"Scene {sn}" if sn else title)
            return " · ".join(parts)
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Counts / stats (used by the migration dry-run and the Navigator header)
# ---------------------------------------------------------------------------


def series_stats(db: Database, project_id: int) -> dict:
    seasons = list_seasons(db, project_id)
    episodes = 0
    linked = 0
    for s in seasons:
        eps = list_episodes(db, s.id)
        episodes += len(eps)
        for ep in eps:
            linked += len(scenes_in_episode(db, ep.id))
    return {
        "seasons": len(seasons),
        "episodes": episodes,
        "scenes_linked": linked,
        "scenes_unassigned": len(unassigned_scenes(db, project_id)),
    }


# ---------------------------------------------------------------------------
# Legacy migration (confirmed, non-destructive)
# ---------------------------------------------------------------------------


def migrate_legacy_series(db: Database, project_id: int, *,
                          confirmed: bool = False) -> dict:
    """Convert a legacy Alpha-shortcut Series into the real hierarchy.

    The Alpha shortcut used canonical **Act = Season / Arc** and **Chapter =
    Episode**. This creates a real ``Season`` per Act and a real ``Episode`` per
    Chapter, then links each scene to its Episode (``episode_id``).

    Non-destructive: scene bodies, labels (``act`` / ``chapter``) and
    ``sort_order`` are left exactly as they are — the old Act name becomes the
    Season title and the old Chapter name the Episode title, so no information is
    lost and the global Outline is unchanged. (The episode-internal Act/Chapter
    therefore echoes the Season/Episode for migrated projects; the Navigator
    collapses that trivial echo for display.)

    Requires ``confirmed=True``. Without it, returns a dry-run plan describing
    what *would* be created (and mutates nothing).
    """
    if not is_series_project(db, project_id):
        return {"ok": False, "error": "Not a Series project."}
    if has_series_hierarchy(db, project_id):
        return {"ok": False, "error": "Series hierarchy already exists."}

    tree = ss.build_structure_tree(db, project_id)
    plan_seasons = 0
    plan_episodes = 0
    plan_scenes = 0
    for act_name, ch_list in tree:
        plan_seasons += 1
        for _ch, scenes in ch_list:
            plan_episodes += 1
            plan_scenes += len(scenes)

    if not confirmed:
        return {"ok": False, "confirmed": False,
                "would_create_seasons": plan_seasons,
                "would_create_episodes": plan_episodes,
                "would_link_scenes": plan_scenes}

    created_seasons = 0
    created_episodes = 0
    linked = 0
    season_no = 0
    for act_name, ch_list in tree:
        season_no += 1
        s_title = (act_name if act_name != ss.UNASSIGNED_ACT
                   else f"Season {season_no}")
        season = db.create_season(project_id, season_number=season_no,
                                  title=s_title)
        created_seasons += 1
        ep_no = 0
        for ch_name, scenes in ch_list:
            ep_no += 1
            e_title = (ch_name if ch_name != ss.UNASSIGNED_CHAPTER
                       else f"Episode {ep_no}")
            episode = db.create_episode(
                season.id, project_id=project_id,
                episode_number=ep_no, title=e_title)
            created_episodes += 1
            for s in scenes:
                db.set_scene_episode(s.id, episode.id)
                linked += 1

    return {"ok": True, "confirmed": True,
            "seasons": created_seasons, "episodes": created_episodes,
            "scenes_linked": linked}


# ---------------------------------------------------------------------------
# Export (structure + scene bodies only — never settings / API keys)
# ---------------------------------------------------------------------------


def export_series_markdown(db: Database, project_id: int) -> str:
    """Markdown outline of the full Season -> Episode -> Act -> Chapter -> Scene
    hierarchy, including scene bodies. Reads only structure + ``Scene.content`` —
    it can never include provider settings or API keys.
    """
    project = db.get_project_by_id(project_id)
    title = (getattr(project, "title", "") or "Series").strip() or "Series"
    lines: list[str] = [f"# {title}", ""]

    series_tree = build_series_tree(db, project_id)
    if not series_tree:
        lines.append("_No Season/Episode structure yet._")
        return "\n".join(lines)

    for season, episodes in series_tree:
        lines.append(f"## {season_label(season)}")
        summary = (getattr(season, "summary", "") or "").strip()
        if summary:
            lines.append(summary)
        lines.append("")
        for episode, ep_tree in episodes:
            lines.append(f"### {episode_label(episode)}")
            logline = (getattr(episode, "logline", "") or "").strip()
            if logline:
                lines.append(f"*{logline}*")
            lines.append("")
            show_struct = episode_has_internal_structure(ep_tree)
            for act_name, ch_list in ep_tree:
                if show_struct and act_name != ss.UNASSIGNED_ACT:
                    lines.append(f"#### {act_name}")
                    lines.append("")
                for ch_name, scenes in ch_list:
                    if show_struct and ch_name != ss.UNASSIGNED_CHAPTER:
                        lines.append(f"##### {ch_name}")
                        lines.append("")
                    for scene in scenes:
                        s_title = (getattr(scene, "title", "") or "Untitled").strip()
                        lines.append(f"- **{s_title or 'Untitled'}**")
                        body = (getattr(scene, "content", "") or "").strip()
                        if body:
                            lines.append("")
                            lines.extend(f"  {ln}" for ln in body.splitlines())
                        lines.append("")

    unassigned = unassigned_scenes(db, project_id)
    if unassigned:
        lines.append("## Unassigned Scenes")
        lines.append("")
        for scene in unassigned:
            s_title = (getattr(scene, "title", "") or "Untitled").strip()
            lines.append(f"- **{s_title or 'Untitled'}**")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _next_name(existing: set[str], prefix: str) -> str:
    i = 1
    while f"{prefix} {i}" in existing:
        i += 1
    return f"{prefix} {i}"
