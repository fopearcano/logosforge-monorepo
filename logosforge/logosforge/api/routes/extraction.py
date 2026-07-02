"""Manuscript -> structured-data extraction endpoints (AI-assisted; propose -> apply).

``POST /extract`` starts an async job (returns a ``job_id`` immediately) so the N
per-scene LLM calls never block the request; ``GET /extract/jobs/{id}`` reports
progress + the final proposals. ``POST /extract/apply`` commits the human-reviewed
subset through the real DB writers. Tier-1 (character cues) is offline; Tier-2
inference uses the active AI provider (degrading to Tier-1 per scene on failure).
"""

from __future__ import annotations

import dataclasses
import threading
import uuid

from fastapi import APIRouter, Depends

from logosforge.api import schemas
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import ApiError
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["extraction"])

# In-process extraction-job registry (single-process core), capped to bound memory.
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_JOBS_CAP = 32


def _set_job(job_id: str, **fields) -> None:
    with _JOBS_LOCK:
        _JOBS.setdefault(job_id, {}).update(fields)
        while len(_JOBS) > _JOBS_CAP:
            _JOBS.pop(next(iter(_JOBS)))


def _get_job(job_id: str) -> dict | None:
    with _JOBS_LOCK:
        return dict(_JOBS[job_id]) if job_id in _JOBS else None


def _hint_to_dto(h) -> schemas.NearDupHintDTO | None:
    if h is None:
        return None
    return schemas.NearDupHintDTO(existing_id=h.existing_id, existing_name=h.existing_name, score=h.score)


def _rel_to_dto(r) -> schemas.RelationProposalDTO:
    return schemas.RelationProposalDTO(
        source=r.source, target=r.target, rel_type=r.rel_type, why=r.why, confidence=r.confidence,
        source_status=getattr(r, "source_status", ""), target_status=getattr(r, "target_status", ""),
        source_hint=_hint_to_dto(getattr(r, "source_hint", None)),
        target_hint=_hint_to_dto(getattr(r, "target_hint", None)),
    )


def _scene_to_dto(s) -> schemas.SceneExtractionDTO:
    return schemas.SceneExtractionDTO(
        scene_id=s.scene_id, title=s.title, characters=list(s.characters),
        who_knows_what=s.who_knows_what, relations=[_rel_to_dto(r) for r in s.relations],
    )


def _result_dto(project_id: int, ext) -> schemas.ExtractionResultDTO:
    return schemas.ExtractionResultDTO(
        project_id=project_id, used_llm=ext.used_llm,
        scenes=[_scene_to_dto(s) for s in ext.scenes],
        setup_payoffs=[_rel_to_dto(r) for r in ext.setup_payoffs],
    )


def _receipt_dto(rec) -> schemas.ExtractionReceiptDTO:
    return schemas.ExtractionReceiptDTO(
        character_ids=list(rec.character_ids),
        links=[[s, c] for s, c in rec.links],
        wkw_scene_ids=list(rec.wkw_scene_ids),
        psyke_ids=list(rec.psyke_ids),
        relations=[schemas.RelationRefDTO(source_id=a, target_id=b, rel_type=t) for a, b, t in rec.relations],
    )


def _report_dto(rec) -> schemas.ExtractionApplyReportDTO:
    return schemas.ExtractionApplyReportDTO(
        characters_created=len(rec.character_ids),
        links_added=len(rec.links),
        who_knows_what_set=len(rec.wkw_scene_ids),
        psyke_created=len(rec.psyke_ids),
        relations_added=len(rec.relations),
        receipt=_receipt_dto(rec),
    )


def _run_extract_job(job_id: str, db: Database, project_id: int, use_llm: bool, model: str, broker: ApiEventBroker) -> None:
    from logosforge import extraction, providers

    def on_progress(done: int, total: int, label: str) -> None:
        _set_job(job_id, done=done, total=total, label=label)
        try:  # best-effort SSE progress; the registry is the source of truth for polling
            broker.publish("extraction_progress", project_id=project_id, job_id=job_id, done=done, total=total, label=label)
        except Exception:
            pass

    # Optional per-run model override (e.g. a stronger local model for richer Tier-2
    # output): keep the active provider's base_url/api_key, swap only the model.
    # Empty => the global default provider (current behavior).
    provider = None
    if model.strip():
        try:
            provider = dataclasses.replace(providers.build_active_provider(), model=model.strip())
        except Exception:
            provider = None

    try:
        ext = extraction.extract_project(db, project_id, provider=provider, use_llm=use_llm, on_progress=on_progress)
        _set_job(job_id, status="done", result=_result_dto(project_id, ext))
    except Exception as exc:
        _set_job(job_id, status="error", error=str(exc))
    finally:
        try:
            broker.publish("extraction_done", project_id=project_id, job_id=job_id)
        except Exception:
            pass


@router.post(
    "/projects/{project_id}/extract",
    response_model=schemas.ExtractionJobDTO,
)
def extract(
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
    use_llm: bool = True,
    model: str = "",
):
    """Start a (non-blocking) extraction job. Poll ``GET /extract/jobs/{job_id}``.

    ``model`` optionally overrides the LLM for this run only (kept on the active
    provider's base_url/api_key) — e.g. point Tier-2 at a stronger local model
    without touching global settings. Empty uses the configured default.
    """
    total = len(db.get_all_scenes(project.id))
    job_id = uuid.uuid4().hex[:12]
    _set_job(job_id, status="running", done=0, total=total, error="", result=None)
    threading.Thread(
        target=_run_extract_job, args=(job_id, db, project.id, use_llm, model, broker), daemon=True,
    ).start()
    return schemas.ExtractionJobDTO(job_id=job_id, status="running", done=0, total=total)


@router.get(
    "/projects/{project_id}/extract/models",
    response_model=schemas.ExtractionModelsDTO,
)
def extract_models(project=Depends(get_project)):
    """The models the active AI provider exposes, to populate the per-run model
    override picker. Best-effort: empty ``models`` when the provider is unreachable
    or not OpenAI-compatible (the override input stays free-text regardless)."""
    from logosforge import assistant, providers

    models: list[str] = []
    active = ""
    try:
        prov = providers.build_active_provider()
        if prov is not None:
            active = getattr(prov, "model", "") or ""
            models = assistant.list_models(prov)
    except Exception:
        models, active = [], ""
    return schemas.ExtractionModelsDTO(models=models, active=active)


@router.get(
    "/projects/{project_id}/extract/jobs/{job_id}",
    response_model=schemas.ExtractionJobDTO,
)
def extract_job(job_id: str, project=Depends(get_project)):
    job = _get_job(job_id)
    if job is None:
        raise ApiError(404, "Unknown extraction job", code="extraction_job_unknown")
    return schemas.ExtractionJobDTO(
        job_id=job_id,
        status=job.get("status", "running"),
        done=job.get("done", 0),
        total=job.get("total", 0),
        error=job.get("error") or "",
        result=job.get("result"),
    )


@router.post(
    "/projects/{project_id}/extract/apply",
    response_model=schemas.ExtractionApplyReportDTO,
)
def extract_apply(
    body: schemas.ExtractionApplyRequestDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Write the reviewed/accepted proposals via the real writers (idempotent)."""
    from logosforge import extraction

    ext = extraction.ProjectExtraction(
        project_id=project.id,
        used_llm=False,
        scenes=[
            extraction.SceneExtraction(
                scene_id=s.scene_id, title=s.title, characters=list(s.characters),
                who_knows_what=s.who_knows_what,
                relations=[extraction.RelationProposal(r.source, r.target, r.rel_type, r.why, r.confidence)
                           for r in s.relations],
            )
            for s in body.scenes
        ],
        setup_payoffs=[extraction.RelationProposal(r.source, r.target, r.rel_type, r.why, r.confidence)
                       for r in body.setup_payoffs],
    )
    receipt = extraction.apply_extraction(db, project.id, ext)
    broker.publish("psyke_changed", project_id=project.id)
    broker.publish("scenes_changed", project_id=project.id)
    broker.publish("project_data_changed", project_id=project.id)
    return _report_dto(receipt)


@router.post(
    "/projects/{project_id}/extract/revert",
    response_model=schemas.ExtractionApplyReportDTO,
)
def extract_revert(
    body: schemas.ExtractionReceiptDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Undo a prior apply via its receipt — delete the created links/relations/entities."""
    from logosforge import extraction

    receipt = extraction.ApplyReceipt(
        character_ids=list(body.character_ids),
        links=[(p[0], p[1]) for p in body.links if len(p) >= 2],
        wkw_scene_ids=list(body.wkw_scene_ids),
        psyke_ids=list(body.psyke_ids),
        relations=[(r.source_id, r.target_id, r.rel_type) for r in body.relations],
    )
    removed = extraction.revert_extraction(db, receipt)
    broker.publish("psyke_changed", project_id=project.id)
    broker.publish("scenes_changed", project_id=project.id)
    broker.publish("project_data_changed", project_id=project.id)
    return _report_dto(removed)
