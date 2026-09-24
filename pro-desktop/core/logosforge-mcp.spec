# -*- mode: python ; coding: utf-8 -*-
"""Small one-file stdio MCP companion for every native Pro package."""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

CORE_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", "..", "logosforge"))

datas = collect_data_files("mcp")
hiddenimports = collect_submodules(
    "mcp", filter=lambda name: not name.startswith("mcp.cli"),
)
hiddenimports += [
    "logosforge.librechat.api_client",
    "logosforge.librechat.mcp_gateway",
    "logosforge.librechat.mcp_runtime",
    "logosforge.librechat.mcp_server",
    "anyio._backends._asyncio",
]

a = Analysis(
    ["mcp_entry.py"],
    pathex=[CORE_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6", "PyQt5", "PyQt6", "shiboken6", "torch", "torchaudio",
        "fastapi", "uvicorn", "sqlmodel", "sqlalchemy", "reportlab", "docx",
        "faster_whisper", "ctranslate2", "onnxruntime", "av", "tkinter",
        "matplotlib", "IPython", "notebook", "pytest", "mcp.cli", "typer",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="logosforge-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
