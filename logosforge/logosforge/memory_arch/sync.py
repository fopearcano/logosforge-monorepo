"""Memory sync service (Phase 2 stub — disabled).

Cloud sync is future/pro (`docs/architecture/SYNC_STRATEGY.md`). Every
method here is a no-op that reports a disabled/not-configured status — no
network, no account, no canonical-state changes.
"""

from __future__ import annotations


class MemorySyncService:
    """Local-first by default; cloud sync not implemented in Phase 2."""

    def sync_memory_to_cloud(self) -> dict:
        return {"status": "disabled",
                "reason": "cloud sync is a future/pro feature (not configured)."}

    def get_sync_status(self) -> dict:
        return {"status": "not_configured", "synced": False,
                "pending": 0, "conflicts": 0}

    def resolve_conflict(self, memory_id: str, resolution: str | None = None
                         ) -> dict:
        return {"status": "disabled", "memory_id": memory_id,
                "reason": "conflict resolution arrives with cloud sync."}
