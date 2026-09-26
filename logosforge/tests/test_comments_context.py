"""Comments -> Assistant/Logos/Counterpart context integration."""

from __future__ import annotations

from logosforge import assistant, counterpart
from logosforge.api import schemas
from logosforge.api.routes import assistant as assistant_routes
from logosforge.chat_context import CONTEXT_MAX_CHARS, build_chat_context
from logosforge.context_builder import (
    EDITORIAL_CONTEXT_MAX_CHARS,
    fit_editorial_contexts,
    gather_comments_context,
    gather_editorial_contexts,
)
from logosforge.db import Database
from logosforge.logos.actions import get_action
from logosforge.logos.context import build_logos_context
from logosforge.logos.prompt_builder import build_logos_messages


def _project_with_scene(title: str = "Comment Context"):
    db = Database()
    project = db.create_project(title)
    scene = db.create_scene(project.id, "Opening", content="Opening line")
    return db, project, scene


def _comment(
    db: Database,
    project_id: int,
    scene,
    *,
    body: str,
    resolved: bool = False,
    quote: str = "Opening",
    replies: list[dict] | None = None,
):
    return db.create_comment_with_replies(
        project_id,
        start_scene_id=scene.id,
        start_field="content",
        from_offset=0,
        end_scene_id=scene.id,
        end_field="content",
        to_offset=len(quote),
        quote=quote,
        body=body,
        resolved=resolved,
        replies=replies or [],
    )


def test_comments_context_empty_without_threads():
    db, project, _scene = _project_with_scene()
    assert gather_comments_context(db, project.id) == ""


def test_comments_context_includes_open_resolved_and_ordered_replies():
    db, project, scene = _project_with_scene()
    _comment(
        db,
        project.id,
        scene,
        body="Already settled.",
        resolved=True,
    )
    _comment(
        db,
        project.id,
        scene,
        body="Tighten this image.",
        replies=[
            {
                "source_id": "later",
                "body": "Second reply",
                "author": "reviewer",
                "sort_order": 2,
            },
            {
                "source_id": "first",
                "body": "First reply",
                "author": "writer",
                "sort_order": 0,
            },
        ],
    )

    context = gather_comments_context(db, project.id, scene.id)

    assert context.startswith("[Project Comments]")
    assert "OPEN threads" in context
    assert "RESOLVED threads" in context
    assert context.index("Tighten this image") < context.index("Already settled")
    assert context.index("Reply by writer: First reply") < context.index(
        "Reply by reviewer: Second reply",
    )
    assert "Opening · content 0-7" in context


def test_comments_context_prioritizes_active_scene_without_hiding_others():
    db, project, first = _project_with_scene()
    second = db.create_scene(project.id, "Second", content="Second line")
    _comment(db, project.id, first, body="Earlier other-scene comment.")
    _comment(
        db,
        project.id,
        second,
        body="Active-scene comment.",
        quote="Second",
    )

    context = gather_comments_context(db, project.id, second.id)

    assert context.index("Active-scene comment") < context.index(
        "Earlier other-scene comment",
    )


def test_comments_context_is_project_scoped():
    db, project, scene = _project_with_scene()
    other = db.create_project("Other")
    other_scene = db.create_scene(other.id, "Other Scene", content="Other")
    _comment(db, project.id, scene, body="Visible here.")
    _comment(
        db, other.id, other_scene, body="Must not leak.", quote="Other",
    )

    context = gather_comments_context(db, project.id)

    assert "Visible here" in context
    assert "Must not leak" not in context


def test_notes_and_comments_share_one_deterministic_character_budget():
    db, project, scene = _project_with_scene()
    for index in range(18):
        db.create_note(
            project.id,
            f"Pinned {index:02d}",
            (f"note-{index} " * 40),
            pinned=True,
        )
    for index in range(12):
        _comment(
            db,
            project.id,
            scene,
            body=(f"comment-{index} " * 40),
            replies=[{
                "body": f"reply-{index} " * 30,
                "author": "writer",
                "sort_order": 0,
            }],
        )

    first = gather_editorial_contexts(db, project.id, scene.id)
    second = gather_editorial_contexts(db, project.id, scene.id)
    notes_context, comments_context = first

    assert first == second
    assert notes_context.startswith("[Relevant Notes]")
    assert comments_context.startswith("[Project Comments]")
    assert len(notes_context) + len(comments_context) + 2 <= EDITORIAL_CONTEXT_MAX_CHARS
    assert "[...source truncated]" in notes_context
    assert "[...source truncated]" in comments_context


def test_short_editorial_source_gives_unused_budget_to_longer_source():
    notes = "[Relevant Notes]\n- short"
    comments = "[Project Comments]\n" + ("comment " * 1000)

    fitted_notes, fitted_comments = fit_editorial_contexts(
        notes, comments, char_budget=300,
    )

    assert fitted_notes == notes
    assert fitted_comments.startswith("[Project Comments]")
    assert len(fitted_notes) + len(fitted_comments) + 2 <= 300


def test_notes_only_context_preserves_legacy_text_without_new_truncation():
    notes = "  [Relevant Notes]\n" + ("durable research " * 100) + "\n"

    fitted_notes, fitted_comments = fit_editorial_contexts(
        notes, "", char_budget=120,
    )

    assert fitted_notes == notes
    assert fitted_comments == ""


def test_comments_only_context_remains_bounded():
    comments = "[Project Comments]\n" + ("editorial request " * 100)

    fitted_notes, fitted_comments = fit_editorial_contexts(
        "", comments, char_budget=120,
    )

    assert fitted_notes == ""
    assert len(fitted_comments) <= 120
    assert fitted_comments.startswith("[Project Comments]")
    assert fitted_comments.endswith("[...source truncated]")


def test_chat_context_includes_notes_and_comments_under_global_budget():
    db, project, scene = _project_with_scene()
    db.create_note(project.id, "Pinned research", "Keep the moon red.", pinned=True)
    _comment(db, project.id, scene, body="Keep the opening quiet.")

    context = build_chat_context(
        db,
        project.id,
        active_scene_id=scene.id,
        include_outline=False,
        include_psyke=False,
        include_memory=False,
    )

    assert "[Relevant Notes]" in context
    assert "Pinned research" in context
    assert "[Project Comments]" in context
    assert "Keep the opening quiet" in context
    assert len(context) <= CONTEXT_MAX_CHARS


def test_chat_context_without_comments_has_no_empty_comment_section():
    db, project, scene = _project_with_scene()
    db.create_note(project.id, "Pinned research", "A durable fact.", pinned=True)

    context = build_chat_context(
        db,
        project.id,
        active_scene_id=scene.id,
        include_outline=False,
        include_psyke=False,
        include_memory=False,
    )

    assert "[Relevant Notes]" in context
    assert "[Project Comments]" not in context


def test_chat_context_keeps_notes_when_comment_selection_fails(monkeypatch):
    db, project, scene = _project_with_scene()
    db.create_note(project.id, "Pinned research", "A durable fact.", pinned=True)

    def _fail(*_args, **_kwargs):
        raise RuntimeError("comment store unavailable")

    monkeypatch.setattr("logosforge.chat_context.gather_comments_context", _fail)
    context = build_chat_context(
        db,
        project.id,
        active_scene_id=scene.id,
        include_outline=False,
        include_psyke=False,
        include_memory=False,
    )

    assert "Pinned research" in context
    assert "Comments context unavailable" in context


def test_assistant_messages_keep_comments_separate_from_notes():
    messages = assistant.build_messages(
        "Assess the passage.",
        "[Scene Context]\nOpening line",
        notes_context="[Relevant Notes]\n- durable research",
        comments_context="[Project Comments]\nOPEN threads:\n- live request",
    )
    user_text = messages[1]["content"]

    assert user_text.index("[Relevant Notes]") < user_text.index(
        "[Project Comments]",
    )
    assert "live request" in user_text


def test_logos_messages_include_comment_threads():
    db, project, scene = _project_with_scene()
    _comment(db, project.id, scene, body="Explain the image, do not replace it.")
    context = build_logos_context(
        db,
        project.id,
        section_name="Manuscript",
        current_scene_id=scene.id,
        selected_text="Opening",
    )

    messages = build_logos_messages(db, context, get_action("explain_selection"))

    assert "[Project Comments]" in messages[1]["content"]
    assert "Explain the image" in messages[1]["content"]


def test_counterpart_messages_include_budgeted_notes_and_comments():
    messages = counterpart.build_counterpart_messages(
        "Give feedback.",
        "Scene text.",
        notes_context="[Relevant Notes]\n- durable research",
        comments_context="[Project Comments]\n- editorial decision",
    )
    user_text = messages[1]["content"]

    assert "[Relevant Notes]" in user_text
    assert "[Project Comments]" in user_text


def test_counterpart_route_selects_server_side_editorial_context(monkeypatch):
    db, project, scene = _project_with_scene()
    db.create_note(project.id, "Pinned research", "A durable fact.", pinned=True)
    _comment(db, project.id, scene, body="Question the final beat.")
    captured: dict[str, str] = {}

    def _capture(*_args, **kwargs):
        captured.update(kwargs)
        return "ok", False

    monkeypatch.setattr(counterpart, "run_counterpart", _capture)
    response = assistant_routes.counterpart(
        body=schemas.CounterpartRequestDTO(mode="Feedback"),
        project=project,
        db=db,
    )

    assert response.reply == "ok"
    assert "Pinned research" in captured["notes_context"]
    assert "Question the final beat" in captured["comments_context"]


def test_assistant_chat_route_injects_comment_context(monkeypatch):
    import importlib

    db, project, scene = _project_with_scene()
    _comment(db, project.id, scene, body="Preserve the unanswered question.")
    captured: dict[str, object] = {}

    def _capture(messages, *args, **kwargs):
        captured["messages"] = messages
        return "ok", False

    # Another isolation test deliberately evicts this module from sys.modules.
    # Resolve the live module here so a full-suite run cannot patch a stale
    # collection-time reference while the route imports the replacement.
    runtime_assistant = importlib.import_module("logosforge.assistant")
    monkeypatch.setattr(runtime_assistant, "chat_completion", _capture)
    monkeypatch.setattr(assistant_routes, "_build_provider", lambda: None)
    response = assistant_routes.assistant_chat(
        body=schemas.AssistantRequestDTO(
            message="What should I revise?",
            active_scene_id=scene.id,
        ),
        project=project,
        db=db,
    )

    assert response.reply == "ok"
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert "[Project Comments]" in messages[0]["content"]
    assert "Preserve the unanswered question" in messages[0]["content"]
