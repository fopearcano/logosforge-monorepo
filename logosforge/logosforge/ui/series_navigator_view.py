"""Series Navigator — the Season -> Episode -> Act -> Chapter -> Scene surface.

This is the canonical structural editor for Series projects. It renders two ways:

* **Hierarchy mode** (the corrected model) — when the project has real Season
  rows it shows ``Season -> Episode -> Act -> Chapter -> Scene`` from
  :mod:`series_structure` (Season/Episode are stored rows; Act/Chapter/Scene are
  episode-scoped, scene-derived). Full CRUD lives here: create / rename / delete
  / move Seasons, Episodes, internal Acts/Chapters and Scenes, plus moving a
  scene between Episodes. A single trivial internal Act/Chapter (e.g. a freshly
  migrated echo) is collapsed so scenes sit directly under their Episode.

* **Legacy mode** (back-compatible) — a Series project that pre-dates the
  hierarchy (Act/Chapter used as Season/Episode, no Season rows) keeps the
  original **read-only** Season/Arc -> Episode -> Scene view over the canonical
  ``story_structure`` tree, with A/B/C buckets from the Episode Beat Plan. A
  one-click, confirmed **Convert to Season/Episode** action migrates it to the
  hierarchy (non-destructive — bodies are never touched).

Series-only. No LLM, no image generation. CRUD writes only Season/Episode rows
and scene structure (``episode_id`` / Act-Chapter labels / order) — never a
scene body — and routes data-change notifications to the host so autosave and
the dirty flag stay correct.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logosforge import series_structure as sst

_ROLE = Qt.ItemDataRole.UserRole

_EMPTY_PROJECT = ("No Series structure yet. Create an Act/Season, Episode, and "
                  "Scene in Outline.")
_NO_PLAN = "No A/B/C story plan yet. Generate or edit Episode Beat Plan."
_NO_SCENES = "No scenes in this episode."
_EMPTY_HIERARCHY = ("No Seasons yet. Use \"Add Season\" to start the "
                    "Season → Episode → Act → Chapter → Scene structure.")
_NO_EPISODES = "No episodes yet — use \"Add Episode\"."
_UNASSIGNED_SCENES = "Unassigned Scenes"


class SeriesNavigatorView(QWidget):
    """Season -> Episode -> Act -> Chapter -> Scene navigator + editor."""

    def __init__(
        self, db, project_id: int, *,
        on_open_outline: Callable[[int], None] | None = None,
        on_open_manuscript: Callable[[int], None] | None = None,
        on_open_timeline: Callable[[int], None] | None = None,
        on_data_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("seriesNavigatorView")
        self._db = db
        self._project_id = project_id
        self._on_open_outline = on_open_outline
        self._on_open_manuscript = on_open_manuscript
        self._on_open_timeline = on_open_timeline
        self._on_data_changed = on_data_changed

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        heading = QLabel("Series Navigator")
        heading.setObjectName("seriesNavigatorHeading")
        heading.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(heading)

        # -- Structural CRUD toolbar --
        crud = QHBoxLayout()
        for label, slot, name in (
            ("+ Season", self._on_add_season, "seriesNavAddSeason"),
            ("+ Episode", self._on_add_episode, "seriesNavAddEpisode"),
            ("+ Act", self._on_add_act, "seriesNavAddAct"),
            ("+ Chapter", self._on_add_chapter, "seriesNavAddChapter"),
            ("+ Scene", self._on_add_scene, "seriesNavAddScene"),
            ("Rename", self._on_rename, "seriesNavRename"),
            ("Delete", self._on_delete, "seriesNavDelete"),
            ("▲", self._on_move_up, "seriesNavMoveUp"),
            ("▼", self._on_move_down, "seriesNavMoveDown"),
        ):
            btn = QPushButton(label)
            btn.setObjectName(name)
            btn.clicked.connect(slot)
            crud.addWidget(btn)
        crud.addStretch()
        self._convert_btn = QPushButton("Convert to Season/Episode…")
        self._convert_btn.setObjectName("seriesNavConvert")
        self._convert_btn.clicked.connect(self._on_convert_legacy)
        crud.addWidget(self._convert_btn)
        layout.addLayout(crud)

        # -- Navigation toolbar --
        controls = QHBoxLayout()
        controls.addStretch()
        for label, slot in (("Open in Outline", self._open_outline),
                            ("Open in Manuscript", self._open_manuscript),
                            ("Open in Timeline", self._open_timeline)):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            controls.addWidget(btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("seriesNavigatorRefresh")
        refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(refresh_btn)
        layout.addLayout(controls)

        self._tree = QTreeWidget()
        self._tree.setObjectName("seriesNavigatorTree")
        self._tree.setHeaderHidden(True)
        self._tree.itemDoubleClicked.connect(lambda it, _c: self._activate(it))
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self._tree, stretch=1)

        self.refresh()

    # -- Build dispatch ------------------------------------------------------

    def refresh(self) -> None:
        self._tree.clear()
        hierarchy = sst.has_series_hierarchy(self._db, self._project_id)
        self._convert_btn.setVisible(
            sst.is_legacy_series(self._db, self._project_id))
        if hierarchy:
            self._build_hierarchy()
        else:
            self._build_legacy()

    # -- Build: new Season/Episode hierarchy --------------------------------

    def _build_hierarchy(self) -> None:
        from logosforge import series_pipeline as spp
        tree = sst.build_series_tree(self._db, self._project_id)
        if not tree:
            self._tree.addTopLevelItem(QTreeWidgetItem([_EMPTY_HIERARCHY]))
        for season, episodes in tree:
            s_item = QTreeWidgetItem([sst.season_label(season)])
            s_item.setData(0, _ROLE, {"kind": "season", "season_id": season.id})
            self._tree.addTopLevelItem(s_item)
            if not episodes:
                s_item.addChild(QTreeWidgetItem([_NO_EPISODES]))
            for episode, ep_tree in episodes:
                e_item = QTreeWidgetItem([sst.episode_label(episode)])
                e_item.setData(0, _ROLE, {"kind": "episode",
                                          "episode_id": episode.id,
                                          "season_id": season.id})
                s_item.addChild(e_item)
                self._add_abc_buckets(spp, e_item, episode)
                self._add_episode_structure(e_item, episode, ep_tree)
                e_item.setExpanded(True)
            s_item.setExpanded(True)

        # Scenes not yet placed in any episode — surfaced so a body is never lost.
        orphans = sst.unassigned_scenes(self._db, self._project_id)
        if orphans:
            u_item = QTreeWidgetItem([f"{_UNASSIGNED_SCENES} ({len(orphans)})"])
            u_item.setData(0, _ROLE, {"kind": "unassigned"})
            self._tree.addTopLevelItem(u_item)
            for sc in orphans:
                title = (getattr(sc, "title", "") or "Untitled").strip() or "Untitled"
                it = QTreeWidgetItem([f"Scene — {title}"])
                it.setData(0, _ROLE, {"kind": "scene", "scene_id": sc.id,
                                      "episode_id": None})
                u_item.addChild(it)
            u_item.setExpanded(True)

    def _add_abc_buckets(self, spp, e_item, episode) -> None:
        plan = None
        try:
            plan = spp.get_episode_plan(self._db, self._project_id,
                                        (episode.title or "").strip())
        except Exception:
            plan = None
        if plan is None or plan.is_empty():
            return
        for label, val in (("A-Story", plan.a_story), ("B-Story", plan.b_story),
                           ("C-Story", plan.c_story)):
            if (val or "").strip():
                t = QTreeWidgetItem([f"{label}: {val.strip()[:80]}"])
                t.setData(0, _ROLE, {"kind": "abc"})
                e_item.addChild(t)

    def _add_episode_structure(self, e_item, episode, ep_tree) -> None:
        numbers = sst.episode_scene_numbers(self._db, episode.id)
        scenes_n = numbers.get("scenes", {})
        acts_n = numbers.get("acts", {})
        chaps_n = numbers.get("chapters", {})

        # Collapse a trivial single Act/Chapter (e.g. a migrated echo): show the
        # scenes directly under the Episode.
        if not sst.episode_has_internal_structure(ep_tree):
            flat = [sc for _a, chs in ep_tree for _c, scs in chs for sc in scs]
            if not flat:
                e_item.addChild(QTreeWidgetItem([_NO_SCENES]))
            for sc in flat:
                e_item.addChild(self._scene_item(sc, scenes_n, episode.id))
            return

        from logosforge import story_structure as ss
        for act_name, ch_list in ep_tree:
            a_label = (act_name if act_name != ss.UNASSIGNED_ACT else "Unassigned")
            a_item = QTreeWidgetItem([a_label])
            a_item.setData(0, _ROLE, {"kind": "act", "episode_id": episode.id,
                                      "act": ss.act_key(act_name)})
            e_item.addChild(a_item)
            for ch_name, scenes in ch_list:
                c_label = (ch_name if ch_name != ss.UNASSIGNED_CHAPTER
                           else "Unassigned")
                c_item = QTreeWidgetItem([c_label])
                c_item.setData(0, _ROLE, {"kind": "chapter",
                                          "episode_id": episode.id,
                                          "act": ss.act_key(act_name),
                                          "chapter": ss.chapter_key(ch_name)})
                a_item.addChild(c_item)
                if not scenes:
                    c_item.addChild(QTreeWidgetItem([_NO_SCENES]))
                for sc in scenes:
                    c_item.addChild(self._scene_item(sc, scenes_n, episode.id))
                c_item.setExpanded(True)
            a_item.setExpanded(True)

    def _scene_item(self, sc, scenes_n, episode_id) -> QTreeWidgetItem:
        snum = scenes_n.get(sc.id, "")
        title = (getattr(sc, "title", "") or "Untitled").strip() or "Untitled"
        label = f"Scene {snum} — {title}" if snum else f"Scene — {title}"
        it = QTreeWidgetItem([label])
        it.setData(0, _ROLE, {"kind": "scene", "scene_id": sc.id,
                              "episode_id": episode_id})
        return it

    # -- Build: legacy (read-only) canonical Act/Chapter/Scene --------------

    def _build_legacy(self) -> None:
        from logosforge import story_structure as ss
        try:
            tree = ss.build_structure_tree(self._db, self._project_id)
            numbers = ss.compute_structural_numbers(
                tree, ss.is_novel_project(self._db, self._project_id))
        except Exception:
            tree, numbers = [], {"acts": {}, "chapters": {}, "scenes": {}}

        if not tree or not any(chs for _a, chs in tree):
            self._tree.addTopLevelItem(QTreeWidgetItem([_EMPTY_PROJECT]))
            return

        acts_n = numbers.get("acts", {})
        chaps_n = numbers.get("chapters", {})
        scenes_n = numbers.get("scenes", {})

        for act, chapters in tree:
            anum = acts_n.get(act, "")
            atext = (f"Season / Arc {anum} — {act}" if act != ss.UNASSIGNED_ACT
                     else "Unassigned")
            act_item = QTreeWidgetItem([atext])
            act_item.setData(0, _ROLE, {"kind": "season", "act": act})
            self._tree.addTopLevelItem(act_item)

            for chapter, scenes in chapters:
                if chapter == ss.UNASSIGNED_CHAPTER:
                    ep_text = "Unassigned"
                else:
                    cnum = chaps_n.get((act, chapter), "")
                    ep_text = (f"Episode {cnum} — {chapter}" if cnum
                               else f"Episode — {chapter}")
                ep_item = QTreeWidgetItem([ep_text])
                ep_item.setData(0, _ROLE, {"kind": "episode", "act": act,
                                           "chapter": chapter})
                act_item.addChild(ep_item)
                self._add_legacy_episode_children(ep_item, chapter, scenes,
                                                  scenes_n)
            act_item.setExpanded(True)

    def _add_legacy_episode_children(self, ep_item, chapter, scenes,
                                     scenes_n) -> None:
        from logosforge import series_pipeline as spp
        plan = None
        try:
            plan = spp.get_episode_plan(self._db, self._project_id, chapter)
        except Exception:
            plan = None
        threads = []
        if plan is not None and not plan.is_empty():
            for label, val in (("A-Story", plan.a_story), ("B-Story", plan.b_story),
                               ("C-Story", plan.c_story)):
                if (val or "").strip():
                    threads.append((label, val.strip()))
        if threads:
            for label, val in threads:
                t_item = QTreeWidgetItem([f"{label}: {val[:80]}"])
                t_item.setData(0, _ROLE, {"kind": "abc", "chapter": chapter,
                                          "thread": label[0]})
                ep_item.addChild(t_item)
                t_item.addChild(QTreeWidgetItem(["No linked scenes yet"]))
        else:
            ep_item.addChild(QTreeWidgetItem([_NO_PLAN]))

        all_scenes = QTreeWidgetItem(["All Scenes"])
        ep_item.addChild(all_scenes)
        if not scenes:
            all_scenes.addChild(QTreeWidgetItem([_NO_SCENES]))
        for sc in scenes:
            snum = scenes_n.get(sc.id, "")
            title = (getattr(sc, "title", "") or "Untitled").strip() or "Untitled"
            label = f"Scene {snum} — {title}" if snum else f"Scene — {title}"
            s_item = QTreeWidgetItem([label])
            s_item.setData(0, _ROLE, {"kind": "scene", "scene_id": sc.id})
            all_scenes.addChild(s_item)
        all_scenes.setExpanded(True)

    # -- Navigation (no mutation) -------------------------------------------

    def _activate(self, item) -> None:
        """Double-click: Scene -> Manuscript; structural nodes -> Outline."""
        data = item.data(0, _ROLE) if item is not None else None
        if not isinstance(data, dict):
            return
        kind = data.get("kind")
        if kind == "scene" and self._on_open_manuscript:
            self._on_open_manuscript(int(data["scene_id"]))
        elif kind in ("season", "episode", "act", "chapter") and self._on_open_outline:
            self._on_open_outline(0)

    def _selected_data(self) -> dict | None:
        item = self._tree.currentItem()
        data = item.data(0, _ROLE) if item is not None else None
        return data if isinstance(data, dict) else None

    def _open_outline(self) -> None:
        if self._on_open_outline:
            self._on_open_outline(0)

    def _open_manuscript(self) -> None:
        data = self._selected_data()
        if data and data.get("kind") == "scene" and self._on_open_manuscript:
            self._on_open_manuscript(int(data["scene_id"]))

    def _open_timeline(self) -> None:
        data = self._selected_data()
        if data and data.get("kind") == "scene" and self._on_open_timeline:
            self._on_open_timeline(int(data["scene_id"]))

    # -- Notify host ---------------------------------------------------------

    def _notify_changed(self) -> None:
        self.refresh()
        if self._on_data_changed:
            self._on_data_changed()

    # ======================================================================
    # CRUD — data methods (test-callable, no dialogs). Each writes via
    # series_structure, then refreshes + notifies the host.
    # ======================================================================

    def add_season(self, title: str = "") -> int:
        season = sst.create_season(self._db, self._project_id, title)
        self._notify_changed()
        return season.id

    def add_episode(self, season_id: int, title: str = "") -> int | None:
        if season_id is None:
            return None
        ep = sst.create_episode(self._db, season_id, title,
                                project_id=self._project_id)
        self._notify_changed()
        return ep.id

    def add_scene(self, episode_id: int, title: str = "Untitled Scene",
                  *, act: str | None = None, chapter: str | None = None
                  ) -> int | None:
        if episode_id is None:
            return None
        sc = sst.create_episode_scene(self._db, self._project_id, episode_id,
                                      title=title, act=act, chapter=chapter)
        self._notify_changed()
        return sc.id

    def add_act(self, episode_id: int, name: str = "") -> bool:
        if episode_id is None:
            return False
        sst.create_episode_act(self._db, self._project_id, episode_id, name)
        self._notify_changed()
        return True

    def add_chapter(self, episode_id: int, act: str, name: str = "") -> bool:
        if episode_id is None:
            return False
        sst.create_episode_chapter(self._db, self._project_id, episode_id,
                                   act, name)
        self._notify_changed()
        return True

    def rename_season(self, season_id: int, title: str) -> None:
        sst.rename_season(self._db, season_id, title)
        self._notify_changed()

    def rename_episode(self, episode_id: int, title: str) -> None:
        sst.rename_episode(self._db, episode_id, title)
        self._notify_changed()

    def rename_scene(self, scene_id: int, title: str) -> None:
        self._db.update_scene_title(scene_id, (title or "").strip())
        self._notify_changed()

    def rename_act(self, episode_id: int, old: str, new: str) -> None:
        sst.rename_episode_act(self._db, episode_id, old, new)
        self._notify_changed()

    def rename_chapter(self, episode_id: int, act: str, old: str,
                       new: str) -> None:
        sst.rename_episode_chapter(self._db, episode_id, act, old, new)
        self._notify_changed()

    def delete_season(self, season_id: int) -> None:
        sst.delete_season(self._db, season_id)
        self._notify_changed()

    def delete_episode(self, episode_id: int) -> None:
        sst.delete_episode(self._db, episode_id)
        self._notify_changed()

    def delete_scene(self, scene_id: int) -> None:
        self._db.delete_scene(scene_id)
        self._notify_changed()

    def move_season(self, season_id: int, delta: int) -> bool:
        ok = sst.move_season(self._db, self._project_id, season_id, delta)
        if ok:
            self._notify_changed()
        return ok

    def move_episode(self, season_id: int, episode_id: int, delta: int) -> bool:
        ok = sst.move_episode(self._db, season_id, episode_id, delta)
        if ok:
            self._notify_changed()
        return ok

    def move_scene(self, scene_id: int, delta: int) -> bool:
        ok = sst.move_episode_scene(self._db, self._project_id, scene_id, delta)
        if ok:
            self._notify_changed()
        return ok

    def assign_scene(self, scene_id: int, episode_id: int | None) -> None:
        sst.assign_scene_to_episode(self._db, scene_id, episode_id)
        self._notify_changed()

    def convert_legacy(self, *, confirmed: bool = False) -> dict:
        result = sst.migrate_legacy_series(self._db, self._project_id,
                                           confirmed=confirmed)
        if result.get("ok"):
            self._notify_changed()
        return result

    # ======================================================================
    # CRUD — GUI handlers (selection + dialogs -> data methods)
    # ======================================================================

    def _on_add_season(self) -> None:
        title, ok = QInputDialog.getText(self, "Add Season", "Season title:")
        if ok:
            self.add_season(title.strip())

    def _on_add_episode(self) -> None:
        data = self._selected_data() or {}
        season_id = data.get("season_id")
        if season_id is None and data.get("kind") == "season":
            season_id = data.get("season_id")
        if season_id is None:
            seasons = sst.list_seasons(self._db, self._project_id)
            if not seasons:
                self._warn("Add a Season first.")
                return
            season_id = seasons[0].id
        title, ok = QInputDialog.getText(self, "Add Episode", "Episode title:")
        if ok:
            self.add_episode(season_id, title.strip())

    def _on_add_act(self) -> None:
        ep_id = self._current_episode_id()
        if ep_id is None:
            self._warn("Select an Episode first.")
            return
        name, ok = QInputDialog.getText(self, "Add Act", "Act name:")
        if ok:
            self.add_act(ep_id, name.strip())

    def _on_add_chapter(self) -> None:
        data = self._selected_data() or {}
        ep_id = self._current_episode_id()
        if ep_id is None:
            self._warn("Select an Episode or Act first.")
            return
        act = data.get("act") or ""
        name, ok = QInputDialog.getText(self, "Add Chapter", "Chapter name:")
        if ok:
            self.add_chapter(ep_id, act, name.strip())

    def _on_add_scene(self) -> None:
        data = self._selected_data() or {}
        ep_id = self._current_episode_id()
        if ep_id is None:
            self._warn("Select an Episode first.")
            return
        title, ok = QInputDialog.getText(self, "Add Scene", "Scene title:")
        if ok:
            self.add_scene(ep_id, (title.strip() or "Untitled Scene"),
                           act=data.get("act"), chapter=data.get("chapter"))

    def _on_rename(self) -> None:
        data = self._selected_data()
        if not data:
            return
        kind = data.get("kind")
        current = self._tree.currentItem()
        cur_text = current.text(0) if current else ""
        if kind not in ("season", "episode", "scene", "act", "chapter"):
            return
        new, ok = QInputDialog.getText(self, "Rename", "New name:", text=cur_text)
        if not ok or not new.strip():
            return
        if kind == "season":
            self.rename_season(int(data["season_id"]), new.strip())
        elif kind == "episode":
            self.rename_episode(int(data["episode_id"]), new.strip())
        elif kind == "scene":
            self.rename_scene(int(data["scene_id"]), new.strip())
        elif kind == "act":
            self.rename_act(int(data["episode_id"]), data.get("act", ""),
                            new.strip())
        elif kind == "chapter":
            self.rename_chapter(int(data["episode_id"]), data.get("act", ""),
                                data.get("chapter", ""), new.strip())

    def _on_delete(self) -> None:
        data = self._selected_data()
        if not data:
            return
        kind = data.get("kind")
        if kind == "season":
            if self._confirm("Delete this Season and its Episodes? Scenes are "
                             "kept (unassigned), not deleted."):
                self.delete_season(int(data["season_id"]))
        elif kind == "episode":
            if self._confirm("Delete this Episode? Its scenes are kept "
                             "(unassigned), not deleted."):
                self.delete_episode(int(data["episode_id"]))
        elif kind == "scene":
            if self._confirm("Delete this scene? This removes its body."):
                self.delete_scene(int(data["scene_id"]))

    def _on_move_up(self) -> None:
        self._move(-1)

    def _on_move_down(self) -> None:
        self._move(+1)

    def _move(self, delta: int) -> None:
        data = self._selected_data()
        if not data:
            return
        kind = data.get("kind")
        if kind == "season":
            self.move_season(int(data["season_id"]), delta)
        elif kind == "episode":
            self.move_episode(int(data["season_id"]), int(data["episode_id"]),
                              delta)
        elif kind == "scene" and data.get("episode_id") is not None:
            self.move_scene(int(data["scene_id"]), delta)

    def _on_convert_legacy(self) -> None:
        plan = self.convert_legacy(confirmed=False)
        msg = (f"Convert this Series to a real Season/Episode hierarchy?\n\n"
               f"This creates {plan.get('would_create_seasons', 0)} Season(s) and "
               f"{plan.get('would_create_episodes', 0)} Episode(s) from the current "
               f"Acts/Chapters and links "
               f"{plan.get('would_link_scenes', 0)} scene(s).\n\n"
               f"Scene bodies are not changed.")
        if self._confirm(msg, title="Convert to Season/Episode"):
            self.convert_legacy(confirmed=True)

    # -- helpers -------------------------------------------------------------

    def _current_episode_id(self) -> int | None:
        data = self._selected_data() or {}
        return data.get("episode_id")

    def _context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is not None:
            self._tree.setCurrentItem(item)
        data = self._selected_data() or {}
        kind = data.get("kind")
        menu = QMenu(self)
        menu.addAction("Add Season", self._on_add_season)
        if kind in ("season", "episode"):
            menu.addAction("Add Episode", self._on_add_episode)
        if kind in ("episode", "act", "chapter", "scene"):
            menu.addAction("Add Act", self._on_add_act)
            menu.addAction("Add Chapter", self._on_add_chapter)
            menu.addAction("Add Scene", self._on_add_scene)
        if kind in ("season", "episode", "scene", "act", "chapter"):
            menu.addSeparator()
            menu.addAction("Rename", self._on_rename)
        if kind in ("season", "episode", "scene"):
            menu.addAction("Delete", self._on_delete)
        if kind in ("season", "episode", "scene"):
            menu.addSeparator()
            menu.addAction("Move Up", self._on_move_up)
            menu.addAction("Move Down", self._on_move_down)
        if kind == "scene":
            menu.addSeparator()
            menu.addAction("Open in Manuscript", self._open_manuscript)
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _warn(self, message: str) -> None:
        QMessageBox.information(self, "Series Navigator", message)

    def _confirm(self, message: str, *, title: str = "Series Navigator") -> bool:
        return QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes
