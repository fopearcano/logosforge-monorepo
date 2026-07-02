# Stage Script Mode — Integrity Audit (Phase 8)

Status: **A — Phases 1–7 are integrated and stable.**
Scope: writing/storytelling/script-health only. **No ComfyUI, no image generation,
no production scheduling, no rehearsal management, no stage-diagram rendering, no
lighting-board integration** — confirmed across every module and the Logos registry.

This document records a full integration audit of Stage Script mode after Phases
1–7. It is audit/stabilization only: no new features were added, and no confirmed
bugs were found that required a fix.

---

## 1. Implemented phases

All built on the **universal Manuscript** architecture — a Stage Script Scene's
body *is* `Scene.content` (flat text parsed into ordered, typed stage blocks). No
schema change, no parallel storage, no separate Manuscript section.

| Phase | Module | What it does |
|------|--------|--------------|
| 1 | `stage_script_blocks.py` | Stage-play block adapter (`StageScript`/`StageBlock`, parse/serialize, validate, export) over `Scene.content` |
| 2 | `stage_script_pipeline.py` | Outline summary → Stage Beat Plan → Blocking/Cue Plan → draft preview → **confirmed** apply (settings-stored plans; apply via Controlled Apply, `target_type="scene"`) |
| 3 | `stage_script_diagnostics.py` | Deterministic stage-script health checks (8 categories) + the `stage_check` Logos action |
| 4 | `stage_script_reflection.py` | Counterpart / Reflection (Audience / Actor / Director / Dramaturg) + `stage_reflection` |
| 5 | `stage_script_rewrite.py` | Controlled rewrite: targeted preview → diff → **confirmed** apply; selection/block/scene targets; generative `stage_*` rewrite actions (preview only) |
| 6 | `stage_script_continuity.py` | Cross-scene continuity (entrance/exit, blocking, props/set, cues, setup/payoff, Timeline, PSYKE) + `stage_continuity_check` |
| 7 | `stage_script_dashboard.py` + `ui/stage_script_review_view.py` | Project Review Dashboard (cards/table/filters/navigation/copy); `stage_review_dashboard` |

The **legacy project-level stage engine** (`stage_script_plot.py`,
`stage_script_review.py`, `stages.py` + tests) is a **distinct surface** and was
intentionally left untouched.

---

## 2. What passed

**Writing mode.** Stage Script projects resolve to `stage_script`
(`writing_modes.get_project_writing_mode_by_id`); Novel/Screenplay/Graphic Novel
are unaffected. Every Stage Script Logos action is `modes=("stage_script",)`; none
leak into the other modes (`available_actions` excludes `stage_*` there — verified).
The Manuscript review hook is mode-aware (Stage Script → the Stage Script
dashboard) without changing other modes.

**Universal Manuscript.** One `WritingCoreView`; a stage project shows neither
screenplay-only nor graphic-novel-only controls (both editor flags False) and
applies the existing `STAGE_SCRIPT` writing format. No separate Stage Manuscript
section; primary unit = Scene. Beat plan / blocking-cue plan / reflection reports
are stored/served separately and never become the body (verified by the smoke
flow).

**Structure invariant.** Act → Chapter → Scene preserved; the continuity report,
dashboard, and export all read `story_structure.canonical_scene_order` (never
id/created order). Moving a Scene re-orders every surface and re-numbers canonical
labels (verified across surfaces).

**No auto-mutation.** Beat/blocking/draft **previews**, health, reflection,
continuity, and dashboard never mutate the body; rewrite/draft apply require
`confirmed=True` and go through Controlled Apply (STAGE checkpoint +
`project_data_changed`), touching only `Scene.content` and preserving Outline
summary, beat plan, blocking/cue plan, Timeline, PSYKE, and Notes.

**Project isolation.** Blocks, beat/blocking plans, continuity, dashboard, PSYKE,
and export are project-scoped; switching projects shows no debris and a new
project has none (sentinel-string isolation test passes).

**Export / privacy.** `export_*_markdown` and the dashboard/continuity reports are
body/status only — no API keys, provider settings, or system prompts (sentinel
`SECRET_KEY_SENTINEL` never appears).

**No scope creep.** A code-skeleton scan (identifiers/imports, excluding
docstrings) of all seven authored modules + the review view finds **none** of:
comfyui, image generation, image prompt, lora, render, stable diffusion, img2img,
txt2img, rehearsal, production schedule, lighting board, stage diagram. The Logos
registry contains no image-generation or production-management action.

**Novel / Screenplay / Graphic Novel regression.** Novel prose flow intact;
Screenplay blocks/Fountain/diagnostics/rewrite/dashboard and Graphic Novel
pages/panels/checks/dashboard all still resolve as their mode-gated actions.

---

## 3. What failed / fixes applied

No confirmed integration bugs were found during this audit; **no production code
was changed** in Phase 8. (During Phase 4 authoring, the dialogue "stated, not
staged" heuristic was given its own first-person feeling vocabulary rather than
the third-person Phase 3 set — noted here for completeness; it predates this audit.)

---

## 4. Remaining limitations (documented, out of scope)

- Pre-existing, unrelated: two stale `tests/test_logos_integration.py` tests
  reference the removed `_action_buttons` button-row API (the toolbar is now an
  `_action_combo` dropdown); they fail on `HEAD` independently of Stage Script
  work. An `editing_integrity` cross-suite focus flake passes in isolation;
  optional-dependency DOCX/PDF export tests degrade gracefully.
- The full ~120-file suite can't complete inside the environment's 20-minute cap
  (heavy psyke/quantum/voice/visual suites); the audit runs a broad blast-radius
  sweep covering every Stage Script + cross-mode surface instead.
- Heuristics are conservative, rule-based string checks (no NLP) — directional
  craft signals, not authoritative. "Selected text" rewrite is best-effort;
  block/scene are the structured paths.

---

## 5. Deferred items

- Persistent theatrical relation links (setup/payoff, prop/cue/entrance-exit
  continuity, Scene→Scene) — Phase 6 detects and reports them but persists none.
- Per-perspective Logos sub-actions; bespoke rewrite/preview dialog; per-block
  revision-candidate table; open-in-Manuscript block-level selection.
- **Production tooling** (rehearsal management, production scheduling, stage-diagram
  rendering, lighting-board integration) and any **visual production** (image
  generation, ComfyUI) are **explicitly deferred and out of scope** for the
  Creative-Writing product.

---

## 6. ComfyUI / image-generation / production confirmation

Stage Script mode is a **writing/storytelling/script-health** system. Phases 1–7
introduced **no** ComfyUI module, image-generation/image-prompt action, image
model selector, render status, image preview panel, production schedule, rehearsal
manager, stage-diagram renderer, or lighting-board integration. The rewrite path
actively **rejects** screenplay-formatting leakage; the registry has no such
actions. All of this remains out of scope.

---

## 7. Recommended next phase

Stage Script mode is integrated and stable (classification **A**). Logosforge now
hosts four coherent writing modes (Novel, Screenplay, Graphic Novel, Stage Script)
on one universal Manuscript + writing_mode adapter. Reasonable next candidates
(all still writing-only): a refreshed **global multi-mode integrity audit** that
now includes Stage Script; export polish (theatre-friendly script layout / page
breaks for stage); or persistent setup/payoff & cue/prop continuity links surfaced
in Timeline/Graph. Visual production and production tooling remain deferred.
