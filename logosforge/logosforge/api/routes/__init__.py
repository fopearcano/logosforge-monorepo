"""API route routers."""

from logosforge.api.routes import (
    assistant,
    characters,
    connector,
    dashboard,
    events,
    export,
    extraction,
    format_data,
    intelligence,
    logos,
    notes,
    outline,
    plot,
    projects,
    psyke,
    quantum,
    scenes,
    themes,
    timeline,
    writing_modes,
)

# Ordered list of every router mounted under the /api prefix.
ALL_ROUTERS = [
    projects.router,
    scenes.router,
    outline.router,
    plot.router,
    timeline.router,
    psyke.router,
    notes.router,
    characters.router,
    themes.router,
    dashboard.router,
    intelligence.router,
    quantum.router,
    extraction.router,
    format_data.router,
    assistant.router,
    logos.router,
    connector.router,
    export.router,
    events.router,
    writing_modes.router,
]

__all__ = ["ALL_ROUTERS"]
