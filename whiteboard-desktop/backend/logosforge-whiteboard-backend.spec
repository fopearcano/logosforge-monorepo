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

from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

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
hiddenimports += collect_submodules("logosforge")
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
    pathex=[],
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
