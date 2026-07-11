"""Import external documents into a new project.

Currently: **Free Whiteboard → Pro** graduation — a Whiteboard block document
(``~/.logosforge/whiteboards/{id}.json``) is segmented into scenes and written
into a brand-new project with the matching writing mode. See
:mod:`logosforge.whiteboard_import`.
"""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException

from logosforge.api import schemas
from logosforge.api.deps import get_broker, get_db
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["import"])


@router.post("/import/whiteboard", response_model=schemas.WhiteboardImportResultDTO)
def import_whiteboard(
    body: schemas.WhiteboardImportDTO,
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Graduate a Free-tier Whiteboard document into a NEW Pro project: segment
    its blocks into scenes and create the project with the document's mode."""
    from logosforge import whiteboard_import
    result = whiteboard_import.import_whiteboard_document(db, body.model_dump())
    broker.publish("project_data_changed", project_id=result["project_id"])
    return schemas.WhiteboardImportResultDTO(**result)


@router.post("/import/manuscript", response_model=schemas.ManuscriptImportResultDTO)
def import_manuscript(
    body: schemas.ManuscriptImportDTO,
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Import an already-written, unformatted manuscript (.txt / .md / .docx) into
    a NEW project, segmenting the prose into scenes (see manuscript_import)."""
    from logosforge import manuscript_import
    try:
        data = base64.b64decode(body.content_base64 or "", validate=False)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="content_base64 is not valid base64")
    if not data:
        raise HTTPException(status_code=400, detail="the manuscript file is empty")
    try:
        result = manuscript_import.import_manuscript_document(
            db,
            title=body.title,
            mode=body.mode,
            strategy=body.strategy,
            filename=body.filename,
            data=data,
        )
    except RuntimeError as exc:  # e.g. python-docx missing / unreadable .docx
        raise HTTPException(status_code=400, detail=str(exc))
    broker.publish("project_data_changed", project_id=result["project_id"])
    return schemas.ManuscriptImportResultDTO(**result)
