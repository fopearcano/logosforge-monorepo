"""Tests for chat memory: summarization, personality, action parsing."""

from logosforge.chat_memory import (
    RECENT_WINDOW,
    SUMMARIZE_THRESHOLD,
    ActionProposal,
    build_memory_frame,
    build_system_prompt,
    heuristic_summary,
    is_valid_personality,
    needs_summary_update,
    parse_action_proposals,
    personality_prompt,
    strip_action_blocks,
    visible_reply_text,
)
from logosforge.db import Database
from logosforge.models import CHAT_PERSONALITIES


# -- Personality presets ------------------------------------------------------

def test_default_personality_prompt_exists():
    assert personality_prompt("default")


def test_all_personalities_have_prompts():
    for p in CHAT_PERSONALITIES:
        prompt = personality_prompt(p)
        assert prompt
        assert len(prompt) > 20


def test_unknown_personality_falls_back():
    assert personality_prompt("nope") == personality_prompt("default")


def test_is_valid_personality():
    assert is_valid_personality("mentor")
    assert not is_valid_personality("unicorn")


def test_personalities_distinct():
    prompts = {p: personality_prompt(p) for p in CHAT_PERSONALITIES}
    # Each personality should have a unique prompt
    assert len(set(prompts.values())) == len(CHAT_PERSONALITIES)


# -- System prompt assembly ---------------------------------------------------

def test_system_prompt_includes_personality():
    prompt = build_system_prompt("mentor", "")
    assert "mentor" in prompt.lower()


def test_system_prompt_includes_context():
    prompt = build_system_prompt("default", "[Project] Test story")
    assert "[Project] Test story" in prompt


def test_system_prompt_includes_action_rules():
    prompt = build_system_prompt("default", "")
    assert "<action>" in prompt
    assert "create_psyke_entry" in prompt
    assert "delete_" in prompt  # mentions destructive guard


def test_system_prompt_handles_empty_context():
    prompt = build_system_prompt("default", "   ")
    assert "Project context" not in prompt


# -- Memory frame -------------------------------------------------------------

def _make_msg(id_, role, content):
    class _M:
        def __init__(self):
            self.id = id_
            self.role = role
            self.content = content
    return _M()


def test_memory_frame_recent_window():
    msgs = [_make_msg(i, "user", f"m{i}") for i in range(1, 21)]
    frame = build_memory_frame(msgs, "summary text", 0)
    assert frame.summary == "summary text"
    assert len(frame.recent) == RECENT_WINDOW
    assert frame.recent[0]["content"] == f"m{21 - RECENT_WINDOW}"


def test_memory_frame_empty_messages():
    frame = build_memory_frame([], "", 0)
    assert frame.recent == []
    assert frame.summary == ""


def test_memory_frame_fewer_than_window():
    msgs = [_make_msg(i, "user", f"m{i}") for i in range(1, 4)]
    frame = build_memory_frame(msgs, "", 0)
    assert len(frame.recent) == 3


# -- Summary trigger ----------------------------------------------------------

def test_needs_summary_under_threshold():
    msgs = [_make_msg(i, "user", "x") for i in range(1, 5)]
    assert needs_summary_update(msgs, 0) is False


def test_needs_summary_over_threshold():
    msgs = [_make_msg(i, "user", "x") for i in range(1, SUMMARIZE_THRESHOLD + 5)]
    assert needs_summary_update(msgs, 0) is True


def test_needs_summary_already_caught_up():
    msgs = [_make_msg(i, "user", "x") for i in range(1, SUMMARIZE_THRESHOLD + 5)]
    last_id = msgs[-RECENT_WINDOW].id - 1
    assert needs_summary_update(msgs, last_id + 100) is False


# -- Heuristic summary --------------------------------------------------------

def test_heuristic_summary_appends():
    msgs = [_make_msg(1, "user", "first"), _make_msg(2, "assistant", "reply")]
    summary, last_id = heuristic_summary("", msgs)
    assert "first" in summary
    assert "reply" in summary
    assert last_id == 2


def test_heuristic_summary_extends_previous():
    summary, _ = heuristic_summary(
        "earlier note", [_make_msg(5, "user", "new thing")],
    )
    assert "earlier note" in summary
    assert "new thing" in summary


def test_heuristic_summary_truncates_long_messages():
    long_text = "x" * 500
    summary, _ = heuristic_summary("", [_make_msg(1, "user", long_text)])
    # Should be truncated to ~120 chars
    assert "..." in summary


def test_heuristic_summary_empty_input():
    summary, last_id = heuristic_summary("prev", [])
    assert summary == "prev"
    assert last_id == 0


# -- Action proposal parsing --------------------------------------------------

def test_parse_action_tag():
    text = (
        'I will create a PSYKE entry.\n'
        '<action>{"action": "create_psyke_entry", "args": {"name": "Bob"}, '
        '"label": "Create Bob entry"}</action>'
    )
    proposals = parse_action_proposals(text)
    assert len(proposals) == 1
    assert proposals[0].action == "create_psyke_entry"
    assert proposals[0].args == {"name": "Bob"}
    assert proposals[0].label == "Create Bob entry"


def test_parse_action_no_label_humanizes():
    text = '<action>{"action": "create_note", "args": {}}</action>'
    proposals = parse_action_proposals(text)
    assert len(proposals) == 1
    assert "Create note" == proposals[0].label


def test_parse_multiple_actions():
    text = (
        '<action>{"action": "a1", "args": {}}</action>'
        '<action>{"action": "a2", "args": {}}</action>'
    )
    proposals = parse_action_proposals(text)
    assert [p.action for p in proposals] == ["a1", "a2"]


def test_parse_invalid_json_skipped():
    text = '<action>{not json}</action>'
    assert parse_action_proposals(text) == []


def test_parse_no_action_returns_empty():
    assert parse_action_proposals("Just a friendly reply.") == []


def test_parse_action_missing_closing_tag():
    # Live failure: the model dropped the </action> closing tag.
    text = (
        '<action>{"action": "create_scene", '
        '"args": {"title": "The Harbor at Midnight"}, "label": "Add Scene"}'
    )
    proposals = parse_action_proposals(text)
    assert len(proposals) == 1
    assert proposals[0].action == "create_scene"
    assert proposals[0].args == {"title": "The Harbor at Midnight"}


def test_strip_action_missing_closing_tag_leaves_no_json():
    text = (
        '<action>{"action": "create_scene", '
        '"args": {"title": "X"}, "label": "Add Scene"}'
    )
    cleaned = strip_action_blocks(text)
    assert "<action>" not in cleaned
    assert "create_scene" not in cleaned
    assert cleaned == ""


def test_unclosed_action_only_reply_is_narrated():
    # The end-to-end guard: an unclosed action-only reply must not show raw JSON.
    text = '<action>{"action": "create_scene", "args": {"title": "X"}, "label": "Add Scene"}'
    out = visible_reply_text(text, parse_action_proposals(text))
    assert "<action>" not in out
    assert "Add Scene" in out


def test_two_tight_fences_no_duplicate():
    # Two close ```json fences must not yield a duplicate from the first
    # fence's closing ``` being read as a second opener.
    text = (
        '```json\n{"action": "a"}\n```\n'
        '```json\n{"action": "b"}\n```'
    )
    proposals = parse_action_proposals(text)
    assert [p.action for p in proposals] == ["a", "b"]


def test_parse_json_fence_fallback():
    text = (
        'Here is what I would do:\n'
        '```json\n'
        '{"action": "create_scene", "args": {"title": "X"}}\n'
        '```'
    )
    proposals = parse_action_proposals(text)
    assert len(proposals) == 1
    assert proposals[0].action == "create_scene"


def test_strip_action_blocks_removes_tags():
    text = 'visible <action>{"action": "x"}</action> more visible'
    cleaned = strip_action_blocks(text)
    assert "<action>" not in cleaned
    assert "visible" in cleaned
    assert "more visible" in cleaned


def test_strip_action_blocks_removes_fences():
    text = 'Reply.\n```json\n{"action": "x"}\n```\nDone.'
    cleaned = strip_action_blocks(text)
    assert "```" not in cleaned
    assert "Reply." in cleaned
    assert "Done." in cleaned


def test_action_proposal_dataclass():
    p = ActionProposal(action="x", args={"k": 1}, label="lbl", raw="<action>...")
    assert p.action == "x"
    assert p.args == {"k": 1}


# -- Visible reply text (no empty "(no response)" bubbles) --------------------

def test_visible_reply_keeps_prose():
    raw = 'Here you go.\n<action>{"action": "x", "label": "L"}</action>'
    assert visible_reply_text(raw, parse_action_proposals(raw)) == "Here you go."


def test_visible_reply_narrates_action_only():
    # The live failure: model returns ONLY an action block, no prose.
    raw = '<action>{"action": "create_psyke_entry", "label": "Flaws of Ada Reyes"}</action>'
    out = visible_reply_text(raw, parse_action_proposals(raw))
    assert out != "(no response)"
    assert "Flaws of Ada Reyes" in out


def test_visible_reply_narrates_multiple_actions():
    raw = (
        '<action>{"action": "a", "label": "A"}</action>'
        '<action>{"action": "b", "label": "B"}</action>'
    )
    out = visible_reply_text(raw, parse_action_proposals(raw))
    assert "2" in out and "(no response)" not in out


def test_visible_reply_truly_empty_falls_back():
    assert visible_reply_text("   ", []) == "(no response)"


def test_action_rules_require_conversational_reply():
    # The system prompt should steer the model away from action-only turns.
    prompt = build_system_prompt("default", "")
    assert "only an action block" in prompt
