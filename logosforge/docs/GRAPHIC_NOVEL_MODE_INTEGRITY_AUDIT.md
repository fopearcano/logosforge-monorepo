# Graphic Novel Mode — Integrity Audit (Phase 8)

Status: **A — Phases 1–7 are integrated and stable.**
Scope: writing/storytelling/script-health only. **No ComfyUI, no image generation,
no image-prompt generation** — confirmed across every module and the Logos registry.

This document records a full integration audit of Graphic Novel mode after Phases
1–7. It is audit/stabilization only: no new features were added, and no confirmed
bugs were found that required a fix.

---

## 1. Implemented phases

All built on the **universal Manuscript** architecture — a Graphic Novel Scene's
body *is* `Scene.content` (flat text parsed into a Page/Panel script). No schema
change, no parallel storage, no separate Manuscript section.

| Phase | Module | What it does |
|------|--------|--------------|
| 1 | `graphic_novel_blocks.py` | `Page`/`Panel`/`GraphicNovelScript`, parse/serialize over `Scene.content`, validation, Markdown export |
| 2 | `graphic_novel_pipeline.py` | Outline summary → page breakdown → panel plan → draft preview → **confirmed** apply (settings-stored plans; apply via Controlled Apply, `target_type="scene"`) |
| 3 | `graphic_novel_diagnostics.py` | Deterministic page/panel health checks (7 categories) + `gn_scene_health` Logos action |
| 4 | `graphic_novel_reflection.py` | Counterpart / Reflection (Reader / Artist / Story / Dialogue lenses) + `gn_reflection` |
| 5 | `graphic_novel_rewrite.py` | Controlled rewrite: targeted preview → diff → **confirmed** apply; panel/page/scene/selection targets; generative `gn_rewrite_*` actions (preview only) |
| 6 | `graphic_novel_continuity.py` | Cross-scene visual continuity / page-flow / motif / setup-payoff / Timeline / PSYKE; `gn_continuity_check` |
| 7 | `graphic_novel_dashboard.py` + `ui/graphic_novel_review_view.py` | Project Review Dashboard (cards/table/filters/navigation/copy); `gn_review_dashboard` |

The **legacy project-level GN engine** modules (`graphic_novel_review.py`,
`graphic_novel_plot.py`, `graphic_novel_ai_export.py`, `graphic_novel_manuscript.py`
— the separate Pages/Panels board keyed on `db.get_gn_pages`) are a **distinct
surface** and were intentionally left untouched.

---

## 2. What passed

**Writing mode.** GN projects resolve to `graphic_novel` (`writing_modes.
get_project_writing_mode_by_id`); Novel/Screenplay are unaffected. Every GN Logos
action is `modes=("graphic_novel",)`; none leak into Novel/Screenplay
(`available_actions` excludes `gn_*` there — verified). The Manuscript review hook
is mode-aware (GN → GN dashboard, otherwise Screenplay review) without changing
Novel/Screenplay behavior.

**Universal Manuscript.** One `WritingCoreView`; GN adapts via the page/panel body
grammar. No separate GN Manuscript section; page breakdown / panel plan /
reflection reports are stored/served separately and never become the body
(verified by the smoke flow).

**Structure invariant.** Act → Chapter → Scene preserved; the continuity report,
dashboard, and export all read `story_structure.canonical_scene_order` (never
id/created order). Moving a Scene re-orders Manuscript/Dashboard/Continuity/Export
and re-numbers canonical labels (verified across surfaces).

**No auto-mutation.** Breakdown/plan/draft **previews**, health, reflection,
continuity, and dashboard never mutate the body; rewrite/draft apply require
`confirmed=True` and go through Controlled Apply (STAGE checkpoint +
`project_data_changed`), touching only `Scene.content` and preserving Outline
summary, breakdown, plan, Timeline, PSYKE, and Notes.

**Project isolation.** Pages/panels, breakdown, plan, continuity, dashboard,
PSYKE, and export are project-scoped; switching projects shows no debris and a new
project has none (sentinel-string isolation test passes).

**Export / privacy.** `export_*_markdown` and the dashboard/continuity reports are
body/status only — no API keys, provider settings, system prompts, or
image-generation data (sentinel `SECRET_KEY_SENTINEL` never appears).

**No image-generation scope creep.** A code-skeleton scan (identifiers/imports,
excluding docstrings) of all seven authored modules + the review view finds **none**
of: comfyui, image generation, image prompt, lora, render, stable diffusion,
img2img, txt2img, diffusion model. The Logos registry contains no image-gen
action, and no GN report text mentions render/image workflows.

**Novel / Screenplay regression.** Novel prose flow intact; Screenplay blocks,
Fountain interchange, diagnostics, rewrite, continuity, and review dashboard all
still resolve as `sp_*` mode-gated actions.

---

## 3. What failed / fixes applied

No confirmed integration bugs were found during this audit; **no production code
was changed** in Phase 8. (During Phase 7 one wrong import —
`_psyke_character_map` imported from `graphic_novel_diagnostics` instead of
`screenplay_diagnostics` — was caught and fixed before commit; it is noted here
for completeness.)

---

## 4. Remaining limitations (documented, out of scope)

- **Pre-existing, unrelated:** two stale tests in `tests/test_logos_integration.py`
  reference the removed `_action_buttons` button-row API (the toolbar is now a
  `_action_combo` dropdown). They fail on `HEAD` independently of Graphic Novel
  work and are out of scope for this audit.
- A cross-suite focus-pollution flake in `test_editing_integrity` passes in
  isolation; optional-dependency DOCX/PDF export tests degrade gracefully when
  `docx`/`reportlab` are absent.
- The full ~120-file test suite cannot complete inside the environment's 20-minute
  cap (heavy psyke/quantum/voice/visual suites); the audit runs a broad
  blast-radius sweep covering every Graphic Novel + cross-mode surface instead.
- "Selected text" (arbitrary, non-panel) rewrite is best-effort string surgery;
  panel/page/scene are the structured paths. Cross-scene heuristics
  (motif/bridge/place-change) are conservative, rule-based signals (no NLP).

---

## 5. Deferred items

- Persistent visual-motif / setup-payoff **relation links** (Scene→Scene,
  motif/echo/contrast) — Phase 6 detects and reports them but persists none.
- Per-perspective Logos sub-actions and a bespoke GN rewrite/preview dialog and
  per-panel revision-candidate table — the headless preview/apply APIs are
  complete; richer dedicated UI is a follow-up.
- Any **visual-production** surface (image generation, ComfyUI, render panels,
  model/LoRA selectors) is **explicitly deferred and out of scope** for the
  Creative-Writing product.

---

## 6. ComfyUI / image-generation confirmation

Graphic Novel mode is a **writing/storytelling/script-health** system. Phases 1–7
introduced **no** ComfyUI module, image-generation action, image-prompt
generation, image model selector, LoRA field, render status, image preview panel,
or visual-production dock. Validation in the rewrite path actively **rejects**
image-generation/ComfyUI leakage in AI output. This remains out of scope.

---

## 7. Recommended next phase

Graphic Novel mode is integrated and stable (classification **A**) and ready for a
new implementation phase. Reasonable next candidates (all still writing-only):
export polish (PDF/EPUB script layout, lettering-friendly text export), persistent
setup/payoff & motif relation links surfaced in Timeline/Graph, or a richer
in-Manuscript review/reflection drawer. Visual production remains deferred.
