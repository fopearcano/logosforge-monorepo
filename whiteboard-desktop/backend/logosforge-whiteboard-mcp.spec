# -*- mode: python ; coding: utf-8 -*-
"""One-file stdio MCP companion for native LogosForge Whiteboard packages."""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

BACKEND_ROOT = os.path.abspath(SPECPATH)

datas = collect_data_files("mcp")
hiddenimports = collect_submodules(
    "mcp", filter=lambda name: not name.startswith("mcp.cli"),
)
hiddenimports += collect_submodules("app.whiteboard_mcp")
hiddenimports += ["anyio._backends._asyncio"]

a = Analysis(
    ["whiteboard-mcp-entry.py"],
    pathex=[BACKEND_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6", "PyQt5", "PyQt6", "shiboken6", "torch", "torchaudio",
        "fastapi", "uvicorn", "sqlmodel", "sqlalchemy",
        "reportlab", "docx", "faster_whisper", "ctranslate2", "onnxruntime",
        "av", "tkinter", "matplotlib", "IPython", "notebook", "pytest",
        "mcp.cli", "typer", "logosforge",
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
    name="logosforge-whiteboard-mcp",
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
