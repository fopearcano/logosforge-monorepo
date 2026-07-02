# LogosForge Whiteboard — Desktop Shell

Minimal **Electron + React + TypeScript** desktop shell for Whiteboard Free. It
opens a window, loads the React UI, starts (or connects to) the local FastAPI
backend, checks `/health`, and shows the backend status + API version above a
blank placeholder whiteboard area.

> Phase 2 foundation — shell only. No real editor and no Pro features yet.

## Layout

```
desktop/
├── electron/
│   ├── main.ts            # window + app lifecycle, wires backend status to the UI
│   ├── preload.ts         # contextBridge — exposes a tiny, typed IPC surface
│   └── backend-manager.ts # start/connect backend, poll /health, report status
├── renderer/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/backend.ts # typed bridge to the main process (+ browser fallback)
│   │   ├── components/    # StatusBar, Whiteboard placeholder
│   │   └── styles/
│   ├── index.html
│   └── vite.config.ts
└── package.json
```

## Prerequisites

- Node.js 18+ and npm
- The backend from `../backend` (Python 3.10+). In development the desktop app
  auto-starts it using `../backend/.venv` if present.

## 1. Install frontend dependencies

```bash
cd desktop
npm install
```

## 2. Run the backend

The desktop app will **auto-start** the backend in development (it looks for
`../backend/.venv`), so the one-time setup is just creating that venv:

```bash
cd ../backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

You can also run it yourself; the app will detect and connect to it:

```bash
# from backend/, with the venv active
uvicorn app.main:app --host 127.0.0.1 --port 8777
```

Override host/port with `LOGOSFORGE_HOST` / `LOGOSFORGE_PORT` (defaults
`127.0.0.1:8777`).

## 3. Run the Electron app

```bash
cd desktop
npm run dev
```

This starts the Vite dev server (renderer) and launches Electron once the dev
server is ready. The backend manager connects to a running backend or starts one
from `../backend`, polls `/health`, and reports status to the window.

### Production preview (optional)

```bash
npm run preview     # builds the renderer + electron, then runs with --prod
```

### Minimal packaging smoke (optional)

```bash
npm run pack        # builds, then electron-builder --dir -> release/ (unpacked app)
```

Packages only the Electron shell (no installer, no bundled backend) — see
`../docs/PRO_TODO.md`.

### Type-check

```bash
npm run typecheck
```

## What you should see

- Window titled **LogosForge Whiteboard**.
- A bottom status bar: a colored dot + `Backend: Connecting… / Connected /
  Unavailable`, and `API v1.0.0 · core 0.1.0` once connected.
- A central **writing sheet** (the TipTap editor) with a save indicator
  (`Saving… / Saved / Save failed`) at the top-right.
- A small **Writing Mode** dropdown in the status line (Novel, Screenplay, …)
  with the mode's structural vocabulary.
- A hideable **Outline** panel on the left (toggle with `☰` or Ctrl/Cmd+Shift+O).
- A **PSYKE** panel (story-bible search) — open with the `PSYKE` button or
  Ctrl/Cmd+Shift+P; type to search, click a result for a simple detail view.
- A **Logos** inline assistant — press Ctrl/Cmd+K in the editor to open a
  floating box at the cursor; run a quick action and Replace/Insert the result.

## Editor (Phase 3)

The writing surface is a [TipTap](https://tiptap.dev) (ProseMirror) editor — the
editor technology chosen in the architecture report — under
`renderer/src/features/whiteboard/`:

| File | Role |
|---|---|
| `WhiteboardPage.tsx` | Composes load/save state + editor + save indicator; loading/error states. |
| `WhiteboardEditor.tsx` | The TipTap editor + block ↔ ProseMirror mapping. |
| `useWhiteboardDocument.ts` | Loads `GET /api/whiteboard`, autosaves via `PUT /api/whiteboard` (700 ms debounce), tracks save status. |
| `whiteboardApi.ts` | Frontend HTTP client for the whiteboard endpoints. |
| `types.ts` | Shared DTO types. |

It is intentionally minimal — a blank sheet with **paragraphs, headings
(`#` / `##` / `###`), and undo/redo**. Inline marks (bold/italic) and lists are
off for now because the backend persists plain text per block; richer content
(canonical ProseMirror JSON) is a later milestone, so **what you see is exactly
what is saved**. The editor loads once the backend reports connected and
autosaves on edit.

## Outline (Phase 4)

A simple, hideable Outline panel on the left, under
`renderer/src/features/outline/` (`OutlinePanel`, `useOutline`, `outlineApi`,
`types`). It lists the document structure from **`GET /api/outline`** (headings,
indented by level) and refreshes after each save.

- **Toggle:** the `☰` button in the title bar, or **Ctrl/Cmd+Shift+O**.
- **Hidden = gone:** when off, the panel is removed entirely (no collapsed rail)
  and the editor expands to fill the space.
- Clicking an item scrolls the editor to that heading.

Minimal by design: a flat indented list — no drag/drop, no tree management, no
Pro dockable-panel behavior.

## Writing Modes (Phase 5)

The five StoryPlanner Writing Modes (Novel, Screenplay, Graphic Novel, Stage
Script, Series) are loaded from **`GET /api/writing-modes`** and selectable from
a small keyboard-accessible dropdown in the editor's status line, under
`renderer/src/features/writingModes/` (`WritingModeSelector`, `useWritingModes`,
`writingModesApi`, `types`).

- Selecting a mode persists it on the document (`PUT /api/whiteboard { mode }`,
  partial update) and shows the mode's structural vocabulary (e.g. *Acts /
  Sequences / Scenes*); the dropdown tooltip shows its medium constraints.
- The editor reacts via a `data-writing-mode` attribute on the writing surface —
  the clean boundary for future per-mode element grammars. Today Screenplay and
  Stage Script switch the surface to a monospaced typeface (a real convention).
- Only StoryPlanner-derived modes are used; none are invented. The backend
  already serves the modes and normalizes the document mode, so no backend
  change was needed. Full per-mode element formatting is deferred.

## PSYKE (Phase 6)

Lightweight access to the PSYKE story bible, under
`renderer/src/features/psyke/` (`PsykeWindow`, `PsykeSearch`, `usePsykeSearch`,
`psykeApi`, `types`). It opens as a simple floating panel on the right.

- **Open/close:** the `PSYKE` title-bar button or **Ctrl/Cmd+Shift+P** (Esc also
  closes). If text is selected in the editor when you open it, the search box is
  pre-filled with that selection (contextual lookup).
- **Search → list → detail:** queries **`GET /api/psyke/search?q=`** (matches
  names and aliases), shows a result list with type badges, and a simple detail
  view (name / type / aliases) on click.
- Minimal by design: **no graph visualization, no Pro Codex workspace, no full
  dockable panel system.**

> The backend currently serves a few **placeholder sample entries** so search is
> demonstrable; a persistent, user-populated PSYKE store arrives later.

## Logos inline assistant (Phase 7)

Logos is an inline, Codex-style assistant **embedded in the writing surface**
(not a chat panel), under `renderer/src/features/logos/` (`LogosFloatingBox`,
`useLogosInline`, `logosApi`, `logosActions`, `types`).

- **Open:** press **Ctrl/Cmd+K** in the editor — a floating box appears at the
  cursor / selection (Esc or Ctrl/Cmd+K again closes).
- **Context captured:** the selected text, the surrounding block, and the
  current Writing Mode are sent to **`POST /api/logos/inline`**.
- **Actions:** Suggest, Rewrite, Expand, Explain, Summarize, **Connect**
  (searches PSYKE for entities in the selection), and **Mode pass** — plus a
  free-text prompt.
- **Apply:** results apply back into the document via ProseMirror transactions
  (**Replace** the selection / **Insert below** / Copy / Dismiss).
- **Graceful states:** thinking / error / placeholder note.
- **Streaming-ready:** the backend currently returns a single response (the
  service is an offline placeholder); the transport has a streaming seam and the
  box renders output reactively, so wiring a real provider/stream needs no UI
  change.

> The backend Logos service is an offline, deterministic **placeholder** (no LLM
> yet); a provider transport is wired in a later milestone.

## Notes & scope

- The backend manager stops the backend on app close **only if the app started
  it** (an externally-run backend is left alone).
- Production packaging (electron-builder) and bundling a frozen backend are a
  later milestone; `--prod` here just loads the built renderer from disk.
- Out of scope (Pro): dashboard, project hub, timeline, graph, analytics, Pro
  dockable workspace, advanced HUD visuals.
