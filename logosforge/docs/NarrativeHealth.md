# Narrative Health Engine

`logosforge/logos/health/` turns Logos PSYKE diagnostics into an explainable,
project-level health report. Rule-based, evidence-driven, **no fake percentages**,
no background LLM, no DB mutation.

## Report

`HealthEngine.generate_report()` builds a shared `ProjectFacts` snapshot once,
runs the diagnostics, and aggregates them into one `NarrativeHealthMetric` per
category, then derives an overall status and prioritized recommendations.

### Categories (12)
Structure, Character, Relationships, Theme/Motif, Continuity, Timeline, Pacing,
Scene Purpose, Setup/Payoff, PSYKE Completeness, Graph Connectivity, Notes
Integration.

### Status labels (no scores)
`Stable` · `Needs Attention` · `Weak Area` · `Critical Risk` · **`Not Enough
Data`** (used whenever a category has no analyzable data — never a false
negative).

### Overall status
`critical` if any critical metric or ≥2 weak **core** categories
(structure/continuity/character); else `weak` / `watch` / `stable`; `unknown`
when no category has data.

## Recommendations

Deterministic, derived from important/critical diagnostics: each carries problem,
why-it-matters, evidence, a mapped **existing Logos action**, and a target. There
is no autonomous fixing — acting on a recommendation runs the Logos action
through the normal preview/confirm path.

## UI

`LogosDiagnosticsDrawer` (diagnostics) and `LogosDiagnostics`/health drawer show
status cards, top risks, strengths, and recommendations with **Ask Logos**,
**Open Target**, **Dismiss**, **Copy**, **Refresh**, and **Export JSON/MD**.
Non-modal, never steals focus, hidden by default. Dismissals share the proactive
`SuppressionStore`.

## Refresh / safety

- Current-section diagnostics rescan on section change / `project_data_changed`;
  the health report refreshes on toggle / manual refresh / project switch.
- Scans never call the LLM and never mutate the DB.
- On project switch the drawers are cleared and the engines re-pointed, so no
  stale findings from the previous project are shown.

## Assistant integration (opt-in)

`health_context.top_risks_text()` produces a compact `[Narrative Health]` block
for optional prompt inclusion (`health_include_in_assistant`, default **false**).
The Assistant is not auto-fed the report.

## Screenplay-mode categories (Phase 10C)

For projects whose writing mode is **screenplay**, the report appends mode-aware
categories computed deterministically from the screenplay diagnostics engine
(`logosforge/screenplay_diagnostics.py`): **Visual Action, Scene Economy,
Dialogue Economy, Scene Turn, Character Objective, Setup/Payoff**. Status uses the
same no-score labels; categories with no analyzable data return *Not Enough Data*.
Phase 10D additionally populates **Dialogue Subtext, Motif Recurrence** and
**On-the-Nose Dialogue Risk** from the deterministic setup/payoff + subtext
engines. Phase 10E adds **Confirmed Setup/Payoff Coverage** (confirmed
`StoryLink`s weigh more than candidates) and **Unresolved Candidate Density**
(a cautious warning, never a hard failure). Phase 10F adds **format-health**
categories — Export Readiness, Title Page Completeness, Scene Heading Integrity,
Dialogue Formatting Integrity — derived from the deterministic export validator.
These are **capped at *Needs Attention*** so a formatting issue never flips the
narrative overall status: format problems are kept distinct from craft problems. Phase 10G adds Fountain Export Readiness and Unsupported Screenplay Elements (also capped). Phase 10H adds Professional Output Readiness and FDX Compatibility Risk (FDX is a standing experimental watch). Phase 10J adds Production Draft Readiness, Scene Numbering Integrity, and Revision Set Integrity (only when production mode is active; capped — duplicate scene numbers block in the production validator, not in story health). Phase 10K adds Revision Causality Risk and Continuity Revision Risk (only when a saved impact report exists; diagnostic, capped, confidence shown).
**Cinematic Continuity** remains deferred (*Not Enough Data* — a future phase).
No fake precision, no background LLM, no DB mutation. Novel/other modes are
unaffected.

## Rewrite sandbox health (Phase 10L)

For **any** writing mode, when an open Adaptive Rewrite Sandbox session
exists, the report appends **Rewrite Continuity Risk**, **PSYKE
Preservation Risk** and **Source Staleness Risk** — capped at *Needs
Attention*. These reflect *open, unapplied* variants only; rejected/applied
variants and canonical story health are unaffected. See
**docs/AdaptiveRewriteSandbox.md**.

## Settings (defaults)

`health_enabled=True`, `health_auto_refresh_on_load=True`,
`health_include_in_assistant=False`, `health_show_unknown=True`.
