"""Passive assistant context integration (Phase 6 — opt-in, read-only, local).

Bridges the Phase-5 `AssistantContextBuilder` into the live assistant prompt
pipeline **without changing model-provider behavior and without writing any
durable memory**. It is:

- **Opt-in / default-off** — gated by `assistant_memory_context_enabled`
  (settings). When disabled, callers get an empty string and the prompt is
  exactly as before.
- **Read-only** — it only *retrieves* and *serializes* memory; it never calls
  `add_event` / `write_candidate` / `approve_candidate` / `update` /
  `supersede` / sync / GitHub. Candidate extraction stays separate and explicit.
- **Provider-agnostic** — providers are generation backends only; capabilities
  are metadata, never memory.
- **Fail-safe** — any error (no store, builder failure) degrades to an empty
  block; the assistant is never blocked.

Production note: a concrete memory store is **not** wired here. Enabling the
flag alone changes nothing until a store is registered via
`register_memory_store(...)` (a later, explicit step) or passed per-call. This
keeps Alpha behavior unchanged while the integration seam is fully in place.
"""

from __future__ import annotations

_ENABLED_KEY = "assistant_memory_context_enabled"
_DIAGNOSTICS_KEY = "assistant_memory_context_diagnostics_enabled"

_MEMORY_BLOCK_HEADER = (
    "=== LogosForge Memory Context (read-only; the model does not own this) ===")

# Bundle sections that belong in the injected block. "Current Task" /
# "Current Document Context" are intentionally omitted — the host prompt
# already owns those.
_MEMORY_SECTION_TITLES = (
    "Project Memory", "User Memory", "Workspace Memory",
    "Assistant Meta-Memory", "Assistant Rules", "Provider Capabilities",
)
_DIAGNOSTIC_TITLE = "Warnings / Exclusions"
_EMPTY_BODIES = {"(none)", "(no provider selected)"}

# Optional app-registered backends. Default None → no memory is injected even
# when the flag is on (fully passive until something is wired).
_registered_store = None
_registered_gateway = None

# kwargs accepted from a caller's ``memory_context_params``.
_ALLOWED_PARAMS = {
    "user_request", "project_id", "user_id", "workspace_id", "current_mode",
    "document", "provider_id", "store", "gateway",
}


def register_memory_store(store) -> None:
    """Register a default read-only memory store for passive context. Optional;
    callers may also pass ``store=`` per call. Registering does not enable the
    feature — the settings flag still gates everything."""
    global _registered_store
    _registered_store = store


def register_model_gateway(gateway) -> None:
    global _registered_gateway
    _registered_gateway = gateway


def get_memory_store():
    """The app-registered read/write memory store (or None). Shared by the
    passive context builder and the automatic memory capture path so a single
    `register_memory_store(...)` wires both. None → nothing is wired."""
    return _registered_store


def is_enabled() -> bool:
    try:
        from logosforge.settings import get_manager
        return bool(get_manager().get(_ENABLED_KEY))
    except Exception:
        return False


def is_diagnostics_enabled() -> bool:
    try:
        from logosforge.settings import get_manager
        return bool(get_manager().get(_DIAGNOSTICS_KEY))
    except Exception:
        return False


def render_memory_block(bundle, diagnostic: bool = False) -> str:
    """Serialize only the memory + capability sections (plus warnings in
    diagnostic mode) into a clearly-labelled block. Empty sections are dropped;
    returns "" if nothing meaningful is present. Secrets / raw-audio paths are
    already redacted by `ContextBundle.to_prompt_sections`."""
    titles = list(_MEMORY_SECTION_TITLES)
    if diagnostic:
        titles.append(_DIAGNOSTIC_TITLE)
    sections = bundle.to_prompt_sections(diagnostic=diagnostic)
    chosen = [s for s in sections
              if s["title"] in titles and s["body"] not in _EMPTY_BODIES]
    if not chosen:
        return ""
    out = [_MEMORY_BLOCK_HEADER]
    for s in chosen:
        out.append(f"## {s['title']}\n{s['body']}")
    return "\n\n".join(out)


def maybe_build_context_block(*, user_request: str = "",
                              project_id=None, user_id=None, workspace_id=None,
                              current_mode=None, document=None,
                              provider_id=None, store=None,
                              gateway=None) -> str:
    """Return a read-only memory context block, or "" when disabled / no store /
    on any failure. Never writes memory; never calls a provider."""
    if not is_enabled():
        return ""
    store = store if store is not None else _registered_store
    gateway = gateway if gateway is not None else _registered_gateway
    if store is None:
        return ""                       # passive: nothing wired → add nothing
    diagnostic = is_diagnostics_enabled()
    try:
        from logosforge.assistant_arch.context_builder import (
            AssistantContextBuilder)
        bundle = AssistantContextBuilder(store, gateway).build_context(
            user_request or "", project_id=project_id, user_id=user_id,
            workspace_id=workspace_id, provider_id=provider_id,
            current_mode=current_mode, document=document,
            diagnostic=diagnostic)
        return render_memory_block(bundle, diagnostic=diagnostic)
    except Exception:
        return ""                       # fail-safe: never block the assistant


def context_block_for_messages(memory_context_params: dict | None,
                               default_request: str = "") -> str:
    """Helper for `assistant.build_messages`: filter caller params, default the
    query to the action prompt, and build the block (or "")."""
    if not memory_context_params:
        return ""
    params = {k: v for k, v in memory_context_params.items()
              if k in _ALLOWED_PARAMS}
    params.setdefault("user_request", default_request)
    return maybe_build_context_block(**params)
