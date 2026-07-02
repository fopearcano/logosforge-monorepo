# Narrative Dashboard

Visual story intelligence at a glance. The Narrative Dashboard renders four synchronized panels from a single read-only pass over scenes and PSYKE entries.

Opens from the sidebar (`Narrative`) or via the dashboard view. Clicking a scene in any panel navigates to that scene in the editor.

## Panels

### 1. Tension Curve

A polyline with filled area showing a per-scene tension score from 0 to 100.

**Score formula** — four signals, each capped at 25 points:

```
score =  min(characters_present / 4, 1) * 25
       + min(relation_pairs     / 3, 1) * 25
       + min(keyword_hits       / 5, 1) * 25
       + min(progression_count  / 3, 1) * 25
```

- **characters_present** — count of PSYKE characters mentioned in the scene text
- **relation_pairs** — how many co-present character pairs are linked in PSYKE relations
- **keyword_hits** — occurrences of ~50 curated conflict/emotion keywords (fight, betray, reveal, death, escape, rage, sacrifice, …)
- **progression_count** — number of PSYKE progression entries anchored to the scene

**Flags raised**
- *Flat section* — three consecutive scenes within 5 points
- *Spike at scene N* — scene whose score is >30 points above both neighbours
- *Weak buildup in first third* — average of first third < 20

Hover shows the full breakdown; click opens the scene.

### 2. Character Presence

One horizontal strip per PSYKE character. A dot appears at each scene where the character is mentioned (by name or alias).

- Click a character name to toggle that strip's visibility.
- *Over-dominant* flag when a character appears in >80% of scenes.
- *Absent for N consecutive scenes* flag when N ≥ 3.

### 3. Act / Structure Distribution

A single segmented horizontal bar. Segment width is proportional to word count.

- Uses `scene.act` labels when any scene has one.
- Otherwise falls back to an inferred **25% / 50% / 25%** three-act split.
- *Weak section* flag when a segment's word count < 30% of the average.
- *Weak middle* flag when the middle segment is < 40% of the average of the others.

### 4. Theme Continuity

Bar-style presence map for each PSYKE theme, analogous to Character Presence.

- *Underused* flag when the theme appears in fewer than 20% of scenes.
- *Disappears for N scenes* flag when N ≥ 3.

## Data flow

`logosforge/narrative_dashboard.py` exposes a single entry point:

```python
data = compute_dashboard(db, project_id)
# NarrativeDashboardData(
#   tension: TensionCurve,
#   characters: list[CharacterPresence],
#   structure: StructureDistribution,
#   themes: list[ThemePresence],
# )
```

Computation is pure, deterministic, and makes **no AI calls**. The same text-scan pass builds a `scene_id -> set[entry_id]` presence index that feeds all four panels, so presence is consistent across views.

## Integration

- Flags surface at the top of the view as a compact summary (top 10), and inline per-panel.
- The view accepts an `on_scene_selected(scene_id)` callback for click-to-navigate.
- `refresh()` recomputes when the underlying project changes.

## Design constraints

- Minimal dependencies — all rendering is `QPainter` on top of `QWidget`, no external chart library.
- Soft colour palette, consistent 0–100 scale across tension.
- Non-intrusive — the dashboard is an optional sidebar view; no other view requires it.
- Read-only — nothing is written back to the database.
