"""Deterministic fake model provider for the Writer QA harness.

Returns canned outputs per profile so validators / cache / apply safety can be
proven WITHOUT calling any real provider or the network. Includes both
known-good (mode-correct) outputs and the known-bad output shapes that the
Assistant must block (planning/meta/context dumps, wrong mode, empty, error).
"""

from __future__ import annotations


class FakeProviderError(Exception):
    """Simulated provider failure (timeout / connection error)."""


# Bad-output fixtures must contain the exact leakage patterns the Assistant
# contract validator is expected to reject.
_INVALID_PLANNING = (
    "### Suggested Scene Structure\n"
    "- [INTRODUCING] establish the archive at dawn\n"
    "- [MAIN ACTION] Milo confronts Ada\n"
    "- [CULMINATING MOMENT] the reveal\n\n"
    "## Production Notes\n"
    "Key Questions to Explore:\n"
    "1. What does Ada want?\n"
    "Key Improvements: tighten the open.\n"
    "Let me craft a taut scene. This creates visual rhythm.\n"
    "Six-Task Line Test applies here."
)
_INVALID_CONTEXT_DUMP = (
    "[AI Mode: Balance]\n"
    "Based on PSYKE Context and Global Story Memory, here is the scene.\n"
    "Using the context above, I will now write."
)
_INVALID_META = (
    "I'll help you with this. Here's how I will approach the scene. "
    "This structured approach uses the Stack Technique. Let me begin."
)
# Mode-correct, valid outputs.
_VALID_SCREENPLAY = (
    "MILO VOSS\nIt was not open when I arrived.\n\n"
    "ADA NORTH\nThen someone wanted us to think it was.\n\n"
    "Milo looks toward the velvet cushion."
)
_VALID_NOVEL = (
    "Ada stepped into the archive, the dust hanging in the dawn light. Milo did "
    "not look up. \"You're late,\" he said, and she heard the accusation under it."
)
_VALID_GN_PANEL = (
    "Panel 1\nVisual: Ada in the doorway, notebook clutched to her chest.\n"
    "Caption: Dawn, and the lock already broken.\n"
    "Dialogue: MILO: You are late.\nSFX: creak"
)
_VALID_STAGE = (
    "MILO. You are late.\n(He does not turn from the window.)\n"
    "ADA. The door was not supposed to be open."
)
_VALID_SERIES = (
    "Ada crossed the bullpen. On the monitor, last night's footage looped. "
    "\"Run it back,\" she told Milo. \"The part everyone skipped.\""
)
_VALID_OUTLINE = (
    "## Act I\n- Scene 1: Ada arrives at the archive\n"
    "- Scene 2: the missing ledger\n- Scene 3: the first lie"
)
_VALID_PSYKE = (
    "Ada North — methodical archivist; distrusts easy answers; haunted by a "
    "case she could not close. Wants the truth even when it costs her."
)
_VALID_NOTE_SUMMARY = (
    "Summary: the heist hinges on the archive's blind spot. Open questions: who "
    "tipped them off; where the ledger went."
)
# A wrong-mode response: prose returned where screenplay/panel is expected.
_WRONG_MODE = _VALID_NOVEL

RESPONSES: dict[str, str] = {
    "valid_screenplay_dialogue": _VALID_SCREENPLAY,
    "valid_novel_prose": _VALID_NOVEL,
    "valid_graphic_novel_panel": _VALID_GN_PANEL,
    "valid_stage_script_dialogue": _VALID_STAGE,
    "valid_series_scene": _VALID_SERIES,
    "valid_outline_structure": _VALID_OUTLINE,
    "valid_psyke_entity": _VALID_PSYKE,
    "valid_note_summary": _VALID_NOTE_SUMMARY,
    "invalid_planning_markdown": _INVALID_PLANNING,
    "invalid_context_dump": _INVALID_CONTEXT_DUMP,
    "invalid_wrong_mode": _WRONG_MODE,
    "invalid_meta_reasoning": _INVALID_META,
    "invalid_empty": "",
}

PROFILES = tuple(RESPONSES) + ("provider_error",)


class FakeProvider:
    """Deterministic, offline. Never touches the network or a real provider."""

    name = "fake"

    def respond(self, profile: str, contract=None) -> str:
        if profile == "provider_error":
            raise FakeProviderError("simulated provider timeout")
        if profile not in RESPONSES:
            raise KeyError(f"unknown fake-provider profile: {profile}")
        return RESPONSES[profile]
