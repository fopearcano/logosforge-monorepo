"""Phase 10E — screenplay story-link graph + confirmed story links."""

from __future__ import annotations

import json
import warnings

import pytest

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import screenplay_graph as sg


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False)
    yield
    settings._instance = None


def _film_with_planted_object(db):
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_psyke_entry(db_project := pid, "Excalibur", "object")
    s1 = db.create_scene(pid, "Plant",
                         content="INT. HALL - DAY\n\nA gun rests on the mantle.\n\n"
                                 "ALICE\nKeep it safe.",
                         summary="x").id
    s2 = db.create_scene(pid, "Use",
                         content="EXT. FIELD - DAY\n\nAlice grabs the gun and fires.",
                         summary="x").id
    return pid, s1, s2


# ===========================================================================
# Model DTOs
# ===========================================================================


def test_node_dto_serializes():
    n = sg.ScreenplayGraphNode(id="scene:1", node_type="scene", label="Open",
                               scene_id=1, confidence=0.5)
    d = n.to_dict()
    assert json.dumps(d) and d["node_type"] == "scene" and d["confidence"] == 0.5


def test_edge_dto_serializes():
    e = sg.ScreenplayGraphEdge(id="e1", edge_type="setup_to_payoff",
                               source_node_id="a", target_node_id="b")
    assert json.dumps(e.to_dict())


def test_invalid_edge_type_rejected_by_builder_helper():
    assert not sg.is_valid_edge_type("nonsense_edge")
    assert sg.is_valid_edge_type("setup_to_payoff")


def test_graph_dto_has_schema_version():
    g = sg.ScreenplayGraph(project_id=1)
    assert g.to_dict()["schema_version"] == sg.SCHEMA_VERSION


# ===========================================================================
# Builder
# ===========================================================================


def test_builds_setup_payoff_edges():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    g = sg.build_screenplay_graph(db, pid)
    assert any(e.edge_type == "setup_to_payoff" for e in g.edges)


def test_builds_character_in_scene_edges():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    g = sg.build_screenplay_graph(db, pid)
    assert any(e.edge_type == "character_in_scene" for e in g.edges)
    assert any(n.node_type == "character" and n.label == "ALICE" for n in g.nodes)


def test_builds_psyke_to_scene_edges():
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    db.create_psyke_entry(pid, "Excalibur", "object")
    db.create_scene(pid, "S", content="INT. X - DAY\n\nExcalibur gleams here.",
                    summary="x")
    g = sg.build_screenplay_graph(db, pid)
    assert any(e.edge_type == "psyke_to_scene" for e in g.edges)


def test_nodes_deduped():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    g = sg.build_screenplay_graph(db, pid)
    ids = [n.id for n in g.nodes]
    assert len(ids) == len(set(ids))


def test_build_does_not_mutate_db():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    before = (len(db.get_all_scenes(pid)), len(db.get_story_links(pid)))
    sg.build_screenplay_graph(db, pid)
    after = (len(db.get_all_scenes(pid)), len(db.get_story_links(pid)))
    assert before == after


def test_build_does_not_call_llm(monkeypatch):
    import logosforge.assistant as assistant
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    sg.build_screenplay_graph(db, pid)
    assert calls == []


def test_current_scene_scope():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    g = sg.build_screenplay_graph(db, pid, scene_id=s2)
    scene_nodes = [n for n in g.nodes if n.node_type == "scene"]
    # Scene-scoped structural nodes only include the scoped scene (cross-scene
    # setup/payoff may still reference the planting scene).
    assert any(n.scene_id == s2 for n in scene_nodes)


def test_no_stale_project_leak():
    db = Database()
    p1, _, _ = _film_with_planted_object(db)
    p2 = db.create_project("P2", narrative_engine="screenplay").id
    db.create_scene(p2, "Empty", content="INT. X - DAY\n\nNothing of note here.",
                    summary="x")
    g2 = sg.build_screenplay_graph(db, p2)
    assert not any("gun" in (e.label or "").lower() for e in g2.edges)


def test_graph_references_not_copies():
    """Nodes hold ids/labels, not raw scene/PSYKE text."""
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    g = sg.build_screenplay_graph(db, pid)
    blob = json.dumps(g.to_dict())
    assert "rests on the mantle" not in blob   # no scene content copied


# ===========================================================================
# Persistence (StoryLink) — confirmed links
# ===========================================================================


def test_confirm_candidate_persists_link():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    link = sg.confirm_candidate(
        db, pid, link_type="setup_to_payoff", label="gun",
        source_type="scene", source_id=str(s1), target_type="scene",
        target_id=str(s2), source_scene_id=s1, target_scene_id=s2,
        evidence="gun planted then used", confidence=0.5)
    assert link.id is not None and link.status == "confirmed"
    assert len(db.get_story_links(pid, status="confirmed")) == 1


def test_dismiss_candidate_updates_status():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    link = sg.confirm_candidate(db, pid, link_type="setup_to_payoff", label="gun",
                                source_type="scene", source_id=str(s1),
                                target_type="scene", target_id=str(s2))
    sg.dismiss_link(db, link.id)
    assert db.get_story_link_by_id(link.id).status == "dismissed"


def test_resolved_link_persists():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    link = sg.confirm_candidate(db, pid, link_type="setup_to_payoff", label="gun",
                                source_type="scene", source_id=str(s1),
                                target_type="scene", target_id=str(s2))
    sg.resolve_link(db, link.id)
    assert db.get_story_link_by_id(link.id).status == "resolved"


def test_confirmed_link_appears_in_graph_distinct_from_candidate():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    sg.confirm_candidate(db, pid, link_type="motif_recurrence", label="gun",
                         source_type="scene", source_id=str(s1),
                         target_type="scene", target_id=str(s2))
    g = sg.build_screenplay_graph(db, pid)
    statuses = {e.status for e in g.edges}
    assert "confirmed" in statuses and "candidate" in statuses


def test_dismissed_link_excluded_from_graph():
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    link = sg.confirm_candidate(db, pid, link_type="motif_recurrence", label="gun",
                                source_type="scene", source_id=str(s1),
                                target_type="scene", target_id=str(s2))
    sg.dismiss_link(db, link.id)
    g = sg.build_screenplay_graph(db, pid)
    assert not any(e.id == f"link:{link.id}" for e in g.edges)


def test_migration_idempotent_old_projects_safe():
    """The StoryLink table is created idempotently; old/empty DBs load fine."""
    db = Database()
    db._migrate()                      # re-run; must not raise
    pid = db.create_project("Old").id  # pre-existing-style project
    assert db.get_story_links(pid) == []
    # Building a graph on a project with no links is safe.
    assert isinstance(sg.build_screenplay_graph(db, pid).to_dict(), dict)


def test_links_not_auto_confirmed():
    """Generated candidates never persist on their own — graph build is read-only."""
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    sg.build_screenplay_graph(db, pid)
    assert db.get_story_links(pid) == []


# ===========================================================================
# Logos integration
# ===========================================================================


def test_graph_logos_actions_registered_deterministic_screenplay_only():
    from logosforge.logos import actions as A
    from logosforge.logos import deterministic as det
    for name in ("sp_show_story_links", "sp_explain_link"):
        act = A.get_action(name)
        assert act and act.modes == ("screenplay",) and act.deterministic
        assert det.is_deterministic(name)


def test_graph_actions_do_not_dominate_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    ctl = LogosController(db)
    names = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "sp_show_story_links" not in names


def test_show_story_links_action_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def boom(*a, **k):
        raise AssertionError("deterministic graph action must not use the LLM")

    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    ctl = LogosController(db, provider_resolver=boom, chat_fn=boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=s2)
    res = ctl.run(ctx, "sp_show_story_links")
    assert res.ok and "node(s)" in res.message
    assert res.proposed_operations == []


# ===========================================================================
# Assistant context
# ===========================================================================


def test_assistant_context_includes_story_links():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=s2)
    assert "[Screenplay Story Links]" in ctx


def test_story_links_block_capped():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=s2)
    block = ctx.split("[Screenplay Story Links]")[-1].split("[")[0]
    assert block.count("\n- ") <= 9   # at most 3 per group x 3 groups


def test_story_links_block_disableable_and_novel_absent():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.settings import get_manager
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    get_manager().set("include_screenplay_links_in_assistant_context", False)
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=s2)
    assert "[Screenplay Story Links]" not in ctx
    nov = db.create_project("Book", narrative_engine="novel").id
    nsid = db.create_scene(nov, "S", content="A gun.", summary="x").id
    nctx = gather_injected_context(db, nov, section_name="Manuscript", scene_id=nsid)
    assert "[Screenplay Story Links]" not in nctx


def test_assistant_assembly_no_llm_no_mutation(monkeypatch):
    import logosforge.assistant as assistant
    from logosforge.assistant_context_policy import gather_injected_context
    calls = []
    monkeypatch.setattr(assistant, "chat_completion",
                        lambda *a, **k: calls.append(1) or ("", False))
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    before = len(db.get_story_links(pid))
    gather_injected_context(db, pid, section_name="Manuscript", scene_id=s2)
    assert calls == []
    assert len(db.get_story_links(pid)) == before


# ===========================================================================
# Health integration
# ===========================================================================


def test_health_link_coverage_and_candidate_density():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    report = HealthEngine(db, pid).generate_report()
    by = {m.category: m for m in report.metrics}
    assert M.CAT_LINK_COVERAGE in by and M.CAT_CANDIDATE_DENSITY in by


def test_health_confirmed_links_improve_coverage():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    # Before confirming: coverage is watch/unknown.
    before = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    sg.confirm_candidate(db, pid, link_type="setup_to_payoff", label="gun",
                         source_type="scene", source_id=str(s1),
                         target_type="scene", target_id=str(s2))
    after = {m.category: m for m in HealthEngine(db, pid).generate_report().metrics}
    assert after[M.CAT_LINK_COVERAGE].status == M.STATUS_STABLE
    assert before[M.CAT_LINK_COVERAGE].status != M.STATUS_STABLE


def test_novel_health_has_no_link_categories():
    from logosforge.logos.health import HealthEngine
    from logosforge.logos.health import metric as M
    db = Database()
    pid = db.create_project("Book", narrative_engine="novel").id
    db.create_scene(pid, "Ch1", content="A quiet morning.", summary="x")
    cats = {m.category for m in HealthEngine(db, pid).generate_report().metrics}
    assert M.CAT_LINK_COVERAGE not in cats


# ===========================================================================
# Export
# ===========================================================================


def test_screenplay_graph_json_export():
    from logosforge.export import export_screenplay_graph_json
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    data = json.loads(export_screenplay_graph_json(db, pid))
    assert data["schema_version"] == sg.SCHEMA_VERSION
    assert data["project"]["writing_mode"] == "screenplay"
    assert "nodes" in data and "edges" in data


def test_story_links_json_export():
    from logosforge.export import export_story_links_json
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    sg.confirm_candidate(db, pid, link_type="setup_to_payoff", label="gun",
                         source_type="scene", source_id=str(s1),
                         target_type="scene", target_id=str(s2))
    data = json.loads(export_story_links_json(db, pid))
    assert data["schema_version"] == 1
    assert len(data["story_links"]) == 1
    assert data["story_links"][0]["status"] == "confirmed"


def test_existing_exports_unbroken():
    from logosforge.export import export_json, export_screenplay
    db = Database()
    pid, s1, s2 = _film_with_planted_object(db)
    assert json.loads(export_json(db, pid))["project"]["writing_mode"] == "screenplay"
    assert "Writing Mode: Screenplay" in export_screenplay(db, pid)


# ===========================================================================
# Guards
# ===========================================================================


def test_build_active_provider_unchanged():
    from logosforge.providers import build_active_provider
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", "OpenAI")
    mgr.set("ai_base_url", "https://api.openai.com/v1")
    mgr.set("ai_model", "gpt-4o")
    p = build_active_provider(require_configured=True)
    assert p is not None and p.name == "OpenAI"


def test_strategy_screenplay_active():
    from logosforge.logos.strategy.router import StrategyRouter
    from logosforge.settings import get_manager
    get_manager().set("strategy_enabled", True)
    db = Database()
    pid = db.create_project("Film", narrative_engine="screenplay").id
    assert "screenplay" in StrategyRouter(db, pid).decide("Manuscript").active_strategies
