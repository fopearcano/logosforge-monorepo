"""Logos reply sanitizer — strips a leaked grounding-context preamble the model
echoes ("[PSYKE Context] ... Expanded text:") while keeping the real text, and
withholds only when the reply is nothing but a leak. Engages ONLY on a leading
standalone grounding head, so legitimate prose that merely mentions psyke/memory
is never touched. Covers the pure helpers + the LogosController chokepoint."""

from __future__ import annotations

from logosforge.db import Database
from logosforge.logos.context import build_logos_context
from logosforge.logos.controller import LogosController
from logosforge.logos.sanitize import (
    leads_with_context_head,
    sanitize_logos_reply,
    strip_leaked_preamble,
)

# The exact shape observed live: echoed PSYKE block + a model-invented header.
LEAKED = (
    "[PSYKE Context]\n\n"
    "Entries:\n"
    "- Mara (character)\n"
    "- Mara (character)\n\n\n"
    "Expanded text:\n\n"
    "She turned up the gain, and the static resolved into a single voice."
)
REAL = "She turned up the gain, and the static resolved into a single voice."


# -- leads_with_context_head -------------------------------------------------

def test_head_detection_requires_standalone_bracket_line():
    assert leads_with_context_head(LEAKED)
    assert leads_with_context_head("[Global Story Memory]\n\n- premise")
    assert leads_with_context_head("[AI Mode: Balance]\nGlobal:\n- x")
    # NOT a head: a bracketed aside that continues as prose on the same line.
    assert not leads_with_context_head("[Memory] of her mother flooded back.")
    assert not leads_with_context_head("[AI Mode: cynical] narration suits this.")
    assert not leads_with_context_head("Based on PSYKE entries, he reads as thin.")


# -- strip_leaked_preamble ---------------------------------------------------

def test_strips_leading_preamble_keeps_real_text():
    assert strip_leaked_preamble(LEAKED) == REAL


def test_no_leading_leak_returned_unchanged():
    assert strip_leaked_preamble(REAL) == REAL
    # A bracketed aside is real prose, not a head -> untouched.
    assert strip_leaked_preamble("[Memory] of her mother flooded back.") == (
        "[Memory] of her mother flooded back."
    )


def test_strips_without_output_header():
    leaked = "[PSYKE Context]\n\nEntries:\n- Mara (character)\n\nShe ran for the door."
    assert strip_leaked_preamble(leaked) == "She ran for the door."


def test_only_a_leaked_block_strips_to_empty():
    assert strip_leaked_preamble("[PSYKE Context]\n\nEntries:\n- Mara (character)\n") == ""


def test_global_story_memory_head():
    leaked = "[Global Story Memory]\n\nGlobal:\n- premise\n\nOutput:\n\nThe sea swallowed the bell."
    assert strip_leaked_preamble(leaked) == "The sea swallowed the bell."


def test_real_bullets_after_blank_gap_survive():
    # Echoed grounding bullets, then a blank, then the real bullet output.
    leaked = "[PSYKE Context]\nEntries:\n- Mara\n\n- Beat one of the scene\n- Beat two."
    assert strip_leaked_preamble(leaked) == "- Beat one of the scene\n- Beat two."


def test_short_colon_lead_in_survives():
    # A real first line that is a short clause ending in ':' must NOT be eaten.
    assert strip_leaked_preamble("[PSYKE Context]\n- Mara\n\nThe truth was simple:\nAll had lied.") == (
        "The truth was simple:\nAll had lied."
    )
    assert strip_leaked_preamble("[PSYKE Context]\n- Mara\n\nNew plan:\nWe move at dawn.") == (
        "New plan:\nWe move at dawn."
    )


def test_action_required_label_survives_after_strip():
    # If the model used the action's required "Expanded version:" label, keep it
    # (the output-header regex deliberately matches "text:" not "version:").
    leaked = "[PSYKE Context]\nEntries:\n- Mara\n\nExpanded version:\nShe turned up the gain."
    assert strip_leaked_preamble(leaked) == "Expanded version:\nShe turned up the gain."


# -- sanitize_logos_reply (the gate that must NOT over-fire) ------------------

def test_sanitize_clean_passes_through():
    assert sanitize_logos_reply(REAL) == (REAL, False)


def test_sanitize_leading_leak_keeps_text():
    assert sanitize_logos_reply(LEAKED) == (REAL, False)


def test_sanitize_only_leak_withholds():
    assert sanitize_logos_reply("[PSYKE Context]\n\nEntries:\n- Mara (character)\n") == ("", True)


def test_sanitize_does_not_withhold_legit_prose_mentioning_markers():
    # The critical regression guard: ordinary grounded advice that references
    # PSYKE / memory / ai mode in prose must pass through UNCHANGED, not be blanked.
    for legit in (
        "Based on PSYKE entries for Mara, she'd more likely deflect than confess.",
        "The hidden context of the letter changes everything in the final act.",
        "Your PSYKE context feeds the model your characters automatically.",
        "You can switch the AI mode: balance, creative, or precise.",
        "[Memory] of her mother flooded back as she opened the box.",
        "Rewrite with a colder voice. [AI Mode: cynical] narration suits this beat.",
    ):
        assert sanitize_logos_reply(legit) == (legit, False), legit


# -- controller chokepoint (end-to-end, injected chat_fn) --------------------

def _ctl(reply: str):
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    ctl = LogosController(
        db, provider_resolver=lambda: object(), chat_fn=lambda m, p: reply,
    )
    ctx = build_logos_context(
        db, pid, section_name="Inline", selected_text="She turns up the gain.",
    )
    return ctl, ctx


def test_controller_strips_leaked_preamble():
    ctl, ctx = _ctl(LEAKED)
    res = ctl.run(ctx, "inline_expand")
    assert res.ok
    assert "PSYKE Context" not in res.message
    assert "Expanded text:" not in res.message
    assert res.message == REAL


def test_controller_does_not_blank_legit_marker_prose():
    legit = "Based on PSYKE entries for Mara, she would deflect, not confess."
    ctl, ctx = _ctl(legit)
    res = ctl.run(ctx, "inline_expand")
    assert res.ok
    assert res.message == legit  # unchanged, NOT withheld


def test_controller_withholds_when_only_leak():
    ctl, ctx = _ctl("[PSYKE Context]\n\nEntries:\n- Mara (character)\n")
    res = ctl.run(ctx, "inline_expand")
    assert res.ok
    assert "PSYKE Context" not in res.message
    assert "echoed internal context" in res.message
    assert res.suggestions == []
