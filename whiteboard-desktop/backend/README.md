# LogosForge Whiteboard — backend (core wrapper)

A thin FastAPI **wrapper** over the LogosForge core API. It does **not**
reimplement core logic (the previous standalone backend's drift) — it imports
`logosforge` in-process, builds the core API with `create_api(...)`, and calls
it over in-process ASGI. One process, one port (8777), one SQLite database.

The Whiteboard frontend is project-agnostic; the core is project-scoped. Each
Whiteboard document is one core project id, giving every document an isolated
PSYKE bible while the wrapper translates between the two DTO contracts.

## Setup (local, editable core)

```sh
python -m venv .venv
. .venv/Scripts/activate           # Windows; use bin/activate on POSIX
pip install -e ../../logosforge    # the headless core + API (no PySide6)
pip install -r requirements.txt    # fastapi / uvicorn / httpx
```

## Run

```sh
python -m uvicorn app.main:app --host 127.0.0.1 --port 8777
# GET /health -> {"status":"ok", ...}
```

The Electron `backend-manager` spawns this exactly as it spawned the old
backend; only the venv (now has `logosforge`) and the wrapped routes differ.

## Endpoint coverage

| Frontend route | Status | How |
|---|---|---|
| `/health`, `/api/version` | ✅ | mapped from core `/api/health` |
| `/api/documents` | ✅ | core project CRUD; document id = core project id |
| `/api/writing-modes` | ✅ | imports core `logosforge.writing_modes` |
| `/api/psyke/search`, `/elements` | ✅ | wraps project-scoped core PSYKE routes |
| `/api/littleboy/billy/chat`, `/logos/inline` | ✅ | prompt orchestration → core Assistant/Logos; manual Whiteboard outline added to AI grounding |
| `/api/settings/ai`, `/test` | ✅ | global provider settings passthrough + actionable connection test |
| `/api/whiteboard`, `/api/outline/items`, `/api/comments` | ✅ | per-document atomic JSON stores (desktop-only board state) |
| `/api/export/project` | ✅ | complete `.lfbundle` (manuscript + outline + comments + PSYKE) |

## Verification

```sh
# Provider transport, error translation, manual-outline + PSYKE grounding
.venv/Scripts/python tests/test_ai_grounding.py

# Complete project-bundle export
.venv/Scripts/python tests/test_export.py
```

Both tests use temporary data/DB state; the AI test uses loopback mock OpenAI
and Anthropic servers and never needs or reads a real API key.
