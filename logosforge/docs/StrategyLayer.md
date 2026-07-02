# Strategy Layer — medium-aware narrative router

The Strategy Layer (`logosforge/logos/strategy/`) is a **deterministic**
decision layer that tells Assistant and Logos which reasoning should dominate in
a given situation. It never calls an LLM to route, never mutates data, and does
**not** modify the Assistant — it only informs it.

## Inputs (all read-only)

- Project **narrative engine** (`project_compat.get_project_narrative_engine`)
- **Writing format** (`get_project_writing_format`)
- Selected **outline template** (project settings `outline_template`)
- **Go McKee** enabled (`gomckee_bridge.is_gomckee_enabled`)
- **Idea di Controllo** enabled (`controlling_idea.load(...).enabled`)
- **Quantum/Lambda** mode (`quantum_outliner.state.get_outline_mode`)
- Active **section**, and the user `strategy_user_mode_override` setting.

## Output: `StrategyDecision`

`active_strategies`, `dominant_strategy`, `suppressed_strategies`,
`included_context_blocks`, `active_diagnostics`, `recommended_logos_actions`,
`reasoning_notes`, and a human `explanation`.

## Medium profiles

Novel, Screenplay, Graphic Novel, Stage Script, Series — each declares craft
priorities, context blocks, diagnostic priorities, preferred Logos actions, and
per-principle stances (e.g. screenplay/stage/graphic-novel **suppress
interiority**; novel/series **allow** it). Missing/unknown mode → Novel default.

## Conflict resolution

Precedence (highest first):
**user override > project mode > selected template > active plugin > general.**

- A **contrast-based** template (Story Circle; future Kishotenketsu) is not
  forced into McKee-style conflict; conflict-driven templates (Three-Act, Save
  the Cat, Hero's Journey, Five-Act) keep it.
- **Lambda** mode allows superposition / alternate timelines; **Classical**
  enforces linear causality.
- Go McKee influences reasoning **only when the plugin is enabled**, and is
  suppressed when a contrast template defuses forced conflict.

## Commands & visibility

- `/strategy` or `/strategy explain` — show the active decision's explanation.
- `/strategy mode <engine>` — force a medium (`""` = auto).
- `/strategy off` / `/strategy on` — toggle the layer.
- A small **"Strategy: <name>"** indicator appears in the Logos Health drawer
  header (gated by `strategy_show_indicator`).

## Assistant integration

`strategy_context.gather_strategy_context()` returns a compact `[Strategy]`
block that a caller **may** fold into a prompt. It is intentionally **not** wired
into `AssistantPanel` — the panel stays untouched.

## Settings (defaults)

`strategy_enabled=True`, `strategy_show_indicator=True`,
`strategy_debug_explanation=False`, `strategy_user_mode_override=""`.

## Not automated / deferred

- Auto-injecting strategy into the live Assistant prompt (hook is ready).
- A dedicated Kishotenketsu template (Story Circle is the contrast-leaning
  built-in; the conflict table already lists `kishotenketsu`).
- Numeric per-page screenplay duration modeling.
