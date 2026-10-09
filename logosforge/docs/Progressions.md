# Progressions

Progressions are the canonical way to model change across a LogosForge project.
They are separate from the manuscript hierarchy: a track describes one arc and
its ordered beats describe how that arc advances.

## Track kinds

| Kind | Subject rule | Typical use |
| --- | --- | --- |
| `story` | no PSYKE subject | the main narrative or a major plot arc |
| `character` | one Character entry | a character's internal or external arc |
| `relationship` | two distinct PSYKE entries | how a relationship changes |
| `theme` | one Theme entry | development of an idea or argument |
| `world` | one Place, Object, or Lore entry | change in the setting or its systems |
| `custom` | no PSYKE subject | any writer-defined progression |

Tracks and their beats have explicit dense ordering. Reordering is
transactional and requires the complete set of current ids, which prevents a
stale client from silently dropping or duplicating material.

## Anchors and coverage

A beat can be unanchored, anchored to a Pro scene, or anchored to a Whiteboard
manuscript block. Whiteboard uses the persisted block UUID as `anchor_ref`, not
the block's current index or text. Editing or moving that block therefore keeps
the anchor stable. If a referenced block is missing, Whiteboard resolves it
against the open manuscript and shows it as missing; LogosForge does not guess
another target. Drafter pages are useful working material but are not canonical
manuscript anchors.

The Core API's coverage is structural anchor coverage: it counts a valid scene
target or a syntactically valid document-block reference. Core cannot inspect a
Whiteboard document file, so Whiteboard also shows local resolved coverage using
the current manuscript's block IDs. Both answer "where has this arc been
placed?", not "how good or complete is this story?". The API also reports
scene/document totals and scene beats whose anchor order differs from their
track order.

## Concurrency and recovery

`GET /api/projects/{project_id}/progressions` returns the complete snapshot and
revision. All eight mutations go through
`POST /api/projects/{project_id}/progressions/commands` with that exact
`expected_revision`. Core performs the revision check, validation, and mutation
in one SQLite transaction.

Apply clients should supply a stable `Idempotency-Key`. Core stores a durable
receipt with the request digest and original outcome. After a lost response, a
client can look up `/progressions/command-receipt` with the same key and recover
the result without guessing whether a retry is safe. Reusing a key for a
different request fails closed.

## Product behavior

- Pro exposes the full Progressions workspace as a detachable panel, with
  scene-axis coverage and links to the relevant manuscript and PSYKE records.
- Whiteboard exposes a compact editor inside PSYKE and anchors beats to stable
  manuscript blocks.
- LittleBoy and Logos receive a bounded, project-scoped Progressions summary so
  the model can reason about current arcs without loading every beat into the
  context window.
- The local MCP server exposes `logosforge_get_progressions` and
  `logosforge_propose_progression_command`; proposal review remains separate
  from `logosforge_apply_proposal`.
- Whiteboard exports canonical `project.progression_tracks` in its one-way
  `.lfbundle`. Pro remaps PSYKE ids and uniquely matched scene titles during
  import while preserving document-block anchors when no safe scene mapping
  exists.

## Legacy compatibility

The older `PsykeProgression` surface is retained as a compatibility projection.
Database migration moves those rows into designated canonical tracks while
preserving identifiers, and legacy reads/writes continue to operate through
the canonical store. New UI, integration, and agent work should use the
revisioned Progressions API instead.

## Knowledge Graph and Decision Radar

The Narrative Knowledge Graph reads one canonical Progressions snapshot per
build. Designated legacy compatibility tracks keep their established confirmed
PSYKE-to-scene `appears_in` edge and are not emitted again as native nodes.
Every native track instead becomes a focusable `progression_track` node and
each included beat becomes a `progression_beat` node:

- a track `belongs_to` its project and `relates_to` its declared PSYKE subject
  or subjects;
- a beat `belongs_to` its track, and adjacent beats are joined by confirmed
  `precedes` edges that describe track order only;
- an explicitly scene-anchored beat `advances_in` that scene; typed character,
  relationship, theme, and world subjects receive the same confirmed
  `advances_in` evidence;
- document-block and unanchored beats remain visible through their nodes,
  metadata, membership, and order, but Core never guesses a scene for them;
- subjectless story/custom tracks never count as PSYKE scene coverage.

Projection is deterministic and bounded to 100 native tracks and 400 native
beats. Canonical order is retained; when more than 100 tracks exist, the first
affected track for each Radar issue class is guaranteed a focusable slot, with
later ordinary tracks omitted before those diagnostic targets. A warning
records either cap. A bounded internal diagnostic summary retains authoritative
full-snapshot issue totals even when track or beat-node projection is capped.

Decision Radar contributes at most one aggregated card for each actionable
issue class: empty native tracks, truly unanchored beats, and scene anchors
whose order moves backward. Cards report the authoritative total across all
affected native tracks, include at most five exact track/beat evidence records,
and deep-link to the first affected track. Valid Whiteboard document-block
anchors are not reported as unanchored.
