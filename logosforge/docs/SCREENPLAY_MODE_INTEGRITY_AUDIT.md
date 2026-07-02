# Screenplay Mode — Integrity Audit (Phase 9)

Branch: `claude/setup-logosforge-app-5cVxF`

Full integration audit of Screenplay Mode Phases 1–8. Goal: verify the phases
work together as one coherent system and do not break the rest of Logosforge.
Audit-first; fix only confirmed regressions / integration bugs.

## 1. Implemented phases (all present)

| Phase | Feature | Core module(s) |
|-------|---------|----------------|
| 1 | Block grammar + Fountain foundation | `screenplay.py`, `screenplay_blocks.py`, `screenplay_fountain.py` |
| 2 | Beat plan → draft preview → confirmed apply | `screenplay_pipeline.py` |
| 3 | Screenplay intelligence / scene-health checks | `screenplay_diagnostics.py` |
| 4 | Fountain export/import + interchange safety | `screenplay_interchange.py`, `export.py` |
| 5 | Counterpart / Reflection (two-stance) | `screenplay_reflection.py` |
| 6 | Controlled rewrite preview/diff/apply | `screenplay_rewrite.py`, `ui/screenplay_rewrite_dialog.py` |
| 7 | Multi-scene continuity / coherence | `screenplay_continuity.py` |
| 8 | Screenplay Review Dashboard | `screenplay_review.py`, `ui/screenplay_review_view.py` |

All mutating paths route through `controlled_apply` (preview → `confirmed=True`).
Screenplay Logos actions are mode-gated (`modes=("screenplay",)`).

## 2. What passed

- **Writing mode:** screenplay primary unit = Scene; novel = Chapter; screenplay
  Logos actions absent from Novel; beat-plan context empty for Novel.
- **Structure invariant:** Act → Chapter → Scene holds after a full screenplay
  flow (rewrite apply included); `build_structure_tree` valid; no orphans.
- **Canonical order coherence:** `canonical_scene_order`, Fountain export, Review
  Dashboard, and Continuity scene chain all agree, and all update together when a
  scene is moved.
- **No auto-mutation:** every preview/report step (beat-plan prompt, draft
  preview, health, reflection, continuity, review, export readiness, rewrite
  preview) leaves body/summary/beat-plan/PSYKE/Notes unchanged; apply requires
  `confirmed=True`; cancel/copy never mutate.
- **Project isolation (A→B→C):** screenplay body, beat plans, reflection notes,
  Timeline links, and Fountain export do not leak across projects; new projects
  start clean; returning to A restores its data.
- **Privacy:** Fountain (scene + project), Review Markdown, Continuity, and
  Reflection text never contain a planted API key / provider base URL.
- **UI routing:** Manuscript→`WritingCoreView`, Outline→`PlanView`,
  Timeline→`PlotTimelineView`, Review→`ScreenplayReviewView`; review-row
  "Open in Manuscript" navigates without mutating.
- **Novel regression:** novel writing flow intact; prose body not converted to
  screenplay blocks; screenplay editor hooks inert (`_screenplay_mode is False`).
- **Test totals (this audit):** 8 phase suites 255/255; phase10A–Q + screenplay_*
  engines 689 pass; mode/invariant/isolation/canvas/logos 122; manuscript/
  outline/timeline/autosave/editing 330; new integration suite 9/9.

## 3. What failed / bug found

**BUG (fixed): `serialize_blocks` round-trip dropped character/dialogue grouping.**
`serialize_blocks` blank-line-separated *every* block, so a character cue and its
dialogue were emitted as `MARIA\n\nThe truth.`. Re-parsing that text classified
the lone uppercase cue as an `action` line — so applying a draft (Phase 2) or a
rewrite (Phase 6), which store `serialize_blocks(...)` as the body, degraded all
dialogue/character blocks to action on the next parse. Downstream analysis
(health, reflection, continuity, dashboard) then saw **0 dialogue / 0 characters**
for a scene that clearly had them. Surfaced by the Phase 9 smoke flow.

## 4. Fixes applied

- `logosforge/screenplay_blocks.py::serialize_blocks` — keep a character cue and
  its following parentheticals/dialogue together as one blank-line-separated
  paragraph (single newlines within the group), matching the Fountain serializer.
  Round-trip is now structurally stable (`parse → serialize → parse` preserves
  block types). Action-only and orphan cases are unchanged; all existing
  `serialize_blocks` substring tests (Phase 1, 10B) still pass.

No other production change was required — every other audited behavior was already
correct.

## 5. Known non-bugs (environment / harness, not screenplay defects)

- **DOCX/PDF export tests (5: `test_phase10h` ×2, `test_phase10i` ×3)** fail with
  `ModuleNotFoundError: No module named 'docx' / 'reportlab'`. These optional
  output libraries are not installed in this environment; the export code already
  degrades gracefully (`ok=False` + clear message). PDF/DOCX are out of scope for
  the screenplay phases.
- **`test_editing_integrity::test_autosave_status_does_not_change_focus`** can fail
  only inside a large multi-suite batch (a stray focused `QPushButton` from a
  prior UI suite pollutes the shared offscreen `QApplication`). It passes in
  isolation (18/18) and is unrelated to screenplay code. Run UI suites per-file.

## 6. Remaining limitations / deferred

- PDF / DOCX / FDX output remain optional-dependency features (graceful when
  absent); deferred by design.
- Phase 5 reflections are generated on demand (not persisted) → the Review
  Dashboard shows reflection status as "Not Checked".
- Continuity does not yet persist new causal links (report-only); confirming
  candidate links remains the existing `screenplay_graph` / story-link path.
- Dashboard entry points are the Manuscript scene-menu item + the project-level
  Logos action (no dedicated sidebar button, to avoid cluttering other modes).
- Per-block (sub-scene) targeting exists in the rewrite API but has no dedicated
  block-picker UI yet (the menu targets the whole scene).

## 7. Recommended next phase

Screenplay Mode is integrated and stable. Suggested next work (new features, not
this phase): persistent causal/setup-payoff links from the Continuity report
(confirm-to-graph), and a per-block rewrite-target UI. Optionally install
`python-docx`/`reportlab` in CI to exercise the professional-output paths.

## Final classification

**A — Screenplay mode Phases 1–8 are integrated and stable.** One real
round-trip bug was found and fixed; all remaining failures are missing optional
dependencies or a known headless focus-pollution artifact, neither of which is a
screenplay integration defect.
