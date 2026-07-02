# Structural Intelligence (PSYKE-Driven)

Analyzes narrative structure using PSYKE data, scenes, and outline to detect weaknesses. Fully deterministic — no AI calls.

## Data Sources

- **Scenes** — act, beat, chapter, conflict, content, sort order
- **PSYKE entries** — characters, themes, places, lore with temporal progressions
- **Narrative Dashboard** — tension curve, character presence, structure distribution, theme presence
- **Temporal Graph** — in-memory PSYKE state indexed by narrative time

## Detectors (7)

### Act Balance
Flags acts whose word count falls below 15% of the total when 3+ acts exist. Specifically flags weak middles (Act 2 < 30% in a 3-act structure).

### Arc Completion
Uses the Temporal Graph to find characters with progressions that start but never advance past their first entry. Flags incomplete arcs for non-global characters.

### Climax Preparation
Checks whether tension rises in the final third of the story. Computes a linear slope over the last-third tension scores; flags if the slope is flat or negative.

### Tension Curve
Detects flat tension across the full story. If the standard deviation of tension scores falls below a threshold, flags overall monotony.

### Theme Continuity
Flags themes that appear in fewer than 20% of scenes, or that disappear for 3+ consecutive scenes.

### Character Presence
Flags characters absent from 60%+ of scenes (excluding global entries).

### Beat Placement
Checks Save-the-Cat beats against expected position ranges. Flags beats placed outside their structural window (e.g., "Midpoint" appearing in the first quarter).

## Output

`StructuralAnalysis` — a list of `StructuralIssue` objects, each with:
- `issue_type` — detector identifier
- `severity` — 1 (critical) to 3 (advisory)
- `message` — human-readable description
- `suggestion` — actionable recommendation
- `data` — detector-specific metadata

## Integration

- **Review overlay** — top 3 issues shown in the manuscript review panel
- **AI context** — `gather_structural_context()` produces a `[STRUCTURAL ANALYSIS]` block injected into the AI prompt
- **Context hints** — top 2 issues converted to `ContextHint` objects for the proactive assistant

## Caching

`StructuralCache` with 30-second TTL and a dirty flag. The cache is invalidated when scenes are saved. Prevents recomputation on every keystroke.

## Performance

Single-pass computation via `narrative_dashboard.compute_dashboard()`. All 7 detectors run on the dashboard output. No database queries beyond the initial dashboard computation.
