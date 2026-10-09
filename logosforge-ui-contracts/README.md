# @logosforge/ui-contracts

The **shared language** between the LogosForge Python core and every frontend
(Whiteboard + Studio, desktop + web). It contains **only**:

- **`types.ts`** — DTO interfaces mirrored 1:1 from `logosforge.api.schemas`.
- **`events.ts`** — change-event names + the `EventMessage` shape.
- **`commands.ts`** — stable vocabulary enums (writing modes, PSYKE types,
  export types/formats).
- **`routes.ts`** — the `/api` route map.

The current mirrored HTTP contract is **1.17.0**. Phase 7F adds canonical,
revisioned Progressions snapshots, eight track/beat commands, durable
idempotency receipts, and the `progressions_changed` event. Track DTOs expose
their required `legacy_compatibility` provenance so migrated per-entry PSYKE
tracks remain lossless without weakening ordinary create/update invariants.
Phase 7D's opaque broker-instance token and bounded-ring reset signal remain in
polling so transport replacement or cursor truncation forces authoritative
resource reconciliation. The coherent Timeline
snapshot now includes a story-flow curve aligned 1:1 with its active events,
contiguous pacing warnings, and a required narrative-mode projection for
Novel, Screenplay, Graphic Novel, Stage Script, or Series projects. The
transactional command and durable receipt vocabulary remains unchanged from
1.14.0; Progressions follows the same crash/retry discipline under 1.17.0.

`TimelineSnapshotDTO.story_flow.points` has exactly the same scene ids and
one-based order as `events`; warning spans name contiguous point ranges.
`mode_projection` is a required `kind`-discriminated union. Screenplay and
Stage Script scene rows align with active events, Graphic Novel page turns
reference returned pages, and Series scene/episode/arc references remain
project-scoped. Consumers should switch exhaustively on `kind` rather than
inferring the narrative mode from optional fields.

No logic, no React, no platform code. Every UI package depends on this so all
frontends speak the same shapes; the core is the source of truth and these stay
in sync with `logosforge.api`.

> When the core API contract changes, update `logosforge.api.schemas` first,
> then this package, then the UI packages that consume it.
