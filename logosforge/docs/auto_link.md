# Auto-Link (Manuscript ↔ PSYKE)

A non-intrusive suggestion layer that connects the prose in the manuscript editor to the Story Bible (PSYKE).

Core principle: **suggest, never auto-commit.** Auto-link proposes; the writer decides.

## What it detects

`logosforge/auto_link.py` scans the manuscript text per scene and produces four kinds of `Suggestion`:

| Kind       | Trigger                                                                                      | Example                                          |
|------------|----------------------------------------------------------------------------------------------|--------------------------------------------------|
| `create`   | A 1–3-word capitalized token that occurs ≥ 2 times across the project and is not a stop word | "Aragorn rode north. Aragorn was weary." → create `Aragorn` |
| `alias`    | A recurring token whose first 3 letters match an existing entry, or a single-letter initial  | "Cap" while `Captain` exists → add alias         |
| `relation` | Two known PSYKE entries co-occur in a scene and are not already related                      | Alice + Bob appear together → propose relation   |
| `memory`   | A state-verb sentence mentions a known entity                                                | "Alice realized the truth." → progression candidate |

State verbs include: *became, felt, realized, discovered, learned, decided, swore, vowed, understood, accepted, regretted, forgave, betrayed, chose*.

Stop words filter out obvious non-entities (pronouns, articles, days/months, honorifics, *Chapter*, *Scene*, *Act*, *Part*).

## The UI flow

1. After the debounced auto-save fires (1500 ms idle), `AutoLinkSuggester.suggest_for_project` runs.
2. Each scene gets at most **one** inline `SuggestionBanner`, so the editor never feels noisy.
3. The banner offers three actions:
   - **Accept** — opens the right flow (see below), then PSYKE is updated and the banner refreshes.
   - **Dismiss** — hides this suggestion for the session.
   - **Ignore** — persists the suggestion's stable `entity_key` to `~/.logosforge/settings.json` under `"auto_link_ignored"` so it never returns.

### Accept flows

- `create` → opens `PsykeQuickCreateDialog` prefilled with the detected name.
- `alias` → appends the token to the existing entry's comma-separated `aliases`.
- `relation` → calls `db.add_psyke_relation(a_id, b_id)`.
- `memory` → creates a `PsykeProgression` anchored to the current scene with the state-verb sentence as text.

After any accept, the PSYKE term map refreshes in place and suggestions are recomputed — newly-created entries immediately highlight in the prose.

## Safety rules

- No PSYKE write happens without an explicit click.
- No suggestion ever replaces scene text.
- Per-scene limit (default 1) prevents banner pile-ups.
- Ignored suggestions persist across sessions via their stable `entity_key`.
- A running ignore list on the suggester prevents re-surfacing within a session.

## Extending

To add a new suggestion kind:

1. Add a branch in `AutoLinkSuggester._suggest_*` that emits `Suggestion(kind="your_kind", …)`.
2. Give it an icon in `SuggestionBanner._ICON_FOR_KIND`.
3. Add an accept handler in `WritingCoreView` wired to `banner.accepted`.
4. Extend the `Suggestion.entity_key` rule if it needs per-item ignore memory.
