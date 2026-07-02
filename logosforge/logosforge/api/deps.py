"""FastAPI dependencies — DB access, project resolution, events, auth hook."""

from __future__ import annotations

from fastapi import Depends, Header, Path, Request

from logosforge.api.config import ApiConfig
from logosforge.api.errors import forbidden, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_config(request: Request) -> ApiConfig:
    return request.app.state.config


def get_broker(request: Request) -> ApiEventBroker:
    return request.app.state.broker


def get_project(
    project_id: int = Path(..., ge=1),
    db: Database = Depends(get_db),
):
    """Resolve and validate the project for the route, returning the ORM row."""
    project = db.get_project_by_id(project_id)
    if project is None:
        raise not_found(f"Project {project_id} not found")
    return project


def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    """Auth hook.

    No-op unless an ``API_AUTH_TOKEN`` is configured, in which case a matching
    ``Authorization: Bearer <token>`` header is required.  This keeps a single,
    clean place to grow real authentication later without touching routes.
    """
    config: ApiConfig = request.app.state.config
    token = config.auth_token
    if not token:
        return
    expected = f"Bearer {token}"
    if authorization != expected:
        raise forbidden("Missing or invalid authorization token")
