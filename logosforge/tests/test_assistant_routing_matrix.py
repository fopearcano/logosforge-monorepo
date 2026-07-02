"""Assistant routing matrix + cache-key safety (pure, no provider/UI calls).

Output is determined by SECTION × WRITING MODE × ACTION × TARGET × REQUEST. The
router produces an AssistantTaskContract for every request; the cache key is
unique per request shape and per contract/validator version.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from logosforge.assistant_contract import (
    ANALYSIS, ANSWER, AssistantTaskContract, CLARIFICATION, CODEX,
    DIRECT_CONTENT, NOTES, STRUCTURE, SUGGESTIONS, TIMELINE, TRANSCRIPT,
    cache_key, infer_intent, route,
)


# 1. Every entry point yields a contract.
def test_every_entry_point_produces_contract():
    for ep in ("assistant_panel", "chat", "logos_inline", "billy",
               "dexter_text", "menu_action", "other"):
        c = route(entry_point=ep, section="Manuscript", writing_mode="novel",
                  action="generate")
        assert isinstance(c, AssistantTaskContract)
        assert c.output_kind and c.validator_profile


# 2-4. Manuscript direct-writing actions route to direct content per mode.
def test_manuscript_direct_actions():
    c = route(section="Manuscript", writing_mode="screenplay", action="Dialogue")
    assert c.output_kind == DIRECT_CONTENT
    assert c.validator_profile == "screenplay_direct" and c.apply_allowed
    c2 = route(section="Manuscript", writing_mode="novel", action="generate")
    assert c2.output_kind == DIRECT_CONTENT and c2.validator_profile == "novel_direct"
    c3 = route(section="Manuscript", writing_mode="graphic_novel",
               action="Dialogue")
    assert c3.output_kind == DIRECT_CONTENT
    assert c3.validator_profile == "graphic_novel_direct"


# 5-8. Non-manuscript sections route to their own output kinds.
def test_section_routing():
    assert route(section="Outline", action="generate").output_kind == STRUCTURE
    assert route(section="PSYKE", action="generate").output_kind == CODEX
    assert route(section="Notes", action="generate").output_kind == NOTES
    assert route(section="Timeline", action="generate").output_kind == TIMELINE
    assert route(section="Dexter", action="format").output_kind == TRANSCRIPT


# 9-10. Suggest is suggestions; Structure action is structure (not direct).
def test_suggest_and_structure_actions():
    s = route(section="Manuscript", writing_mode="novel", action="suggest")
    assert s.output_kind == SUGGESTIONS and s.apply_allowed is False
    st = route(section="Manuscript", writing_mode="novel", action="structure")
    assert st.output_kind == STRUCTURE and st.apply_allowed is False


# 11. Direct writing with no target → clarification (never a planning essay).
def test_missing_target_triggers_clarification():
    c = route(section="Manuscript", writing_mode="screenplay", action="Dialogue",
              has_target=False)
    assert c.needs_clarification is True
    assert c.output_kind == CLARIFICATION
    assert c.clarification_question
    assert c.apply_allowed is False


# 12-13. Action (not mode/modifier) drives output kind; Dialogue stays direct.
def test_action_drives_output_not_modifier():
    # No "assistant_mode" parameter exists on route -> mode can't hijack action.
    assert route(section="Manuscript", writing_mode="screenplay",
                 action="Dialogue").output_kind == DIRECT_CONTENT
    assert route(section="Manuscript", writing_mode="screenplay",
                 action="rewrite").output_kind == DIRECT_CONTENT


# 14-18. Chat intent classification.
def test_chat_intent_routing():
    assert route(entry_point="chat", section="Chat",
                 action="ask", user_instruction="continue this scene"
                 ).output_kind == DIRECT_CONTENT
    assert route(entry_point="chat", section="Chat", action="ask",
                 user_instruction="analyze this scene").output_kind == ANALYSIS
    assert route(entry_point="chat", section="Chat", action="ask",
                 user_instruction="give me the structure").output_kind == STRUCTURE
    assert route(entry_point="chat", section="Chat", action="ask",
                 user_instruction="what is the theme?").output_kind == ANSWER


# 19-23. Cache key is unique per request shape + invalidates across versions.
def test_cache_key_discriminates():
    base = dict(project_id="p1", target_id="s1", user_instruction="go",
                target_text="hello")
    c_dialogue = route(section="Manuscript", writing_mode="screenplay",
                       action="Dialogue")
    c_rewrite = route(section="Manuscript", writing_mode="screenplay",
                      action="rewrite")
    c_outline = route(section="Outline", writing_mode="screenplay",
                      action="generate")
    c_novel = route(section="Manuscript", writing_mode="novel", action="Dialogue")
    k = cache_key(c_dialogue, **base)
    assert k == cache_key(c_dialogue, **base)               # stable
    assert k != cache_key(c_rewrite, **base)                # action
    assert k != cache_key(c_outline, **base)                # section
    assert k != cache_key(c_novel, **base)                  # writing mode
    assert k != cache_key(c_dialogue, **{**base, "target_text": "world"})  # text
    assert k != cache_key(c_dialogue, **{**base, "user_instruction": "x"})  # instr


# 24. apply_allowed is True only for direct content.
def test_apply_allowed_only_direct():
    assert route(section="Manuscript", writing_mode="novel",
                 action="generate").apply_allowed is True
    assert route(section="Outline", action="generate").apply_allowed is False
    assert route(section="PSYKE", action="generate").apply_allowed is False
    assert route(section="Manuscript", writing_mode="novel",
                 action="suggest").apply_allowed is False


# 25. Intent inference for the core actions.
def test_intent_inference():
    assert infer_intent("generate") == "write_content"
    assert infer_intent("dialogue") == "generate_dialogue"
    assert infer_intent("suggest") == "give_suggestions"
    assert infer_intent("structure") == "generate_structure"
    assert infer_intent("summarize") == "analyze"
    assert infer_intent("ask", "please continue the scene") == "write_content"
