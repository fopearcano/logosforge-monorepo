"""Assistant (chat + actions + settings) endpoints.

Chat reuses the existing :func:`logosforge.assistant.chat_completion`; actions
are routed through the safe connector action layer so the API never performs raw
DB mutations on the assistant's behalf.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import ApiError
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["assistant"])

# Settings keys this endpoint exposes (api_key is write-only).
_AI_KEYS = {
    "provider": "ai_provider",
    "model": "ai_model",
    "base_url": "ai_base_url",
    "timeout": "assistant_api_timeout",
}


def _build_provider():
    # Delegates to the single shared provider builder (Phase 8B).
    from logosforge.providers import build_active_provider
    return build_active_provider()


@router.post(
    "/projects/{project_id}/assistant/chat",
    response_model=schemas.AssistantResponseDTO,
)
def assistant_chat(
    body: schemas.AssistantRequestDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    from logosforge import assistant
    from logosforge.chat_context import build_chat_context
    from logosforge.chat_memory import build_system_prompt

    # Project-aware context so Billy answers about THIS manuscript, not a
    # hallucinated generic one. build_chat_context bundles project header +
    # (optional) active scene + outline + PSYKE bible + story memory, already
    # capped at CONTEXT_MAX_CHARS. A context failure degrades to no context so
    # it can never break chat.
    from logosforge.settings import get_manager
    _s = get_manager()
    try:
        context = build_chat_context(
            db, project.id, active_scene_id=body.active_scene_id,
            include_outline=bool(_s.get("assistant_ctx_outline")),
            include_psyke=bool(_s.get("assistant_ctx_bible")),
            include_memory=bool(_s.get("assistant_ctx_memory")),
        )
    except Exception:
        context = ""

    # Irrational mode — fold surreal creative provocations into the grounding
    # block (per-request; needs an active scene to draw fragments from).
    if getattr(body, "irrational", False) and body.active_scene_id:
        try:
            from logosforge.irrational import build_irrational_context
            irr = build_irrational_context(db, project.id, int(body.active_scene_id))
            if irr:
                context = (context + "\n\n" + irr) if context else irr
        except Exception:
            pass

    # Fold any inline-editor context (selection / nearby text / document title)
    # into the same grounding block, so a thin editor client just sends the raw
    # fields instead of hand-building a competing context preamble.
    editor_bits: list[str] = []
    if body.document_title.strip():
        editor_bits.append(f"Open document: {body.document_title.strip()}")
    if body.selected_text.strip():
        editor_bits.append("Selected text:\n" + body.selected_text.strip())
    if body.nearby_text.strip():
        editor_bits.append("Nearby text:\n" + body.nearby_text.strip())
    if editor_bits:
        block = "Editor context:\n" + "\n\n".join(editor_bits)
        context = (context + "\n\n" + block) if context else block

    system_prompt = build_system_prompt("default", context)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    if body.system_prompt:  # preserve any caller-supplied extra system prompt
        messages.append({"role": "system", "content": body.system_prompt})
    for m in body.history:
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": body.message})

    try:
        reply, cached = assistant.chat_completion(
            messages, provider=_build_provider(),
        )
    except Exception as exc:  # network / provider errors
        raise ApiError(502, f"Assistant request failed: {exc}", code="assistant_error")
    return schemas.AssistantResponseDTO(reply=reply, cached=cached)


@router.post(
    "/projects/{project_id}/counterpart",
    response_model=schemas.AssistantResponseDTO,
)
def counterpart(
    body: schemas.CounterpartRequestDTO,
    project=Depends(get_project),
):
    """COUNTERPART — a reflective second reader (feedback/critique/interpret/…).

    LLM-backed and read-only (never rewrites or mutates). Unlike the quantum
    endpoints there is no offline stub, so a missing provider returns 502.
    """
    from logosforge import counterpart as cp

    try:
        reply, cached = cp.run_counterpart(
            body.mode,
            scene_context=body.scene_context,
            outline_context=body.outline_context,
            story_memory_context=body.story_memory_context,
            psyke_context=body.psyke_context,
            graph_context=body.graph_context,
            user_note=body.user_note,
            custom_prompt=body.custom_prompt,
        )
    except Exception as exc:
        raise ApiError(502, f"Counterpart request failed: {exc}", code="counterpart_error")
    return schemas.AssistantResponseDTO(reply=reply, cached=cached)


@router.post(
    "/projects/{project_id}/assistant/action",
    response_model=schemas.ConnectorResultDTO,
)
def assistant_action(
    body: schemas.AssistantActionRequestDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    from logosforge.api.actions import run_action

    result = run_action(db, project.id, body.action, body.args)
    if result.get("ok"):
        broker.publish(
            "assistant_action_completed", project_id=project.id,
            action=body.action,
        )
        broker.publish("project_data_changed", project_id=project.id)
    return schemas.ConnectorResultDTO(
        ok=bool(result.get("ok")),
        action=result.get("action", body.action),
        result=result.get("result"),
        error=result.get("error", ""),
    )


@router.get(
    "/projects/{project_id}/assistant/settings",
    response_model=schemas.AssistantSettingsDTO,
)
def get_assistant_settings(project=Depends(get_project)):
    from logosforge.settings import get_manager

    settings = get_manager()
    return schemas.AssistantSettingsDTO(
        provider=str(settings.get("ai_provider") or ""),
        model=str(settings.get("ai_model") or ""),
        base_url=str(settings.get("ai_base_url") or ""),
        timeout=int(settings.get("assistant_api_timeout") or 0),
        api_key=None,  # never returned
    )


@router.patch(
    "/projects/{project_id}/assistant/settings",
    response_model=schemas.AssistantSettingsDTO,
)
def patch_assistant_settings(
    body: schemas.AssistantSettingsDTO,
    project=Depends(get_project),
):
    from logosforge.settings import get_manager

    settings = get_manager()
    patch = body.model_dump(exclude_unset=True)
    if "provider" in patch:
        settings.set("ai_provider", patch["provider"])
    if "model" in patch:
        settings.set("ai_model", patch["model"])
    if "base_url" in patch:
        settings.set("ai_base_url", patch["base_url"])
    if "timeout" in patch:
        settings.set("assistant_api_timeout", patch["timeout"])
    if patch.get("api_key"):  # write-only; only set when non-empty
        settings.set("ai_api_key", patch["api_key"])
    return get_assistant_settings(project=project)


# Behaviour keys → global settings keys. Only flags the HEADLESS API actually
# honours are exposed here (chat grounding + connector governance), so every
# toggle a client shows is a real control, never a mockup.
_BEHAVIOR_KEYS = {
    "ctx_outline": "assistant_ctx_outline",
    "ctx_bible": "assistant_ctx_bible",
    "ctx_memory": "assistant_ctx_memory",
    "connector_enabled": "connector_enabled",
    "connector_allow_writes": "connector_allow_writes",
    "connector_confirm_writes": "connector_confirm_writes",
    "connector_disabled_actions": "connector_disabled_actions",
    "adaptive_override": "adaptive_mode_override",
}


@router.get(
    "/projects/{project_id}/ai/behavior",
    response_model=schemas.AiBehaviorDTO,
)
def get_ai_behavior(project=Depends(get_project)):
    from logosforge.settings import get_manager

    s = get_manager()
    disabled = s.get("connector_disabled_actions")
    return schemas.AiBehaviorDTO(
        ctx_outline=bool(s.get("assistant_ctx_outline")),
        ctx_bible=bool(s.get("assistant_ctx_bible")),
        ctx_memory=bool(s.get("assistant_ctx_memory")),
        connector_enabled=bool(s.get("connector_enabled")),
        connector_allow_writes=bool(s.get("connector_allow_writes")),
        connector_confirm_writes=bool(s.get("connector_confirm_writes")),
        connector_disabled_actions=list(disabled) if isinstance(disabled, list) else [],
        adaptive_override=str(s.get("adaptive_mode_override") or ""),
    )


@router.patch(
    "/projects/{project_id}/ai/behavior",
    response_model=schemas.AiBehaviorDTO,
)
def patch_ai_behavior(body: schemas.AiBehaviorUpdateDTO, project=Depends(get_project)):
    from logosforge.settings import get_manager

    s = get_manager()
    patch = body.model_dump(exclude_unset=True)
    for dto_key, settings_key in _BEHAVIOR_KEYS.items():
        if dto_key in patch:
            s.set(settings_key, patch[dto_key])
    return get_ai_behavior(project=project)
