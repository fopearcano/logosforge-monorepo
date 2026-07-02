# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — bundle the LogosForge Whiteboard backend (which wraps the
# headless core API in-process) as a standalone onedir tree
# (logosforge-whiteboard-backend/) that whiteboard-desktop ships as an Electron
# extraResource and spawns in production. Build (run from whiteboard-desktop/backend/):
#
#     pyinstaller logosforge-whiteboard-backend.spec
#
# Output: ./dist/logosforge-whiteboard-backend/logosforge-whiteboard-backend(.exe)
#         + its dependency tree.
#
# The build venv must have the core API installed WITHOUT the heavy gui/voice
# extras, plus the wrapper's own deps:
#     pip install "./logosforge[export]" fastapi "uvicorn[standard]" httpx pyinstaller
# (fastapi/uvicorn/sqlmodel + reportlab/python-docx for export, + httpx for the
# in-process ASGI transport — no PySide6/torch/whisper.)

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# The core (logosforge) SOURCE tree, resolved from THIS spec's location in the
# monorepo (whiteboard-desktop/backend -> ../../logosforge). We add it to pathex
# and enumerate the core's submodules from it directly, rather than trusting the
# pip-installed copy, because BOTH prior approaches dropped ``logosforge.models``
# and crashed the frozen backend:
#   * ``collect_submodules('logosforge')`` enumerates by IMPORTING each submodule
#     and the walk aborts at the PySide6-dependent ``logosforge.ui.*`` in a
#     headless venv, silently dropping later submodules;
#   * enumerating the INSTALLED wheel proved environment-dependent (the CI wheel's
#     on-disk submodule set differed from a local install).
# The source tree is identical in every checkout, so this is deterministic.
CORE_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", "..", "logosforge"))
CORE_PKG = os.path.join(CORE_ROOT, "logosforge")


def core_submodules():
    """Every ``logosforge.*`` module, enumerated from the SOURCE tree (no
    imports), skipping the GUI/voice subpackages (heavy PySide6 / torch+whisper
    deps the headless backend never uses)."""
    skip_top = {"ui", "voice"}
    mods = set()
    for dirpath, dirnames, filenames in os.walk(CORE_PKG):
        rel = os.path.relpath(dirpath, CORE_PKG)
        parts = [] if rel == "." else rel.split(os.sep)
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and not (not parts and d in skip_top)]
        for f in filenames:
            if f.endswith(".py"):
                tail = [] if f == "__init__.py" else [f[:-3]]
                mods.add(".".join(["logosforge", *parts, *tail]))
    print(
        f"[spec] core pkg={CORE_PKG!r} exists={os.path.isdir(CORE_PKG)} "
        f"count={len(mods)} has_models={'logosforge.models' in mods}",
        file=sys.stderr,
    )
    return sorted(mods)


datas = []
binaries = []
hiddenimports = []

# Packages with dynamic imports and/or bundled data files (fonts, templates,
# CA bundle, compiled extensions) that PyInstaller's static analysis misses.
# Same core set as pro-desktop's spec, plus httpx/httpcore/anyio for the
# wrapper's in-process ASGI client (app/core_client.py).
for pkg in ("uvicorn", "fastapi", "starlette", "sqlalchemy", "pydantic",
            "pydantic_core", "reportlab", "docx",
            "httpx", "httpcore", "anyio"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# The wrapper app package (routers are pulled in via from-imports, but collect
# them explicitly to be safe), the core (imported partly via dynamic registries:
# providers, deterministic handlers, route modules), and sqlmodel.
hiddenimports += collect_submodules("app")
hiddenimports += core_submodules()  # was collect_submodules("logosforge") — see core_submodules() above
# Belt-and-braces: the backend imports these at startup (db.database -> models),
# force them regardless of how enumeration/analysis resolves.
hiddenimports += ["logosforge.models", "logosforge.models.models", "logosforge.models.psyke_details"]
hiddenimports += collect_submodules("sqlmodel")

# certifi ships cacert.pem (used for any HTTPS the providers make).
datas += collect_data_files("certifi")

# uvicorn resolves its loop/protocol/lifespan implementations by string at
# runtime; pin the "auto" targets so the frozen build can find them.
hiddenimports += [
    "app.main",
    "logosforge.api", "logosforge.api.server", "logosforge.api.app",
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols", "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan", "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "anyio._backends._asyncio",
]

block_cipher = None

a = Analysis(
    ["backend-entry.py"],
    pathex=[CORE_ROOT],  # core SOURCE tree — deterministic across local/CI (see CORE_ROOT)
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Keep the bundle lean: the headless backend never needs the GUI/voice/heavy
    # ML stacks. (They aren't installed in the build venv either — belt + braces.)
    excludes=["PySide6", "PyQt5", "PyQt6", "shiboken6", "torch", "torchaudio",
              "faster_whisper", "ctranslate2", "tkinter", "matplotlib",
              "IPython", "notebook", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="logosforge-whiteboard-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # a server process; Electron spawns it with windowsHide:true
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="logosforge-whiteboard-backend",
)
