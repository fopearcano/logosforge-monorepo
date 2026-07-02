# CLAUDE.md — LogosForge Core (`fopearcano/logosforge`)

> Canonical template:
> `fopearcano/logosforge-architecture` → `repo-templates/logosforge/CLAUDE.md`.
> If this file ever disagrees with the architecture repo, the architecture
> repo wins.

## Repo identity

This repo is the **canonical Python core of LogosForge — and the existing
Python app**. It is the single source of truth for all core behavior and
data.

**Status: real alpha.** This is one of only two LogosForge repos containing
real application code (the other is the Free Whiteboard Electron alpha,
`logosforge-desktop`). In the target architecture, every LogosForge product
(Whiteboard and Studio, desktop and web) will be built over this core
through its API layer — today those shared packages and extra apps are
future scaffolds.

## What this repo owns

- Python core logic — and the existing Python app
- Project logic and data models
- PSYKE logic
- Assistant logic
- Import/export logic
- API/backend logic — the API layer frontends consume (and will consume)

## What this repo must NOT own

- **React or any visual UI** — no components, no styling, no frontend assets
- **Electron packaging** — no main/renderer/preload code, no desktop shells
- **Web cloud deployment** — no hosting config, auth, or cloud storage for
  frontends
- TypeScript contracts — those live in `logosforge-ui-contracts`, mirroring
  this repo's API
- Anything specific to the Whiteboard or Studio visual identity

**Frontend changes belong elsewhere.** If a task is about how something looks
or behaves in a UI, stop: route it to the owning repo via the repo map in
`fopearcano/logosforge-architecture` (`docs/REPO_MAP.md`).

## Dependencies

- **Allowed:** Python ecosystem dependencies only.
- **Forbidden:** any frontend dependency — never import from, vendor, or
  reference app repos, shared UI packages, or the contracts package.
  Rule: `logosforge API -> no frontend dependency`.

## Update rules

- Changes flow **downstream only**. Target cascade:
  `logosforge → logosforge-ui-contracts → shared UI → apps` — but the
  contracts and shared-UI stages are **future**; today the only downstream
  consumer to consider is the Free desktop alpha (`logosforge-desktop`).
  Never adapt the core to a frontend; frontends adapt to the core.
- When the API/backend surface changes: **today**, record what the Free
  desktop alpha must adapt to as a follow-up for `logosforge-desktop`.
  **Once `logosforge-ui-contracts` exists** (it is a future scaffold today),
  it must additionally be updated to match, in its own session in that repo.
- The API layer is the only entry point for frontends. Do not add side doors,
  private hooks for one app, or frontend-specific endpoints that bypass the
  shared contracts.
- Internal refactors that do not change the API surface end here — no
  downstream updates needed.

## Forbidden actions

- Adding React components, CSS, or any UI code
- Adding Electron code or desktop packaging config
- Adding web deployment, auth, or cloud storage for frontends
- Defining or editing TypeScript contracts here instead of in
  `logosforge-ui-contracts`
- Importing or copying code from any LogosForge frontend repo
- Implementing product behavior in a frontend because "it's faster" —
  behavior lives here

## Architecture source of truth

Ecosystem rules live in **`fopearcano/logosforge-architecture`**. Before any
cross-repo work, read there: `docs/REPO_MAP.md`, `docs/OWNERSHIP_RULES.md`,
`docs/CHANGE_PROTOCOL.md`, `docs/DEPENDENCY_POLICY.md`. Answer the change
protocol questions before editing.
