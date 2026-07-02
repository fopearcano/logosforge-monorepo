"""Logos — the inline, contextual, section-aware assistant layer.

Logos is a *second* assistant layer that lives next to the author's work and
reacts to selection / cursor / active scene / active outline item. It reuses the
existing Assistant backend (provider settings, chat, context builders) — it does
NOT replace the chat-centric AssistantPanel, and it owns no provider system of
its own.

Phase 0 is the non-destructive foundation: context object, action registry,
controller, structured result, and minimal Manuscript/Outline entry points.
"""

from logosforge.logos.actions import (
    FUTURE_ACTIONS,
    LogosAction,
    describe_all_actions,
    list_actions,
    list_actions_for_section,
)
from logosforge.logos.context import LogosContext, build_logos_context
from logosforge.logos.controller import LogosController
from logosforge.logos.result import LogosResult

__all__ = [
    "LogosContext",
    "build_logos_context",
    "LogosController",
    "LogosResult",
    "LogosAction",
    "list_actions",
    "list_actions_for_section",
    "describe_all_actions",
    "FUTURE_ACTIONS",
]
