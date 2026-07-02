"""Logosforge — local-first writing-intelligence app.

Canonical version / release-status constants. ``__version__`` already has a
consumer (``cloud_storage._app_version`` records it in per-project lock
metadata), so this is the single source of truth for the app version.

Alpha closure: see docs/ALPHA_SCOPE.md and docs/ALPHA_FREEZE.md.
"""

__version__ = "0.9.0-alpha"
__status__ = "alpha"

__all__ = ["__version__", "__status__"]
