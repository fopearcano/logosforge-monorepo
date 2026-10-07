"""Change-event endpoints for React live sync.

* ``GET /events``       — Server-Sent Events stream (preferred transport).
* ``GET /events/poll``  — polling fallback returning buffered events as JSON.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse

from logosforge.api.deps import get_broker, get_project
from logosforge.api.events import KNOWN_EVENTS, ApiEventBroker
from logosforge.api.schemas import EventsPollDTO

router = APIRouter(tags=["events"])


@router.get(
    "/projects/{project_id}/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def stream_events(
    once: bool = Query(False, description="Drain buffered events and close (no live tail)"),
    since: int | None = Query(
        None,
        ge=0,
        description="Resume with events whose id is greater than this cursor",
    ),
    last_event_id: int | None = Header(None, alias="Last-Event-ID", ge=0),
    project=Depends(get_project),
    broker: ApiEventBroker = Depends(get_broker),
):
    resume_cursor = since if since is not None else last_event_id
    generator = broker.stream(
        project_id=project.id,
        once=once,
        since=resume_cursor,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/projects/{project_id}/events/poll",
    response_model=EventsPollDTO,
)
def poll_events(
    since: int = Query(0, ge=0, description="Return events with id greater than this"),
    project=Depends(get_project),
    broker: ApiEventBroker = Depends(get_broker),
):
    events, cursor, broker_instance_id, reset_required = broker.snapshot(
        since,
        project_id=project.id,
    )
    return {
        "events": events,
        "cursor": cursor,
        "broker_instance_id": broker_instance_id,
        "reset_required": reset_required,
        "known_events": list(KNOWN_EVENTS),
    }
