# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — bundle the LogosForge headless core API as a standalone
# onedir tree (logosforge-core/) that pro-desktop ships as an Electron
# extraResource and spawns in production. Build:
#
#     pyinstaller logosforge-core.spec          # run from pro-desktop/core/
#
# Output: ./dist/logosforge-core/logosforge-core(.exe) + its dependency tree.
#
# The build venv must have the core API installed WITHOUT the heavy gui/voice
# extras: `pip install ./logosforge[export] pyinstaller` (fastapi/uvicorn/
# sqlmodel + reportlab/python-docx for export — no PySide6/torch/whisper).

from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

datas = []
binaries = []
hiddenimports = []

# Packages with dynamic imports and/or bundled data files (fonts, templates,
# CA bundle, compiled extensions) that PyInstaller's static analysis misses.
for pkg in ("uvicorn", "fastapi", "starlette", "sqlalchemy", "pydantic",
            "pydantic_core", "reportlab", "docx"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Our own package + sqlmodel are imported partly via dynamic registries
# (providers, deterministic handlers, proactive detectors, route modules).
hiddenimports += collect_submodules("logosforge")
hiddenimports += collect_submodules("sqlmodel")

# certifi ships cacert.pem (used for any HTTPS the providers make).
datas += collect_data_files("certifi")

# Dexter's Room voice: bundle the faster-whisper / CTranslate2 STT stack (CT2
# only — no torch). ctranslate2 + av ship native extensions/DLLs; faster_whisper
# ships its VAD asset + tokenizer data. The GPU CUDA runtime DLLs are NOT bundled
# — the host adds the user's local ones to the DLL path at runtime. Resilient:
# skip any package the build venv doesn't have (voice just reports unavailable).
for pkg in ("ctranslate2", "faster_whisper", "av", "tokenizers", "onnxruntime", "huggingface_hub"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# uvicorn resolves its loop/protocol/lifespan implementations by string at
# runtime; pin the "auto" targets so the frozen build can find them.
hiddenimports += [
    "logosforge.api", "logosforge.api.server", "logosforge.api.app",
    "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols", "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan", "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "anyio._backends._asyncio",
]

block_cipher = None

a = Analysis(
    ["core_entry.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Keep the bundle lean: the headless API never needs the GUI/voice/heavy
    # ML stacks. (They aren't installed in the build venv either — belt + braces.)
    # faster_whisper / ctranslate2 / av are now BUNDLED (collected above) for
    # Dexter's Room voice; only the genuinely-unused heavy stacks stay excluded.
    excludes=["PySide6", "PyQt5", "PyQt6", "shiboken6", "torch", "torchaudio",
              "tkinter", "matplotlib", "IPython", "notebook", "pytest"],
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
    name="logosforge-core",
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
    name="logosforge-core",
)
