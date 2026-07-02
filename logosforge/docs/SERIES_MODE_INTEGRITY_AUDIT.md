# Series Mode — Integrity Audit (Phase 8)

Status: **A — Phases 1–7 are integrated and stable.**
Scope: writing/storytelling/serial-script-health only. **No ComfyUI, no image
generation, no showrunner automation, no writers-room management, no production
scheduling, and no separate Season/Episode storage hierarchy** — confirmed across
every module and the Logos registry.

This document records a full integration audit of Series mode after Phases 1–7. It
is audit/stabilization only: no new features were added, and no confirmed product
bugs were found that required a fix.

---

## 1. Implemented phases

All built on the **universal Manuscript** architecture — a Series Scene's body
*is* `Scene.content` (flat text parsed into ordered, typed teleplay blocks). No
schema change, no parallel storage, no separate Manuscript section. The canonical
structure is unchanged (Act → Chapter → Scene); Series merely *interprets* it as
**Season/Arc → Episode → Scene** and *displays* a Chapter as an Episode.

| Phase | Module | What it does |
|------|--------|--------------|
| 1 | `series_blocks.py` | Teleplay block adapter (`SeriesScript`/`SeriesBlock`, parse/serialize, validate, export) over `Scene.content`; reuses `screenplay_blocks` + serial markers (Act Break / Teaser-Cold Open / Tag) |
| 2 | `series_pipeline.py` | Outline summaries → Season/Arc Plan → Episode Beat Plan → scene draft preview → **confirmed** apply (settings-stored plans; apply via Controlled Apply, `target_type="scene"`) |
| 3 | `series_diagnostics.py` | Deterministic scene + episode intelligence (metrics, format, scene function, dialogue/action balance, episode structure, season-arc, A/B/C, Timeline/PSYKE) + 7 `series_*` check actions |
| 4 | `series_reflection.py` | Counterpart / Reflection (Audience / Showrunner / Character Arc / Episode Structure / Writers-Room) + `series_reflection` and per-perspective actions |
| 5 | `series_rewrite.py` | Controlled rewrite: targeted preview → block diff → **confirmed** apply; selection/block/scene targets; 13 generative `series_*` rewrite actions (preview only) |
| 6 | `series_continuity.py` | Cross-episode continuity (season/arc coherence, episode chain, A/B/C tracking, character arcs, setup/payoff, episode structure, Timeline, PSYKE) + `series_continuity_check` |
| 7 | `series_dashboard.py` + `ui/series_review_view.py` | Project Review Dashboard (Season→Episode→Scene rows, cards, filters, navigation, copy/save-as-note) + `series_review_dashboard` |

The **legacy project-level series surface** (`series_plot.py`, `series_review.py`,
`psyke_series.py`, and the pre-existing `Season` / `Episode` SQLModel tables in
`models/models.py`) is a **distinct surface** that predates this work
(present at `ab08333^`) and was intentionally left untouched. The universal-
Manuscript Series writing system above **never imports or uses** those tables —
verified by a tokenized code-skeleton scan of all eight authored modules.

---

## 2. What passed

**Writing mode.** Series projects resolve to `series`
(`writing_modes.get_project_writing_mode_by_id`); Novel/Screenplay/Graphic
Novel/Stage Script are unaffected. The primary writing unit is the **Scene**
(`current_primary_unit_type == "scene"`). All 31 Series Logos actions are
`modes=("series",)`; none leak into the other modes, and no other mode's actions
appear in Series (verified for Manuscript, Outline, and Timeline sections).

**Universal Manuscript.** One `WritingCoreView`; a Series project shows neither
screenplay-only nor graphic-novel-only controls (both editor flags `False`) and
applies the existing `SERIES` writing format. No separate Series Manuscript
section; the Season/Arc plan, Episode beat plan, reflection, continuity, and
dashboard are stored/served separately and never become the body (verified by the
smoke flow).

**Structure invariant.** Act → Chapter → Scene preserved. The continuity report,
dashboard, and export all read `story_structure.canonical_scene_order` /
`compute_structural_numbers` (never id/created order); moving an Episode (Chapter)
or a Scene re-orders every surface and re-numbers canonical labels (verified
across continuity chain, dashboard, and export).

**No auto-mutation.** Season/Arc and Episode plan **previews**, scene-draft
previews, health, reflection, continuity, and the dashboard never mutate the body;
draft/rewrite apply require `confirmed=True` and go through Controlled Apply (STAGE
checkpoint + `project_data_changed`), touching only `Scene.content` and preserving
Outline summaries, both plan layers, Timeline, PSYKE, and Notes. Cancel/copy leave
data unchanged.

**Project isolation.** Blocks, Season/Arc plans, Episode beat plans, continuity,
dashboard, PSYKE, and export are project-scoped (settings + scene rows keyed by
project); switching to an empty project shows no debris and the original project's
data returns intact (sentinel-string isolation test passes).

**Export / privacy.** `export_project_markdown` and the continuity / dashboard
reports are body/status only — no API keys, provider settings, or Outline
planning summaries leak (sentinels `SECRET_KEY_SENTINEL` / `PLAN_ONLY_SENTINEL`
never appear).

**No scope creep.** A code-skeleton scan (identifiers/imports, excluding
docstrings/strings) of all eight authored modules finds **none** of: comfyui,
image generation, image prompt, lora, stable diffusion, img2img, txt2img,
production schedule, rehearsal. The Logos registry contains no image-generation or
production-management action. (The words "showrunner" and "Writers-Room" appear
only as a Season-plan prompt persona and a *reflection perspective label* — a
writer-facing note, not an automation system. "render" appears only in the
unrelated, pre-existing screenplay "preview render" = formatted-script preview.)
The Series writing system is settings-backed (`series_season_plans` /
`series_episode_plans`), so **no new Season/Episode storage hierarchy** was
introduced.

**Novel / Screenplay / Graphic Novel / Stage Script regression.** Novel prose
flow + Chapter primary-unit intact; Screenplay `sp_*`, Graphic Novel `gn_*`, and
Stage Script `stage_*` actions all still resolve as their mode-gated actions and
never collide with `series_*`.

**UI routing.** The Manuscript scene-menu review hook is mode-aware: in Series it
binds to `_show_series_review` (→ `SeriesReviewView`), and in Novel it does not;
dashboard rows navigate to Manuscript/Outline/Timeline via read-only callbacks
without mutating the body.

---

## 3. What failed / fixes applied

No confirmed integration bugs were found during this audit; **no production code
was changed** in Phase 8. One *test-scaffolding* false positive was corrected
while authoring this suite: a registry-wide "no image generation" assertion used
the bare token `render`, which matches the pre-existing, legitimate screenplay
action `sp_preview_render` (a formatted-script preview, not image generation). The
audit assertion was narrowed to image-generation-specific terms; the Series-module
skeleton scan was already precise.

---

## 4. Remaining limitations (documented, out of scope)

- Heuristics are conservative, rule-based string/marker/overlap checks (no NLP) —
  directional craft signals (A/B/C support, season-arc alignment, continuity), not
  authoritative; paraphrased threads can read as unsupported.
- A/B/C tracking requires the Episode beat plan's A/B/C fields; with no plan it
  reports "unavailable" rather than inferring threads.
- The dashboard table is **scene-centric** (with inherited Episode columns); the
  per-Season and per-Episode rows live in the model (`seasons[]`/`episodes[]`) and
  summary cards rather than as a separate expandable table tier. "Open in
  Manuscript" focuses the scene (scroll/select); block-level deep-linking is the
  scene scroll today.
- Refresh is on-open + a manual button (no auto-debounced live recompute),
  matching the screenplay/stage/graphic-novel dashboards.
- Acts/Chapters are scene-derived **name-keyed** labels (no id tables), so the
  Season/Arc and Episode plans are keyed by Act/Chapter name (consistent with the
  app's existing `act_summaries` / `chapter_summaries` / note-link conventions);
  renaming or duplicate names across acts can desync a plan.
- The full ~120-file suite cannot complete inside the environment's time cap; this
  audit runs a broad blast-radius sweep covering every Series + cross-mode surface
  instead.

---

## 5. Deferred items

- **Separate Season/Episode storage hierarchy** (a real `Season`/`Episode` table
  model wired into the writing system) — **explicitly deferred**. The pre-existing
  `Season`/`Episode` tables belong to the legacy series surface and are not used by
  the universal-Manuscript Series system.
- Persistent serialized-story relation links (setup/payoff, cliffhanger/reveal,
  A/B/C thread, character-arc, contradiction, Scene→Scene / Episode→Scene /
  PSYKE→Scene) — Phase 6 detects and reports them but persists none.
- Per-block revision-candidate tables; bespoke rewrite/preview diff dialog; a
  tree/grouped (Season→Episode→Scene) dashboard tier; block-level open-in-Manuscript
  selection; a stored reflection timestamp.
- **Writers-room management, showrunner automation, production scheduling, pitch-deck
  generation, broadcaster formatting** and any **visual production** (image
  generation, ComfyUI) are **explicitly deferred and out of scope** for the
  Creative-Writing product.

---

## 6. ComfyUI / image-generation / production confirmation

Series mode is a **writing/storytelling/serial-script-health** system. Phases 1–7
introduced **no** ComfyUI module, image-generation/image-prompt action, image
model selector, render status, image preview panel, production schedule,
writers-room manager, or showrunner-automation that mutates data. The rewrite path
actively **rejects** wrong-mode (Stage cue / Graphic Novel page-panel) formatting;
the registry has no such actions. All of this remains out of scope.

---

## 7. Recommended next phase

Series mode is integrated and stable (classification **A**). Logosforge now hosts
five coherent writing modes (Novel, Screenplay, Graphic Novel, Stage Script,
Series) on one universal Manuscript + writing_mode adapter. Reasonable next
candidates (all still writing-only): export polish (broadcaster-friendly teleplay
layout / per-episode export), persistent serialized-story relation links surfaced
in Timeline/Graph, or a refreshed **global multi-mode integrity audit** that now
includes Series. A real Season/Episode storage hierarchy, visual production, and
production tooling remain deferred.
