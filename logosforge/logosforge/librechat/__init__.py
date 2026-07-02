"""LibreChat integration — an OPTIONAL advanced conversational sidecar.

LogosForge stays the narrative brain (project memory, context engine, PSYKE
authority, safe propose→confirm→apply action authority). LibreChat is a
separate, general-purpose chat workspace that LogosForge can detect, connect
to, embed (or open in the browser), and — in a future phase — talk to through
the existing FastAPI/OpenAPI surface or an MCP server via the :mod:`bridge`
adapter boundary.

This package never touches the LogosForge SQLite database directly and never
bundles LibreChat's own infrastructure (MongoDB / Meilisearch / Docker / …).
LogosForge stays fully functional when LibreChat is absent.
"""

from logosforge.librechat.config import LibreChatConfig

__all__ = ["LibreChatConfig"]
