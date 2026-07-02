"""Assistant behavior model — section/mode/action-aware output contracts.

The assistant must adapt to the current SECTION, WRITING MODE, and ACTION:
direct manuscript-writing actions produce mode-formatted manuscript content
(screenplay text in Screenplay mode, prose in Novel, panel script in Graphic
Novel), never planning structure / analysis / markdown templates — and a
validator rejects such leakage before it is shown/applied. Pure-function tests;
no provider/network calls.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from logosforge.assistant_contract import (
    is_direct_manuscript_writing,
    output_contract,
    validate_response,
)

# The observed bad output (condensed from the bug report screenshot).
BAD_SCREENPLAY_OUTPUT = """\
Your Scene: Expanded & Refined

### Suggested Scene Structure
- [INTRODUCING] Establish the archive at dawn.
- [MAIN ACTION] Milo confronts Ada.
- [CULMINATING MOMENT] The reveal.

## Production Notes
Key Questions to Explore:
1. What does Ada want?
2. Why is the door open?

Prose Style & Cadence: keep it taut.
"""

GOOD_SCREENPLAY_OUTPUT = """\
MILO VOSS
It was not open when I arrived.

ADA NORTH
Then someone wanted us to think it was.

Milo looks toward the velvet cushion.

MILO VOSS
The key is gone.
"""


# 1. Manuscript + Screenplay + Dialogue → screenplay output contract.
def test_screenplay_dialogue_contract():
    assert is_direct_manuscript_writing("Manuscript", "Dialogue")
    c = output_contract(writing_mode="screenplay", section="Manuscript",
                        action="Dialogue").lower()
    assert "screenplay" in c and "character" in c
    assert "suggested scene structure" in c     # explicitly forbidden
    assert "nothing else" in c


# 2. Manuscript + Screenplay + Generate → screenplay contract (not structure).
def test_screenplay_generate_contract():
    c = output_contract(writing_mode="screenplay", section="Manuscript",
                        action="generate").lower()
    assert "screenplay" in c and "outline" not in c.split("forbidden")[0]


# 3-4. Manuscript + Novel → prose contract (no screenplay format unless asked).
def test_novel_generate_and_dialogue_contract():
    for action in ("generate", "Dialogue"):
        c = output_contract(writing_mode="novel", section="Manuscript",
                            action=action).lower()
        assert "prose" in c
        assert "screenplay scene headings" in c   # forbidden unless requested


# 5. Manuscript + Graphic Novel + Dialogue → panel contract; no legacy/ComfyUI.
def test_graphic_novel_dialogue_contract():
    c = output_contract(writing_mode="graphic_novel", section="Manuscript",
                        action="Dialogue").lower()
    assert "panel" in c and "visual" in c and "caption" in c and "sfx" in c
    assert "comics script" in c and "comfyui" in c   # named as forbidden


# 6. Outline + Generate → structure allowed (not a direct-writing action).
def test_outline_generate_allows_structure():
    assert not is_direct_manuscript_writing("Outline", "generate")
    c = output_contract(writing_mode="novel", section="Outline",
                        action="generate").lower()
    assert "structure" in c or "outline" in c


# 7. PSYKE + Generate → codex/story-bible content.
def test_psyke_generate_codex():
    assert not is_direct_manuscript_writing("PSYKE", "generate")
    c = output_contract(writing_mode="novel", section="PSYKE",
                        action="generate").lower()
    assert "story bible" in c or "codex" in c


# 8. Notes + Generate → note content.
def test_notes_generate():
    c = output_contract(writing_mode="novel", section="Notes",
                        action="generate").lower()
    assert "notes" in c


# 9. "Structure" action does not turn into direct writing; "Dialogue" does.
def test_structure_vs_dialogue_routing():
    assert not is_direct_manuscript_writing("Manuscript", "structure")
    assert is_direct_manuscript_writing("Manuscript", "dialogue")


# 10. Suggest is analysis (not direct writing); Dialogue is direct writing.
def test_suggest_vs_dialogue():
    assert not is_direct_manuscript_writing("Manuscript", "suggest")
    assert is_direct_manuscript_writing("Manuscript", "dialogue")


# 11. The contract defers to the user's explicit request.
def test_contract_honors_user_request():
    c = output_contract(writing_mode="screenplay", section="Manuscript",
                        action="Dialogue").lower()
    assert "user's request" in c


# 12-15. Validator catches the bad-output leakage for Screenplay Dialogue.
def test_validator_catches_bad_screenplay_output():
    issues = validate_response(BAD_SCREENPLAY_OUTPUT, writing_mode="screenplay",
                              section="Manuscript", action="Dialogue")
    joined = " ".join(issues).lower()
    assert "suggested scene structure" in joined
    assert "[introducing]" in joined
    assert "production notes" in joined
    assert "markdown heading" in joined


# Clean screenplay output passes the validator (no false positives).
def test_validator_passes_good_screenplay_output():
    assert validate_response(GOOD_SCREENPLAY_OUTPUT, writing_mode="screenplay",
                             section="Manuscript", action="Dialogue") == []


# 16. Non-writing (analysis) actions are not validated → no false warnings.
def test_validator_skips_analysis_actions():
    assert validate_response(BAD_SCREENPLAY_OUTPUT, writing_mode="screenplay",
                             section="Manuscript", action="Suggest") == []
    assert validate_response("### Outline\n- beat one\n- beat two\n- beat three",
                             writing_mode="novel", section="Outline",
                             action="generate") == []


# Validator also catches markdown/bullet structure leaking into Novel prose.
def test_validator_catches_structure_in_novel():
    bad = "### Scene Plan\n- beat 1\n- beat 2\n- beat 3\n"
    issues = validate_response(bad, writing_mode="novel", section="Manuscript",
                               action="generate")
    assert issues


# 17. format_writing_block drops the engine's critique/"key questions" overlay.
def test_writing_block_has_no_reasoning_overlay():
    from logosforge.narrative_engines.screenplay import SCREENPLAY_ENGINE
    wb = SCREENPLAY_ENGINE.format_writing_block()
    full = SCREENPLAY_ENGINE.format_context_block()
    assert "Writing mode: Screenplay" in wb
    assert "Key questions" not in wb and "Review checks" not in wb
    assert "Key questions" in full          # the full block still has it


# 18-19. Provider independence: the contract module imports/uses no provider.
def test_contract_has_no_provider_dependency():
    import importlib
    import sys
    for m in ("logosforge.providers", "logosforge.assistant"):
        sys.modules.pop(m, None)
    importlib.import_module("logosforge.assistant_contract")
    assert "logosforge.providers" not in sys.modules


# Empty / unknown action defaults to a writing action in a writing section.
def test_empty_action_is_writing_in_manuscript():
    assert is_direct_manuscript_writing("Manuscript", "")
    assert not is_direct_manuscript_writing("Outline", "")
