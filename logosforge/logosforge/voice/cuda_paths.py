"""Optional: make local GPU transcription work out-of-the-box on Windows.

faster-whisper (CTranslate2) needs the CUDA runtime libraries (cuBLAS + cuDNN)
on the process DLL search path to run ``device=cuda``. On Windows these are not
installed system-wide by default, so GPU transcription otherwise fails with
``cublas64_*.dll not found`` unless the app is launched from a shell that has
them on PATH.

A user who has those DLLs (e.g. in a dedicated folder, or shipped with another
CUDA app) can point at the containing directory via the ``voice_cuda_dll_dirs``
setting (a list of paths). At startup we add each existing directory to the DLL
search path, so ``device=cuda`` loads without any launcher wrapper.

Local-first and conservative: only directories the user configured are added,
nothing is downloaded, and it is a no-op when the setting is empty or the
directory is missing. Put ONLY the CUDA runtime DLLs in such a folder — adding a
directory that also contains another framework's OpenMP/MKL runtimes can collide
with the app's and crash the process.
"""

from __future__ import annotations

import os
from collections.abc import Iterable


def ensure_cuda_dll_path(dirs: Iterable[str] | None) -> list[str]:
    """Add each existing directory in ``dirs`` to the DLL search path.

    Returns the list of directories actually added (existing ones), so callers
    can log what took effect. Safe to call unconditionally and repeatedly.
    """
    added: list[str] = []
    if not dirs:
        return added
    add_dll_directory = getattr(os, "add_dll_directory", None)  # Windows + 3.8+
    for raw in dirs:
        d = str(raw or "").strip()
        if not d or not os.path.isdir(d):
            continue
        if callable(add_dll_directory):
            try:
                add_dll_directory(d)
            except (OSError, ValueError):  # pragma: no cover - defensive
                pass
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        added.append(d)
    return added
