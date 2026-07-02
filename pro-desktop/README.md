# @logosforge/pro-desktop

LogosForge **Studio (Pro)** — the Electron desktop shell. It owns no UI of its
own: it **spawns the logosforge core API** and composes the
`@logosforge/pro-shared-ui` panels into a workspace, injecting a real
`ApiClient` (`createHttpApiClient`) and a desktop `PlatformAdapter`.

## Layout

```
electron/                 main process (CommonJS → dist-electron/)
  core-manager.ts         connect to / spawn `python -m logosforge.api --mode desktop`
  file-manager.ts         open/save dialogs + per-project layout persistence
  preload.ts              flat `window.logosforge` bridge (contextBridge)
  main.ts                 window + IPC + lifecycle
renderer/                 the React app (Vite)
  src/App.tsx             StudioProvider + createHttpApiClient + the panels
  src/platform.ts         PlatformAdapter over the preload bridge
```

The shared package + contracts are aliased straight to source (vite + tsconfig
`paths`), so there's no build/link step in dev and HMR works across the monorepo.

## Run (dev)

Prereq: the **logosforge core venv** exists at `../logosforge/venv` (the app
falls back to system `python` if not, and will simply connect to a core you
already started on `:8765`).

```
npm install
npm run dev
```

This starts Vite (`:5173`) and Electron together. On launch the app connects to
a running core, or spawns one from the core's venv, then auto-selects its first
project. In `desktop` mode the core's CORS allows any `localhost` origin, so the
renderer talks to `:8765` directly — no proxy.

Env overrides: `LOGOSFORGE_PORT`, `LOGOSFORGE_HOST`, `LOGOSFORGE_CORE_DIR`,
`LOGOSFORGE_PYTHON`.

## Status / next steps

- **Workspace** is a single-panel switcher today. The dockable/draggable layout
  (persisted via the `loadLayout`/`saveLayout` PlatformAdapter hooks) is next.
- **Packaging**: a `file://` origin isn't in the core's localhost CORS allow-list
  — serve the packaged renderer from a localhost origin (or widen the core's
  allowed origins) before shipping. `electron-builder` config isn't set up yet.
- Fonts load from Google Fonts (online); bundle them for offline packaging.
