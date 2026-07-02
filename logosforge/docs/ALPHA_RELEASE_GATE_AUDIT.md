# Logosforge — Alpha Release Gate Audit

Status: **A — Ready for Alpha Release Candidate.**

Logosforge is a **Creative Writing** system. This audit is the final global
multi-mode integrity gate after the five writing modes and their phases shipped.
It is audit/stabilization only: no new features, and the only changes were
test-harness fixes (no production code changed).

---

## 1. Implemented modes

One **universal Manuscript** (`ui/writing_core_view.py` — a single
`WritingCoreView`) adapts by `writing_mode`; there are **no per-mode Manuscript
view classes**. Canonical structure is **Project → Act → Chapter → Scene**.

| Mode | Primary unit | Manuscript body editor |
|------|--------------|------------------------|
| Novel | **Chapter** | prose |
| Screenplay | Scene | screenplay blocks (+ Fountain foundation) |
| Graphic Novel | Scene | Page / Panel script (no image generation) |
| Stage Script | Scene | stage-play blocks |
| Series | Scene | teleplay blocks (Act↦Season/Arc, Chapter↦Episode display only) |

Confirmed: each project resolves to its mode; primary unit is Chapter for Novel
and Scene for the other four; only the matching mode's editor flags are set
(`_screenplay_mode` / `_graphic_novel_mode`), the others stay off.

## 2. Universal Manuscript confirmation

One section, one view class for every mode. Switching `writing_mode` is
**non-destructive**: `Scene.content` (the mode-agnostic flat body) and
`Scene.summary` are preserved across all five modes. Each mode has its own,
distinct block adapter (`screenplay_blocks` → list, `graphic_novel_blocks` →
`GraphicNovelScript(pages…)`, `stage_script_blocks` → `StageScript`,
`series_blocks` → `SeriesScript`) — four distinct parse-result types, no shared
structure, no cross-contamination.

## 3. Canonical structure confirmation

Act → Chapter → Scene invariant holds in every mode (no orphan scenes/chapters).
Outline, Manuscript, Timeline, Notes, Export, Assistant, and Logos all read order
and numbering from `story_structure` (`canonical_scene_order` /
`compute_structural_numbers`) — never id/created order. Moving a Scene re-orders
canonical output and re-numbers labels everywhere. Series labels (Season/Arc,
Episode) are **display-only** and never change storage.

## 4. Mode-specific body-editor status

| Mode | Phases | Planning (not body) | Health | Reflection | Rewrite | Continuity | Dashboard |
|------|--------|---------------------|--------|------------|---------|-----------|-----------|
| Screenplay | 1–10 | beat plan | ✓ | ✓ | ✓ | ✓ | ✓ |
| Graphic Novel | 1–8 | page/panel plan | ✓ | ✓ | ✓ | ✓ | ✓ |
| Stage Script | 1–8 | beat + blocking/cue plan | ✓ | ✓ | ✓ | ✓ | ✓ |
| Series | 1–8 | Season/Arc + Episode beat plan | ✓ | ✓ | ✓ | ✓ | ✓ |
| Novel | core | Outline | n/a | n/a | n/a | n/a | n/a |

All mode planning artifacts are stored **separately from the body** (settings or
their own stores) and never overwrite `Scene.content`; all generative apply paths
go through **Controlled Apply** with `confirmed=True` (STAGE checkpoint +
`project_data_changed`), touching only `Scene.content`.

## 5. Outline / Timeline / Notes / PSYKE status

- **Outline** — canonical structural planner (Acts → Chapters → Scenes); summaries
  remain planning data and never become body; double-click opens the universal
  Manuscript in the correct mode.
- **Timeline** — independent lanes; creating structure does not auto-create lanes;
  events link to Act/Chapter/Scene with canonical labels; a Timeline event never
  creates fake structure or body; project-isolated.
- **Notes** — link to Scene (and Act/Chapter via the structure-link label system),
  project-bound, canonical path via `note_link_label`; do not mutate other surfaces.
- **PSYKE** — project-bound, read-only in checks/reflections (never auto-creates
  entries), surfaced to Assistant/Logos only through capped context maps.

## 6. Assistant / Logos status

Single Assistant provider system (no duplicate backend). The Logos quick-actions
toolbar is a **readable dropdown** (`_action_combo`), not a tiny button row. All
208 registry actions are mode-aware: each mode's actions appear only in that mode
and never leak into another (`sp_*` / `gn_*` / `stage_*` / `series_*` verified
mutually exclusive). Selection/block actions carry `needs_selection=True`;
full-scene/episode actions do not. Deterministic checks never call the LLM; every
mutating action goes through preview/confirmed apply — no direct overwrite from
Assistant or Logos. Theme changes propagate to the Logos toolbar live.

## 7. Export / import status

Body-mode exports (`graphic_novel_blocks` / `stage_script_blocks` /
`series_blocks` `export_project_markdown`) use canonical order and contain **no**
API keys / provider settings / Outline-summary leakage / cross-project data /
image-generation or production metadata (sentinel-verified). Screenplay Fountain
export/import is covered by its own phase suite; Fountain import preview does not
mutate before confirmation. Novel export is unchanged.

## 8. Dirty-state / save status

Data changes mark the project dirty (`MainWindow._on_data_changed` →
`_dirty` / `_modified_since_save`); read-only report builders (health / reflection
/ continuity / dashboard) never touch dirty state; cancel/preview leave data
unchanged; project switch and close honor the dirty flag.

## 9. What passed

The Alpha gate suite (`tests/test_alpha_release_gate.py`, 35 tests) plus the
per-mode phase suites are green: mode recognition + primary unit (×5), one
universal Manuscript view (×5), mode-switch body preservation, distinct adapters,
Act→Chapter→Scene invariant (×5), canonical-order propagation, Timeline
independence + isolation, Notes project-bound + canonical, Logos mode-gating (×4)
+ deterministic no-LLM + needs-selection, export privacy + canonical order,
dirty-state, full project isolation, Canvas-Plot-hidden, registry scope-clean,
no-Season/Episode-table use, five-modes-present.

## 10. What failed / fixes applied

**No product bugs.** Two **test-harness** issues were fixed (tests only, no
`logosforge/**` change):

1. `tests/test_logos_integration.py` — two tests asserted on the **removed**
   `_action_buttons` button-row API; the toolbar is now an `_action_combo`
   dropdown (covered by `test_logos_toolbar_dropdown.py`). Updated to read labels
   from the combo. This cleared the last red tests in the suite.
2. `tests/test_alpha_release_gate.py` (this audit's new suite) — two scaffolding
   assertions were corrected to the real parser return shapes (screenplay returns
   a `list`; Graphic Novel returns `GraphicNovelScript(pages…)`).

## 11. Remaining limitations

- Heuristic checks across all modes are conservative rule-based string/marker/
  overlap signals (no NLP) — directional, not authoritative.
- Review dashboards refresh on open + a manual button (no live debounced
  recompute); "Open in Manuscript" focuses the scene (block-level deep-link is the
  scene scroll today).
- Series Season/Arc and Episode plans are name-keyed to Acts/Chapters (scene-
  derived labels), consistent with `act_summaries` / `chapter_summaries`.
- Persistent cross-scene/episode relation links (setup/payoff, threads) are
  detected and reported but not yet persisted.

## 12. Optional-dependency limitations

DOCX/PDF export paths depend on optional packages and degrade gracefully when the
dependency is absent (those optional-export tests skip/degrade rather than fail).
The full ~120-file suite cannot complete within the environment's time cap; this
gate runs a broad blast-radius sweep across every mode + cross-cutting surface.

## 13. Deferred items (out of scope, intentionally)

- **Canvas Plot** — deferred and hidden from navigation (`_apply_canvas_plot_
  availability`); data preserved, never reactivated.
- **ComfyUI / image generation / image prompts / LoRA / render panels** — not in
  core; reserved for future optional undockable panels.
- **Separate Season/Episode storage hierarchy** — deferred; Series is settings-
  backed over the canonical Act→Chapter→Scene structure. The pre-existing
  `Season`/`Episode` SQLModel tables are a legacy surface the writing system never
  uses.
- **Production scheduling, rehearsal/writers-room management, showrunner
  automation, pitch decks, broadcaster formatting** — out of scope.

## 14. Scope confirmations

- **ComfyUI / image generation:** none added. The Logos registry and every
  authored writing module are clean of comfyui/image-generation/image-prompt/
  img2img/txt2img/stable-diffusion/LoRA terms (code-skeleton scan; disclaimers in
  docstrings excluded).
- **Season/Episode storage migration:** none added. Series writing is settings-
  backed; the new modules never import the legacy `Season`/`Episode` tables.
- **Production / writers-room automation:** none added. "Showrunner" / "Writers-
  Room" appear only as a prompt persona and a reflection perspective label.

## 15. Recommendation

**Ready for Alpha Release Candidate (classification A).** Logosforge presents five
coherent writing modes on one universal Manuscript + `writing_mode` adapter, with
the canonical Act→Chapter→Scene invariant, project isolation, export privacy,
dirty-state handling, mode-aware non-mutating AI assistance, and no scope creep.
Recommended post-Alpha work (all writing-only): export polish (Fountain/teleplay/
broadcaster layouts), persistent serialized-story relation links surfaced in
Timeline/Graph, and a refreshed global audit after any new mode. Visual production
(ComfyUI/image generation), a real Season/Episode storage hierarchy, and
production tooling remain deferred.

## 16. Final Alpha RC status (packaging step)

The Alpha RC was packaged on **2026-06-08** (branch
`claude/setup-logosforge-app-5cVxF`, version `0.9.0-alpha`) as a
**documentation/freeze step — no production code changed.** Added/updated:
`RELEASE_NOTES_ALPHA.md`, `CHANGELOG.md`, `docs/ALPHA_RC_STATUS.md`,
`docs/ALPHA_RC_CHECKLIST.md`, `docs/ALPHA_TEST_COMMANDS.md`,
`docs/KNOWN_LIMITATIONS_ALPHA.md`, and this audit. Re-verified: focused gate
`tests/test_alpha_release_gate.py` = **35 passed**; broad certification sweep =
**1527 passed, 0 failures**. The repository is ready for a **manual Alpha RC smoke
test** ([ALPHA_RC_CHECKLIST.md](ALPHA_RC_CHECKLIST.md)); a Git tag / GitHub release
is intentionally **not** created in this step.
