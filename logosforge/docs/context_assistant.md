# Proactive Context-Aware Assistant

A lightweight heuristic engine that detects what the user is writing and surfaces non-intrusive hints. Never writes to the database — produces `ContextHint` objects for the UI.

## Detection Layers (3)

### Writing Mode Detection
Analyzes scene content to identify the dominant writing mode:

- **Dialogue-heavy** — high ratio of quoted speech lines. Hints about tension, pacing, or monotony when dialogue dominates without variation.
- **Descriptive/dense** — long passages with high adjective/adverb density. Hints about rhythm variation.
- **Short scene** — below 40 words. Hints that the scene may need development.
- **Long scene** — above 360 words. Hints about potential splitting or pacing review.

### Structural Detection
Flags missing scene metadata:

- No conflict field set
- No beat assignment
- Empty synopsis
- Missing act designation (when other scenes have acts)

### PSYKE Temporal Detection
Uses the `TemporalGraph` to detect:

- **Stale progressions** — a character present in the current scene whose last progression is 5+ scenes behind
- **Co-occurrence gaps** — two related PSYKE entries that haven't appeared together in 6+ scenes

## Rate Limiting

`HintRateLimiter` prevents the assistant from nagging:

- **Type cooldown:** 60 seconds per hint type
- **Global cooldown:** 15 seconds between any two hints
- **Deduplication:** same hint (by `dedup_key`) never shown twice per scene
- **Scene-change reset:** all cooldowns clear when the user switches scenes

## UI

`ContextHintBanner` — a non-intrusive inline widget per scene block, similar to the auto-link `SuggestionBanner`:

- Displays the hint message
- Three actions: **Apply** (accept suggestion), **Dismiss** (hide this time), **Ignore** (suppress this hint type permanently)
- Ignored hint types persist across sessions via `context_assistant_ignored` in settings

## Timing

- Triggered 2000ms after the last edit (via `QTimer`)
- Never fires during active typing
- Combines writing-mode hints with structural intelligence hints (top 2 structural issues)

## Integration

The `ContextAssistant` engine runs in `WritingCoreView._run_context_analysis()`, which is called by the debounced timer. Structural hints come from `StructuralCache` to avoid recomputation.
