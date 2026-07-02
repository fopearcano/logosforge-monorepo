
# PSYKE Outline Templates

PSYKE-aware outlining plugin for Logosforge-style hosts.

## Files
- `plugin.json`
- `plugin.py`

## What it does
- Applies structure templates from classical, modern, alternative, and genre-specific writing methods
- Uses structured PSYKE story context instead of raw prose
- Annotates beats with protagonist, themes, tensions, arcs, entities, and settings
- Emits connector-friendly outline actions

## Supported methods
- hero_journey
- three_act
- freytag
- fichtean_curve
- save_the_cat
- story_circle
- seven_point
- twenty_seven_chapter
- kishotenketsu
- heroine_journey
- in_medias_res
- snowflake
- mystery
- romcom
- quest

## Minimal context example
```json
{
  "psyke_story": {
    "title": "The Glass Orchard",
    "genre": "mystery",
    "premise": "A memory archivist discovers that missing civic records may hide a living witness.",
    "protagonist": {"name": "Lena Vale"},
    "central_goal": "Find the missing witness before the archive purge completes.",
    "themes": ["memory", "truth", "institutional erasure"],
    "tensions": ["Lena vs archive administration", "truth vs safety"],
    "arcs": ["Lena moves from procedural caution to moral risk"],
    "key_entities": ["Lena Vale", "Central Archive", "Missing Witness"],
    "settings": ["Central Archive", "Sub-basement vaults"],
    "requested_method": "mystery",
    "conflict_mode": "mystery",
    "arc_mode": "procedural",
    "scope": "compact",
    "pacing": "balanced"
  }
}
```
