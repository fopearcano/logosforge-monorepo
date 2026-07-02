# Semantic Continuity Engine (Phase 10Q)

Detects continuity problems, contradictions, missing transitions and unresolved
narrative commitments across the whole project — **deterministically, with
evidence and confidence, and without mutating content, calling an LLM, or
auto-fixing anything.** It answers: what changed? was it prepared? is character/
location/time/object continuity coherent? are setup/payoff chains alive? are
proposed rewrites introducing continuity damage? which issues come first?

## Service (`logosforge/continuity/`)

Qt-free, LLM-free, read-only by default, deterministic, current-project-only,
capped.

- `build_continuity_report(db, project_id, *, scope, scene_id, chapter_id, writing_mode, options) -> ContinuityReport`
- `check_scene_continuity(db, project_id, scene_id, *, include_previous, include_next)`
- `validate_continuity_change(db, project_id, target_type, target_id, before_text, after_text, *, writing_mode) -> ContinuityChangeValidation`
- `get_continuity_summary_for_assistant(...)`, `explain_issue`
- `get_continuity_issues(...)`, `build_continuity_decision_cards(...)`
- `persist_check_run(...)`, `set_issue_status(...)`

## Data model

Two idempotent tables (`create_all`; old DBs gain them empty):

- `ContinuityIssue` — persists **only the user's status** (dismissed / resolved /
  deferred), keyed by a stable `issue_key`. Issues themselves are **recomputed**
  each run and merged with persisted status by key (open issues come from the
  computed run).
- `ContinuityCheckRun` — a lightweight run summary (counts, scope, mode).

**Facts and states are rebuilt in-memory each run, never persisted** — no
manuscript duplication, no stale facts. Evidence stores short excerpts/refs only.

## Facts / states / issues

- **`ContinuityFact`** — `character_state, location_state, object_state,
  temporal_marker, lore_rule, motif, …` extracted from PSYKE + scene fields
  (`location`, `time_of_day`, `interior_exterior`, text mentions via the existing
  `revision_intelligence.psyke_impact` matcher).
- **`ContinuityState`** — ordered observation lists per subject (character
  presence, place occupancy). `unknown` is acceptable; sparse projects never fail.
- **`ContinuityIssueData`** — `issue_type`, `dimension`, `severity`, `confidence`,
  title, explanation, evidence, related scenes, status.

## Dimensions

`character, temporal, spatial, object, plot, lore, theme, dialogue, production,
mode_specific`. See **docs/ContinuityChecks.md** for the per-dimension catalog.

## Confidence & severity

Confidence: `confirmed / likely / possible / unknown`. Severity: `info /
suggestion / warning / blocking`. **`blocking` is reserved for confirmed
structural breaks** (e.g. a `setup_payoff_links` reference to a scene that does
not exist). Softer signals are `warning`/`suggestion` at `likely`/`possible`.
Inferred signals are **never** presented as confirmed truth, and the engine never
invents causality or contradictions.

## Detectors (deterministic, evidence-backed)

- **continuity_gap (plot, blocking/confirmed)** — dangling setup/payoff scene link.
- **unresolved_setup / payoff_without_setup (plot, possible)** — screenplay
  setup/payoff candidate analysis.
- **location_jump (spatial, suggestion/possible)** — consecutive scenes change
  explicit location with no travel cue in the later scene.
- **production_continuity_risk (production, screenplay, warning)** — scene missing
  ≥2 of slugline / INT-EXT / time-of-day.
- **state_drift (character, suggestion/possible)** — a defined character appears
  once, or a recurring character vanishes before the final ~40%.
- **continuity_gap (character, info/possible)** — a scene references no tracked
  PSYKE entry.

## Rewrite / Controlled Apply validation

`validate_continuity_change` compares before/after **(preview only — never
mutates)**: removed PSYKE references, screenplay heading/time changes, and large
text cuts → warnings + a suggested safe apply mode + follow-up checks + related
PSYKE. Apply still requires the existing Controlled Apply confirmation; if
Controlled Apply is deferred, this is a read-only warning.

## Writing-mode awareness

Novel = prose/structure/character/motif checks; Screenplay adds production-
continuity + export-aware validation; Graphic Novel / Stage / Series surface a
clean `*_continuity` deferred placeholder (no false warnings). The engine is
**not** screenplay-only — only specific detectors are mode-specific.

## Logos (deterministic, no LLM)

`Run Continuity Check`, `Check Current Scene Continuity`, `Show Continuity
Issues`, `Continuity Decision Cards` — deterministic, read-only. `Explain
Continuity Issue` is generative (advisory; never auto-fixes or dismisses).
Dismiss/resolve/defer are issue-**metadata** writes via `set_issue_status` (no
content mutation); change-validation is a service call from Controlled Apply /
Rewrite.

## Assistant context

`[Continuity]` block — only emits when there are open issues; scene-scoped when a
scene is open. Top issues with severity/confidence + "advisory only — never
auto-fix/dismiss". Capped; deterministic; no LLM/DB write during assembly; no
cross-project leak. Disable via `include_continuity_in_assistant_context`.

The Assistant **can** explain issues, propose fix options, draft a bridge/
transition if asked, and send a proposed change to Controlled Apply. It **cannot**
auto-fix, auto-apply, or silently dismiss.

## Dashboard / Decision Radar

`build_continuity_decision_cards` produces deterministic, traceable cards
(category `continuity`) ranked by severity — a dedicated feed surfaced via the
`Continuity Decision Cards` Logos action, kept separate so the core 10N radar
contract is unchanged.

## Guided Workflows

`Continuity Review` (mode-agnostic) and `Screenplay Continuity Pass` (screenplay)
guide the user through a check → review → fix → re-check loop. No automatic
mutation; fixes route through Controlled Apply; issue resolution only after the
underlying data changes or the user marks resolved.

## Graph integration

Continuity issues are consumable as data (issue → related scene/PSYKE). The
dedicated **Continuity Risk / Character State / Setup-Payoff** Graph visualization
modes are **deferred** with the Knowledge Graph UI (docs/NarrativeKnowledgeGraph.md).

## Refresh / project switch

Reads are per-`project_id`; reports rebuild on demand (no background LLM scan).
Persisted issue status + check runs are project-scoped, so no old-project issues
leak after a switch.

## Limitations & deferred

- **UI deferred** (Continuity section, Dashboard panel, Graph modes, Controlled
  Apply preview section) — the service + Logos + Assistant context are the
  current surface.
- No deep NLP: knowledge-leak, voice-drift, object-destruction-then-reuse, and
  lore-rule-violation detection are **deferred** (would need semantic inference;
  the engine refuses to hallucinate them).
- No separate timeline table — temporal checks use manuscript scene order +
  scene time markers only.
- Graphic Novel / Stage / Series continuity are deferred placeholders.

## Next recommended phase

Build the deferred **Continuity UI** (section + Dashboard panel + Controlled
Apply preview integration + Graph risk modes) on this service, and add
opt-in, user-confirmed semantic checks (voice/knowledge) routed through the
Assistant rather than auto-run.
