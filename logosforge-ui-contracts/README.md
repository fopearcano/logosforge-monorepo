# @logosforge/ui-contracts

The **shared language** between the LogosForge Python core and every frontend
(Whiteboard + Studio, desktop + web). It contains **only**:

- **`types.ts`** — DTO interfaces mirrored 1:1 from `logosforge.api.schemas`.
- **`events.ts`** — change-event names + the `EventMessage` shape.
- **`commands.ts`** — stable vocabulary enums (writing modes, PSYKE types,
  export types/formats).
- **`routes.ts`** — the `/api` route map.

The current mirrored HTTP contract is **1.13.0**. It adds the complete Guided
Workflows / Project OS surface: templates and deterministic recommendations,
revisioned run and audit-event reads, atomic lifecycle commands, durable
idempotency receipts, and the `workflow_changed` project event.

No logic, no React, no platform code. Every UI package depends on this so all
frontends speak the same shapes; the core is the source of truth and these stay
in sync with `logosforge.api`.

> When the core API contract changes, update `logosforge.api.schemas` first,
> then this package, then the UI packages that consume it.
