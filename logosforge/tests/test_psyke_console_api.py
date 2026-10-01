"""HTTP coverage for PSYKE suggestions and safe plan/execute commands."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from logosforge.api.app import create_api
from logosforge.api.config import ApiConfig
from logosforge.db import Database
from logosforge.psyke_command_plans import (
    CommandPlanNotFoundError,
    PsykeCommandPlanService,
)


@pytest.fixture
def env():
    db = Database()
    project = db.create_project("Console API")
    app = create_api(db=db, config=ApiConfig(mode="desktop"))
    return TestClient(app), db, project.id


def _suggest(client: TestClient, project_id: int, q: str, **params):
    response = client.get(
        f"/api/projects/{project_id}/psyke/console/suggestions",
        params={"q": q, **params},
    )
    assert response.status_code == 200
    return response.json()


def _plan(client: TestClient, project_id: int, command: str, **body):
    response = client.post(
        f"/api/projects/{project_id}/psyke/console/plan",
        json={"command": command, **body},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _execute(client: TestClient, project_id: int, plan_id: str):
    return client.post(
        f"/api/projects/{project_id}/psyke/console/execute",
        json={"plan_id": plan_id, "confirmed": True},
    )


def test_console_suggestions_rank_exact_entity_above_prefix_match(env):
    client, db, project_id = env
    exact = db.create_psyke_entry(project_id, "Raven", entry_type="character")
    db.create_psyke_entry(project_id, "Ravenna", entry_type="place")

    results = _suggest(client, project_id, "Raven")
    entity_results = [item for item in results if item["category"] == "entity"]

    assert entity_results[0] == {
        "text": "Raven",
        "description": "character",
        "icon": "👤",
        "category": "entity",
        "score": 1.0,
        "entry_id": exact.id,
    }
    assert [item["score"] for item in results] == sorted(
        (item["score"] for item in results),
        reverse=True,
    )


def test_console_suggestions_are_strictly_project_scoped(env):
    client, db, project_id = env
    db.create_psyke_entry(project_id, "Local Beacon", entry_type="object")
    other_project_id = db.create_project("Other").id
    db.create_psyke_entry(
        other_project_id,
        "FOREIGN_CONSOLE_SECRET",
        entry_type="lore",
        aliases="foreign-alias",
    )

    assert _suggest(client, project_id, "FOREIGN_CONSOLE_SECRET") == []
    assert _suggest(client, project_id, "foreign-alias") == []


def test_console_suggestions_include_registered_command_metadata(env):
    client, db, project_id = env

    results = _suggest(client, project_id, "/cr")

    create = next(item for item in results if item["text"] == "/create")
    assert create == {
        "text": "/create",
        "description": "Create a PSYKE entry",
        "icon": "⌘",
        "category": "command",
        "score": pytest.approx(0.8 + 0.1 * (2 / len("create"))),
        "entry_id": 0,
    }
    assert db.get_all_psyke_entries(project_id) == []


def test_console_suggestions_use_exact_scene_mentions_for_context_boost(env):
    client, db, project_id = env
    mara = db.create_psyke_entry(project_id, "Mara", entry_type="character")
    mary = db.create_psyke_entry(project_id, "Mary", entry_type="character")
    mary_jane = db.create_psyke_entry(
        project_id, "Mary Jane", entry_type="character",
    )
    scene = db.create_scene(
        project_id,
        "Mara enters",
        summary="A train leaves Maryland.",
        content="Mary Jane watches. No one else appears.",
    )

    without_context = _suggest(client, project_id, "ma")
    with_context = _suggest(client, project_id, "ma", scene_id=scene.id)

    def entity_scores(items):
        return {
            item["entry_id"]: item["score"]
            for item in items
            if item["category"] == "entity"
        }

    plain = entity_scores(without_context)
    boosted = entity_scores(with_context)
    assert boosted[mara.id] == pytest.approx(plain[mara.id] + 0.05)
    assert boosted[mary.id] == pytest.approx(plain[mary.id] + 0.05)
    assert boosted[mary_jane.id] == pytest.approx(plain[mary_jane.id] + 0.05)


def test_console_suggestions_reject_missing_or_cross_project_scene(env):
    client, db, project_id = env
    other_project_id = db.create_project("Other").id
    foreign_scene = db.create_scene(other_project_id, "Foreign scene")

    missing = client.get(
        f"/api/projects/{project_id}/psyke/console/suggestions",
        params={"q": "anything", "scene_id": 999999},
    )
    foreign = client.get(
        f"/api/projects/{project_id}/psyke/console/suggestions",
        params={"q": "anything", "scene_id": foreign_scene.id},
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "not_found"


def test_command_plan_is_read_only_typed_and_opaque(env):
    client, db, project_id = env

    plan = _plan(client, project_id, "/create character Vesper Vale")

    assert db.get_all_psyke_entries(project_id) == []
    assert plan["plan_id"].startswith("lfcp_")
    assert len(plan["plan_id"]) > 32
    assert plan["command"] == "create"
    assert plan["normalized_command"] == "/create character Vesper Vale"
    assert plan["action"] == "create_psyke_entry"
    assert plan["mutates"] is True
    assert plan["requires_confirmation"] is True
    assert plan["target_type"] == "psyke_entry"
    assert plan["target_id"] is None
    assert plan["effects"]
    assert plan["expires_at"]


@pytest.mark.parametrize(
    "command",
    [
        "/ai rewrite",
        "/ask rewrite",
        "/idea explain",
        "/strategy off",
        "/delete Vesper",
        "/rename Vesper to Vale",
        "/insert Vesper",
        "/unknown anything",
        "/vesper open",
    ],
)
def test_command_planner_rejects_untyped_or_unsupported_commands(env, command):
    client, db, project_id = env

    response = client.post(
        f"/api/projects/{project_id}/psyke/console/plan",
        json={"command": command},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"
    assert db.get_all_psyke_entries(project_id) == []


def test_command_execute_requires_literal_confirmation_and_forbids_injection(env):
    client, db, project_id = env
    plan = _plan(client, project_id, "/create object Black Key")
    endpoint = f"/api/projects/{project_id}/psyke/console/execute"

    missing = client.post(endpoint, json={"plan_id": plan["plan_id"]})
    denied = client.post(
        endpoint,
        json={"plan_id": plan["plan_id"], "confirmed": False},
    )
    injected = client.post(
        endpoint,
        json={
            "plan_id": plan["plan_id"],
            "confirmed": True,
            "action": "delete_psyke_entry",
            "args": {"entry_id": 999},
        },
    )

    assert missing.status_code == denied.status_code == injected.status_code == 422
    assert db.get_all_psyke_entries(project_id) == []

    success = _execute(client, project_id, plan["plan_id"])
    assert success.status_code == 200
    assert success.json()["mutated"] is True
    assert [entry.name for entry in db.get_all_psyke_entries(project_id)] == ["Black Key"]


def test_command_execute_is_single_use_and_emits_one_change_event(env):
    client, db, project_id = env
    broker = client.app.state.broker
    cursor = broker.latest_id()
    plan = _plan(client, project_id, "/create place Glass Harbor")

    first = _execute(client, project_id, plan["plan_id"])
    replay = _execute(client, project_id, plan["plan_id"])

    assert first.status_code == 200
    result = first.json()
    assert result["action"] == "create_psyke_entry"
    assert result["target_type"] == "psyke_entry"
    assert result["target_id"] > 0
    assert replay.status_code == 404
    assert replay.json()["error"]["code"] == "not_found"
    assert [entry.name for entry in db.get_all_psyke_entries(project_id)] == ["Glass Harbor"]
    events = broker.events_since(cursor, project_id)
    assert [(event["event"], event["data"]["entry_id"]) for event in events] == [
        ("psyke_changed", result["target_id"]),
    ]


def test_command_plan_is_project_bound_without_leaking_its_owner(env):
    client, db, project_id = env
    other_project_id = db.create_project("Other").id
    plan = _plan(client, project_id, "/create lore Ash Calendar")

    foreign = _execute(client, other_project_id, plan["plan_id"])

    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "not_found"
    assert db.get_all_psyke_entries(project_id) == []
    assert _execute(client, project_id, plan["plan_id"]).status_code == 200


def test_open_psyke_requires_a_unique_exact_name_or_alias(env):
    client, db, project_id = env
    vesper = db.create_psyke_entry(
        project_id,
        "Vesper Vale",
        entry_type="character",
        aliases="Vess, Pilot",
    )

    alias_plan = _plan(client, project_id, "/open psyke vess")
    assert alias_plan["target_id"] == vesper.id
    assert alias_plan["normalized_command"] == "/open psyke Vesper Vale"
    assert alias_plan["mutates"] is False

    fuzzy = client.post(
        f"/api/projects/{project_id}/psyke/console/plan",
        json={"command": "/open psyke Vesp"},
    )
    assert fuzzy.status_code == 400

    db.create_psyke_entry(
        project_id,
        "Vessel",
        entry_type="object",
        aliases="Vess",
    )
    ambiguous = client.post(
        f"/api/projects/{project_id}/psyke/console/plan",
        json={"command": "/open psyke Vess"},
    )
    assert ambiguous.status_code == 409
    assert ambiguous.json()["error"]["code"] == "ambiguous_command_target"


def test_open_psyke_plan_rejects_a_deleted_frozen_target(env):
    client, db, project_id = env
    entry = db.create_psyke_entry(project_id, "Mara", entry_type="character")
    plan = _plan(client, project_id, "/open psyke Mara")
    db.delete_psyke_entry(entry.id)

    response = _execute(client, project_id, plan["plan_id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_command_plan"


def test_open_and_go_freeze_in_project_scene_targets(env):
    client, db, project_id = env
    first = db.create_scene(project_id, "First")
    second = db.create_scene(project_id, "Second")
    other_project_id = db.create_project("Other").id
    foreign = db.create_scene(other_project_id, "Foreign")

    opened = _plan(client, project_id, f"/open scene {second.id}")
    relative = _plan(
        client,
        project_id,
        "/goto scene next",
        active_scene_id=first.id,
    )

    assert opened["target_id"] == second.id
    assert relative["command"] == "go"
    assert relative["normalized_command"] == "/go scene next"
    assert relative["target_id"] == second.id
    result = _execute(client, project_id, opened["plan_id"])
    assert result.status_code == 200
    assert result.json() == {
        "ok": True,
        "action": "open_scene",
        "message": f"Opened scene #{second.id} 'Second'.",
        "mutated": False,
        "target_type": "scene",
        "target_id": second.id,
    }

    cross_project = client.post(
        f"/api/projects/{project_id}/psyke/console/plan",
        json={"command": f"/open scene {foreign.id}"},
    )
    assert cross_project.status_code == 400

    db.create_scene(project_id, "Third")
    stale = _execute(client, project_id, relative["plan_id"])
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_command_plan"


def test_relative_navigation_requires_context_and_rejects_boundaries(env):
    client, db, project_id = env
    first = db.create_scene(project_id, "Only")

    missing_context = client.post(
        f"/api/projects/{project_id}/psyke/console/plan",
        json={"command": "/go scene next"},
    )
    at_boundary = client.post(
        f"/api/projects/{project_id}/psyke/console/plan",
        json={"command": "/go scene previous", "active_scene_id": first.id},
    )

    assert missing_context.status_code == 400
    assert at_boundary.status_code == 400


def test_create_existing_entry_becomes_a_read_only_navigation_plan(env):
    client, db, project_id = env
    existing = db.create_psyke_entry(project_id, "Raven", entry_type="character")
    plan = _plan(client, project_id, "/create character raven")

    assert plan["action"] == "open_psyke_entry"
    assert plan["mutates"] is False
    assert plan["requires_confirmation"] is False
    assert plan["target_id"] == existing.id
    result = _execute(client, project_id, plan["plan_id"])
    assert result.status_code == 200
    assert len(db.get_all_psyke_entries(project_id)) == 1


def test_plan_store_is_app_local_even_when_database_is_reused():
    db = Database()
    project_id = db.create_project("Restart scope").id
    app_one = create_api(db=db, config=ApiConfig(mode="desktop"))
    app_two = create_api(db=db, config=ApiConfig(mode="desktop"))
    client_one = TestClient(app_one)
    client_two = TestClient(app_two)
    plan = _plan(client_one, project_id, "/create theme Silence")

    response = _execute(client_two, project_id, plan["plan_id"])

    assert response.status_code == 404
    assert db.get_all_psyke_entries(project_id) == []


def test_plan_expiry_and_concurrent_execute_are_fail_closed():
    db = Database()
    project_id = db.create_project("Service safety").id
    now = [10.0]
    service = PsykeCommandPlanService(db, ttl_seconds=2, clock=lambda: now[0])
    expired = service.create_plan(project_id, "/create object Hourglass")
    now[0] = 12.1

    with pytest.raises(CommandPlanNotFoundError):
        service.execute_plan(project_id, expired.plan_id, confirmed=True)
    assert db.get_all_psyke_entries(project_id) == []

    fresh = service.create_plan(project_id, "/create object Compass")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                service.execute_plan,
                project_id,
                fresh.plan_id,
                confirmed=True,
            )
            for _ in range(2)
        ]
    results = []
    failures = []
    for future in futures:
        try:
            results.append(future.result())
        except CommandPlanNotFoundError as exc:  # one replay must fail closed
            failures.append(exc)

    assert len(results) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], CommandPlanNotFoundError)
    assert [entry.name for entry in db.get_all_psyke_entries(project_id)] == ["Compass"]


def test_command_endpoints_inherit_bearer_auth():
    db = Database()
    project_id = db.create_project("Secured").id
    app = create_api(
        db=db,
        config=ApiConfig(mode="lan", auth_token="console-secret"),
    )
    client = TestClient(app)
    endpoint = f"/api/projects/{project_id}/psyke/console/plan"

    missing = client.post(endpoint, json={"command": "/create lore Beacon"})
    wrong = client.post(
        endpoint,
        json={"command": "/create lore Beacon"},
        headers={"authorization": "Bearer wrong"},
    )
    allowed = client.post(
        endpoint,
        json={"command": "/create lore Beacon"},
        headers={"authorization": "Bearer console-secret"},
    )

    assert missing.status_code == wrong.status_code == 403
    assert allowed.status_code == 200
