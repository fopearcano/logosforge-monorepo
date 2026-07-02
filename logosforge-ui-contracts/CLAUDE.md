# CLAUDE.md — LogosForge UI Contracts (`@logosforge/ui-contracts`)

## Repo identity

The **shared TypeScript contracts** that mirror the `logosforge` core API. The
single shared language — types, event names, command/vocabulary names, route
map — that every LogosForge frontend uses to talk to the core. It is the one
thing **both product lines** (Whiteboard *and* Studio) share besides the core
itself.

## What this package owns

- DTO **types** mirrored from `logosforge.api.schemas`
- **Event** names (mirrors `logosforge.api.events`)
- **Vocabulary** enums (writing modes, PSYKE types, export types/formats)
- The **route** map (mirrors `logosforge.api.routes`)

## What this package must NOT own

- Any **logic** (no functions beyond pure type/route helpers)
- Any **React / UI** code
- Any **platform** code (no Electron, Node, browser, networking)
- An HTTP **client implementation** (that's an app/shared-ui adapter)

## Update rules

- The core is the source of truth. When `logosforge.api` changes shape, update
  `schemas` there first, then mirror it here, then update consumers.
- Keep field names identical to the Python DTOs. Additive changes preferred.
- Cascade: `logosforge core → THIS PACKAGE → whiteboard-shared-ui / pro-shared-ui → apps`.

## Forbidden actions

- Adding behaviour, UI, or platform code here.
- Letting the types drift from `logosforge.api.schemas`.
