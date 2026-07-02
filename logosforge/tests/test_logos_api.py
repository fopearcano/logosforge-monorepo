"""HTTP exposure of the core Logos engine (logosforge.logos) — the single Logos
every frontend consumes instead of reinventing one. Covers the action catalog,
the deterministic connect_to_psyke action, an LLM action's offline-preview
degradation, the generative flag, and the headless (Qt-free) import contract."""

import pytest
from fastapi.testclient import TestClient

from logosforge.api import ApiConfig, create_api
from logosforge.db import Database


@pytest.fixture
def env():
    db = Database()
    app = create_api(db=db, config=ApiConfig(mode="desktop"))
    p = db.create_project("LogosTest", narrative_engine="novel")
    return TestClient(app), db, p.id


def test_logos_actions_catalog_inline_section(env):
    client, _, pid = env
    actions = client.get(f"/api/projects/{pid}/logos/actions", params={"section": "Inline"}).json()
    names = {a["name"] for a in actions}
    # the ported inline family + the deterministic connect action
    assert {"inline_rewrite", "inline_expand", "inline_compress", "inline_summarize",
            "connect_to_psyke"} <= names
    by = {a["name"]: a for a in actions}
    assert by["inline_rewrite"]["generative"] is True            # transform -> apply
    assert by["inline_summarize"]["generative"] is False         # diagnostic
    assert by["connect_to_psyke"]["deterministic"] is True
    assert by["inline_rewrite"]["needs_selection"] is True


def test_logos_run_connect_to_psyke_is_deterministic(env):
    """connect_to_psyke runs with NO provider (deterministic) and finds matches."""
    client, db, pid = env
    db.create_psyke_entry(pid, "Mara Voss", entry_type="character")
    db.create_psyke_entry(pid, "The Kraken", entry_type="other")
    r = client.post(f"/api/projects/{pid}/logos/run", json={
        "action": "connect_to_psyke", "section": "Inline",
        "selected_text": "Mara stared at the water.",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and "Mara Voss" in body["message"]
    assert "The Kraken" not in body["message"]          # 'water' != 'kraken'
    assert body["generative"] is False


def test_logos_run_llm_action_returns_result(env):
    """An LLM action runs end-to-end through the route and returns a LogosResult
    shape. ``ok`` depends on provider availability in the environment; the route
    must never crash and must report the generative flag for an inline transform."""
    client, _, pid = env
    body = client.post(f"/api/projects/{pid}/logos/run", json={
        "action": "inline_rewrite", "section": "Inline",
        "selected_text": "the cat sat",
    }).json()
    assert body["action"] == "inline_rewrite" and body["generative"] is True
    assert isinstance(body["ok"], bool)


def test_logos_controller_offline_preview():
    """With NO provider, an LLM action degrades to a safe offline preview (ok=True)
    rather than failing — proven deterministically at the controller layer."""
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.controller import LogosController
    db = Database()
    p = db.create_project("Off", narrative_engine="novel")
    ctx = build_logos_context(db, p.id, section_name="Inline", selected_text="the cat sat")
    res = LogosController(db, provider_resolver=lambda: None).run(ctx, "inline_rewrite")
    assert res.ok is True and "preview" in res.message.lower()


def test_logos_proactive_scan(env):
    """The proactive endpoint scans the project (rule-based, read-only) and returns
    a well-shaped list — empty or not depending on detectors; never errors."""
    client, db, pid = env
    db.create_scene(pid, "A", content="x")
    r = client.get(f"/api/projects/{pid}/logos/proactive")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    for it in items:  # whatever the detectors surface must carry the DTO shape
        assert {"id", "type", "title", "severity", "section_name"} <= set(it)
    # a section filter is accepted too
    assert client.get(f"/api/projects/{pid}/logos/proactive", params={"section": "Manuscript"}).status_code == 200


def test_logos_run_unknown_action(env):
    client, _, pid = env
    body = client.post(f"/api/projects/{pid}/logos/run",
                       json={"action": "does_not_exist"}).json()
    assert body["ok"] is False and body["error"]


def test_logos_route_is_qt_free():
    """A headless API consumer must never pull in Qt. Checked in a CLEAN subprocess
    (the shared pytest process loads PySide6 via unrelated Qt-UI tests)."""
    import subprocess
    import sys
    code = (
        "import sys;"
        "import logosforge.api.routes.logos;"
        "from logosforge.logos.controller import LogosController;"
        "from logosforge.logos.context import build_logos_context;"
        "from logosforge.logos.prompt_builder import build_logos_messages;"
        "import logosforge.logos.deterministic;"
        "from logosforge.providers import build_active_provider;"
        "leaked=[m for m in sys.modules if 'PySide' in m];"
        "assert not leaked, leaked;"
        "print('OK')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0 and "OK" in out.stdout, (out.stdout + out.stderr)
