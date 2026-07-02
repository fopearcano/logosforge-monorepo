# Timeline Phase 1 — Plottr-like Lanes/Colors/Links: Audit

Branch: `claude/setup-logosforge-app-5cVxF`

Audit-first review of "Timeline Phase 1 — Plottr-like lane/matrix timeline with
colors, event blocks, and interlinks." **Finding: the feature was already
implemented in full across earlier Timeline phases.** No production change was
needed; this phase adds a consolidated acceptance suite (spec traceability) and
this document.

## Architecture (already in place)

* **View:** `ui/plot_timeline_view.py` → `PlotTimelineView`
  (`objectName="timeline_target_colored_lane_link_view"`), mounted by
  `main_window._show_timeline`. A horizontal lane/matrix board: sticky left lane
  headers, a scrolling canvas drawing event cards, per-lane colored bands, a
  ruler, and **event-to-event connector lines** (color + optional label).
* **Events = Scenes.** A Timeline event is a Scene placed on the board; explicit
  membership lives in project settings (`timeline_event_ids`). Body is never
  written by the Timeline.
* **Lanes:** `TimelineLane` (name, `color_label`, `order_index`, `collapsed`),
  grouping events by `Scene.plotline == lane.name`. DB: create / rename /
  `set_timeline_lane_color` / reorder / delete / `ensure_timeline_lanes`.
* **Order:** `get/set_timeline_order` + `get/set_timeline_order_mode`
  (`structural` default = canonical Act→Chapter→Scene; opt-in `custom`).
* **Event↔event links:** `TimelineLink(source_scene_id, target_scene_id,
  color_label, link_type, label)` — add/dedup/recolor/relabel/retype/remove.
* **Event→structure links:** `TimelineStructureLink` (act/chapter) with canonical
  chip labels via the shared `story_structure` adapter (`_struct_ref_label` →
  "Act 1" / "Ch 1.2", safe fallback for renamed/missing targets).
* **Unassigned:** a virtual "Unassigned Events" inbox row that appears **only**
  when a timeline event has no matching lane, and hides when empty. Creating an
  Act/lane never spawns it.

## Spec → existing test coverage (all covered)

| Spec test | Covered by |
|---|---|
| 1 sidebar mounts marked view | `test_sidebar_timeline_mounts_marked_view` |
| 2 empty state, no ghost Unassigned | `test_empty_unassigned_is_hidden`, `test_new_project_timeline_is_empty` |
| 3-7 lane create/rename/color/persist/delete | `test_create_lane_via_view`, `test_rename_lane_via_view`, `test_change_lane_color_via_view`, `test_lane_color_persists_after_reload`, `test_delete_lane_unassigns_scenes_not_deletes` |
| 8-9 no auto lane/unassigned | `test_creating_act_creates_no_timeline_lane_or_event`, `test_adding_lane_does_not_create_unassigned` |
| 10-13 event create/edit/color/persist | `test_add_event_to_lane_via_view`, `test_edit_event_title_via_view`, `test_change_event_color_and_persist`, `test_event_color_persists` |
| 14-16 move event (h/lane/persist) | `test_move_block_horizontally`, `test_move_block_to_another_lane_persists`, `test_event_move_*_persists` |
| 17-20 structure links + canonical | `test_link_event_to_act_and_chapter`, `test_link_block_to_act_chapter_scene_via_view`, `test_event_keeps_canonical_label`, `test_timeline_cards_show_canonical_numbers_in_order` |
| 21 move scene updates chip | `test_move_scene_in_outline_updates_numbering`, `test_chapter_move_updates_timeline_numbers` |
| 22 missing target safe | `test_missing_structure_target_safe`, `test_delete_scene_cleans_timeline_and_structure_links` |
| 23 double-click → Manuscript | `test_double_click_opens_manuscript` |
| 24-28 event↔event links | `test_link_same_and_cross_lane`, `test_link_event_to_event_cross_lane_with_color`, `test_link_creation_and_color_persist`, `test_remove_event_link_keeps_events`, `test_missing_link_target_safe_on_reload` |
| 29-32 unassigned gating | `test_unassigned_appears_only_when_lane_less_event_exists`, `test_empty_unassigned_is_hidden`, `test_assigning_unassigned_event_to_lane_clears_inbox`, `test_project_switch_no_timeline_leak` |
| 33-35 project isolation | `test_links_do_not_leak_across_projects`, `test_new_project_has_clean_timeline`, `test_timeline_isolated_and_state_clears_on_switch` |
| export | `test_export_contains_timeline_data`, `test_export_includes_timeline_links_no_cross_project`, `test_timeline_import_round_trip` |

## What this phase added

* `tests/test_timeline_phase1_acceptance.py` — 13 consolidated, end-to-end
  acceptance tests asserting the Phase 1 requirements against the public APIs
  (routing + empty state; lane lifecycle + color persist; event lifecycle with
  body untouched; movement persists without touching Outline order; structure
  links canonical + missing-safe + number-follows-move; event↔event links
  same/cross-lane + color/label + remove-keeps-events; Unassigned gating;
  project isolation + selection cleared on switch; export carries timeline data,
  never provider secrets). No production code changed.

## Tests run

* Timeline suites: `test_timeline_{canonical_order,unassigned,links,
  planner_upgrade}.py`, `test_plot_timeline.py` — **80 passed**.
* New acceptance suite — **13 passed**.
* Regression: writing-mode integrity, outline isolation/repair, plan-view,
  PSYKE isolation, note-links, canvas-deferred, Screenplay Phases 1/2/4/7/8/9,
  writing-core, autosave — **passed** (the lone `test_editing_integrity`
  focus assertion is the known headless cross-suite artifact; passes in
  isolation).

## Remaining limitations / deferred

* Movement uses compact controls (`Move`, `Assign lane`) + persisted timeline
  order; full pointer drag-and-drop of cards is deferred (documented).
* "Link to Scene" for events is expressed as an event↔event `TimelineLink`
  (events are scenes); there is no separate scene-as-structure-link, by design.
* `relation_type` exists on links (`link_type`) but the UI surfaces color +
  optional label primarily; richer relation-type editing is a later pass.

## Classification

**A — Timeline Phase 1 complete: Plottr-like lanes/colors/links are stable.**
The feature was already implemented and exhaustively tested; this phase confirms
it against the spec and adds a consolidated acceptance suite.
