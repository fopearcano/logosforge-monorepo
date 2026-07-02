# Continuity Checks Reference (Phase 10Q)

The per-dimension catalog of what the Semantic Continuity Engine
(docs/SemanticContinuityEngine.md) checks today, what it defers, and the
confidence/severity it assigns. Everything is deterministic and evidence-backed;
uncertain signals are `possible`/`unknown`, never asserted as fact.

## Implemented checks

| Dimension | Issue type | Severity / confidence | What it flags |
|-----------|-----------|-----------------------|---------------|
| plot | `continuity_gap` | blocking / confirmed | `setup_payoff_links` points to a missing scene |
| plot | `unresolved_setup` | suggestion / possible | screenplay setup with no detected payoff |
| plot | `payoff_without_setup` | suggestion / possible | screenplay orphan payoff candidate |
| spatial | `location_jump` | suggestion / possible | consecutive scenes change location, no travel cue |
| production | `production_continuity_risk` | warning / likely | screenplay scene missing ≥2 of slug/INT-EXT/time |
| character | `state_drift` | suggestion / possible | character appears once, or vanishes before final act |
| character | `continuity_gap` | info / possible | scene references no tracked PSYKE entry |

## Rewrite / Controlled Apply validation

`validate_continuity_change(before, after)` (preview only) flags: removed PSYKE
references (warning), screenplay heading/time changes (warning), >50% text cut
(warning); returns a suggested safe apply mode + follow-up checks + related PSYKE.

## Confidence ladder

- `confirmed` — explicit, verifiable data (a link to a non-existent scene).
- `likely` — strong structured signal (production heading gaps).
- `possible` — heuristic signal that may be intentional (a location jump).
- `unknown` — insufficient data; surfaced as such, never as a problem.

## Severity ladder

`blocking` (confirmed structural break) → `warning` → `suggestion` → `info`.
Only confirmed breaks are blocking.

## Deferred checks (intentionally not implemented)

These require semantic inference the engine refuses to fake:

- Character **knowledge leak** (knows something before learning it).
- **Voice/register drift** in dialogue.
- **Object destroyed-then-reused**, ownership handoff.
- **Lore-rule violation** in scene text.
- **Outline↔manuscript** event contradiction beyond structure.
- **Temporal impossibility** beyond scene order (no separate timeline table).
- **Graphic Novel / Stage / Series** mode-specific continuity (clean deferred
  placeholders only).

These are candidates for an opt-in, user-confirmed, Assistant-routed pass in a
future phase — never an auto-run background scan.
