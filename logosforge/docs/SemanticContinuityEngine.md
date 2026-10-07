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
- HTTP 1.12.0 adds revision- and finding-bound transactional status commands
  plus durable receipt lookup; these wrap the same deterministic service data.

## Data model

Three idempotent tables (`create_all`; old DBs gain them empty):

- `ContinuityIssue` — persists **only the user's status** (dismissed / resolved /
  deferred), keyed by a stable `issue_key`. Issues themselves are **recomputed**
  each run and merged with persisted status by key (open issues come from the
  computed run).
- `ContinuityCheckRun` — a lightweight run summary (counts, scope, mode).
- `ContinuityCommandReceipt` — a project-scoped, SHA-256-keyed receipt for one
  exact Defer/Dismiss/Resolve command. The status write and receipt commit in the
  same immediate transaction and the receipt is deleted with the project.

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
  title, explanation, evidence, related scenes/nodes, status, and a
  `review_fingerprint` for the exact derived finding presented to the reviewer.

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
PSYKE. **Repair with Billy** now stages a bounded issue brief in the Assistant
without sending it. A verified related scene can become the proposed prose
target; without one, the handoff remains planning-only. Any generated prose
still goes through the existing Controlled Apply preview and explicit
confirmation. A review-status decision never applies a repair.

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

## Transactional review lifecycle (HTTP 1.12.0)

The Pro Continuity panel exposes Defer, Dismiss, and Resolve only for an open
issue. It rereads the current report before presenting an explicit confirmation
dialog, then sends one strict command containing the current persisted
`review_revision`, canonical issue id, and that issue's `review_fingerprint`.
The fingerprint covers the exact identity, issue type, dimension, severity,
confidence, title, explanation, suggested action, evidence, related scenes, and
related nodes. A stable logical issue key may survive derived-detail changes;
the fingerprint makes an older approval stale instead of silently carrying it
onto changed evidence.

Core rechecks revision, fingerprint, open status, and project ownership inside
the same `BEGIN IMMEDIATE` transaction that persists the new status and durable
receipt. A successful command changes only `open` to `deferred`, `dismissed`, or
`resolved`; it never edits story content or calls an LLM. Exact keyed replay is
resolved from the receipt before live-finding preflight and returns the current
coherent report plus the original applied revision without changing status
again.

The UI treats an uncertain response conservatively: it checks the same
project-scoped receipt first. A proven `continuity_receipt_not_found` permits
exactly one resend of the identical command and idempotency key. If that resend
is also ambiguous, subsequent attempts are receipt-only. An absent, malformed,
or contradictory receipt never proves that resending is safe.

## MCP gateway 1.9.0

The 46-tool Pro gateway exposes the report through
`logosforge_get_story_diagnostics` (`report: "continuity"`) and adds
`logosforge_propose_continuity_command`. Proposal creation is non-mutating and
stores the exact revision- and fingerprint-bound status command for later
review/apply. Continuity is the fourth durable receipt family alongside
Timeline, Canvas Plot, and Knowledge Graph: fresh companions can recover a
committed result, one proven family-specific miss permits one exact resend, and
unknown-id recovery fails closed if more than one family reports a receipt.
MCP can record review status, but it cannot turn that decision into a manuscript
repair.

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
(category `continuity`) ranked by severity. HTTP exposes at most eight cards as
a dedicated, failure-isolated feed so the core 10N and Knowledge Graph contracts
remain unchanged. Every card targets one canonical issue key and carries the
authoritative evidence total plus at most five issue/detail/project-owned scene
facts. The Pro Dashboard merges all three feeds under one ten-card display cap;
cards focus the exact Continuity issue and scene evidence opens the exact
Manuscript scene. Missing keys are reported as stale/resolved and consumed once.
The `Continuity Decision Cards` Logos action remains available.

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

- Defer/Dismiss/Resolve are status decisions, not manuscript repairs. There is
  no automatic fix and no status command can bypass Controlled Apply.
- Dedicated Continuity Risk / Character State / Setup-Payoff Graph modes remain
  deferred.
- No deep NLP: knowledge-leak, voice-drift, object-destruction-then-reuse, and
  lore-rule-violation detection are **deferred** (would need semantic inference;
  the engine refuses to hallucinate them).
- No separate timeline table — temporal checks use manuscript scene order +
  scene time markers only.
- Graphic Novel / Stage / Series continuity are deferred placeholders.

## Next recommended phase

Finish the real Pro workspace-shell integration for the completed Graph,
Decision Radar, and Continuity journeys: remove any preview-harness-only seams,
verify save-barrier navigation and Controlled Apply handoffs in the actual
desktop host, then run the full UI journey in packaged Windows, macOS, and Linux
builds. Dedicated Graph risk modes and opt-in semantic voice/knowledge checks
remain later work.
