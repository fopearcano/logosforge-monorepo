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
from logosforge.api.deps import get_db, get_project
from logosforge.db import Database
from logosforge.quantum_outliner import core as quantum
from logosforge.quantum_outliner.state import OutlineMode

router = APIRouter(tags=["quantum"])


def _override(generative: bool) -> "OutlineMode | None":
    """LAMBDA when the caller asks for the LLM-backed generative branches; None
    lets the project's own (default classical) mode decide."""
    return OutlineMode.LAMBDA if generative else None


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
    result = quantum.generate_branches(
        db, project.id, body.situation,
        n=body.n, extra_context=body.extra_context,
        source_scene_id=body.source_scene_id,
        structure_mode=body.structure_mode, outline_mode=_override(body.generative),
    )
    return serializers.quantum_result_to_dto(result)
