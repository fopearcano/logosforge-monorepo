"""Quantum Outliner routes — generative narrative branches (POST).

Wraps ``quantum_outliner.core``. The generator resolves the active LLM provider
internally and degrades to deterministic stub branches when no provider is
reachable, so these endpoints always return a valid result (they never 502 on a
missing LLM). Note: a generated wavefunction lives in per-process state, so the
returned ``wavefunction_id`` is only meaningful to this server process.

``generative=true`` requests the LLM-backed LAMBDA path; it is passed as a
per-call ``outline_mode`` override so the request never mutates (or races on) the
project's stored mode. Default is the classical beat-sheet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database
from logosforge.quantum_outliner import core as quantum
from logosforge.quantum_outliner.state import OutlineMode

router = APIRouter(tags=["quantum"])


def _override(generative: bool) -> "OutlineMode | None":
    """LAMBDA when the caller asks for the LLM-backed generative branches; None
    lets the project's own (default classical) mode decide."""
    return OutlineMode.LAMBDA if generative else None


def _validate_source_scene(db: Database, project_id: int, scene_id: int | None) -> None:
    if scene_id is None:
        return
    scene = db.get_scene_by_id(scene_id)
    if scene is None or scene.project_id != project_id:
        raise not_found(f"Scene {scene_id} not found")


@router.post(
    "/projects/{project_id}/quantum/outline",
    response_model=schemas.QuantumResultDTO,
)
def post_quantum_outline(
    body: schemas.QuantumOutlineRequestDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Generate a wavefunction of opening branches from a premise."""
    _validate_source_scene(db, project.id, body.source_scene_id)
    result = quantum.generate_outline(
        db, project.id, body.premise,
        n=body.n, source_scene_id=body.source_scene_id,
        structure_mode=body.structure_mode, outline_mode=_override(body.generative),
    )
    return serializers.quantum_result_to_dto(result)


@router.post(
    "/projects/{project_id}/quantum/branches",
    response_model=schemas.QuantumResultDTO,
)
def post_quantum_branches(
    body: schemas.QuantumBranchesRequestDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Generate next-move branches for a situation."""
    _validate_source_scene(db, project.id, body.source_scene_id)
    result = quantum.generate_branches(
        db, project.id, body.situation,
        n=body.n, extra_context=body.extra_context,
        source_scene_id=body.source_scene_id,
        structure_mode=body.structure_mode, outline_mode=_override(body.generative),
    )
    return serializers.quantum_result_to_dto(result)


@router.get(
    "/projects/{project_id}/quantum/settings",
    response_model=schemas.QuantumSettingsDTO,
)
def get_quantum_settings(project=Depends(get_project), db: Database = Depends(get_db)):
    """The project's Lambda-mode scoring configuration (read by the generate path)."""
    from logosforge.quantum_outliner.scoring import DEFAULT_WEIGHTS, PRESET_NAMES

    stored = db.get_project_settings(project.id)
    raw_weights = stored.get("scoring_weights")
    if isinstance(raw_weights, dict) and all(key in raw_weights for key in DEFAULT_WEIGHTS):
        weights = {key: float(raw_weights[key]) for key in DEFAULT_WEIGHTS}
    else:
        weights = dict(DEFAULT_WEIGHTS)
    selection_mode = stored.get("selection_mode", "weighted")
    if selection_mode not in ("weighted", "pareto"):
        selection_mode = "weighted"
    try:
        ensemble_alpha = max(0.0, min(float(stored.get("ensemble_alpha", 0.7)), 1.0))
    except (TypeError, ValueError):
        ensemble_alpha = 0.7
    return schemas.QuantumSettingsDTO(
        preset=str(stored.get("scoring_preset", "Balanced")),
        weights=weights,
        selection_mode=selection_mode,
        show_tradeoffs=bool(stored.get("show_tradeoffs", False)),
        ensemble_alpha=ensemble_alpha,
        weight_learning=bool(stored.get("weight_learning", True)),
        preset_names=list(PRESET_NAMES),
        weight_keys=list(DEFAULT_WEIGHTS.keys()),
    )


@router.patch(
    "/projects/{project_id}/quantum/settings",
    response_model=schemas.QuantumSettingsDTO,
)
def patch_quantum_settings(
    body: schemas.QuantumSettingsUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Update the project's scoring config. Applying a known ``preset`` also sets
    its weights; editing ``weights`` directly marks the preset ``Custom`` (mirrors
    the Qt app's adaptive-weights behaviour)."""
    from logosforge.quantum_outliner.scoring import SCORING_PRESETS

    fields = body.model_fields_set
    changes: dict = {}
    if "preset" in fields and body.preset:
        changes["scoring_preset"] = body.preset
        if body.preset in SCORING_PRESETS and "weights" not in fields:
            changes["scoring_weights"] = dict(SCORING_PRESETS[body.preset])
    if "weights" in fields and body.weights is not None:
        changes["scoring_weights"] = {
            str(k): float(v) for k, v in body.weights.items()
        }
        if "preset" not in fields:
            changes["scoring_preset"] = "Custom"
    if "selection_mode" in fields and body.selection_mode:
        changes["selection_mode"] = (
            "pareto" if body.selection_mode == "pareto" else "weighted"
        )
    if "show_tradeoffs" in fields and body.show_tradeoffs is not None:
        changes["show_tradeoffs"] = body.show_tradeoffs
    if "ensemble_alpha" in fields and body.ensemble_alpha is not None:
        changes["ensemble_alpha"] = max(0.0, min(float(body.ensemble_alpha), 1.0))
    if "weight_learning" in fields and body.weight_learning is not None:
        changes["weight_learning"] = body.weight_learning
    if changes:
        db.patch_project_settings(project.id, changes)
    broker.publish("project_data_changed", project_id=project.id)
    return get_quantum_settings(project=project, db=db)
