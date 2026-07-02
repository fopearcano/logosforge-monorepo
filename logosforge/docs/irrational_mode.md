# IRRATIONAL Mode

A PSYKE rule-disruption engine that generates surreal narrative provocations from the Story Bible. Activated explicitly via the **"Go Irrational"** toggle — never runs unless the writer opts in.

## Purpose

Breaks temporal causality, blends unrelated entities, displaces progressions, and generates surreal prompts to push the writer past conventional narrative logic. All computation is read-only; nothing is written to the database.

## Fragment Generators (5)

### Temporal Displacement
Pulls character progressions out of timeline order. If a character has future progressions (anchored to later scenes), surfaces them in the current scene with surreal verb phrases ("remembers what hasn't happened yet", "speaks in a voice borrowed from tomorrow").

### Entity Blend
Merges two unrelated non-global PSYKE entries using templates ("Where {a} ends, {b} begins — there is no seam", "In the mirror, {a} sees only {b}").

### Arc Inversion
Inverts character or theme arcs using provocative reframings ("What if {entry} wanted the opposite of everything they've pursued?", "{entry}'s arc was never about growth — it was about beautiful unraveling").

### Temporal Echo
Cross-references other scenes in the project surreally ("This scene has already happened. The characters just don't know it yet.", "Time stutters: a moment from {scene} replays inside this one.").

### Reality Rupture
Breaks world rules using places, lore, and themes from the Story Bible ("The rules of {lore} stop working. Just here. Just now.", "{theme} stops being metaphorical and becomes literal."). Falls back to generic phrases when specific entries aren't available.

## Seeding

Deterministic output via `hashlib.md5` seeding. The same scene always produces the same fragments until the writer re-rolls. Re-rolling increments an iteration counter that produces a new seed.

## Output

`IrrationalContext` containing up to 5 `IrrationalFragment` objects. Each fragment has:
- `kind` — "displacement", "blend", "inversion", "echo", or "rupture"
- `text` — the surreal prompt text
- `source_entries` — PSYKE entry IDs that contributed

## AI Integration

`build_irrational_context()` produces an `[IRRATIONAL MODE]` block injected early in the AI prompt (after mode context, before story memory). The block instructs the assistant to weave the fragments into its response, disrupt causality, blend identities, and fracture time.

## UI

- **Toggle:** "Go Irrational" checkbox in the Assistant panel settings section
- **Styling:** Purple indicator when active
- **State:** Per-session (resets on app restart)
