# LogosForge Whiteboard — Desktop

The free LogosForge writing workstation, built with Electron, React, TypeScript,
TipTap, and the shared Python LogosForge core. Packaged builds are self-contained:
electron-builder includes a PyInstaller-frozen FastAPI wrapper, and that wrapper
runs the core in-process. End users do not need Node.js or Python.

Whiteboard is alpha software. Its current core is **0.9.0-alpha**.

## What is implemented

- Multiple isolated, autosaving documents with guarded close, reload, switch,
  delete, external-file save, and recovery paths.
- Four writing modes: Novel, Screenplay (Fountain editing and paginated preview),
  Graphic Novel, and Stage Play.
- A rich TipTap prose editor with formatting, focus mode, themes, zoom, line
  numbers, folding, and syntax aids.
- A persisted manual Outline with typed tree nodes, templates, drag/drop,
  filtering, stable manuscript links, a derived **From Document** navigator, and
  Story Map.
- Per-document PSYKE story-bible entries and anchored comment threads.
- Billy chat and Logos inline assistance through configurable local or cloud AI
  providers. AI is optional; no provider is contacted until the user configures
  one.
- Import from text, Markdown, Fountain, Final Draft, and `.logosforge`; export to
  text, Markdown, Fountain, HTML, JSON, `.logosforge`, comment reports, PDF, and
  complete `.lfbundle` project snapshots. `.lfbundle` import/restoration is
  currently handled by LogosForge Pro, not Whiteboard.
- Windows x64 installer and portable builds, macOS 12+ Intel DMG, and Linux x64
  AppImage release targets.

The app's status bar reports `Backend: Connecting…`, `Connected`, or
`Unavailable`. A healthy release reports **API v1.0.0 · core 0.9.0-alpha**.

## Architecture

```text
desktop/
├── electron/
│   ├── main.ts             # window lifecycle, file IPC, persistence fences
│   ├── preload.ts          # small typed contextBridge surface
│   └── backend-manager.ts  # launches and verifies the local backend
├── renderer/
│   ├── src/
│   │   ├── api/            # renderer-to-main/backend bridge
│   │   ├── features/       # editor, outline, comments, PSYKE, AI, files
│   │   └── styles/
│   └── vite.config.mts
├── tests/                  # main-process and renderer contract regressions
├── electron-builder.yml
└── package.json

../backend/
├── app/                    # thin Whiteboard API and local persistence
├── tests/
└── logosforge-whiteboard-backend.spec
```

The Electron main process binds the backend to loopback, selects a free port if
the default is occupied, and accepts an explicitly configured port only when it
is available. Every managed process gets a random Bearer token and instance
nonce, so the app neither trusts nor terminates an unrelated listener. The
renderer receives no Node.js integration: `contextIsolation`, sandboxing, frame
validation, narrow IPC methods, and explicit file-path grants remain enabled.

User data defaults to `~/.logosforge` (`%USERPROFILE%\.logosforge` on Windows).
Set `LOGOSFORGE_DATA_DIR` and `LOGOSFORGE_DB_PATH` to isolate a development or
test run. `LOGOSFORGE_HOST` and `LOGOSFORGE_PORT` override the loopback endpoint;
an explicit port is strict.

## Development setup

Prerequisites are **Node.js 22.12+**, npm, and **Python 3.11+**. From the
monorepo root, create the backend environment and install both the shared core
and wrapper dependencies:

```bash
python -m venv whiteboard-desktop/backend/.venv
whiteboard-desktop/backend/.venv/bin/python -m pip install -e "./logosforge[export]" -r whiteboard-desktop/backend/requirements.txt
```

On Windows, use
`whiteboard-desktop\backend\.venv\Scripts\python.exe` in the second command.
Then install the desktop dependencies and start the app:

```bash
cd whiteboard-desktop/desktop
npm install
npm run dev
```

Electron automatically launches the wrapper from `../backend/.venv`. For a
browser-only renderer session, start the wrapper yourself from
`whiteboard-desktop/backend`:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8777
```

Use `.venv\Scripts\python.exe` on Windows.

## Verification commands

Run these from `whiteboard-desktop/desktop`:

```bash
npm test
npm run build
npm audit --audit-level=moderate
```

Backend checks run from the monorepo root with the backend venv:

```bash
whiteboard-desktop/backend/.venv/bin/python -m pytest whiteboard-desktop/backend/tests -q
whiteboard-desktop/backend/.venv/bin/python -m compileall -q whiteboard-desktop/backend/app
whiteboard-desktop/backend/.venv/bin/python -m pip check
```

## Packaging

`electron-builder.yml` always expects a native frozen backend at
`../backend/dist/logosforge-whiteboard-backend`; build it on the target operating
system before invoking electron-builder. PyInstaller output is not portable
between Windows, macOS, and Linux.

After the sidecar exists:

```bash
npm run pack        # unpacked application under release/
npm run dist:win    # Windows x64 NSIS + portable executables
npm run dist:mac    # macOS 12+ Intel DMG
npm run dist:linux  # Linux x64 AppImage
```

These commands package the Electron shell **and** the bundled backend/core. The
release workflows build the native backend first and then run the appropriate
platform command. See [../RELEASING.md](../RELEASING.md) for the versioned,
multi-platform release procedure and
[../scripts/validate-macos.sh](../scripts/validate-macos.sh) for local validation
on the Intel Mac runner.

## Scope

Whiteboard intentionally omits Pro's dashboard, project hub, timeline, graph,
analytics, voice room, and dockable Studio workspace. Those are product-tier
boundaries, not missing Whiteboard packaging work.
