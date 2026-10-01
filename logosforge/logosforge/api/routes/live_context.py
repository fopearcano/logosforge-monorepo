"""Authenticated packaged-desktop live-context publication."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from logosforge.api import schemas
from logosforge.api.config import ApiConfig
from logosforge.api.deps import get_config, get_db
from logosforge.api.errors import conflict, forbidden, not_found
from logosforge.db import Database
from logosforge.live_context import (
    StaleLiveContextRevision,
    publish_live_context,
)

router = APIRouter(tags=["live-context"])


@router.put(
    "/live-context",
    response_model=schemas.LiveContextUpdateResultDTO,
)
def update_live_context(
    body: schemas.LiveContextUpdateDTO,
    db: Annotated[Database, Depends(get_db)],
    config: Annotated[ApiConfig, Depends(get_config)],
    publication_token: Annotated[
        str | None,
        Header(alias="X-LogosForge-Live-Context"),
    ] = None,
):
    """Accept one ordered, short-lived snapshot from this desktop instance.

    The app-wide bearer dependency authenticates the request before this
    handler runs. This endpoint additionally refuses tokenless, non-desktop,
    or wrong-instance publishers because it carries transient selected prose.
    """
    if (
        not config.is_desktop
        or not config.auth_token
        or not config.live_context_token
        or publication_token is None
        or not hmac.compare_digest(
            publication_token.encode("utf-8"),
            config.live_context_token.encode("utf-8"),
        )
    ):
        raise forbidden(
            "Live context can only be published by an authenticated desktop instance"
        )
    if (
        not config.instance_nonce
        or not hmac.compare_digest(
            body.source_id.encode("utf-8"),
            config.instance_nonce.encode("utf-8"),
        )
    ):
        raise forbidden("Live-context publisher does not match this API instance")

    if body.project_id is not None:
        project = db.get_project_by_id(body.project_id)
        if project is None:
            raise not_found(f"Project {body.project_id} not found")
        if body.active_scene_id is not None:
            scene = db.get_scene_by_id(body.active_scene_id)
            if scene is None or scene.project_id != body.project_id:
                raise not_found(f"Scene {body.active_scene_id} not found")

    try:
        result = publish_live_context(**body.model_dump())
    except StaleLiveContextRevision as exc:
        raise conflict(
            "The live-context revision is stale; publish a newer snapshot "
            f"than revision {exc.current_revision}.",
            code="stale_live_context_revision",
        ) from exc

    return {
        "ok": True,
        "revision": result.revision,
        "available": result.available,
        "project_id": result.project_id,
        "active_panel_id": result.active_panel_id,
        "active_scene_id": result.active_scene_id,
        "selection_length": result.selection_length,
    }
