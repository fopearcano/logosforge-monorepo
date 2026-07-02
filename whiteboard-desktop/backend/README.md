# LogosForge Whiteboard — backend (core wrapper)

A thin FastAPI **wrapper** over the LogosForge core API. It does **not**
reimplement core logic (the previous standalone backend's drift) — it imports
`logosforge` in-process, builds the core API with `create_api(...)`, and calls
it over in-process ASGI. One process, one port (8777), one SQLite database.

The Whiteboard frontend is project-agnostic; the core is project-scoped, so the
wrapper pins a single **"Whiteboard Session"** project and translates between
the two DTO contracts.

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
| `/api/writing-modes` | ⏳ | import core `logosforge.writing_modes` |
| `/api/psyke/search`, `/elements` | ⏳ | wrap core `…/psyke/*` (pinned project) |
| `/api/littleboy/billy`, `/logos` | ⏳ | orchestrate prompts → core `…/assistant/chat` |
| `/api/whiteboard`, `/api/outline/items` | ⏳ | local JSON (desktop-only board state) |
