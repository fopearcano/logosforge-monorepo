"""Deterministic completion checks for guided-workflow steps (Phase 10O).

Each check answers a single yes/no question about the *current* project state,
derived entirely from the read-only Project Intelligence report. Checks are
deterministic, call no LLM, and mutate nothing.

CRITICAL SAFETY RULE: completion checks only ever apply to ``check`` steps. The
engine never auto-completes ``creative`` steps regardless of any check — see
``engine.refresh_workflow_run``. So a check here can only *tick* a deterministic,
verifiable step (e.g. "every scene has a summary"); it can never decide that a
piece of creative work is "done".
"""

from __future__ import annotations

from collections.abc import Callable

# name -> check(report) -> bool
_CHECKS: dict[str, Callable[[object], bool]] = {}


def register(name: str, fn: Callable[[object], bool]) -> None:
    _CHECKS[name] = fn


def get_check(name: str) -> "Callable[[object], bool] | None":
    return _CHECKS.get(name)


def has_check(name: str) -> bool:
    return name in _CHECKS


def evaluate(name: str, report) -> "bool | None":
    """Run a check by name against a report. Returns None if unknown/error."""
    fn = _CHECKS.get(name)
    if fn is None:
        return None
    try:
        return bool(fn(report))
    except Exception:
        return None


# -- Overview ---------------------------------------------------------------

register("project_has_title",
         lambda r: bool(r.overview.get("title"))
         and r.overview.get("title") != "Untitled")
register("project_has_description",
         lambda r: bool(r.overview.get("description_present")))
register("has_scenes", lambda r: int(r.overview.get("total_scenes", 0)) > 0)

# -- Structure --------------------------------------------------------------

register("all_scenes_have_summary",
         lambda r: int(r.structure.get("total_scenes", 0)) > 0
         and int(r.structure.get("scenes_without_summary", 0)) == 0)
register("all_scenes_have_chapter",
         lambda r: int(r.structure.get("total_scenes", 0)) > 0
         and int(r.structure.get("scenes_without_chapter", 0)) == 0)
register("has_outline_nodes",
         lambda r: int(r.structure.get("outline_nodes", 0)) > 0)
register("no_isolated_graph_nodes",
         lambda r: bool(r.structure.get("graph_available"))
         and int(r.structure.get("graph_isolated_nodes", 0)) == 0)

# -- PSYKE ------------------------------------------------------------------

register("psyke_has_entries",
         lambda r: bool(r.psyke.get("available")) and int(r.psyke.get("total", 0)) > 0)
register("psyke_notes_filled",
         lambda r: bool(r.psyke.get("available"))
         and int(r.psyke.get("empty_notes", 0)) == 0)
register("psyke_has_relations",
         lambda r: bool(r.psyke.get("available"))
         and int(r.psyke.get("no_relations", 0)) == 0)

# -- Workflow / decisions ---------------------------------------------------

register("no_pending_apply",
         lambda r: int(r.workflow.get("controlled_apply", {}).get("pending", 0)) == 0)
register("no_preferred_rewrite",
         lambda r: not r.workflow.get("rewrite", {}).get("preferred"))
register("no_stale_rewrite",
         lambda r: not r.workflow.get("rewrite", {}).get("stale"))
register("radar_clear",
         lambda r: not any(c.severity in ("blocking", "warning") for c in r.radar))
register("no_blocking_decisions",
         lambda r: not any(c.severity == "blocking" for c in r.radar))

# -- Production / export (screenplay) ---------------------------------------

register("production_active",
         lambda r: bool(r.workflow.get("production", {}).get("active")))
register("production_has_revision_set",
         lambda r: bool(r.workflow.get("production", {}).get("revision_sets")))
register("export_safe",
         lambda r: bool(r.export.get("checked"))
         and bool(r.export.get("is_export_safe", False)))
register("export_no_warnings",
         lambda r: bool(r.export.get("checked"))
         and not r.export.get("warnings"))
