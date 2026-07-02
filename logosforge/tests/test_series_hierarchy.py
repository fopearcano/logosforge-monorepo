"""Series Mode Structural Correction — Phase 1.

The corrected serial hierarchy:

    Series Project -> Season -> Episode -> Act -> Chapter -> Scene

Seasons / Episodes are real rows; each Series scene links to its Episode via
``Scene.episode_id``; the Act -> Chapter -> Scene outline is episode-scoped and
scene-derived. Coverage: the model/DB column, the ``series_structure`` data
layer (CRUD + tree + path + stats + non-destructive legacy migration + export),
the rebuilt Navigator (hierarchy CRUD, A/B/C display, unassigned bucket, trivial
collapse, legacy back-compat), project isolation, the mode lock, export privacy,
and that **no other writing mode is affected**.
"""

from __future__ import annotations

import os
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import series_structure as sst
from logosforge import series_pipeline as spp
from logosforge import story_structure as ss
from logosforge import writing_modes as wm

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


# -- builders ---------------------------------------------------------------


def _series(db, title="SR"):
    return db.create_project(title, narrative_engine="series",
                             default_writing_format="series").id


def _legacy_scene(db, pid, *, title="S", content="x", act="Act I",
                  chapter="Episode 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content).id


def _hierarchy(db, pid):
    """A real Season -> Episode with two scenes; returns (season, ep, [sids])."""
    sid_season = sst.create_season(db, pid, "Pilot Season").id
    ep = sst.create_episode(db, sid_season, "Cold Open", project_id=pid)
    a = sst.create_episode_scene(db, pid, ep.id, title="Alpha", )
    b = sst.create_episode_scene(db, pid, ep.id, title="Beta")
    return sid_season, ep.id, [a.id, b.id]


def _nav(db, pid, **cb):
    from logosforge.ui.series_navigator_view import SeriesNavigatorView
    return SeriesNavigatorView(db, pid, **cb)


def _tree_texts(view):
    out = []
    t = view._tree

    def walk(item, depth):
        out.append((depth, item.text(0)))
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)
    for i in range(t.topLevelItemCount()):
        walk(t.topLevelItem(i), 0)
    return out


def _find_item(view, predicate):
    t = view._tree
    stack = [t.topLevelItem(i) for i in range(t.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if predicate(it):
            return it
        for i in range(it.childCount()):
            stack.append(it.child(i))
    return None


# ==========================================================================
# 1-6  Model + DB column
# ==========================================================================


def test_scene_table_has_episode_id_column():
    from sqlalchemy import text
    db = Database()
    with db._engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(scene)")).fetchall()}
    assert "episode_id" in cols


def test_new_scene_episode_id_defaults_none():
    db = Database()
    pid = _series(db)
    sid = _legacy_scene(db, pid)
    assert db.get_scene_by_id(sid).episode_id is None


def test_create_scene_accepts_episode_id():
    db = Database()
    pid = _series(db)
    season = db.create_season(pid, title="S1")
    ep = db.create_episode(season.id, project_id=pid, title="E1")
    sc = db.create_scene(pid, title="X", episode_id=ep.id)
    assert db.get_scene_by_id(sc.id).episode_id == ep.id


def test_set_scene_episode_links_and_clears():
    db = Database()
    pid = _series(db)
    season = db.create_season(pid, title="S1")
    ep = db.create_episode(season.id, project_id=pid, title="E1")
    sid = _legacy_scene(db, pid)
    db.set_scene_episode(sid, ep.id)
    assert db.get_scene_by_id(sid).episode_id == ep.id
    db.set_scene_episode(sid, None)
    assert db.get_scene_by_id(sid).episode_id is None


def test_get_scenes_for_episode_orders_by_sort_order():
    db = Database()
    pid = _series(db)
    season = db.create_season(pid, title="S1")
    ep = db.create_episode(season.id, project_id=pid, title="E1")
    a = db.create_scene(pid, title="A", episode_id=ep.id)
    b = db.create_scene(pid, title="B", episode_id=ep.id)
    ids = [s.id for s in db.get_scenes_for_episode(ep.id)]
    assert ids == [a.id, b.id]


def test_get_unassigned_series_scenes():
    db = Database()
    pid = _series(db)
    season = db.create_season(pid, title="S1")
    ep = db.create_episode(season.id, project_id=pid, title="E1")
    linked = db.create_scene(pid, title="L", episode_id=ep.id)
    free = db.create_scene(pid, title="F")
    free_ids = {s.id for s in db.get_unassigned_series_scenes(pid)}
    assert free.id in free_ids and linked.id not in free_ids


# ==========================================================================
# 7-12  DB: delete (unlink, never destroy) + reorder
# ==========================================================================


def test_delete_episode_unlinks_scenes_keeps_bodies():
    db = Database()
    pid = _series(db)
    season = db.create_season(pid, title="S1")
    ep = db.create_episode(season.id, project_id=pid, title="E1")
    sid = db.create_scene(pid, title="Keep", content="BODY", episode_id=ep.id).id
    db.delete_episode(ep.id)
    scene = db.get_scene_by_id(sid)
    assert scene is not None and scene.content == "BODY"
    assert scene.episode_id is None
    assert db.get_episode_by_id(ep.id) is None


def test_delete_season_cascades_episodes_unlinks_scenes():
    db = Database()
    pid = _series(db)
    season = db.create_season(pid, title="S1")
    ep = db.create_episode(season.id, project_id=pid, title="E1")
    sid = db.create_scene(pid, title="Keep", content="BODY", episode_id=ep.id).id
    db.delete_season(season.id)
    assert db.get_season_by_id(season.id) is None
    assert db.get_episode_by_id(ep.id) is None
    scene = db.get_scene_by_id(sid)
    assert scene is not None and scene.content == "BODY" and scene.episode_id is None


def test_reorder_seasons():
    db = Database()
    pid = _series(db)
    s1 = db.create_season(pid, title="S1")
    s2 = db.create_season(pid, title="S2")
    db.reorder_seasons(pid, [s2.id, s1.id])
    assert [s.title for s in db.get_seasons(pid)] == ["S2", "S1"]


def test_reorder_episodes_renumbers():
    db = Database()
    pid = _series(db)
    season = db.create_season(pid, title="S1")
    e1 = db.create_episode(season.id, project_id=pid, title="E1")
    e2 = db.create_episode(season.id, project_id=pid, title="E2")
    db.reorder_episodes(season.id, [e2.id, e1.id])
    eps = db.get_episodes_for_season(season.id)
    assert [e.title for e in eps] == ["E2", "E1"]
    assert [e.episode_number for e in eps] == [1, 2]


def test_delete_scene_still_works_in_hierarchy():
    db = Database()
    pid = _series(db)
    _s, ep_id, sids = _hierarchy(db, pid)
    db.delete_scene(sids[0])
    assert db.get_scene_by_id(sids[0]) is None
    assert [s.id for s in db.get_scenes_for_episode(ep_id)] == [sids[1]]


def test_episode_plotlines_removed_with_episode():
    db = Database()
    pid = _series(db)
    season = db.create_season(pid, title="S1")
    ep = db.create_episode(season.id, project_id=pid, title="E1")
    db.create_episode_plotline(ep.id, type="A", title="A plot")
    db.delete_episode(ep.id)
    assert db.get_episode_plotlines(ep.id) == []


# ==========================================================================
# 13-22  series_structure: detection + CRUD wrappers
# ==========================================================================


def test_is_series_project_true_for_series_false_otherwise():
    db = Database()
    assert sst.is_series_project(db, _series(db)) is True
    novel = db.create_project("N", narrative_engine="novel").id
    assert sst.is_series_project(db, novel) is False


def test_has_series_hierarchy_tracks_season_rows():
    db = Database()
    pid = _series(db)
    assert sst.has_series_hierarchy(db, pid) is False
    sst.create_season(db, pid, "S1")
    assert sst.has_series_hierarchy(db, pid) is True


def test_is_legacy_series_only_with_scenes_no_seasons():
    db = Database()
    pid = _series(db)
    assert sst.is_legacy_series(db, pid) is False        # empty
    _legacy_scene(db, pid)
    assert sst.is_legacy_series(db, pid) is True         # scenes, no seasons
    sst.create_season(db, pid, "S1")
    assert sst.is_legacy_series(db, pid) is False        # now has hierarchy


def test_create_and_list_seasons_numbered():
    db = Database()
    pid = _series(db)
    sst.create_season(db, pid, "A")
    sst.create_season(db, pid, "B")
    seasons = sst.list_seasons(db, pid)
    assert [s.title for s in seasons] == ["A", "B"]
    assert [s.season_number for s in seasons] == [1, 2]


def test_rename_season_and_episode():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "Old")
    ep = sst.create_episode(db, s.id, "OldEp", project_id=pid)
    sst.rename_season(db, s.id, "NewSeason")
    sst.rename_episode(db, ep.id, "NewEp")
    assert db.get_season_by_id(s.id).title == "NewSeason"
    assert db.get_episode_by_id(ep.id).title == "NewEp"


def test_move_season_up_down():
    db = Database()
    pid = _series(db)
    a = sst.create_season(db, pid, "A")
    b = sst.create_season(db, pid, "B")
    assert sst.move_season(db, pid, b.id, -1) is True
    assert [s.title for s in sst.list_seasons(db, pid)] == ["B", "A"]
    assert sst.move_season(db, pid, b.id, -1) is False   # already at top


def test_move_episode_up_down():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S")
    e1 = sst.create_episode(db, s.id, "E1", project_id=pid)
    e2 = sst.create_episode(db, s.id, "E2", project_id=pid)
    assert sst.move_episode(db, s.id, e2.id, -1) is True
    assert [e.title for e in sst.list_episodes(db, s.id)] == ["E2", "E1"]


def test_create_episode_scene_seeds_valid_internal_labels():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S")
    ep = sst.create_episode(db, s.id, "E", project_id=pid)
    sc = sst.create_episode_scene(db, pid, ep.id, title="Scene one")
    row = db.get_scene_by_id(sc.id)
    assert row.episode_id == ep.id
    assert row.act == ss.DEFAULT_ACT and row.chapter == ss.DEFAULT_CHAPTER


def test_create_episode_scene_inherits_last_labels():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S")
    ep = sst.create_episode(db, s.id, "E", project_id=pid)
    sst.create_episode_scene(db, pid, ep.id, act="Act 2", chapter="Chapter 5")
    sc2 = sst.create_episode_scene(db, pid, ep.id, title="next")
    row = db.get_scene_by_id(sc2.id)
    assert row.act == "Act 2" and row.chapter == "Chapter 5"


# ==========================================================================
# 23-30  series_structure: episode-scoped tree, numbering, path, stats
# ==========================================================================


def test_scenes_in_episode_isolated_from_other_episodes():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S")
    e1 = sst.create_episode(db, s.id, "E1", project_id=pid)
    e2 = sst.create_episode(db, s.id, "E2", project_id=pid)
    a = sst.create_episode_scene(db, pid, e1.id, title="in1")
    sst.create_episode_scene(db, pid, e2.id, title="in2")
    ids = [sc.id for sc in sst.scenes_in_episode(db, e1.id)]
    assert ids == [a.id]


def test_assign_scene_moves_between_episodes():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S")
    e1 = sst.create_episode(db, s.id, "E1", project_id=pid)
    e2 = sst.create_episode(db, s.id, "E2", project_id=pid)
    sc = sst.create_episode_scene(db, pid, e1.id, title="movable")
    sst.assign_scene_to_episode(db, sc.id, e2.id)
    assert [x.id for x in sst.scenes_in_episode(db, e1.id)] == []
    assert [x.id for x in sst.scenes_in_episode(db, e2.id)] == [sc.id]


def test_build_episode_tree_groups_by_act_chapter():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S")
    ep = sst.create_episode(db, s.id, "E", project_id=pid)
    sst.create_episode_scene(db, pid, ep.id, act="Act 1", chapter="Chapter 1")
    sst.create_episode_scene(db, pid, ep.id, act="Act 2", chapter="Chapter 1")
    tree = sst.build_episode_tree(db, ep.id)
    assert [a for a, _ in tree] == ["Act 1", "Act 2"]


def test_episode_has_internal_structure_detects_trivial_vs_rich():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S")
    ep = sst.create_episode(db, s.id, "E", project_id=pid)
    sst.create_episode_scene(db, pid, ep.id)        # single Act 1 / Chapter 1
    assert sst.episode_has_internal_structure(sst.build_episode_tree(db, ep.id)) is False
    sst.create_episode_act(db, pid, ep.id, "Act 2")
    assert sst.episode_has_internal_structure(sst.build_episode_tree(db, ep.id)) is True


def test_episode_scene_numbers_are_flat():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S")
    ep = sst.create_episode(db, s.id, "E", project_id=pid)
    a = sst.create_episode_scene(db, pid, ep.id, title="one")
    b = sst.create_episode_scene(db, pid, ep.id, title="two")
    nums = sst.episode_scene_numbers(db, ep.id)["scenes"]
    assert nums[a.id] == "1.1" and nums[b.id] == "1.2"


def test_build_series_tree_shape():
    db = Database()
    pid = _series(db)
    _s, ep_id, sids = _hierarchy(db, pid)
    tree = sst.build_series_tree(db, pid)
    assert len(tree) == 1                       # one season
    season, episodes = tree[0]
    assert season.title == "Pilot Season"
    assert len(episodes) == 1 and episodes[0][0].id == ep_id


def test_scene_series_path_includes_season_episode():
    db = Database()
    pid = _series(db)
    _s, _ep, sids = _hierarchy(db, pid)
    path = sst.scene_series_path(db, pid, sids[0])
    assert "Pilot Season" in path and "Cold Open" in path and "Scene" in path


def test_scene_series_path_empty_for_unassigned():
    db = Database()
    pid = _series(db)
    sid = _legacy_scene(db, pid)
    assert sst.scene_series_path(db, pid, sid) == ""


def test_series_stats_counts():
    db = Database()
    pid = _series(db)
    _hierarchy(db, pid)
    free = db.create_scene(pid, title="free")
    stats = sst.series_stats(db, pid)
    assert stats == {"seasons": 1, "episodes": 1, "scenes_linked": 2,
                     "scenes_unassigned": 1}


def test_move_episode_scene_reorders_within_chapter():
    db = Database()
    pid = _series(db)
    _s, ep_id, sids = _hierarchy(db, pid)
    assert sst.move_episode_scene(db, pid, sids[1], -1) is True
    ordered = [s.id for s in sst.scenes_in_episode(db, ep_id)]
    assert ordered == [sids[1], sids[0]]


def test_rename_episode_act_and_chapter():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S")
    ep = sst.create_episode(db, s.id, "E", project_id=pid)
    sst.create_episode_scene(db, pid, ep.id, act="Act 1", chapter="Chapter 1")
    assert sst.rename_episode_act(db, ep.id, "Act 1", "Prologue") == 1
    assert sst.rename_episode_chapter(db, ep.id, "Prologue", "Chapter 1", "Open") == 1
    tree = sst.build_episode_tree(db, ep.id)
    assert tree[0][0] == "Prologue" and tree[0][1][0][0] == "Open"


# ==========================================================================
# 31-37  Legacy migration — non-destructive
# ==========================================================================


def test_migrate_dry_run_mutates_nothing():
    db = Database()
    pid = _series(db)
    _legacy_scene(db, pid, act="Act I", chapter="Ep 1")
    plan = sst.migrate_legacy_series(db, pid)
    assert plan["confirmed"] is False
    assert sst.has_series_hierarchy(db, pid) is False
    assert plan["would_create_seasons"] == 1


def test_migrate_confirmed_creates_hierarchy():
    db = Database()
    pid = _series(db)
    _legacy_scene(db, pid, act="Act I", chapter="Ep 1")
    _legacy_scene(db, pid, act="Act I", chapter="Ep 2")
    _legacy_scene(db, pid, act="Act II", chapter="Ep 3")
    res = sst.migrate_legacy_series(db, pid, confirmed=True)
    assert res["ok"] and res["seasons"] == 2 and res["episodes"] == 3
    assert res["scenes_linked"] == 3
    assert sst.has_series_hierarchy(db, pid) is True


def test_migrate_preserves_bodies_labels_order():
    db = Database()
    pid = _series(db)
    sid = _legacy_scene(db, pid, title="Keep", content="BODY",
                        act="Act I", chapter="Ep 1")
    before = db.get_scene_by_id(sid)
    snap = (before.content, before.act, before.chapter, before.sort_order)
    sst.migrate_legacy_series(db, pid, confirmed=True)
    after = db.get_scene_by_id(sid)
    assert (after.content, after.act, after.chapter, after.sort_order) == snap
    assert after.episode_id is not None


def test_migrate_uses_act_chapter_names_as_titles():
    db = Database()
    pid = _series(db)
    _legacy_scene(db, pid, act="The Beginning", chapter="Pilot")
    sst.migrate_legacy_series(db, pid, confirmed=True)
    season = sst.list_seasons(db, pid)[0]
    episode = sst.list_episodes(db, season.id)[0]
    assert season.title == "The Beginning" and episode.title == "Pilot"


def test_migrate_refused_when_hierarchy_exists():
    db = Database()
    pid = _series(db)
    _legacy_scene(db, pid)
    sst.create_season(db, pid, "S1")
    res = sst.migrate_legacy_series(db, pid, confirmed=True)
    assert res["ok"] is False


def test_migrate_refused_for_non_series():
    db = Database()
    novel = db.create_project("N", narrative_engine="novel").id
    res = sst.migrate_legacy_series(db, novel, confirmed=True)
    assert res["ok"] is False


def test_migrated_scenes_remain_in_canonical_global_order():
    # The global story_structure (Outline/Manuscript/Timeline) is unchanged by
    # migration — it never destroys the canonical Act/Chapter view.
    db = Database()
    pid = _series(db)
    a = _legacy_scene(db, pid, title="A", act="Act I", chapter="Ep 1")
    b = _legacy_scene(db, pid, title="B", act="Act I", chapter="Ep 2")
    before = ss.canonical_scene_order(db, pid)
    sst.migrate_legacy_series(db, pid, confirmed=True)
    assert ss.canonical_scene_order(db, pid) == before == [a, b]


# ==========================================================================
# 38-41  Export (structure + bodies only; never settings/keys)
# ==========================================================================


def test_export_series_markdown_includes_structure_and_body():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "Pilot Season")
    ep = sst.create_episode(db, s.id, "Cold Open", project_id=pid)
    db.update_scene_content(
        sst.create_episode_scene(db, pid, ep.id, title="Alpha").id,
        "INT. ROOM - DAY")
    md = sst.export_series_markdown(db, pid)
    assert "Pilot Season" in md and "Cold Open" in md
    assert "Alpha" in md and "INT. ROOM - DAY" in md


def test_export_series_markdown_empty_state():
    db = Database()
    pid = _series(db)
    md = sst.export_series_markdown(db, pid)
    assert "No Season/Episode structure yet" in md


def test_export_lists_unassigned_scenes():
    db = Database()
    pid = _series(db)
    _hierarchy(db, pid)
    db.create_scene(pid, title="Floating Scene")
    md = sst.export_series_markdown(db, pid)
    assert "Unassigned Scenes" in md and "Floating Scene" in md


def test_export_never_contains_api_keys():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S1")
    sst.create_episode(db, s.id, "E1", project_id=pid)
    # Stash a provider secret in settings; export must not surface it.
    settings = db.get_project_settings(pid) or {}
    settings["api_key"] = "sk-SECRET-DO-NOT-LEAK"
    db.save_project_settings(pid, settings)
    md = sst.export_series_markdown(db, pid)
    assert "SECRET" not in md and "sk-" not in md


# ==========================================================================
# 42-52  Navigator — hierarchy rendering + CRUD
# ==========================================================================


def test_navigator_empty_hierarchy_hint_when_no_seasons_and_no_scenes():
    db = Database()
    pid = _series(db)
    texts = [t for _d, t in _tree_texts(_nav(db, pid))]
    assert any("No Series structure yet" in t for t in texts)


def test_navigator_renders_season_episode_scene():
    db = Database()
    pid = _series(db)
    _hierarchy(db, pid)
    texts = [t for _d, t in _tree_texts(_nav(db, pid))]
    assert any("Season 1 — Pilot Season" in t for t in texts)
    assert any("Episode 1 — Cold Open" in t for t in texts)
    assert any("Alpha" in t and "Scene" in t for t in texts)


def test_navigator_collapses_trivial_act_chapter():
    db = Database()
    pid = _series(db)
    _s, ep_id, sids = _hierarchy(db, pid)
    view = _nav(db, pid)
    # Single Act/Chapter -> scenes sit directly under the Episode (no Act node).
    texts = [t for _d, t in _tree_texts(view)]
    assert not any(t == "Act 1" for t in texts)
    ep_item = _find_item(view, lambda it: "Cold Open" in it.text(0))
    child_texts = [ep_item.child(i).text(0) for i in range(ep_item.childCount())]
    assert any("Alpha" in t for t in child_texts)


def test_navigator_shows_act_chapter_when_rich():
    db = Database()
    pid = _series(db)
    _s, ep_id, sids = _hierarchy(db, pid)
    sst.create_episode_act(db, pid, ep_id, "Act 2")
    texts = [t for _d, t in _tree_texts(_nav(db, pid))]
    assert any(t == "Act 2" for t in texts)
    assert any(t == "Act 1" for t in texts)


def test_navigator_add_season_creates_row_and_renders():
    db = Database()
    pid = _series(db)
    changed = []
    view = _nav(db, pid, on_data_changed=lambda: changed.append(1))
    view.add_season("New Season")
    assert any(s.title == "New Season" for s in sst.list_seasons(db, pid))
    assert changed                                # host notified
    assert _find_item(view, lambda it: "New Season" in it.text(0)) is not None


def test_navigator_add_episode_and_scene():
    db = Database()
    pid = _series(db)
    view = _nav(db, pid)
    s_id = view.add_season("S1")
    e_id = view.add_episode(s_id, "E1")
    sc_id = view.add_scene(e_id, "Scene X")
    assert db.get_scene_by_id(sc_id).episode_id == e_id
    assert _find_item(view, lambda it: "Scene X" in it.text(0)) is not None


def test_navigator_rename_and_delete_season():
    db = Database()
    pid = _series(db)
    view = _nav(db, pid)
    s_id = view.add_season("S1")
    view.rename_season(s_id, "Renamed")
    assert db.get_season_by_id(s_id).title == "Renamed"
    view.delete_season(s_id)
    assert db.get_season_by_id(s_id) is None


def test_navigator_delete_episode_keeps_scene_unassigned():
    db = Database()
    pid = _series(db)
    view = _nav(db, pid)
    s_id = view.add_season("S1")
    e_id = view.add_episode(s_id, "E1")
    sc_id = view.add_scene(e_id, "Keep")
    view.delete_episode(e_id)
    scene = db.get_scene_by_id(sc_id)
    assert scene is not None and scene.episode_id is None
    # Surfaced in the Unassigned bucket so it is not lost.
    assert _find_item(view, lambda it: "Unassigned Scenes" in it.text(0)) is not None


def test_navigator_move_scene_between_episodes():
    db = Database()
    pid = _series(db)
    view = _nav(db, pid)
    s_id = view.add_season("S1")
    e1 = view.add_episode(s_id, "E1")
    e2 = view.add_episode(s_id, "E2")
    sc_id = view.add_scene(e1, "Movable")
    view.assign_scene(sc_id, e2)
    assert db.get_scene_by_id(sc_id).episode_id == e2


def test_navigator_move_season_reorders():
    db = Database()
    pid = _series(db)
    view = _nav(db, pid)
    a = view.add_season("A")
    b = view.add_season("B")
    assert view.move_season(b, -1) is True
    assert [s.title for s in sst.list_seasons(db, pid)] == ["B", "A"]


def test_navigator_abc_buckets_from_episode_plan():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S1")
    ep = sst.create_episode(db, s.id, "Heist Night", project_id=pid)
    sst.create_episode_scene(db, pid, ep.id, title="Alpha")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Heist Night", a_story="the heist", b_story="the romance"))
    texts = [t for _d, t in _tree_texts(_nav(db, pid))]
    assert any("A-Story" in t and "the heist" in t for t in texts)
    assert any("B-Story" in t and "the romance" in t for t in texts)


# ==========================================================================
# 53-56  Navigator — legacy mode + convert
# ==========================================================================


def test_navigator_legacy_mode_still_read_only_view():
    db = Database()
    pid = _series(db)
    _legacy_scene(db, pid, title="Alpha", act="Act I", chapter="Episode 1")
    texts = [t for _d, t in _tree_texts(_nav(db, pid))]
    assert any("Season / Arc" in t and "Act I" in t for t in texts)


def test_navigator_convert_button_visible_only_for_legacy():
    db = Database()
    pid = _series(db)
    _legacy_scene(db, pid)
    view = _nav(db, pid)
    # isHidden() reflects the explicit setVisible() flag without needing a shown
    # top-level window (isVisible() is always False offscreen until .show()).
    assert view._convert_btn.isHidden() is False      # offered for legacy
    view.convert_legacy(confirmed=True)
    assert view._convert_btn.isHidden() is True        # now on the hierarchy


def test_navigator_convert_legacy_migrates_and_renders():
    db = Database()
    pid = _series(db)
    _legacy_scene(db, pid, title="Alpha", act="Act I", chapter="Pilot")
    view = _nav(db, pid)
    res = view.convert_legacy(confirmed=True)
    assert res["ok"] is True
    texts = [t for _d, t in _tree_texts(view)]
    assert any("Act I" in t for t in texts)           # season title
    assert any("Pilot" in t for t in texts)           # episode title


def test_navigator_dry_run_convert_does_not_mutate():
    db = Database()
    pid = _series(db)
    _legacy_scene(db, pid)
    view = _nav(db, pid)
    view.convert_legacy(confirmed=False)
    assert sst.has_series_hierarchy(db, pid) is False


# ==========================================================================
# 57-65  Isolation, mode lock, and no cross-mode contamination
# ==========================================================================


def test_hierarchy_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "h.db"))
    a = _series(db, "A")
    sst.create_season(db, a, "A_SENTINEL")
    b = _series(db, "B")
    assert sst.list_seasons(db, b) == []
    texts_b = [t for _d, t in _tree_texts(_nav(db, b))]
    assert not any("A_SENTINEL" in t for t in texts_b)


def test_scene_episode_link_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "h2.db"))
    a = _series(db, "A")
    _s, ep_id, sids = _hierarchy(db, a)
    b = _series(db, "B")
    assert db.get_unassigned_series_scenes(b) == []
    assert {s.id for s in db.get_scenes_for_episode(ep_id)} == set(sids)


def test_creating_season_locks_writing_mode():
    db = Database()
    pid = _series(db)
    assert wm.can_change_writing_mode(db, pid) is True     # empty scaffold
    sst.create_season(db, pid, "S1")
    assert wm.can_change_writing_mode(db, pid) is False    # now meaningful


def test_creating_episode_locks_writing_mode():
    db = Database()
    pid = _series(db)
    s = sst.create_season(db, pid, "S1")
    # Season alone already locks; ensure an episode keeps it locked.
    sst.create_episode(db, s.id, "E1", project_id=pid)
    assert wm.can_change_writing_mode(db, pid) is False


def test_novel_project_unaffected_by_episode_id():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                          title="Prose", content="Body").id
    assert db.get_scene_by_id(sid).episode_id is None
    # series_structure is inert for non-series projects: no Season rows means no
    # hierarchy tree. (unassigned_scenes is not mode-gated — every NULL-episode
    # scene qualifies — so it is only meaningful in a Series context.)
    assert sst.is_series_project(db, pid) is False
    assert sst.has_series_hierarchy(db, pid) is False
    assert sst.build_series_tree(db, pid) == []


@pytest.mark.parametrize("engine", ["novel", "screenplay", "graphic_novel",
                                    "stage_script"])
def test_other_modes_have_no_series_hierarchy(engine):
    db = Database()
    pid = db.create_project(engine, narrative_engine=engine,
                            default_writing_format=engine).id
    ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="S",
                    content="x")
    assert sst.has_series_hierarchy(db, pid) is False
    assert sst.is_legacy_series(db, pid) is False


def test_global_story_structure_unchanged_for_series_without_episode_scope():
    # Adding episode_id support must not alter the canonical Act/Chapter tree.
    db = Database()
    pid = _series(db)
    _legacy_scene(db, pid, title="A", act="Act I", chapter="Ep 1")
    tree = ss.build_structure_tree(db, pid)
    assert [a for a, _ in tree] == ["Act I"]
    assert tree[0][1][0][0] == "Ep 1"


def test_episode_id_column_survives_roundtrip(tmp_path):
    path = str(tmp_path / "persist.db")
    db = Database(path)
    pid = _series(db)
    _s, ep_id, sids = _hierarchy(db, pid)
    del db
    db2 = Database(path)
    assert db2.get_scene_by_id(sids[0]).episode_id == ep_id


def test_navigator_not_mounted_for_non_series_is_safe():
    # Constructing for a non-series project must not raise or create storage.
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="S")
    view = _nav(db, pid)
    assert sst.list_seasons(db, pid) == []
    assert view is not None
