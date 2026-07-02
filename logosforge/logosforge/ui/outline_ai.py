"""Shared helpers for AI outline generation in the UI.

Both the (orphaned) OutlineView and the live PlanView need to run an
outline-generation request off the UI thread and to resolve the configured
provider.  This module centralises that so the behaviour stays identical.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class OutlineGenWorker(QThread):
    """Runs an outline-generation LLM request off the UI thread."""

    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, messages, provider) -> None:
        super().__init__()
        self._messages = messages
        self._provider = provider

    def run(self) -> None:
        try:
            from logosforge.assistant import chat_completion
            text, _from_cache = chat_completion(
                self._messages, provider=self._provider,
            )
            self.completed.emit(text)
        except Exception as e:  # pragma: no cover - network/provider errors
            self.failed.emit(str(e))


def build_provider():
    """Resolve the configured AI provider, or None if none is set.

    Thin delegate to the single shared provider builder (Phase 8B).
    """
    from logosforge.providers import build_active_provider
    return build_active_provider(require_configured=True)


def outline_messages(prompt: str) -> list[dict]:
    """Standard system+user message pair for an outline generation prompt."""
    return [
        {"role": "system",
         "content": "You are a story-structure assistant. Produce a clean, "
                    "structured outline only — no prose."},
        {"role": "user", "content": prompt},
    ]
