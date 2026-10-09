"""Decision Radar HTTP contract with canonical Knowledge Graph evidence."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from logosforge.api import create_api, schemas, serializers
from logosforge.db import Database
from logosforge.project_intelligence.decision_radar import (
    DecisionCard,
    DecisionEvidence,
)
from pydantic import ValidationError


def _project():
    db = Database()
    project = db.create_project("Radar Graph", narrative_engine="novel")
    scene = db.create_scene(
        project.id,
        "Opening",
        content="Nothing happens.",
        summary="",
    )
    relic = db.create_psyke_entry(project.id, "Lonely Relic", "object")
    note = db.create_note(project.id, "Lore", "The Crimson Order waits.")
    return db, project, scene, relic, note


def test_decision_radar_exposes_bounded_traceable_graph_cards():
    db, project, scene, relic, note = _project()
    client = TestClient(create_api(db=db))

    response = client.get(f"/api/projects/{project.id}/decision-radar")

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_graph_available"] is True
    assert len(body["radar"]) <= 10
    assert len(body["knowledge_graph_cards"]) <= 8
    graph_cards = {card["id"]: card for card in body["knowledge_graph_cards"]}

    scene_card = graph_cards["kg_scenes_no_psyke"]
    assert scene_card["created_from"] == "knowledge_graph"
    assert scene_card["graph_focus_key"] == f"scene:scene:{scene.id}"
    assert scene_card["graph_view_mode"] == "project_map"
    assert scene_card["graph_include_inferred"] is True
    assert scene_card["graph_depth"] == 1
    assert scene_card["evidence_total"] == 1
    assert scene_card["evidence"][0]["graph_focus_key"] == scene_card["graph_focus_key"]

    orphan_card = graph_cards[f"kg_isolated_object:psyke:{relic.id}"]
    assert orphan_card["evidence"][0]["source_system"] == "psyke"
    assert orphan_card["evidence"][0]["provenance"] == f"psyke:{relic.id}"

    term_card = graph_cards["kg_undefined_terms"]
    assert term_card["graph_focus_key"] == f"note:note:{note.id}"
    assert term_card["evidence"][0]["kind"] == "term"
    assert "Crimson Order" in term_card["evidence"][0]["label"]


def test_decision_radar_exposes_native_progression_target_and_beat_evidence():
    db = Database()
    project = db.create_project("Progression radar", narrative_engine="novel")
    early = db.create_scene(project.id, "Early")
    late = db.create_scene(project.id, "Late")
    snapshot = db.read_progression_snapshot(project.id)
    assert snapshot is not None
    track_result = db.execute_progression_command(
        project.id,
        kind="create_track",
        expected_revision=snapshot.revision,
        track_kind="story",
        title="Main arc",
    )
    track_id = track_result.created_track_id
    assert track_id is not None
    first_result = db.execute_progression_command(
        project.id,
        kind="create_beat",
        expected_revision=track_result.snapshot.revision,
        track_id=track_id,
        text="Late turn",
        anchor_kind="scene",
        scene_id=late.id,
    )
    second_result = db.execute_progression_command(
        project.id,
        kind="create_beat",
        expected_revision=first_result.snapshot.revision,
        track_id=track_id,
        text="Earlier turn",
        anchor_kind="scene",
        scene_id=early.id,
    )
    beat_id = second_result.created_beat_id
    assert beat_id is not None

    response = TestClient(create_api(db=db)).get(
        f"/api/projects/{project.id}/decision-radar"
    )

    assert response.status_code == 200
    card = next(
        item for item in response.json()["knowledge_graph_cards"]
        if item["id"] == f"kg_progression_order_{track_id}"
    )
    assert card["related_section"] == "Progressions"
    assert card["related_target_type"] == "progression_track"
    assert card["related_target_id"] == track_id
    assert card["graph_focus_key"] == (
        f"progression_track:progressions:{track_id}"
    )
    assert card["evidence_total"] == 1
    assert card["evidence"][0]["related_target_type"] == "progression_beat"
    assert card["evidence"][0]["related_target_id"] == beat_id
    assert card["evidence"][0]["graph_focus_key"] == (
        f"progression_beat:progressions:{beat_id}"
    )


def test_decision_radar_graph_failure_is_truthful_and_preserves_base_feed(monkeypatch):
    db, project, *_ = _project()
    import logosforge.api.routes.intelligence as intelligence_route

    monkeypatch.setattr(
        intelligence_route,
        "build_knowledge_graph",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("broken graph")),
    )
    body = TestClient(create_api(db=db)).get(
        f"/api/projects/{project.id}/decision-radar"
    ).json()

    assert body["knowledge_graph_available"] is False
    assert body["knowledge_graph_cards"] == []
    assert body["continuity_available"] is True
    assert body["radar"]


def test_decision_radar_exposes_traceable_continuity_cards():
    db = Database()
    project = db.create_project("Continuity Radar", narrative_engine="novel")
    scene = db.create_scene(project.id, "Setup", content="A promise is made.")
    db.update_scene(
        scene.id,
        scene.title,
        content=scene.content,
        setup_payoff_links="999999",
    )

    body = TestClient(create_api(db=db)).get(
        f"/api/projects/{project.id}/decision-radar"
    ).json()

    assert body["continuity_available"] is True
    assert len(body["continuity_cards"]) <= 8
    card = next(
        item
        for item in body["continuity_cards"]
        if item["severity"] == "blocking"
    )
    assert card["created_from"] == "semantic_continuity"
    assert card["related_target_type"] == "continuity_issue"
    assert len(card["related_target_key"]) == 16
    assert card["evidence"][0]["related_target_key"] == card["related_target_key"]
    scene_evidence = next(
        item for item in card["evidence"] if item["related_target_type"] == "scene"
    )
    assert scene_evidence["related_target_id"] == scene.id
    assert scene_evidence["related_section"] == "Manuscript"


def test_decision_radar_continuity_failure_is_isolated(monkeypatch):
    db, project, *_ = _project()

    monkeypatch.setattr(
        "logosforge.api.routes.intelligence.continuity_collector.build_continuity_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("broken continuity")
        ),
    )
    body = TestClient(create_api(db=db)).get(
        f"/api/projects/{project.id}/decision-radar"
    ).json()

    assert body["continuity_available"] is False
    assert body["continuity_cards"] == []
    assert body["knowledge_graph_available"] is True
    assert body["radar"]


def test_decision_radar_normalizes_legacy_graph_evidence_confidence(monkeypatch):
    db, project, scene, *_ = _project()
    legacy_card = DecisionCard(
        id="kg_legacy_confidence",
        category="graph",
        severity="warning",
        confidence="likely",
        title="Legacy evidence",
        created_from="knowledge_graph",
        graph_focus_key=f"scene:scene:{scene.id}",
        graph_view_mode="project_map",
        evidence=[DecisionEvidence(
            kind="node",
            label="Legacy node evidence",
            graph_focus_key=f"scene:scene:{scene.id}",
            confidence="medium",
        )],
        evidence_total=1,
    )
    monkeypatch.setattr(
        "logosforge.api.routes.intelligence.build_graph_decision_cards",
        lambda *_args, **_kwargs: [legacy_card],
    )

    response = TestClient(create_api(db=db)).get(
        f"/api/projects/{project.id}/decision-radar"
    )

    assert response.status_code == 200
    card = response.json()["knowledge_graph_cards"][0]
    assert card["evidence"][0]["confidence"] == "unknown"


def test_decision_radar_normalizes_whitespace_only_graph_labels():
    db = Database()
    project = db.create_project("Whitespace", narrative_engine="novel")
    entry = db.create_psyke_entry(project.id, "   ", "object")

    response = TestClient(create_api(db=db)).get(
        f"/api/projects/{project.id}/decision-radar"
    )

    assert response.status_code == 200
    card = next(
        item
        for item in response.json()["knowledge_graph_cards"]
        if item["id"] == f"kg_isolated_object:psyke:{entry.id}"
    )
    assert card["evidence"][0]["label"] == f"object:psyke:{entry.id}"


def test_graph_card_public_keys_use_the_canonical_wire_mapping():
    long_key = "theme:psyke:" + ("x" * 600)
    card = DecisionCard(
        id="kg_long",
        category="graph",
        severity="opportunity",
        confidence="confirmed",
        title="Long canonical key",
        created_from="knowledge_graph",
        graph_focus_key=long_key,
        graph_view_mode="project_map",
        evidence=[DecisionEvidence(
            kind="node",
            label="Long node",
            graph_focus_key=long_key,
            confidence="confirmed",
        )],
        evidence_total=1,
    )

    dto = serializers.decision_card_to_dto(card)

    assert dto.graph_focus_key.startswith("kg:sha256:")
    assert dto.evidence[0].graph_focus_key == dto.graph_focus_key
    assert len(dto.graph_focus_key) < 512


def test_continuity_card_contract_rejects_mixed_graph_evidence():
    issue_key = "0123456789abcdef"
    card = DecisionCard(
        id=f"continuity_{issue_key}",
        category="continuity",
        severity="warning",
        confidence="likely",
        title="Continuity issue",
        related_section="Continuity",
        related_target_type="continuity_issue",
        related_target_key=issue_key,
        created_from="semantic_continuity",
        evidence=[DecisionEvidence(
            kind="continuity_issue",
            label="Continuity issue",
            graph_focus_key="scene:scene:1",
            related_section="Continuity",
            related_target_type="continuity_issue",
            related_target_key=issue_key,
        )],
        evidence_total=1,
    )

    with pytest.raises(ValidationError):
        serializers.decision_card_to_dto(card)


@pytest.mark.parametrize(
    ("target_type", "target_id", "target_key"),
    [
        ("progression_track", None, ""),
        ("progression_track", 1, "not-allowed"),
        ("progression_beat", 0, ""),
    ],
)
def test_progression_decision_targets_require_one_positive_id(
    target_type, target_id, target_key,
):
    evidence = {
        "kind": "node",
        "label": "Progression evidence",
        "graph_focus_key": "progression_track:progressions:1",
        "confidence": "confirmed",
        "related_section": "Progressions",
        "related_target_type": target_type,
        "related_target_id": target_id,
        "related_target_key": target_key,
    }
    with pytest.raises(ValidationError):
        schemas.DecisionEvidenceDTO.model_validate(evidence)

    card = {
        "id": "kg_bad_progression_target",
        "category": "progression",
        "severity": "warning",
        "confidence": "confirmed",
        "title": "Bad target",
        "related_section": "Progressions",
        "related_target_type": target_type,
        "related_target_id": target_id,
        "related_target_key": target_key,
        "created_from": "knowledge_graph",
        "graph_focus_key": "progression_track:progressions:1",
        "graph_view_mode": "project_map",
        "evidence": [{
            **evidence,
            "related_target_type": "progression_track",
            "related_target_id": 1,
            "related_target_key": "",
        }],
        "evidence_total": 1,
    }
    with pytest.raises(ValidationError):
        schemas.DecisionCardDTO.model_validate(card)


def test_python_decision_contract_rejects_client_invalid_vocabularies():
    with pytest.raises(ValidationError):
        schemas.DecisionEvidenceDTO(kind="node", label="   ")

    with pytest.raises(ValidationError):
        schemas.DecisionCardDTO(
            id="bad-vocabulary",
            category="continuity",
            severity="urgent",
            confidence="certain",
            title="Invalid internal card",
        )

    normalized = serializers.decision_card_to_dto(DecisionCard(
        id="bad-vocabulary",
        category="continuity",
        severity="urgent",
        confidence="certain",
        title="Invalid internal card",
    ))

    assert normalized.severity == "info"
    assert normalized.confidence == "unknown"
