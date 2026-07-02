# CLAUDE.md — LogosForge Studio Shared UI (`@logosforge/pro-shared-ui`)

> Ecosystem rules live in `fopearcano/logosforge-architecture`. Studio (Pro) and
> Whiteboard (Free) **never share UI** — this is a forbidden cross-line
> dependency.

## Repo identity

The shared React UI package for the **Pro / Studio** product line — the
complete, power-user writing workstation. Consumed by both Pro apps:
`pro-desktop` (Electron) and `pro-web` (browser). **Platform-neutral**: every
component must run unchanged in an Electron renderer and a plain browser.

## What this repo owns

- The Studio UI: a dockable, cinematic, panel-based workspace (manuscript editor
  + intelligence panels: structure, PSYKE, timeline/plot, knowledge graph,
  quantum outliner, assistant, decision radar, analytics, voice, stages).
- The **Pro visual identity** (Studio theme/tokens, dense/HUD/minimal-cyber).

## What this repo must NOT own

- **Electron-specific code** — no `electron` imports, no Node, no IPC.
- **Browser/cloud-specific code** — no routing/auth/storage/host networking.
- **Whiteboard (Free) UI** — `Pro UI importing Free UI` is forbidden.
- **Python core logic** — behaviour lives in `logosforge`; call its API.
- **Contract definitions** — types/events/commands live in
  `@logosforge/ui-contracts`; import them, never redefine.
- App-specific glue only one consumer needs (that lives in the app).

## Dependencies

- **Allowed:** `@logosforge/ui-contracts`, React (peer), neutral UI libraries.
- **Forbidden:** `electron`/Node/browser-host SDKs, the Whiteboard line, app
  repos, the Python `logosforge` package.
- Platform behaviour (files, dialogs, navigation, layout persistence) and core
  access (the `ApiClient`) are **injected** via the adapters in `src/adapters/`.

## Update rules

- Change here when **both** Pro apps need it; app-only needs live in the app.
- Cascade: `logosforge core → @logosforge/ui-contracts → THIS PACKAGE → pro-desktop / pro-web`.
- Data-shape needs start in the core + contracts, not here.

## Conventions (scaffolded — keep them)

- **`data-screen-label` on every panel root** — a stable screen id matching the
  design's frame label, so design comments map to code. `Placeholder` emits it
  from `screenLabel`; real panels must keep an equivalent on their root.
- **`writingMode → --accent`** — accents come from `var(--accent)` (helper
  `accent()`), scoped once from the active writing mode (`theme/accent.ts`,
  `<StudioProvider writingMode>`). Never hardcode an accent color in a panel.

## Forbidden actions

- Importing Electron/Node/browser APIs, or anything from the Free line.
- Reimplementing core behaviour or redefining contract types locally.
- Copying components to/from an app repo (single owner, single source).
