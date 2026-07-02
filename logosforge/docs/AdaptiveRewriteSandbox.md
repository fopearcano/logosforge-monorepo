# Adaptive Rewrite Sandbox (Phase 10L)

An **isolated** sandbox for generating, scoring, comparing and selectively
applying rewrite variants. **The AI may propose variants; the user decides what
becomes canonical.** Canonical project content is never changed during
generation — only an explicit, confirmed `apply` mutates anything.

Writing-mode-aware (Novel / Screenplay / Graphic Novel / Stage Script / Series),
**not** screenplay-only.

## Safety model

- No auto-apply, no autonomous rewriting, no background generation/scans.
- Generation calls the **shared** Assistant backend (`assistant.chat_completion`
  via the standard provider resolver — no new backend, injectable for tests).
- Apply requires `confirm=True`, is **stale-source guarded** (blocks if the
  source changed since the variant was generated, unless `force=True`), creates a
  STAGE checkpoint when available, writes an audit record, and emits
  `project_data_changed`.
- No automatic mutation of PSYKE / Plot / Timeline / Graph / Outline / Production
  Draft.

## Data model (`models.py`, idempotent `create_all`)

`RewriteSession`, `RewriteVariant`, `RewriteApplyRecord`. Stores source
excerpt + hash and variant text + score/diagnostics JSON — **no full project
snapshots** (full versioning is left to STAGES). Old DBs gain empty tables.

## Components (`logosforge/rewrite_sandbox/`)

- **`strategies.py`** — data-driven, mode-aware strategies (general + per-mode);
  `strategies_for_mode` filters; strategies never change the writing mode.
- **`prompt_builder.py`** — capped system/user prompt + medium constraints +
  optional PSYKE context; **language-preserving**; no full project dump/leak.
- **`scoring.py`** — deterministic score (length/sentence/paragraph/dialogue
  deltas, reading-time delta, PSYKE preserved/removed/added via the 10K detector,
  screenplay format warnings). **No LLM.**
- **`engine.py`** — `create_rewrite_session`, `generate_rewrite_variant` /
  `generate_multiple_variants` (no canonical mutation), `score_rewrite_variant`,
  `apply_rewrite_variant` (confirmed + stale-guarded + checkpoint + event),
  `is_source_stale`, `session_status`, `rewrite_health_metrics`. Handles provider
  errors / timeouts / empty output / empty source.

## Revision Impact integration

A variant can be analyzed with the Phase 10K Change Impact Map
(`build_revision_impact_map(before=source, after=variant)`) on demand; the
report id can be attached to the variant. Unavailable → clean deferred status.

## STAGES / versioning

`apply` creates a Stage checkpoint when `create_stage` exists (rollback via the
existing system); generation never checkpoints or autosaves canonical content.

## Logos (deterministic, no LLM)

`Rewrite Sandbox` (status), `Explain Rewrite Tradeoffs`, `Score Rewrite
Variants`, `Check PSYKE Preservation` — **mode-agnostic** (available in all
modes). `Suggest Rewrite Strategy` is generative (advisory, explicit). Full
generation + apply use the engine API (UI deferred).

## Assistant context

`[Rewrite Sandbox]` block — emitted **only when an open session exists**;
summarizes source type, variant count, preferred variant, staleness and PSYKE
removals. Capped; never dumps variant text; no LLM/DB; no cross-project leak.

## Narrative Health

`Rewrite Continuity Risk`, `PSYKE Preservation Risk`, `Source Staleness Risk` —
from **open sessions only**, capped at *Needs Attention*. Rejected/applied
variants don't affect these; canonical story health is unaffected by open
variants.

## Controlled Apply integration (Phase 10M)

Applying a variant routes through the Controlled Apply service
(`apply_operation`): diff + conflict detection (stale source blocks) +
STAGE checkpoint + `project_data_changed`, and records a
`ControlledApplyOperation`. Generation stays isolated. See
**docs/ControlledApply.md**.

## Deferred (future)

- Sandbox **UI** (side/bottom panel, variant cards, compare/diff view, apply
  confirmation dialog) — engine API + Logos status shipped.
- Counterpart critique wiring (hook present via the shared backend).
- Partial / merge apply (current apply modes: replace scene; outline/PSYKE/note
  apply deferred), manual AI scoring action, multi-variant batch UI.

## Limitations

Apply currently targets scene/manuscript sources (replace); other source types
report a clean "deferred". Diff/compare is deterministic and term-level. No UI
yet — the sandbox is driven by the engine API + Logos status actions +
`[Rewrite Sandbox]` Assistant context.
