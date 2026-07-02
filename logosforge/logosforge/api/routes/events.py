"""Change-event endpoints for React live sync.

* ``GET /events``       — Server-Sent Events stream (preferred transport).
* ``GET /events/poll``  — polling fallback returning buffered events as JSON.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from logosforge.api.deps import get_broker, get_project
from logosforge.api.events import KNOWN_EVENTS, ApiEventBroker

router = APIRouter(tags=["events"])


@router.get("/projects/{project_id}/events")
def stream_events(
    once: bool = Query(False, description="Drain buffered events and close (no live tail)"),
    project=Depends(get_project),
    broker: ApiEventBroker = Depends(get_broker),
):
    generator = broker.stream(project_id=project.id, once=once)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_id}/events/poll")
def poll_events(
    since: int = Query(0, ge=0, description="Return events with id greater than this"),
    project=Depends(get_project),
    broker: ApiEventBroker = Depends(get_broker),
):
    events = broker.events_since(since, project_id=project.id)
    return {
        "events": events,
        "cursor": broker.latest_id(),
        "known_events": list(KNOWN_EVENTS),
    }
