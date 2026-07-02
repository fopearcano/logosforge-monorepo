"""Bridge between the Go McKee plugin and the central Assistant context.

The Go McKee plugin ships a real writing-intelligence service
(GoMcKeeService) that produces craft constraints and structural/character/
dialogue checks, and reads a PSYKE snapshot. Out of the box that service
was only reachable from menu message-boxes — it never influenced the
Assistant prompt.

This module wires it through the Assistant context builder:

- `is_gomckee_enabled()` reads the real, persisted plugin toggle
  (plugin_states) — not merely whether the plugin is loaded.
- `gather_gomckee_context()` builds a PSYKE-aware project snapshot from
  the DB, runs the service, and returns a compact ``[Go McKee]`` block
  for the Assistant. Returns "" when Go McKee is OFF.

Go McKee is READ-ONLY with respect to PSYKE here: it consumes PSYKE
entries/relations/states to inform craft pressure but never mutates
them. Any PSYKE changes remain explicit, user-confirmed actions
elsewhere.
"""

from __future__ import annotations

import sys
from typing import Any

# Caps so the block stays compact and never floods the prompt.
_MAX_CONSTRAINTS = 10
_MAX_CHECKS = 6
_MAX_PSYKE = 12
_MAX_NEARBY = 4

_service_cache: dict[str, Any] = {}


def _gomckee_info():
    """Return the PluginInfo for the Go McKee plugin, or None."""
    try:
        from logosforge.plugin_manager import get_plugin_manager
        mgr = get_plugin_manager()
        for p in mgr.plugins:
            if p.id.lower().startswith("gomckee"):
                return p
    except Exception:
        return None
    return None


def is_gomckee_enabled() -> bool:
    """True iff the Go McKee plugin is enabled (persisted toggle).

    Source of truth is plugin_states via PluginManager.is_enabled, so the
    Enable/Disable toggle genuinely gates behavior and survives restart.
    """
    info = _gomckee_info()
    if info is None:
        return False
    try:
        from logosforge.plugin_manager import get_plugin_manager
        return bool(get_plugin_manager().is_enabled(info.id))
    except Exception:
        return bool(getattr(info, "enabled", False))


def _get_service(plugin_root):
    """Construct (and cache) the GoMcKeeService for a plugin root."""
    key = str(plugin_root)
    if key in _service_cache:
        return _service_cache[key]
    # Ensure the plugin dir is importable (the loader adds it too, but the
    # bridge may run before/without a full plugin load, e.g. in tests).
    if key not in sys.path:
        sys.path.insert(0, key)
    from gomckee.service import GoMcKeeService
    service = GoMcKeeService(plugin_root)
    _service_cache[key] = service
    return service


def _build_project_data(
    db: Any, project_id: int, scene_id: int | None, query_text: str,
) -> dict:
    """Assemble a PSYKE-aware snapshot for the Go McKee service.

    Every field is best-effort: missing DB methods or data degrade to
    empty values rather than failing the whole context.
    """
    data: dict[str, Any] = {}

    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            return default

    project = _safe(lambda: db.get_project_by_id(project_id), None)
    data["project_title"] = getattr(project, "title", "") if project else ""

    scenes = _safe(lambda: db.get_all_scenes(project_id), [])
    data["scene_count"] = len(scenes)

    # PSYKE entries — names + types.
    entries = _safe(lambda: db.get_all_psyke_entries(project_id), [])
    data["psyke_entries"] = [
        {"name": e.name, "type": getattr(e, "entry_type", "")}
        for e in entries[:_MAX_PSYKE]
    ]

    # PSYKE relations — pairs (drives dialogue PSYKE pressure).
    relations: list[dict] = []
    id_to_name = {e.id: e.name for e in entries}
    for e in entries:
        related = _safe(lambda e=e: db.get_related_psyke_entries(e.id), [])
        for r in related:
            relations.append({"a": e.name, "b": id_to_name.get(r.id, r.name)})
            if len(relations) >= _MAX_PSYKE:
                break
        if len(relations) >= _MAX_PSYKE:
            break
    data["relations"] = relations

    # Character progression states for the active scene (drives character
    # PSYKE pressure).
    character_states: dict[str, str] = {}
    if scene_id is not None:
        char_names = {}
        chars = _safe(lambda: db.get_all_characters(project_id), [])
        char_names = {c.id: c.name for c in chars}
        states = _safe(lambda: db.get_scene_character_states(scene_id), [])
        for cid, state in states:
            if state:
                character_states[char_names.get(cid, str(cid))] = state
    data["character_states"] = character_states

    # Current + nearby scenes (drives story PSYKE pressure).
    if scene_id is not None:
        scene = _safe(lambda: db.get_scene_by_id(scene_id), None)
        if scene is not None:
            data["current_scene"] = {
                "title": scene.title,
                "text": (scene.content or "") or (scene.summary or ""),
            }
            order = getattr(scene, "sort_order", None)
            if order is not None:
                nearby = [
                    s.title for s in scenes
                    if abs((getattr(s, "sort_order", 0)) - order) == 1
                ]
                data["nearby_scenes"] = nearby[:_MAX_NEARBY]
    data.setdefault("current_scene", {})
    data.setdefault("nearby_scenes", [])

    # Story memory.
    memories = _safe(lambda: db.get_memories(project_id), [])
    data["story_memory"] = [getattr(m, "value", "") for m in memories[:_MAX_PSYKE]]

    return data


def gather_gomckee_context(
    db: Any, project_id: int, scene_id: int | None = None, query_text: str = "",
) -> str:
    """Return a compact ``[Go McKee]`` constraint block, or "" when OFF.

    When Go McKee is enabled, this runs the plugin's intelligence service
    over a PSYKE-aware project snapshot and surfaces its active craft
    domains, top constraints, and diagnostic checks for the Assistant.
    """
    if not is_gomckee_enabled():
        return ""

    info = _gomckee_info()
    if info is None:
        return ""

    try:
        service = _get_service(info.path)
        project_data = _build_project_data(db, project_id, scene_id, query_text)
        prompt = query_text or "Evaluate the current story material."
        result = service.evaluate(
            prompt + " /gomckee check",
            enabled=True,
            project_data=project_data,
        )
    except Exception:
        return ""

    if result is None or not getattr(result, "enabled", False):
        return ""

    lines: list[str] = ["[Go McKee]"]
    domains = getattr(result, "active_domains", None) or []
    if domains:
        lines.append("Active craft domains: " + ", ".join(domains))

    constraints = getattr(result, "constraints", None) or []
    for c in constraints[:_MAX_CONSTRAINTS]:
        lines.append(f"- {c}")

    checks = getattr(result, "checks", None) or []
    if checks:
        lines.append("Diagnostic checks:")
        for item in checks[:_MAX_CHECKS]:
            domain = getattr(item, "domain", "")
            cid = getattr(item, "check_id", "")
            status = getattr(item, "status", "")
            rationale = getattr(item, "rationale", "")
            lines.append(f"  - {domain}/{cid}: {status} — {rationale}")

    # Nothing actionable beyond the header → skip the block entirely.
    if len(lines) <= 1:
        return ""

    lines.append(
        "Apply these as craft pressure when advising; do not lecture. "
        "You may propose PSYKE updates, but never assume them."
    )
    return "\n".join(lines)
