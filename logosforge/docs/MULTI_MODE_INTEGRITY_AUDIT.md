# Logosforge — Global Multi-Mode Integrity Audit

Status: **A — Multi-mode architecture is stable; safe to start Stage Script Mode.**
Scope: Creative-Writing system only. **No ComfyUI, no image generation, no image
prompts** — confirmed across every mode module and the entire Logos registry.

This document records a global integration audit across Novel / Screenplay /
Graphic Novel and the shared subsystems (Outline / Manuscript / Timeline / Notes /
PSYKE / Assistant / Logos / Export), run after the per-mode audits (Screenplay
Phase 1–10, Graphic Novel Phase 1–8). It is audit/stabilization only: no new
features were added and no confirmed cross-mode bugs were found.

---

## 1. Implemented modes

| Mode | Primary unit | Manuscript body editor | Status |
|------|--------------|------------------------|--------|
| Novel | Chapter | Prose | Stable |
| Screenplay | Scene | Screenplay blocks | Phases 1–10, audited |
| Graphic Novel | Scene | Page/Panel script | Phases 1–8, audited |
| Stage Script | — | — | **Not implemented** (only a `writing_modes.STAGE_SCRIPT` constant + minor review/timeline scaffolding); out of scope here |

All three live modes share **one universal Manuscript** (`ui/writing_core_view.
WritingCoreView`). It routes the per-scene body editor by `writing_mode`:
`_is_screenplay_mode()` / `_is_graphic_novel_mode()` resolve through the single
source of truth (`writing_modes.get_project_writing_mode_by_id`) and set the
editor flags `_screenplay_mode` / `_graphic_novel_mode`; both False ⇒ Novel prose.

---

## 2. Universal Manuscript — confirmed

- **One section.** `WritingCoreView` is the only Manuscript view for all modes
  (verified: Novel/Screenplay/Graphic Novel all instantiate the same class). There
  is **no** separate Screenplay or Graphic Novel Manuscript section, and no
  separate Chapters/Scenes/Pages **main** section (those are deferred sub-members).
- **Mode adapter, not section identity.** The editor flags route by mode
  (Novel → `(sp=False, gn=False)`, Screenplay → `(sp=True, gn=False)`,
  Graphic Novel → `(sp=False, gn=True)` — verified). Only the editor
  area/behavior changes; the app section identity is constant.
- **Mode-aware review hook.** The Manuscript "Open Review" hook resolves to the GN
  Review Dashboard in Graphic Novel mode and the Screenplay Review Dashboard
  otherwise — without altering Novel/Screenplay behavior.

---

## 3. Canonical structure — confirmed

`Project → Act → Chapter → Scene`. Outline (`PlanView`), Manuscript, Timeline,
Continuity, Dashboards, and Export all read `story_structure.canonical_scene_order`
(never id/created order). Moving a Scene re-orders every surface and re-numbers
canonical labels — verified for all three modes. No Scene outside a Chapter, no
Chapter outside an Act.

---

## 4. What passed

- **Writing mode** is a reliable single source of truth: persists across reload,
  invalid values fall back to Novel, propagates on project switch (incl. the
  Assistant mode strip), and Assistant context reflects the current mode
  (Novel/Screenplay/Graphic).
- **Cross-mode non-contamination.** Switching a project's `writing_mode` never
  mutates `Scene.content`/`summary`; each mode's body parser is self-contained and
  lossless (prose survives GN/screenplay parsers without corruption).
- **Logos actions are mode-aware.** Novel shows no `sp_*`/`gn_*`; Screenplay shows
  `sp_*` and no `gn_*`; Graphic Novel shows `gn_*` and no `sp_*`. Deterministic
  actions never call the LLM (a boom provider proves it); mutating actions go
  through preview → confirmed apply (Controlled Apply).
- **Outline** stays the canonical planner; summaries remain planning data —
  Screenplay beat plans and GN page breakdowns read the Scene summary without
  overwriting it; prose body never overwrites the summary.
- **Timeline** lanes are independent of Acts; creating structure does not create
  lanes; linked chips use canonical numbering; events are project-bound.
- **Notes / PSYKE** are project-bound; GN/Screenplay checks never auto-create PSYKE
  entries; reports never mutate Notes/PSYKE.
- **Project isolation.** Three projects (Novel/Screenplay/Graphic Novel) keep their
  scenes, Timeline events, PSYKE entries, and Notes separate; switching shows no
  debris; a review dashboard re-points cleanly on project switch.
- **Export / privacy.** GN Markdown export, the GN Review Dashboard, and the
  Screenplay Review Dashboard exclude API keys/provider settings (sentinel never
  leaks) and use canonical order; bodies/status only.
- **No image-generation scope creep.** A code-skeleton scan of every authored GN
  module + the review view, plus a registry-wide scan of all Logos actions
  (name + label + description), finds none of: comfyui, image generation, image
  prompt, lora, render, stable diffusion, img2img, txt2img.

---

## 5. What failed / fixes applied

No confirmed cross-mode bugs were found; **no production code was changed** in this
audit. (Two test-scaffolding assertions in the new suite were corrected during
authoring — a GN dashboard sentinel and nothing in product code.)

---

## 6. Remaining limitations (documented, out of scope)

- Pre-existing, unrelated: two stale `tests/test_logos_integration.py` tests
  reference the removed `_action_buttons` button-row API (the toolbar is now an
  `_action_combo` dropdown) and fail on `HEAD` independently of any mode work; an
  `editing_integrity` cross-suite focus flake passes in isolation; optional-dep
  DOCX/PDF export tests degrade gracefully when `docx`/`reportlab` are absent.
- The full ~120-file suite cannot finish within the environment's 20-minute cap
  (heavy psyke/quantum/voice/visual suites); the audit runs a broad blast-radius
  sweep across every mode + shared subsystem instead.

---

## 7. Deferred items

- **Stage Script mode** — not implemented; only a mode constant + minor review
  scaffolding exist. Safe to begin as the next mode on the same universal
  Manuscript + writing_mode adapter pattern.
- **Canvas Plot** — the "Plot" surface is a renamed, deferred sub-member
  (`"Plot" → "Canvas Plot"`); not reintroduced as a primary plotting section.
- Persistent motif/setup-payoff relation links (GN Phase 6 reports, persists none);
  richer dedicated mode UIs.
- **Visual production** (image generation, ComfyUI, render panels, model/LoRA
  selectors) — explicitly deferred and out of scope for the Creative-Writing
  product.

---

## 8. ComfyUI / image-generation confirmation

Logosforge remains a Creative-Writing system. The multi-mode architecture
introduces **no** ComfyUI module, image-generation action/provider/setting, image
prompt generation, image model selector, LoRA field, render status, or
visual-production dock. The Graphic Novel rewrite path actively **rejects**
image-generation/ComfyUI leakage in AI output. This remains out of scope.

---

## 9. Recommendation

**Safe to start Stage Script Mode.** The universal Manuscript + `writing_mode`
adapter cleanly supports a fourth mode without a new section or storage change:
add a Stage Script body grammar (cues/dialogue/stage directions) + mode-gated
diagnostics/reflection/rewrite/continuity/review following the Screenplay and
Graphic Novel phase patterns. The canonical structure, isolation, privacy, and
no-image-generation guarantees verified here will carry over.
