"""Tests for the FastAPI layer (logosforge.api)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import warnings

import pytest

warnings.filterwarnings("ignore")

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from logosforge.api.app import create_api  # noqa: E402
from logosforge.api.config import ApiConfig  # noqa: E402
from logosforge.db import Database  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    """Keep assistant-settings tests from touching the real settings file."""
    import logosforge.settings as settings

    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)
    yield
    settings._instance = None


@pytest.fixture
def env():
    db = Database()
    project = db.create_project("API Project", narrative_engine="novel")
    db.create_character(project.id, "Alice")
    app = create_api(db=db, config=ApiConfig(mode="desktop"))
    client = TestClient(app)
    return client, db, project.id


# -- Health & projects -------------------------------------------------------


def test_health(env):
    client, _, _ = env
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "desktop"


def test_health_reports_versions_for_client_compat(env):
    """Desktop (Electron) + Web/PWA clients read these to verify the backend."""
    import logosforge
    from logosforge.api.app import API_CONTRACT_VERSION

    client, _, _ = env
    body = client.get("/api/health").json()
    assert body["api_version"] == API_CONTRACT_VERSION
    assert body["core_version"] == logosforge.__version__
    # OpenAPI schema (used to generate the shared React client) is reachable
    # and carries the stable contract version.
    info = client.get("/openapi.json").json()["info"]
    assert info["version"] == API_CONTRACT_VERSION


def test_cors_allows_localhost_dev_server_in_desktop_mode(env):
    """The React/Vite dev server (any localhost port) must be allowed for
    Electron + local web development."""
    client, _, _ = env
    r = client.get(
        "/api/health",
        headers={"Origin": "http://localhost:5173"},  # Vite default
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in (
        "http://localhost:5173", "*",
    )


def test_list_projects(env):
    client, _, pid = env
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json())


def test_create_project(env):
    client, _, _ = env
    r = client.post(
        "/api/projects",
        json={"title": "Fresh", "narrative_engine": "screenplay"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Fresh"
    assert body["narrative_engine"] == "screenplay"
    assert body["default_writing_format"] == "screenplay"
    assert body["format_mode"] == "screenplay"


def test_project_mode_patch_is_atomic_for_empty_project(env):
    client, _, _ = env
    created = client.post(
        "/api/projects", json={"title": "Series", "narrative_engine": "novel"},
    ).json()
    r = client.patch(
        f"/api/projects/{created['id']}", json={"narrative_engine": "series"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["narrative_engine"] == "series"
    assert body["default_writing_format"] == "screenplay"
    assert body["format_mode"] == "screenplay"


def test_project_mode_patch_rejects_locked_project_without_partial_metadata(env):
    client, _, _ = env
    created = client.post(
        "/api/projects", json={"title": "Locked", "narrative_engine": "novel"},
    ).json()
    pid = created["id"]
    client.post(
        f"/api/projects/{pid}/scenes",
        json={"title": "Opening", "content": "Meaningful prose."},
    )
    r = client.patch(
        f"/api/projects/{pid}",
        json={"title": "Must Not Rename", "narrative_engine": "screenplay"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "writing_mode_locked"
    unchanged = client.get(f"/api/projects/{pid}").json()
    assert unchanged["title"] == "Locked"
    assert unchanged["narrative_engine"] == "novel"


def test_project_mode_patch_rejects_unknown_mode(env):
    client, _, pid = env
    r = client.patch(
        f"/api/projects/{pid}", json={"narrative_engine": "teleplay-ish"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


def test_get_project_and_404(env):
    client, _, pid = env
    assert client.get(f"/api/projects/{pid}").json()["id"] == pid
    assert client.get("/api/projects/99999").status_code == 404


def test_project_lifecycle_endpoints(env):
    client, _, pid = env
    assert client.post(f"/api/projects/{pid}/open").status_code == 200
    assert client.post(f"/api/projects/{pid}/save").json()["ok"] is True
    assert client.post(f"/api/projects/{pid}/close").json()["ok"] is True


def test_delete_project_now_supported(env):
    client, db, pid = env
    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 200 and r.json()["deleted"] == pid
    assert db.get_project_by_id(pid) is None
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_project_settings_roundtrip(env):
    client, _, pid = env
    assert client.get(f"/api/projects/{pid}/settings").json()["settings"] == {}
    r = client.patch(
        f"/api/projects/{pid}/settings", json={"settings": {"theme": "dark"}},
    )
    assert r.json()["settings"]["theme"] == "dark"
    # Persisted.
    assert client.get(f"/api/projects/{pid}/settings").json()["settings"]["theme"] == "dark"


def test_concurrent_project_settings_patches_do_not_lose_keys(tmp_path):
    db = Database(str(tmp_path / "concurrent-settings.db"))
    pid = db.create_project("Concurrent settings").id
    client = TestClient(create_api(db=db, config=ApiConfig(mode="desktop")))

    def patch(index: int) -> None:
        response = client.patch(
            f"/api/projects/{pid}/settings",
            json={"settings": {f"setting_{index}": index}},
        )
        assert response.status_code == 200

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(patch, range(24)))

    settings = client.get(f"/api/projects/{pid}/settings").json()["settings"]
    assert settings == {f"setting_{index}": index for index in range(24)}


# -- Scenes ------------------------------------------------------------------


def test_scene_crud(env):
    client, _, pid = env
    # Create
    r = client.post(
        f"/api/projects/{pid}/scenes",
        json={"title": "Opening", "summary": "It begins", "plotline": "Main"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    # List
    assert any(s["id"] == sid for s in client.get(f"/api/projects/{pid}/scenes").json())
    # Get
    assert client.get(f"/api/projects/{pid}/scenes/{sid}").json()["title"] == "Opening"
    # Patch (must not clobber summary)
    client.patch(f"/api/projects/{pid}/scenes/{sid}", json={"beat": "inciting"})
    scene = client.get(f"/api/projects/{pid}/scenes/{sid}").json()
    assert scene["summary"] == "It begins"
    assert scene["beat"] == "inciting"
    # Delete
    assert client.delete(f"/api/projects/{pid}/scenes/{sid}").json()["ok"] is True
    assert client.get(f"/api/projects/{pid}/scenes/{sid}").status_code == 404


def test_scene_unsaved_changes_visible_immediately(env):
    """A mutation is reflected by the very next read (single source of truth)."""
    client, db, pid = env
    sid = client.post(f"/api/projects/{pid}/scenes", json={"title": "X"}).json()["id"]
    client.patch(f"/api/projects/{pid}/scenes/{sid}", json={"title": "Renamed"})
    assert db.get_scene_by_id(sid).title == "Renamed"


def test_scene_patch_preserves_associations(env):
    """A partial PATCH must not wipe character/place links or states."""
    client, db, pid = env
    alice = db.create_character(pid, "Alice")
    castle = db.create_place(pid, "Castle")
    sid = client.post(
        f"/api/projects/{pid}/scenes",
        json={"title": "S", "character_ids": [alice.id], "place_ids": [castle.id]},
    ).json()["id"]
    client.patch(f"/api/projects/{pid}/scenes/{sid}", json={"beat": "inciting"})
    scene = client.get(f"/api/projects/{pid}/scenes/{sid}").json()
    assert scene["character_ids"] == [alice.id]
    assert scene["place_ids"] == [castle.id]


def test_scene_revision_rejects_a_stale_patch_without_losing_newer_text(env):
    client, db, pid = env
    created = client.post(
        f"/api/projects/{pid}/scenes",
        json={"title": "Revision", "content": "original"},
    ).json()
    assert created["revision"]

    first = client.patch(
        f"/api/projects/{pid}/scenes/{created['id']}",
        json={"content": "newer", "expected_revision": created["revision"]},
    )
    assert first.status_code == 200
    assert first.json()["revision"] != created["revision"]

    stale = client.patch(
        f"/api/projects/{pid}/scenes/{created['id']}",
        json={"content": "stale overwrite", "expected_revision": created["revision"]},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "scene_conflict"
    assert db.get_scene_by_id(created["id"]).content == "newer"

    overwritten = client.patch(
        f"/api/projects/{pid}/scenes/{created['id']}",
        json={"content": "intentional overwrite"},
    )
    assert overwritten.status_code == 200
    assert overwritten.json()["content"] == "intentional overwrite"

    # A direct core mutation also changes the derived revision.
    db.update_scene_content(created["id"], "core update")
    refreshed = client.get(f"/api/projects/{pid}/scenes/{created['id']}").json()
    assert refreshed["revision"] != overwritten.json()["revision"]


def test_concurrent_scene_patches_with_one_revision_have_one_winner(tmp_path):
    # Concurrent Sessions cannot safely share SQLite's one in-memory connection
    # (StaticPool). Exercise the production, file-backed connection path instead.
    db = Database(str(tmp_path / "concurrent-scenes.db"))
    pid = db.create_project("Concurrent scenes", narrative_engine="novel").id
    client = TestClient(create_api(db=db, config=ApiConfig(mode="desktop")))
    scene = client.post(
        f"/api/projects/{pid}/scenes",
        json={"title": "Concurrent", "content": "base"},
    ).json()
    start = threading.Barrier(2)

    def patch(content: str):
        start.wait(timeout=2)
        return client.patch(
            f"/api/projects/{pid}/scenes/{scene['id']}",
            json={"content": content, "expected_revision": scene["revision"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(patch, ["writer A", "writer B"]))

    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response.json()["content"] for response in responses if response.status_code == 200)
    current = client.get(f"/api/projects/{pid}/scenes/{scene['id']}").json()
    assert current["content"] == winner


# -- Outline / Plot / Timeline -----------------------------------------------


def test_outline_crud(env):
    client, _, pid = env
    root = client.post(f"/api/projects/{pid}/outline/nodes", json={"title": "Act I"}).json()
    child = client.post(
        f"/api/projects/{pid}/outline/nodes",
        json={"title": "Ch 1", "parent_id": root["id"]},
    ).json()
    tree = client.get(f"/api/projects/{pid}/outline").json()
    assert tree[0]["title"] == "Act I"
    assert tree[0]["children"][0]["title"] == "Ch 1"
    client.patch(
        f"/api/projects/{pid}/outline/nodes/{child['id']}", json={"title": "Chapter One"},
    )
    assert client.get(f"/api/projects/{pid}/outline").json()[0]["children"][0]["title"] == "Chapter One"
    assert client.delete(f"/api/projects/{pid}/outline/nodes/{child['id']}").json()["ok"]


def test_plot_blocks_and_rename(env):
    client, _, pid = env
    client.post(f"/api/projects/{pid}/scenes", json={"title": "S1", "plotline": "Main"})
    blocks = client.get(f"/api/projects/{pid}/plot").json()
    assert blocks[0]["plotline"] == "Main"
    renamed = client.patch(
        f"/api/projects/{pid}/plot/blocks/Main", json={"plotline": "A-Plot"},
    )
    assert renamed.json()["plotline"] == "A-Plot"


def test_timeline_create_and_update(env):
    client, _, pid = env
    ev = client.post(
        f"/api/projects/{pid}/timeline/events",
        json={"title": "Dawn", "time_of_day": "DAY", "duration_minutes": 5},
    ).json()
    assert ev["time_of_day"] == "DAY"
    assert ev["duration_minutes"] == 5
    upd = client.patch(
        f"/api/projects/{pid}/timeline/events/{ev['id']}",
        json={"location": "Castle"},
    ).json()
    assert upd["location"] == "Castle"


# -- PSYKE -------------------------------------------------------------------


def test_psyke_entry_crud(env):
    client, _, pid = env
    e = client.post(
        f"/api/projects/{pid}/psyke/entries",
        json={"name": "Justice", "type": "theme", "aliases": ["Law"]},
    ).json()
    eid = e["id"]
    assert e["type"] == "theme"
    assert e["aliases"] == ["Law"]
    client.patch(f"/api/projects/{pid}/psyke/entries/{eid}", json={"notes": "core"})
    assert client.get(f"/api/projects/{pid}/psyke/entries/{eid}").json()["notes"] == "core"
    assert client.delete(f"/api/projects/{pid}/psyke/entries/{eid}").json()["ok"]


def test_psyke_relations(env):
    client, _, pid = env
    a = client.post(f"/api/projects/{pid}/psyke/entries", json={"name": "Hero"}).json()
    b = client.post(f"/api/projects/{pid}/psyke/entries", json={"name": "Theme", "type": "theme"}).json()
    rel = client.post(
        f"/api/projects/{pid}/psyke/relations",
        json={"source_id": a["id"], "target_id": b["id"], "relation_type": "thematic_echo"},
    ).json()
    assert rel["relation_type"] == "thematic_echo"
    rels = client.get(f"/api/projects/{pid}/psyke/relations").json()
    assert len(rels) == 1
    assert client.delete(f"/api/projects/{pid}/psyke/relations/{rel['id']}").json()["ok"]
    assert client.get(f"/api/projects/{pid}/psyke/relations").json() == []


def test_relation_delete_rejects_cross_project_target(env):
    """Deleting a relation must validate both endpoints belong to the project."""
    client, db, pid = env
    a = client.post(f"/api/projects/{pid}/psyke/entries", json={"name": "Hero"}).json()
    other_pid = db.create_project("Other").id
    foreign = db.create_psyke_entry(other_pid, "Foreign", entry_type="theme")
    r = client.delete(f"/api/projects/{pid}/psyke/relations/{a['id']}:{foreign.id}")
    assert r.status_code == 404


def test_psyke_progressions_and_search(env):
    client, _, pid = env
    e = client.post(f"/api/projects/{pid}/psyke/entries", json={"name": "Hero"}).json()
    prog = client.post(
        f"/api/projects/{pid}/psyke/progressions",
        json={"entry_id": e["id"], "text": "grows up"},
    ).json()
    assert prog["text"] == "grows up"
    found = client.get(f"/api/projects/{pid}/psyke/search", params={"q": "hero"}).json()
    assert any(x["name"] == "Hero" for x in found)


# -- Notes -------------------------------------------------------------------


def test_note_crud(env):
    client, _, pid = env
    n = client.post(
        f"/api/projects/{pid}/notes",
        json={"title": "Idea", "content": "body", "tags": ["draft"]},
    ).json()
    nid = n["id"]
    assert n["tags"] == ["draft"]
    client.patch(f"/api/projects/{pid}/notes/{nid}", json={"pinned": True})
    assert client.get(f"/api/projects/{pid}/notes").json()[0]["pinned"] is True
    assert client.delete(f"/api/projects/{pid}/notes/{nid}").json()["ok"]


# -- Assistant / Connector ---------------------------------------------------


def test_assistant_chat_mocked(env, monkeypatch):
    client, _, pid = env
    from logosforge import assistant

    monkeypatch.setattr(
        assistant, "chat_completion", lambda *a, **k: ("Mocked reply", False),
    )
    r = client.post(
        f"/api/projects/{pid}/assistant/chat", json={"message": "hello"},
    )
    assert r.status_code == 200
    assert r.json() == {"reply": "Mocked reply", "cached": False}


def test_assistant_chat_injects_project_context(env, monkeypatch):
    """Billy must see THIS project (title + bible), not a blank slate, so it can't
    hallucinate a generic story. See memory ``logosforge-pro-writer-qa``."""
    client, db, pid = env
    db.create_psyke_entry(pid, "Mara Voss", entry_type="character", notes="sonar operator")
    from logosforge import assistant

    captured: dict = {}

    def _capture(messages, *a, **k):
        captured["messages"] = messages
        return ("ok", False)

    monkeypatch.setattr(assistant, "chat_completion", _capture)
    r = client.post(
        f"/api/projects/{pid}/assistant/chat",
        json={"message": "who is in this story?"},
    )
    assert r.status_code == 200
    msgs = captured["messages"]
    assert msgs[0]["role"] == "system"
    assert "API Project" in msgs[0]["content"]      # the project header
    assert "Mara Voss" in msgs[0]["content"]        # the bible reached the model
    assert msgs[-1] == {"role": "user", "content": "who is in this story?"}


def test_assistant_settings_roundtrip(env):
    client, _, pid = env
    client.patch(
        f"/api/projects/{pid}/assistant/settings",
        json={"provider": "OpenAI", "model": "gpt-4o", "api_key": "secret"},
    )
    got = client.get(f"/api/projects/{pid}/assistant/settings").json()
    assert got["provider"] == "OpenAI"
    assert got["model"] == "gpt-4o"
    assert got["api_key"] is None  # never returned


def test_assistant_settings_reports_persistence_failure(env, monkeypatch):
    client, _, pid = env
    from logosforge.settings import get_manager

    monkeypatch.setattr(get_manager(), "update", lambda _changes: False)
    response = client.patch(
        f"/api/projects/{pid}/assistant/settings",
        json={"provider": "OpenRouter", "model": "openrouter/auto"},
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "settings_save_failed"


def test_ai_behavior_roundtrip_is_atomic(env):
    client, _, pid = env
    response = client.patch(
        f"/api/projects/{pid}/ai/behavior",
        json={"ctx_outline": False, "connector_enabled": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ctx_outline"] is False
    assert body["connector_enabled"] is True
    stored = client.get(f"/api/projects/{pid}/ai/behavior").json()
    assert stored["ctx_outline"] is False
    assert stored["connector_enabled"] is True


def test_quantum_settings_patch_updates_one_coherent_snapshot(env):
    client, _, pid = env
    response = client.patch(
        f"/api/projects/{pid}/quantum/settings",
        json={
            "weights": {
                "structure_fit": 0.4,
                "psyke_consistency": 0.2,
                "tension_gain": 0.2,
                "novelty": 0.1,
                "goal_alignment": 0.1,
            },
            "selection_mode": "pareto",
            "show_tradeoffs": True,
            "ensemble_alpha": 4.0,
            "weight_learning": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["preset"] == "Custom"
    assert body["weights"]["structure_fit"] == 0.4
    assert body["weights"]["goal_alignment"] == 0.1
    assert body["selection_mode"] == "pareto"
    assert body["show_tradeoffs"] is True
    assert body["ensemble_alpha"] == 1.0
    assert body["weight_learning"] is False


def test_characters_list_link_and_backfill(env):
    """The /characters endpoints surface psyke_entry_id and let a client set/clear
    + auto-link it (the manuscript Character <-> PSYKE bible bridge)."""
    client, db, pid = env  # env seeds a Character "Alice"
    entry = db.create_psyke_entry(pid, "Alice", entry_type="character")

    chars = client.get(f"/api/projects/{pid}/characters").json()
    alice = next(c for c in chars if c["name"] == "Alice")
    assert alice["psyke_entry_id"] is None  # unlinked initially
    cid = alice["id"]

    # set the link, then clear it
    r = client.patch(f"/api/projects/{pid}/characters/{cid}", json={"psyke_entry_id": entry.id})
    assert r.status_code == 200 and r.json()["psyke_entry_id"] == entry.id
    r = client.patch(f"/api/projects/{pid}/characters/{cid}", json={"psyke_entry_id": None})
    assert r.json()["psyke_entry_id"] is None

    # the backfill action auto-links by name
    r = client.post(f"/api/projects/{pid}/characters/backfill-links")
    assert r.status_code == 200 and r.json()["linked"] >= 1
    chars = client.get(f"/api/projects/{pid}/characters").json()
    assert next(c["psyke_entry_id"] for c in chars if c["id"] == cid) == entry.id

    # linking to a non-character (theme) entry is rejected
    theme = db.create_psyke_entry(pid, "Hope", entry_type="theme")
    r = client.patch(f"/api/projects/{pid}/characters/{cid}", json={"psyke_entry_id": theme.id})
    assert r.status_code == 400

    # an explicit-null name must not 500 or clobber — it leaves the value unchanged
    r = client.patch(f"/api/projects/{pid}/characters/{cid}", json={"name": None})
    assert r.status_code == 200 and r.json()["name"] == "Alice"


def test_extract_accepts_model_override(env):
    """The /extract endpoint accepts an optional per-run model override and threads
    it into the job (use_llm=false keeps it deterministic — the param must not break
    the run)."""
    import time

    client, db, pid = env
    db.create_scene(pid, "INT. ROOM - DAY", content="MARA\nHello there.")
    r = client.post(f"/api/projects/{pid}/extract?use_llm=false&model=some-stronger-model")
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    j = {"status": "running"}
    for _ in range(60):
        j = client.get(f"/api/projects/{pid}/extract/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert j["status"] == "done"  # Tier-1 completes; the model param didn't break it


def test_extract_job_can_be_cancelled_cooperatively(env, monkeypatch):
    import threading
    import time
    from logosforge import extraction

    client, _, pid = env
    started = threading.Event()

    def wait_for_cancel(*_args, should_cancel=None, **_kwargs):
        started.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if should_cancel and should_cancel():
                raise extraction.ExtractionCancelled("cancelled by test")
            time.sleep(0.01)
        raise AssertionError("job never received cancellation")

    monkeypatch.setattr(extraction, "extract_project", wait_for_cancel)
    started_job = client.post(f"/api/projects/{pid}/extract?use_llm=false")
    assert started_job.status_code == 200
    job_id = started_job.json()["job_id"]
    assert started.wait(timeout=1)

    cancel = client.delete(f"/api/projects/{pid}/extract/jobs/{job_id}")
    assert cancel.status_code == 200
    assert cancel.json()["status"] in ("cancelling", "cancelled")
    status = cancel.json()
    for _ in range(100):
        status = client.get(f"/api/projects/{pid}/extract/jobs/{job_id}").json()
        if status["status"] == "cancelled":
            break
        time.sleep(0.01)
    assert status["status"] == "cancelled"
    assert status.get("result") is None


def test_extract_models_endpoint_returns_dto(env):
    """The model-picker endpoint always returns a well-formed DTO (best-effort:
    empty models when the provider is unreachable — never errors)."""
    client, db, pid = env
    r = client.get(f"/api/projects/{pid}/extract/models")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("models"), list)
    assert "active" in body


def test_theme_scenes_link_get_and_set(env):
    """Theme<->scene links: GET lists tagged scenes; PUT replaces the set (ignoring
    out-of-project scene ids); a non-theme entry 400s; an unknown entry 404s."""
    client, db, pid = env
    s = [db.create_scene(pid, f"S{i}", content="x") for i in range(3)]
    theme = db.create_psyke_entry(pid, "Doubt", entry_type="theme")
    char = db.create_psyke_entry(pid, "Mara", entry_type="character")

    assert client.get(f"/api/projects/{pid}/themes/{theme.id}/scenes").json()["scene_ids"] == []
    r = client.put(f"/api/projects/{pid}/themes/{theme.id}/scenes", json={"scene_ids": [s[0].id, s[2].id, 99999]})
    assert r.status_code == 200 and sorted(r.json()["scene_ids"]) == sorted([s[0].id, s[2].id])  # 99999 filtered
    assert sorted(client.get(f"/api/projects/{pid}/themes/{theme.id}/scenes").json()["scene_ids"]) == sorted([s[0].id, s[2].id])
    # PUT can shrink/clear
    assert client.put(f"/api/projects/{pid}/themes/{theme.id}/scenes", json={"scene_ids": []}).json()["scene_ids"] == []
    # a 'character' entry is not a theme -> 400; an unknown entry -> 404
    assert client.put(f"/api/projects/{pid}/themes/{char.id}/scenes", json={"scene_ids": []}).status_code == 400
    assert client.get(f"/api/projects/{pid}/themes/88888/scenes").status_code == 404


def test_delete_project_cascades_with_no_orphans(env):
    """DELETE /projects/{id} removes the project AND all its data — no orphan child
    rows. (The endpoint was previously 'not supported'.)"""
    from sqlmodel import Session, text
    client, db, _ = env
    p = db.create_project("DelMe", narrative_engine="screenplay")
    mara = db.create_character(p.id, "Mara")
    e = db.create_psyke_entry(p.id, "Mara", entry_type="character")
    s = db.create_scene(p.id, "A", content="MARA enters.", character_ids=[mara.id])
    th = db.create_psyke_entry(p.id, "Grief", entry_type="theme")
    db.set_theme_scenes(th.id, [s.id])
    db.add_psyke_relation(e.id, th.id, "visual_motif")

    r = client.delete(f"/api/projects/{p.id}")
    assert r.status_code == 200 and r.json()["deleted"] == p.id
    assert db.get_project_by_id(p.id) is None
    assert client.get(f"/api/projects/{p.id}").status_code == 404
    with Session(db._engine) as sess:
        for tbl, col, val in [("scene", "project_id", p.id), ("character", "project_id", p.id),
                              ("psykeentry", "project_id", p.id), ("scenethemelink", "scene_id", s.id),
                              ("psykerelation", "entry_id", e.id)]:
            assert list(sess.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE {col}={val}")))[0][0] == 0


def test_series_memory_requires_valid_entry(env):
    """PUT series-memory to a non-existent / cross-project entry -> 404 (was 200)."""
    client, db, _ = env
    p = db.create_project("SR", narrative_engine="series")
    assert client.put(f"/api/projects/{p.id}/psyke/88888/series-memory", json={"continuity_flags": "x"}).status_code == 404


def test_assistant_chat_folds_editor_context(env, monkeypatch):
    """Inline-editor context (selection / document title) sent as request fields is
    folded into the core's chat grounding — so a thin editor client never hand-
    builds a competing context preamble."""
    import logosforge.assistant as _assistant
    client, _, pid = env
    captured: dict = {}

    def _fake_chat(messages, provider=None):
        captured["messages"] = messages
        return ("ok", False)

    monkeypatch.setattr(_assistant, "chat_completion", _fake_chat)
    r = client.post(f"/api/projects/{pid}/assistant/chat", json={
        "message": "tighten this", "selected_text": "the salt ledger glints",
        "document_title": "Chapter One",
        "planning_outline": "[Writer Plan]\n- Act Two\n  - The observatory",
    })
    assert r.status_code == 200
    system_text = " ".join(m["content"] for m in captured["messages"] if m["role"] == "system")
    assert "the salt ledger glints" in system_text and "Chapter One" in system_text
    assert "[Writer Plan]" in system_text and "The observatory" in system_text


def test_connector_actions_listed(env):
    client, _, pid = env
    actions = client.get(f"/api/projects/{pid}/connector/actions").json()
    names = {a["name"] for a in actions}
    assert "get_project" in names
    assert all("category" in a for a in actions)


def test_connector_execute_validates_unknown_action(env):
    client, _, pid = env
    r = client.post(
        f"/api/projects/{pid}/connector/execute", json={"action": "does_not_exist"},
    )
    body = r.json()
    assert body["ok"] is False
    assert "Unknown action" in body["error"]


def test_unknown_connector_action_is_validated_before_disabled_list(env):
    from logosforge.settings import get_manager

    client, _, pid = env
    get_manager().set("connector_disabled_actions", ["does_not_exist"])
    r = client.post(
        f"/api/projects/{pid}/connector/execute", json={"action": "does_not_exist"},
    )
    assert "Unknown action" in r.json()["error"]


def test_connector_read_action_allowed(env):
    client, _, pid = env
    r = client.post(
        f"/api/projects/{pid}/connector/execute", json={"action": "get_project"},
    )
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["id"] == pid


def test_connector_write_action_remains_blocked_when_connector_is_off(env):
    client, db, pid = env
    r = client.post(
        f"/api/projects/{pid}/connector/execute",
        json={"action": "create_note", "args": {"title": "Must not exist"}},
    )
    body = r.json()
    assert body["ok"] is False
    assert "disabled" in body["error"].lower()
    assert db.get_all_notes(pid) == []


def test_assistant_action_uses_safe_layer(env):
    client, _, pid = env
    # Write action is gated by connector settings (disabled by default) → the
    # safe layer refuses rather than performing a raw mutation.
    r = client.post(
        f"/api/projects/{pid}/assistant/action",
        json={"action": "create_scene", "args": {"title": "Forced"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False  # connector disabled by default
    assert "disabled" in body["error"].lower()


# -- Export ------------------------------------------------------------------


def test_export_json(env):
    client, _, pid = env
    client.post(f"/api/projects/{pid}/scenes", json={"title": "S1", "plotline": "Main"})
    r = client.post(
        f"/api/projects/{pid}/export",
        json={"export_type": "story_elements", "format": "json"},
    )
    payload = r.json()["payload"]
    assert payload["export_type"] == "story_elements"
    assert "plot" in payload


def test_export_markdown_and_csv(env):
    client, _, pid = env
    client.post(f"/api/projects/{pid}/psyke/entries", json={"name": "Justice", "type": "theme"})
    md = client.post(
        f"/api/projects/{pid}/export",
        json={"export_type": "psyke_data", "format": "markdown"},
    ).json()
    assert md["content"] and "#" in md["content"]
    csv = client.post(
        f"/api/projects/{pid}/export",
        json={"export_type": "psyke_data", "format": "csv"},
    ).json()
    assert isinstance(csv["files"], dict) and csv["files"]


def test_export_bad_request(env):
    client, _, pid = env
    r = client.post(
        f"/api/projects/{pid}/export", json={"export_type": "nope", "format": "json"},
    )
    assert r.status_code == 400


# -- Events ------------------------------------------------------------------


def test_events_poll_captures_mutations(env):
    client, _, pid = env
    before = client.get(f"/api/projects/{pid}/events/poll").json()["cursor"]
    client.post(f"/api/projects/{pid}/scenes", json={"title": "Boom"})
    after = client.get(f"/api/projects/{pid}/events/poll", params={"since": before}).json()
    event_names = {e["event"] for e in after["events"]}
    assert "scene_changed" in event_names or "scenes_changed" in event_names
    assert after["cursor"] > before


def test_events_sse_stream_connects(env):
    client, _, pid = env
    # Use the finite "drain" mode so the test never blocks on the live tail.
    r = client.get(f"/api/projects/{pid}/events", params={"once": True})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    assert "event: connected" in r.text


def test_events_sse_drains_buffered_events(env):
    client, _, pid = env
    client.post(f"/api/projects/{pid}/notes", json={"title": "N"})
    body = client.get(f"/api/projects/{pid}/events", params={"once": True}).text
    assert "connected" in body


# -- Auth hook ---------------------------------------------------------------


def test_auth_hook_enforced_when_token_set():
    db = Database()
    db.create_project("Secured")
    app = create_api(
        db=db,
        config=ApiConfig(
            mode="remote",
            auth_token="s3cret",
            instance_nonce="desktop-instance-1",
        ),
    )
    client = TestClient(app)
    # Health is open; project routes require the token.
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["instance_nonce"] == "desktop-instance-1"
    assert "s3cret" not in health.text
    assert client.get("/api/projects").status_code == 403
    ok = client.get("/api/projects", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
