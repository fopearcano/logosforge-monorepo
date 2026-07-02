# Revision Intelligence + Change Impact Map (Phase 10K)

When a screenplay scene changes, Revision Intelligence explains the
*consequences* — which scenes, PSYKE entries, setup/payoff chains and continuity
assumptions may be affected. It is an **assisted** layer (deterministic,
confidence-aware), **not** an autonomous script doctor: nothing is rewritten or
mutated automatically.

## Confidence is explicit

Every finding carries a confidence: **confirmed** (a data-backed link exists),
**likely** (a strong heuristic match), **possible** (a weak signal), or
**unknown** (insufficient data). Inferred impact is never presented as fact.

## Layers (`logosforge/revision_intelligence/`)

- **`diff.py`** — `create_scene_diff(before, after)` → hashes, added/removed
  terms, changed lines, truncated excerpts, change size. Accent/Unicode-safe; no
  LLM/DB.
- **`psyke_impact.py`** — PSYKE entries mentioned/added/removed (name + alias
  matching, **confirmed**); relation-pulled entries (**likely**); capped.
- **`scene_impact.py`** — affected scenes: **confirmed** via StoryLinks /
  setup-payoff / same act / adjacency; **likely** via shared characters or
  location. Plus setup/payoff and lightweight continuity checks (omitted-scene,
  heading/time change) — `unknown` when data is missing.
- **`impact_map.py`** — `build_revision_impact_map(db, pid, *, scene_id,
  before_text=None, after_text=None, save_report=False, …)` combines all layers
  into a `RevisionImpactMapResult` (impact_level low/medium/high/critical,
  confidence, direct changes, impacted PSYKE/scenes, setup-payoff, continuity,
  production). **No DB mutation unless `save_report=True`**; works without a
  previous snapshot (partial map + limitation note); current project only.

## Data model

`RevisionImpactReport`, `RevisionImpactItem`, `RevisionDiffSnapshot` —
lightweight references (hashes + excerpts + metadata), **no full-manuscript
copies**. Created idempotently by `create_all` (old DBs gain empty tables).
Saving a report is explicit/user-confirmed.

## Production integration

When a production draft is active, the impact map includes the scene number and
omitted status and references the active draft. Revision Intelligence works for
spec drafts too — production mode just adds stronger context.

## Logos (deterministic, no LLM)

Generate Revision Impact Map, Check PSYKE Impact, Check Setup/Payoff Impact,
Check Continuity Impact, Check Impacted Scenes, Prepare Revision Follow-up
Checklist. Screenplay-only. **Saving a report / converting a finding to a graph
link** are explicit service calls (UI deferred).

## Assistant

`[Revision Impact]` block — summarizes the **last saved report** (cheap read; it
never recomputes a project-wide map during context assembly). Empty until a
report is saved. Capped, deterministic, no scene-body dump, no cross-project
leak, no LLM/DB.

## Narrative Health

`Revision Causality Risk` and `Continuity Revision Risk` — only when a saved
report exists; capped at *Needs Attention* (diagnostic, not story failure);
confidence shown. Novel/other modes show none.

## Optional AI enhancement

Interpreting an impact map with the Assistant/Counterpart is a **manual,
user-triggered** action through the existing provider path (no new backend, no
automatic call) — advisory only. Wiring is deferred to a future phase.

## Controlled Apply (Phase 10M)

Mutations that follow a revision/impact analysis pass through the
Controlled Apply gate (preview + conflicts + confirmation). See
**docs/ControlledApply.md**.

## Rewrite Sandbox integration (Phase 10L)

The Adaptive Rewrite Sandbox can run a Change Impact Map on a candidate
variant (`build_revision_impact_map(before=source, after=variant)`) to show
what applying it would affect. See **docs/AdaptiveRewriteSandbox.md**.

## Deferred (future)

- Revision-impact **UI** (report dialog with severity/confidence filters) and
  Graph **visualization mode** (the impact map already provides node/edge-style
  data).
- Convert-finding-to-graph-link / create-PSYKE-relation mutations (service
  hooks; confirmation UI deferred).
- Deep STAGES/versioning snapshot comparison (currently hash-based, scene-level).
- Manual AI-enhancement actions.

## Limitations

Causality is **not** perfectly detected — confirmed links are data-backed;
everything else is clearly marked likely/possible/unknown. Continuity checks use
only existing project data (no hallucinated rules). Diff and PSYKE/scene impact
are scene-level and capped.
