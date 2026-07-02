"""Tests for COUNTERPART — dialogic narrative assistant."""

from logosforge.counterpart import (
    DIALOGIC_MODES,
    SYSTEM_PROMPT,
    build_counterpart_messages,
)


# -- System prompt constraints -------------------------------------------------

def test_system_prompt_contains_counterpart():
    assert "COUNTERPART" in SYSTEM_PROMPT


def test_system_prompt_forbids_rewrite():
    assert "NEVER rewrite" in SYSTEM_PROMPT


def test_system_prompt_forbids_commands():
    assert "NEVER execute commands" in SYSTEM_PROMPT


def test_system_prompt_no_flattery():
    assert "No flattery" in SYSTEM_PROMPT


# -- Dialogic modes ------------------------------------------------------------

def test_dialogic_modes_exist():
    assert "Feedback" in DIALOGIC_MODES
    assert "Critique" in DIALOGIC_MODES
    assert "Interpret" in DIALOGIC_MODES
    assert "Ask Back" in DIALOGIC_MODES
    assert "Compare" in DIALOGIC_MODES


def test_dialogic_modes_count():
    assert len(DIALOGIC_MODES) == 5


def test_feedback_mode_no_rewriting():
    assert "No rewriting" in DIALOGIC_MODES["Feedback"]


def test_critique_mode_no_rewrites():
    assert "No suggestions for rewrites" in DIALOGIC_MODES["Critique"]


def test_ask_back_questions_only():
    assert "Questions only" in DIALOGIC_MODES["Ask Back"]


def test_compare_does_not_write():
    assert "Do NOT write the alternatives" in DIALOGIC_MODES["Compare"]


# -- Message construction ------------------------------------------------------

def test_build_messages_basic():
    msgs = build_counterpart_messages(
        "Give feedback on this scene.",
        "Scene: The hero enters the castle.",
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_build_messages_system_is_counterpart():
    msgs = build_counterpart_messages(
        "Critique this.",
        "Scene text here.",
    )
    assert "COUNTERPART" in msgs[0]["content"]


def test_build_messages_includes_scene():
    msgs = build_counterpart_messages(
        "Feedback",
        "The dragon breathed fire.",
    )
    assert "The dragon breathed fire." in msgs[1]["content"]


def test_build_messages_includes_mode_prompt():
    msgs = build_counterpart_messages(
        "What is this scene doing?",
        "Scene text.",
    )
    assert "What is this scene doing?" in msgs[1]["content"]


def test_build_messages_includes_user_note():
    msgs = build_counterpart_messages(
        "Feedback",
        "Scene text.",
        user_note="Focus on pacing.",
    )
    assert "Focus on pacing" in msgs[1]["content"]
    assert "Writer's focus:" in msgs[1]["content"]


def test_build_messages_includes_outline():
    msgs = build_counterpart_messages(
        "Critique",
        "Scene text.",
        outline_context="Act 1: Setup",
    )
    assert "Act 1: Setup" in msgs[1]["content"]


def test_build_messages_includes_story_memory():
    msgs = build_counterpart_messages(
        "Interpret",
        "Scene text.",
        story_memory_context="[Story Memory]\n- Hero: broken",
    )
    assert "[Story Memory]" in msgs[1]["content"]


def test_build_messages_includes_psyke():
    msgs = build_counterpart_messages(
        "Feedback",
        "Scene text.",
        psyke_context="[Story Bible]\nTheme: loyalty",
    )
    assert "Theme: loyalty" in msgs[1]["content"]


def test_build_messages_includes_graph():
    msgs = build_counterpart_messages(
        "Feedback",
        "Scene text.",
        graph_context="[Graph]\nHero -> Villain: enmity",
    )
    assert "Hero -> Villain" in msgs[1]["content"]


def test_build_messages_no_mode_context():
    """COUNTERPART does not use adaptive AI mode — it has its own voice."""
    msgs = build_counterpart_messages(
        "Feedback",
        "Scene text.",
    )
    # No mode_context parameter exists
    user_content = msgs[1]["content"]
    assert "[AI Mode:" not in user_content


def test_build_messages_empty_optional_fields():
    msgs = build_counterpart_messages(
        "Compare alternatives",
        "Scene text.",
        outline_context="",
        story_memory_context="",
        psyke_context="",
        graph_context="",
        user_note="",
    )
    user_content = msgs[1]["content"]
    assert "Scene text." in user_content
    assert "Compare alternatives" in user_content
    # Should not have empty sections with double newlines
    assert "\n\n\n" not in user_content


# -- Safety: no action execution -----------------------------------------------

def test_system_prompt_no_ui_actions():
    assert "NEVER suggest UI actions" in SYSTEM_PROMPT or "NEVER execute" in SYSTEM_PROMPT


def test_system_prompt_grounds_in_text():
    assert "actual text" in SYSTEM_PROMPT


# -- Each dialogic mode produces valid messages --------------------------------

def test_all_modes_produce_messages():
    for mode_name, mode_prompt in DIALOGIC_MODES.items():
        msgs = build_counterpart_messages(
            mode_prompt,
            "The hero stood at the edge of the cliff.",
        )
        assert len(msgs) == 2, f"Mode {mode_name} failed"
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "cliff" in msgs[1]["content"]
