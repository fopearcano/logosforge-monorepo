# Building LogosForge Pro (desktop) — Windows release

LogosForge Pro ships as a **self-contained Windows app**: the Electron shell +
the built renderer + a PyInstaller-frozen copy of the Python `logosforge` core.
**No Python install is required on the user's machine** — the app spawns the
bundled core (`resources/core/logosforge-core.exe`) on startup and talks to it
over `http://127.0.0.1:8765`.

## What the build produces

`electron-builder --win` writes to `pro-desktop/release/`:

- `LogosForge Pro-<version>-x64.exe` — NSIS installer (Start-menu + desktop
  shortcuts, user can choose the install dir).
- `LogosForge Pro-<version>-x64-portable.exe` — single portable exe (no install).

Both embed: `LogosForge Pro.exe` (Electron) · `resources/app.asar` (main +
renderer) · `resources/core/` (the frozen core + its `_internal/` deps).

## CI (recommended): GitHub Actions

`/.github/workflows/release-windows.yml` builds the whole thing on
`windows-latest`. It runs the PyInstaller bundle, **smoke-tests** that the
frozen core answers `/api/health`, then runs `electron-builder --win`.

- **Manual run:** Actions → "Release — LogosForge Pro (Windows)" → *Run
  workflow* → uploads the installers as a build artifact.
- **Tagged release:** push a tag `vX.Y.Z` → it also publishes a GitHub Release
  with the installers attached.

```bash
git tag v0.1.0 && git push origin v0.1.0
```

The workflow assumes a **single monorepo checkout** containing `logosforge/`,
`logosforge-ui-contracts/`, `pro-shared-ui/`, and `pro-desktop/` as sibling
dirs (the current on-disk layout). If these become separate repos, replace the
single `actions/checkout` with one checkout per repo into those sibling paths.

## Local build (Windows)

Prereqs: Node 20, Python 3.11, and (for `electron-builder`) **Windows Developer
Mode enabled** or an elevated/admin shell — otherwise electron-builder fails
extracting its `winCodeSign` cache with *"Cannot create symbolic link: A
required privilege is not held"*. (That cache holds macOS signing tools a
Windows build never uses; the GitHub runner has the privilege, so CI is
unaffected.)

```bash
# 1. Freeze the core (from the repo root)
python -m venv core-venv
./core-venv/Scripts/python -m pip install "./logosforge[export]" pyinstaller
cd pro-desktop/core
../../core-venv/Scripts/python -m PyInstaller logosforge-core.spec --noconfirm --clean

# 2. Build + package the app
cd ..              # -> pro-desktop
npm install
npm run dist:win   # NSIS + portable  ->  release/
#   or:  npm run pack   (unpacked dir only, fast, no installer)
```

## How the pieces fit

- **`core/core_entry.py` + `core/logosforge-core.spec`** — the PyInstaller
  entry (forwards `--host/--port/--mode` to `logosforge.api.server.main`) and
  the onedir spec. Excludes the GUI/voice stacks (PySide6/torch/whisper); the
  frozen core is headless-API only, plus `reportlab`/`python-docx` for export.
- **`electron/core-manager.ts`** — packaged builds spawn
  `resources/core/logosforge-core.exe` (`windowsHide`); dev builds spawn
  `python -m logosforge.api` from the sibling `logosforge/venv`.
- **`electron/static-server.ts`** — packaged builds serve the renderer from
  `http://127.0.0.1:<port>` (NOT `file://`) so its origin is allowed by the
  core's desktop-mode CORS regex. Without this, every renderer→core fetch fails.

## Known follow-ups

- **Code signing.** The build is **unsigned** → users get a Windows SmartScreen
  prompt ("More info → Run anyway"). To sign, add an EV/OV cert and set
  `CSC_LINK` + `CSC_KEY_PASSWORD` as repo secrets (electron-builder picks them
  up automatically).
- **App icon.** No custom icon yet → the default Electron icon is used. Add
  `pro-desktop/build/icon.ico` (256×256) and electron-builder will use it.
- **macOS / Linux.** Not built yet (planned). Add `mac`/`linux` targets to the
  `build` block and matching jobs; the core must be PyInstaller-frozen **on each
  OS** (PyInstaller does not cross-compile).
- **AI features.** The bundled core runs fully offline for deterministic
  features; Billy/Logos/extraction need an LLM provider (e.g. local LM Studio)
  configured by the user, and degrade gracefully without one.
