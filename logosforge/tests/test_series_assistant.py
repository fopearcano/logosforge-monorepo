"""Tests for Series-aware Assistant: review checks, context, commands."""

import pytest

from logosforge.db import Database
from logosforge.narrative_engines import SERIES_ENGINE
from logosforge.psyke_series import build_series_memory_context, set_series_memory
from logosforge.series_review import (
    SERIES_COMMANDS,
    SeriesReviewCheck,
    format_series_command,
    review_series,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _show(db):
    return db.create_project(
        "Show", narrative_engine="series", default_writing_format="series",
    )


def _types(checks):
    return {c.check_type for c in checks}


# =========================================================================
# 1. Engine priorities (§1)
# =========================================================================

def test_engine_priorities_episodic():
    for pr in ("episode engine", "season arc", "series arc",
               "A/B/C plot balance", "continuity", "cliffhangers",
               "delayed payoff", "unresolved threads",
               "character progression across episodes", "callbacks"):
        assert pr in SERIES_ENGINE.assistant_priorities


def test_engine_context_block_is_showrunner():
    block = SERIES_ENGINE.format_context_block()
    assert "[Narrative Engine: Series]" in block
    assert "episode engine" in block


# =========================================================================
# 2. Review checks (§2, §4)
# =========================================================================

def test_review_detects_missing_episode_engine():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    db.create_episode(s.id, title="Pilot", logline="A body turns up")
    assert "episode_engine" in _types(review_series(db, p.id))


def test_episode_engine_present_passes():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    db.create_episode(s.id, title="Pilot", logline="x",
                      episode_engine="mystery", cliffhanger="phone rings")
    assert "episode_engine" not in _types(review_series(db, p.id))


def test_review_detects_no_a_plot():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    e = db.create_episode(s.id, title="Pilot", episode_engine="case",
                          cliffhanger="hook")
    db.create_episode_plotline(e.id, type="B", title="romance")
    assert "abc_balance" in _types(review_series(db, p.id))


def test_a_plot_present_balances():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    e = db.create_episode(s.id, title="Pilot", episode_engine="case",
                          cliffhanger="hook")
    db.create_episode_plotline(e.id, type="A", title="the case")
    db.create_episode_plotline(e.id, type="B", title="romance")
    assert "abc_balance" not in _types(review_series(db, p.id))


def test_review_detects_missing_cliffhanger():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    # Two episodes so the first is non-final and should hook the next.
    db.create_episode(s.id, title="Pilot", logline="x", episode_engine="case")
    db.create_episode(s.id, title="Two", logline="y", episode_engine="case",
                      cliffhanger="end")
    checks = review_series(db, p.id)
    cliff = [c for c in checks if c.check_type == "cliffhanger"]
    assert any("Pilot" in c.message for c in cliff)


def test_review_detects_unresolved_payoff():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    e1 = db.create_episode(s.id, title="Pilot", logline="x",
                           episode_engine="case", cliffhanger="hook")
    db.create_series_arc(p.id, scope="mystery", title="Who killed Laura",
                         setup_episode_id=e1.id, status="active")
    assert "unresolved_payoff" in _types(review_series(db, p.id))


def test_tracked_payoff_passes():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    e1 = db.create_episode(s.id, title="Pilot", episode_engine="c",
                           cliffhanger="h")
    e2 = db.create_episode(s.id, title="Finale", episode_engine="c",
                           cliffhanger="h")
    db.create_series_arc(p.id, scope="mystery", title="Who killed Laura",
                         setup_episode_id=e1.id, payoff_episode_id=e2.id,
                         status="active")
    assert "unresolved_payoff" not in _types(review_series(db, p.id))


def test_review_flags_unresolved_threads():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    db.create_episode(s.id, title="Pilot", episode_engine="c", cliffhanger="h")
    db.create_series_arc(p.id, scope="mystery", title="Open", status="active")
    assert "unresolved_threads" in _types(review_series(db, p.id))


def test_review_surfaces_continuity_flags():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    db.create_episode(s.id, title="Pilot", episode_engine="c", cliffhanger="h")
    cooper = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    set_series_memory(db, cooper.id, continuity_flags="lost an eye in ep3")
    checks = review_series(db, p.id)
    cont = [c for c in checks if c.check_type == "continuity"]
    assert cont and "lost an eye" in cont[0].message


def test_review_typed_and_empty_safe():
    db = Database()
    p = _show(db)
    assert review_series(db, p.id) == []
    s = db.create_season(p.id, title="Season 1")
    db.create_episode(s.id, title="Pilot", logline="x")
    assert all(isinstance(c, SeriesReviewCheck) for c in review_series(db, p.id))


def test_review_episode_scoped():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    e1 = db.create_episode(s.id, title="Pilot", logline="x")
    db.create_episode(s.id, title="Two", logline="y")
    # Scoped to e1: only e1's checks, no project-level arc checks.
    scoped = review_series(db, p.id, episode_id=e1.id)
    assert all(c.episode_id == e1.id for c in scoped)


# =========================================================================
# 3. Context builder (§3) — series-specific facets
# =========================================================================

def test_context_includes_setup_payoff_chain():
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    e1 = db.create_episode(s.id, title="Pilot")
    e2 = db.create_episode(s.id, title="Finale")
    db.create_series_arc(p.id, scope="mystery", title="Who killed Laura",
                         setup_episode_id=e1.id, payoff_episode_id=e2.id,
                         status="active")
    ctx = build_series_memory_context(db, p.id, e2.id)
    assert "Setup→payoff chains" in ctx
    assert "Who killed Laura" in ctx


def test_context_empty_when_no_series_data():
    db = Database()
    p = _show(db)
    assert build_series_memory_context(db, p.id) == ""


def test_assistant_uses_psyke_series_context():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    db.create_episode(s.id, title="Pilot")
    cooper = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    set_series_memory(db, cooper.id, episode_state="on the run")
    db.create_scene(p.id, "Scene", content="x")
    panel = AssistantPanel(db, p.id)
    structural = panel._build_context()[8]
    assert "[Series Memory]" in structural
    assert "on the run" in structural


def test_novel_project_gets_no_series_context():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = db.create_project("Novel")
    db.create_scene(p.id, "Chapter 1", content="x")
    panel = AssistantPanel(db, p.id)
    assert "[Series Memory]" not in panel._build_context()[8]


# =========================================================================
# 4. /series commands (§5)
# =========================================================================

def _seed_commands(db):
    p = _show(db)
    s = db.create_season(p.id, title="Season 1")
    e1 = db.create_episode(s.id, title="Pilot", logline="x",
                           cliffhanger="the phone rings")
    e2 = db.create_episode(s.id, title="Finale", episode_engine="reveal",
                           cliffhanger="cut to black")
    db.create_series_arc(p.id, scope="mystery", title="Who killed Laura",
                         setup_episode_id=e1.id, payoff_episode_id=e2.id,
                         status="active")
    db.create_series_arc(p.id, scope="character", title="Open thread",
                         setup_episode_id=e1.id, status="active")
    cooper = db.create_psyke_entry(p.id, "Cooper", entry_type="character")
    set_series_memory(db, cooper.id, episode_state="grieving",
                      continuity_flags="wears the ring")
    return p


def test_command_check_reports_issues():
    db = Database()
    p = _seed_commands(db)
    out = format_series_command(db, p.id, "check")
    assert "Series review" in out
    assert "Pilot" in out  # Pilot has no engine → flagged


def test_command_arcs_lists_arcs():
    db = Database()
    p = _seed_commands(db)
    out = format_series_command(db, p.id, "arcs")
    assert "Who killed Laura" in out and "mystery" in out


def test_command_continuity_shows_ledger():
    db = Database()
    p = _seed_commands(db)
    out = format_series_command(db, p.id, "continuity")
    assert "Cooper" in out and "wears the ring" in out


def test_command_cliffhanger_lists_hooks():
    db = Database()
    p = _seed_commands(db)
    out = format_series_command(db, p.id, "cliffhanger")
    assert "the phone rings" in out


def test_command_payoff_shows_chain_and_open():
    db = Database()
    p = _seed_commands(db)
    out = format_series_command(db, p.id, "payoff")
    assert "Who killed Laura" in out          # chain
    assert "Open thread" in out                # awaiting payoff


def test_command_default_is_check():
    db = Database()
    p = _seed_commands(db)
    assert format_series_command(db, p.id, "") == \
        format_series_command(db, p.id, "check")


def test_command_unknown_lists_options():
    db = Database()
    p = _show(db)
    out = format_series_command(db, p.id, "bogus")
    for c in SERIES_COMMANDS:
        assert f"/series {c}" in out


def test_chat_view_series_command_integration():
    from logosforge.ui.chat_view import ChatView
    db = Database()
    p = _seed_commands(db)
    view = ChatView(db, p.id)
    assert view._handle_slash_command("/series arcs") is True
    msgs = db.get_chat_messages(p.id)
    assert any("Who killed Laura" in m.content for m in msgs if m.role == "system")


def test_chat_view_series_command_rejected_for_novel():
    from logosforge.ui.chat_view import ChatView
    db = Database()
    p = db.create_project("Novel")
    view = ChatView(db, p.id)
    assert view._handle_slash_command("/series check") is True
    msgs = db.get_chat_messages(p.id)
    assert any("only available for Series" in m.content
               for m in msgs if m.role == "system")
