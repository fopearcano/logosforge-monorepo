"""Whiteboard adapter for canonical, revisioned Progressions.

The core owns storage, validation, concurrency, and durable command receipts.
Whiteboard only binds the active document incarnation to its core project and
forwards the exact public contract under a project-agnostic route.
"""
from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse

from app.document_lifecycle import locked_document_request

router = APIRouter()


def _core_error(exc: httpx.HTTPStatusError) -> JSONResponse:
    response = exc.response
    try:
        content = response.json()
    except Exception:
        content = {
            "error": {
                "code": "core_request_failed",
                "message": "The Progressions request failed.",
            }
        }
    headers = {
        name: value
        for name, value in response.headers.items()
        if name.lower() in {"cache-control", "vary"}
    }
    return JSONResponse(
        status_code=response.status_code,
        content=content,
        headers=headers,
    )


@router.get("/api/progressions")
async def get_progressions(
    request: Request,
    doc: int | None = Query(None),
):
    async with locked_document_request(request, doc) as locked:
        try:
            response = await request.app.state.core.request(
                "GET",
                f"/api/projects/{locked.project_id}/progressions",
            )
        except httpx.HTTPStatusError as exc:
            return _core_error(exc)
        return response.json()


@router.post("/api/progressions/commands")
async def execute_progression_command(
    request: Request,
    payload: dict[str, Any],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    doc: int | None = Query(None),
):
    async with locked_document_request(request, doc, mutation=True) as locked:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key is not None else {}
        try:
            response = await request.app.state.core.request(
                "POST",
                f"/api/projects/{locked.project_id}/progressions/commands",
                json=payload,
                headers=headers,
            )
        except httpx.HTTPStatusError as exc:
            return _core_error(exc)
        return response.json()


@router.get("/api/progressions/command-receipt")
async def get_progression_command_receipt(
    request: Request,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    doc: int | None = Query(None),
):
    async with locked_document_request(request, doc) as locked:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key is not None else {}
        try:
            response = await request.app.state.core.request(
                "GET",
                f"/api/projects/{locked.project_id}/progressions/command-receipt",
                headers=headers,
            )
        except httpx.HTTPStatusError as exc:
            return _core_error(exc)
        result = JSONResponse(content=response.json())
        for name in ("Cache-Control", "Vary"):
            if name in response.headers:
                result.headers[name] = response.headers[name]
        return result
