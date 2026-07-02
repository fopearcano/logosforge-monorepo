"""Screenplay production-draft service layer (Phase 10J).

A safe, optional, screenplay-only production layer: production drafts, persistent
scene numbering, omitted-scene tracking, dated/coloured revision sets, and
production-readiness validation. Deterministic; no LLM; mutations are explicit
(callers obtain user confirmation). Page locking is *awareness only* — never
"stable" — because pagination is approximate.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from logosforge.models.models import REVISION_COLORS

# Readiness levels.
LEVEL_SPEC = "spec"
LEVEL_STRUCTURAL = "production-ready-structural"
LEVEL_NUMBERED = "production-ready-numbered"
LEVEL_REVISED = "production-ready-revised"
LEVEL_OUTPUT_LIMITED = "production-output-limited"
LEVEL_UNSUPPORTED = "unsupported"


def _is_screenplay(db, project_id: int) -> bool:
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        return get_project_writing_mode_by_id(db, project_id) == "screenplay"
    except Exception:
        return False


def _scene_hash(scene) -> str:
    content = getattr(scene, "content", "") or ""
    return hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Production mode + drafts (explicit, user-confirmed mutations)
# ---------------------------------------------------------------------------


def enable_production_mode(db, project_id: int, *, draft_label: str = "",
                           draft_date: str = "") -> "object | None":
    """Create (or return) the active production draft for a screenplay project."""
    if not _is_screenplay(db, project_id):
        return None
    existing = db.get_active_production_draft(project_id)
    if existing is not None:
        return existing
    return db.create_production_draft(
        project_id, status="production", is_active=True,
        scene_numbering_enabled=False, page_locking_enabled=False,
        page_locking_status="approximate", draft_label=draft_label,
        draft_date=draft_date)


def is_production_mode(db, project_id: int) -> bool:
    return db.get_active_production_draft(project_id) is not None


# ---------------------------------------------------------------------------
# Scene numbering
# ---------------------------------------------------------------------------

_NUM_RE = re.compile(r"^([A-Za-z]*)(\d+)([A-Za-z]*)$")


def _ordered_scenes(db, project_id: int):
    try:
        return db.get_all_scenes(project_id)
    except Exception:
        return []


def assign_scene_numbers(db, project_id: int) -> dict[int, str]:
    """Assign sequential numbers (1,2,3…) to non-omitted scenes in order.

    Preserves existing numbers and omitted markers; only fills gaps and numbers
    new scenes. Inserted scenes between N and N+1 get a letter suffix (``10A``).
    Returns {scene_id: scene_number}. Explicit/user-confirmed.
    """
    draft = enable_production_mode(db, project_id)
    if draft is None:
        return {}
    db.update_production_draft(draft.id, scene_numbering_enabled=True)
    existing = {r.scene_id: r for r in db.get_production_scene_numbers(draft.id)}
    scenes = _ordered_scenes(db, project_id)

    # First pass: keep already-numbered (non-omitted) scenes; collect used numbers.
    used: set[str] = {r.scene_number for r in existing.values() if r.scene_number}
    result: dict[int, str] = {}
    next_base = 1

    def _fresh_number() -> str:
        nonlocal next_base
        while str(next_base) in used:
            next_base += 1
        n = str(next_base)
        used.add(n)
        next_base += 1
        return n

    for idx, scene in enumerate(scenes):
        row = existing.get(scene.id)
        if row is not None and row.is_omitted:
            result[scene.id] = row.scene_number  # keep omitted number, don't reuse
            db.set_production_scene_number(project_id, draft.id, scene.id,
                                           sort_index=idx)
            continue
        if row is not None and row.scene_number:
            result[scene.id] = row.scene_number
            db.set_production_scene_number(project_id, draft.id, scene.id,
                                           sort_index=idx)
            continue
        num = _fresh_number()
        db.set_production_scene_number(
            project_id, draft.id, scene.id, scene_number=num,
            original_scene_number=num, sort_index=idx)
        result[scene.id] = num
    return result


def insert_scene_number(between: str, after: str | None = None) -> str:
    """Production-safe inserted number between *between* and the next number.

    Convention: append a letter suffix to the lower number (``10`` → ``10A``);
    repeated inserts advance the suffix (``10A`` → ``10B``).
    """
    m = _NUM_RE.match(between or "")
    if not m:
        return f"{between}A"
    prefix, digits, suffix = m.groups()
    if not suffix:
        return f"{prefix}{digits}A"
    return f"{prefix}{digits}{chr(ord(suffix[-1]) + 1)}"


def omit_scene(db, project_id: int, scene_id: int, *, label: str = "OMITTED"):
    """Mark a scene omitted — keeps its number, never reused. Explicit."""
    draft = db.get_active_production_draft(project_id)
    if draft is None:
        return None
    rows = {r.scene_id: r for r in db.get_production_scene_numbers(draft.id)}
    row = rows.get(scene_id)
    number = row.scene_number if row else ""
    return db.set_production_scene_number(
        project_id, draft.id, scene_id, is_omitted=True, omitted_label=label,
        scene_number=number)


def restore_scene(db, project_id: int, scene_id: int):
    draft = db.get_active_production_draft(project_id)
    if draft is None:
        return None
    return db.set_production_scene_number(
        project_id, draft.id, scene_id, is_omitted=False, omitted_label="")


def scene_number_map(db, project_id: int) -> dict[int, dict]:
    """{scene_id: {"number": str, "omitted": bool}} for the active draft."""
    draft = db.get_active_production_draft(project_id)
    if draft is None:
        return {}
    return {
        r.scene_id: {"number": r.scene_number, "omitted": r.is_omitted,
                     "label": r.omitted_label}
        for r in db.get_production_scene_numbers(draft.id) if r.scene_id is not None
    }


def validate_scene_numbers(db, project_id: int) -> list[str]:
    """Return a list of scene-number problems (empty = valid)."""
    problems: list[str] = []
    draft = db.get_active_production_draft(project_id)
    if draft is None:
        return ["No active production draft."]
    rows = db.get_production_scene_numbers(draft.id)
    seen: dict[str, int] = {}
    for r in rows:
        if r.is_omitted:
            continue
        if not (r.scene_number or "").strip():
            problems.append(f"Scene {r.scene_id} has no scene number.")
            continue
        seen[r.scene_number] = seen.get(r.scene_number, 0) + 1
    for num, count in seen.items():
        if count > 1:
            problems.append(f"Duplicate scene number '{num}'.")
    return problems


# ---------------------------------------------------------------------------
# Revision sets (scene-level, text-hash change detection)
# ---------------------------------------------------------------------------


def _latest_hashes(db, draft_id: int) -> dict[int, str]:
    out: dict[int, str] = {}
    for ch in db.get_revision_changes(draft_id):
        if ch.scene_id is not None and ch.new_text_hash:
            out[ch.scene_id] = ch.new_text_hash
    return out


def create_revision_set(db, project_id: int, *, label: str = "",
                        description: str = "", revision_date: str = ""):
    """Create the next-coloured revision set and record changed scenes.

    First set records all scenes as 'added'; later sets record 'modified' only
    for scenes whose content hash changed since the previous set. Never triggered
    automatically per keystroke — this is an explicit action.
    """
    draft = db.get_active_production_draft(project_id)
    if draft is None:
        return None
    existing = db.get_revision_sets(draft.id)
    color = REVISION_COLORS[min(len(existing), len(REVISION_COLORS) - 1)]
    rs = db.create_revision_set(
        project_id, draft.id, label=label or color, color_name=color,
        status="draft", description=description, revision_date=revision_date)

    baseline = _latest_hashes(db, draft.id)
    first = not existing
    for scene in _ordered_scenes(db, project_id):
        h = _scene_hash(scene)
        old = baseline.get(scene.id, "")
        if first:
            db.create_revision_change(project_id, draft.id, rs.id, scene_id=scene.id,
                                      change_type="added", new_text_hash=h)
        elif old != h:
            db.create_revision_change(project_id, draft.id, rs.id, scene_id=scene.id,
                                      change_type="modified", old_text_hash=old,
                                      new_text_hash=h, summary="Scene content changed.")
    db.update_production_draft(draft.id, status="revised")
    return rs


def changed_scenes_since_last_revision(db, project_id: int) -> list[int]:
    draft = db.get_active_production_draft(project_id)
    if draft is None:
        return []
    baseline = _latest_hashes(db, draft.id)
    if not baseline:
        return []
    changed = []
    for scene in _ordered_scenes(db, project_id):
        if baseline.get(scene.id, "") != _scene_hash(scene):
            changed.append(scene.id)
    return changed


# ---------------------------------------------------------------------------
# Status + validation
# ---------------------------------------------------------------------------


@dataclass
class ProductionValidationReport:
    project_id: int
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    readiness_level: str = LEVEL_SPEC

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "blocking_errors": list(self.blocking_errors),
            "warnings": list(self.warnings), "suggestions": list(self.suggestions),
            "readiness_level": self.readiness_level,
        }


def production_status(db, project_id: int) -> dict:
    """Concise, deterministic production status (read-only)."""
    draft = db.get_active_production_draft(project_id)
    if draft is None:
        return {"mode": "spec", "active": False}
    nums = db.get_production_scene_numbers(draft.id)
    revs = db.get_revision_sets(draft.id)
    numbered = [r for r in nums if r.scene_number and not r.is_omitted]
    omitted = [r for r in nums if r.is_omitted]
    return {
        "mode": "production", "active": True,
        "draft_label": draft.draft_label or draft.name,
        "draft_date": draft.draft_date,
        "scene_numbering_enabled": draft.scene_numbering_enabled,
        "numbered_scenes": len(numbered),
        "omitted_scenes": len(omitted),
        "active_revision_set": (revs[-1].label if revs else ""),
        "revision_sets": len(revs),
        "page_locking_status": draft.page_locking_status,
        "warnings": validate_scene_numbers(db, project_id) if draft.scene_numbering_enabled else [],
    }


def validate_production_draft(db, project_id: int) -> ProductionValidationReport:
    report = ProductionValidationReport(project_id=project_id)
    if not _is_screenplay(db, project_id):
        report.blocking_errors.append("Project is not a screenplay.")
        report.readiness_level = LEVEL_UNSUPPORTED
        return report
    draft = db.get_active_production_draft(project_id)
    if draft is None:
        report.readiness_level = LEVEL_SPEC
        report.suggestions.append("Enable production mode to assign scene numbers.")
        return report

    report.readiness_level = LEVEL_STRUCTURAL
    if draft.scene_numbering_enabled:
        problems = validate_scene_numbers(db, project_id)
        dupes = [p for p in problems if "Duplicate" in p]
        report.blocking_errors.extend(dupes)            # duplicates block
        report.warnings.extend(p for p in problems if p not in dupes)
        if not report.blocking_errors:
            report.readiness_level = LEVEL_NUMBERED
    else:
        report.suggestions.append("Assign scene numbers for a numbered draft.")

    revs = db.get_revision_sets(draft.id)
    if revs and report.readiness_level == LEVEL_NUMBERED:
        report.readiness_level = LEVEL_REVISED

    # Page locking is approximate at best -> output-limited note (not blocking).
    if draft.page_locking_status in ("approximate", "unsupported"):
        report.warnings.append(
            "Page locking is approximate — true page-accurate locking is deferred.")
        if report.readiness_level in (LEVEL_NUMBERED, LEVEL_REVISED):
            report.suggestions.append(
                "Output is structurally production-ready; pagination is approximate.")
    return report
