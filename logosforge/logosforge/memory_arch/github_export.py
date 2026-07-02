"""GitHub memory export service (Phase 2 stub — disabled, opt-in only).

GitHub is optional and never default (`docs/architecture/
GITHUB_EXPORT_STRATEGY.md`). No GitHub API, no commits, no pushes. Markdown
export here is in-memory text generation only (via a provided store); the
actual GitHub sync is a disabled placeholder requiring future explicit
opt-in.
"""

from __future__ import annotations

from logosforge.memory_arch.schema import MemoryScope
from logosforge.memory_arch.store import MemoryStore


class GitHubMemoryExportService:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store

    def export_memory_to_markdown(self, scope: MemoryScope | None = None,
                                  project_id: str | None = None) -> str:
        """Human-readable markdown (no file write, no network). Secrets are
        already excluded upstream by the writer policy."""
        if self._store is None:
            return "# Memory export\n\n_(no store configured)_\n"
        return self._store.export_markdown(scope=scope, project_id=project_id)

    def prepare_github_export_preview(self, scope: MemoryScope | None = None,
                                     project_id: str | None = None) -> dict:
        md = self.export_memory_to_markdown(scope=scope, project_id=project_id)
        return {"status": "preview", "would_push": False,
                "scope": scope.value if scope else "all",
                "markdown_preview": md,
                "note": "Preview only — no commit/push without explicit opt-in."}

    def optional_sync_memory_to_github(self) -> dict:
        return {"status": "disabled",
                "reason": "GitHub export is opt-in and manual-only; not "
                          "configured. No commits/pushes are performed."}
