"""Screenplay Fountain interchange — export + import safety layer (Phase 4).

A thin, deterministic layer on top of the mature Fountain format module
(:mod:`logosforge.screenplay_fountain`) and the canonical project export
(:mod:`logosforge.export`). It adds what interchange needs end to end:

* **Export** — a single scene or the full project to ``.fountain`` text, and the
  same written to a file path. Always canonical Act→Chapter→Scene order, always
  **body only** (``Scene.content``) — never Outline summaries, Timeline notes,
  PSYKE metadata, or provider/API settings.
* **Validation** — a pre-export readiness check that warns (never silently
  corrupts) about missing headings, orphan dialogue/parentheticals, empty
  scenes, leaked markdown fences, or an Outline summary pasted into the body.
* **Import** — parse ``.fountain`` into *grouped scenes*, build a preview that
  performs **no mutation**, and apply it only with explicit confirmation. New
  scenes are created through :mod:`logosforge.story_structure` (so they always
  get a valid Act + Chapter parent — never orphaned); scene-body writes route
  through Controlled Apply (so an existing body is never overwritten unconfirmed).

Pure logic + DB service calls. No Qt, no LLM. The UI owns file pickers / dialogs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb
from logosforge import screenplay_fountain as sf

# -- Import modes ------------------------------------------------------------
IMPORT_NEW_PROJECT = "new_project"        # create a fresh screenplay project
IMPORT_INTO_PROJECT = "into_project"      # add as a new Act/Chapter of scenes
IMPORT_INTO_SCENE = "into_scene"          # append the import to one scene's body
IMPORT_REPLACE_SCENE = "replace_scene"    # replace one scene's body
IMPORT_MODES = (IMPORT_NEW_PROJECT, IMPORT_INTO_PROJECT,
                IMPORT_INTO_SCENE, IMPORT_REPLACE_SCENE)


# ===========================================================================
# Export — scene + project
# ===========================================================================


def _scene_heading_text(scene) -> str:
    """A heading line for a scene that doesn't open with one (slug or title)."""
    slug = (getattr(scene, "slugline", "") or "").strip()
    if slug:
        return slug
    return (getattr(scene, "title", "") or "Untitled Scene").strip().upper()


def build_scene_blocks(db, project_id: int, scene_id: int) -> list[sb.ScreenplayBlock]:
    """Build one scene's screenplay blocks (body only), injecting a scene heading
    from the slug/title when the body doesn't already open with one. Read-only."""
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return []
    raw = getattr(scene, "content", "") or ""
    parsed = sb.parse_screenplay_text(raw, scene_id=scene_id) if raw.strip() else []
    blocks: list[sb.ScreenplayBlock] = []
    order = 0
    if not (parsed and parsed[0].element_type == "scene_heading"):
        blocks.append(sb.ScreenplayBlock(
            element_type="scene_heading", text=_scene_heading_text(scene),
            order_index=order))
        order += 1
    for b in parsed:
        blocks.append(sb.ScreenplayBlock(
            element_type=b.element_type, text=b.text, order_index=order,
            metadata=dict(b.metadata)))
        order += 1
    return blocks


def serialize_scene_to_fountain(
    db, project_id: int, scene_id: int, *, options=None,
) -> sf.FountainExportResult:
    """Serialize a single scene's **body** to ``.fountain`` (no title page by
    default — a scene fragment isn't a whole document). Read-only."""
    opts = options or sf.FountainExportOptions(include_title_page=False)
    scene = db.get_scene_by_id(scene_id)
    title = (getattr(scene, "title", "") or "scene") if scene else "scene"
    return sf.serialize_screenplay_to_fountain(
        build_scene_blocks(db, project_id, scene_id),
        title_page=None, options=opts, project_title=title)


def serialize_project_to_fountain(
    db, project_id: int, *, options=None, include_empty_scenes: bool = True,
) -> sf.FountainExportResult:
    """Serialize the whole project to ``.fountain`` in canonical scene order.

    Body only, title page from project metadata, contamination-free. By default
    delegates to the canonical project serializer; when *include_empty_scenes* is
    False, scenes with a blank body are skipped (planning-only scenes are not
    exported as empty heading stubs)."""
    if include_empty_scenes:
        from logosforge.export import export_screenplay_fountain_result
        return export_screenplay_fountain_result(db, project_id, options=options)

    # Filtered assembly — canonical order, skip blank-body scenes.
    from logosforge.screenplay_render import get_export_prefs, get_title_page
    project = db.get_project_by_id(project_id)
    title = project.title if project else "Untitled"
    if options is None:
        prefs = get_export_prefs(db, project_id)
        options = sf.FountainExportOptions(
            include_notes=bool(prefs.get("show_notes_in_export", False)),
            include_title_page=bool(prefs.get("include_title_page", True)),
            uppercase_scene_headings=bool(prefs.get("uppercase_scene_headings", True)),
            uppercase_character_cues=bool(prefs.get("uppercase_character_cues", True)),
        )
    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        scenes = []
    blocks: list[sb.ScreenplayBlock] = []
    for scene in scenes:
        if not (getattr(scene, "content", "") or "").strip():
            continue
        blocks.extend(build_scene_blocks(db, project_id, scene.id))
    return sf.serialize_screenplay_to_fountain(
        blocks, title_page=get_title_page(db, project_id), options=options,
        project_title=title)


def _write_text(path: str, text: str) -> str:
    if not path.endswith(".fountain"):
        path += ".fountain"
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        raise OSError(f"Directory does not exist: {parent}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def export_scene_fountain(
    db, project_id: int, scene_id: int, output_path: str, *, options=None,
) -> dict:
    """Write one scene to a ``.fountain`` file. Returns ``{ok, path, warnings}``.
    Does not mutate project data."""
    result = serialize_scene_to_fountain(db, project_id, scene_id, options=options)
    try:
        path = _write_text(output_path, result.text)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "warnings": list(result.warnings)}
    return {"ok": True, "path": path, "warnings": list(result.warnings),
            "filename": os.path.basename(path)}


def export_project_fountain(
    db, project_id: int, output_path: str, *, options=None,
    include_empty_scenes: bool = True,
) -> dict:
    """Write the whole project to a ``.fountain`` file. Returns ``{ok, path,
    warnings}``. Does not mutate project data."""
    result = serialize_project_to_fountain(
        db, project_id, options=options, include_empty_scenes=include_empty_scenes)
    try:
        path = _write_text(output_path, result.text)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "warnings": list(result.warnings)}
    return {"ok": True, "path": path, "warnings": list(result.warnings),
            "filename": os.path.basename(path)}


# ===========================================================================
# Pre-export validation (deterministic, read-only)
# ===========================================================================


@dataclass
class FountainExportReadiness:
    is_ready: bool = True               # False only when output would be corrupt
    scene_count: int = 0
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_ready": self.is_ready, "scene_count": self.scene_count,
            "blocking_errors": list(self.blocking_errors),
            "warnings": list(self.warnings), "summary": self.summary,
        }


def validate_fountain_export_readiness(
    db, project_id: int, *, scene_id: int | None = None,
) -> FountainExportReadiness:
    """Deterministic pre-export check. Warnings never block; only structurally
    corrupt output (empty result) blocks. Read-only — never mutates."""
    report = FountainExportReadiness()
    if scene_id is not None:
        scenes = [db.get_scene_by_id(scene_id)]
        scenes = [s for s in scenes if s is not None]
    else:
        try:
            scenes = db.get_all_scenes(project_id)
        except Exception:
            scenes = []
    report.scene_count = len(scenes)

    if not scenes:
        report.blocking_errors.append("Nothing to export — no scenes.")
        report.is_ready = False
        report.summary = "Not ready: no scenes to export."
        return report

    for idx, scene in enumerate(scenes, start=1):
        content = getattr(scene, "content", "") or ""
        label = (getattr(scene, "title", "") or f"Scene {idx}").strip() or f"Scene {idx}"
        if not content.strip():
            report.warnings.append(f"{label}: empty scene (no body to export).")
            continue
        if "```" in content:
            report.warnings.append(f"{label}: body contains markdown code fences.")
        summary = (getattr(scene, "summary", "") or "").strip()
        if summary and len(summary) > 12 and summary in content:
            report.warnings.append(
                f"{label}: an Outline summary appears inside the body.")
        blocks = sb.parse_screenplay_text(content, scene_id=getattr(scene, "id", None))
        has_heading = (any(b.element_type == "scene_heading" for b in blocks)
                       or bool((getattr(scene, "slugline", "") or "").strip()))
        if not has_heading:
            report.warnings.append(f"{label}: no scene heading (INT./EXT. …).")
        prev = None
        for b in blocks:
            if b.element_type == "dialogue" and prev not in (
                    "character", "parenthetical", "dialogue"):
                report.warnings.append(f"{label}: dialogue without a character cue.")
            if b.element_type == "parenthetical" and prev not in (
                    "character", "dialogue"):
                report.warnings.append(f"{label}: parenthetical without dialogue context.")
            prev = b.element_type

    # Format-level check on the generated output (catches a structurally empty
    # export -> the only thing that actually blocks).
    try:
        result = (serialize_scene_to_fountain(db, project_id, scene_id)
                  if scene_id is not None
                  else serialize_project_to_fountain(db, project_id))
        fval = sf.validate_fountain_export(result.text)
        if not fval.is_valid:
            report.blocking_errors.extend(fval.blocking_errors)
    except Exception as exc:
        report.blocking_errors.append(f"Could not generate Fountain output: {exc}")

    # De-duplicate while preserving order.
    report.warnings = list(dict.fromkeys(report.warnings))
    report.blocking_errors = list(dict.fromkeys(report.blocking_errors))
    report.is_ready = not report.blocking_errors
    report.summary = (
        ("Ready to export" if report.is_ready else "Not export-ready")
        + f": {len(report.blocking_errors)} error(s), {len(report.warnings)} warning(s)."
    )
    return report


def validate_export_blocks(
    blocks: list[sb.ScreenplayBlock],
) -> FountainExportReadiness:
    """Deterministic block-level export check (used for imported/constructed
    block lists). Warnings never block; only an empty list blocks. Read-only.

    Note: :class:`ScreenplayBlock` normalizes unknown element types to ``action``
    (safe degradation), so an "unknown block type" can never reach export as a
    corrupt type — it is reported as a (degraded) action instead."""
    report = FountainExportReadiness()
    if not blocks:
        report.blocking_errors.append("No blocks to export.")
        report.is_ready = False
        report.summary = "Not ready: no blocks."
        return report

    if not any(b.element_type == "scene_heading" for b in blocks):
        report.warnings.append("No scene heading (INT./EXT. …).")
    empty = sum(1 for b in blocks if not (b.text or "").strip())
    if empty:
        report.warnings.append(f"{empty} empty block(s).")
    if any("```" in (b.text or "") for b in blocks):
        report.warnings.append("A block contains markdown code fences.")
    prev = None
    orphan_dlg = orphan_paren = 0
    for b in blocks:
        if b.element_type == "dialogue" and prev not in (
                "character", "parenthetical", "dialogue"):
            orphan_dlg += 1
        if b.element_type == "parenthetical" and prev not in ("character", "dialogue"):
            orphan_paren += 1
        prev = b.element_type
    if orphan_dlg:
        report.warnings.append(f"{orphan_dlg} dialogue block(s) without a character cue.")
    if orphan_paren:
        report.warnings.append(f"{orphan_paren} parenthetical(s) without dialogue context.")

    report.warnings = list(dict.fromkeys(report.warnings))
    report.is_ready = not report.blocking_errors
    report.summary = (
        ("Ready" if report.is_ready else "Not ready")
        + f": {len(report.warnings)} warning(s)."
    )
    return report


# ===========================================================================
# Import — parse into grouped scenes + preview (no mutation)
# ===========================================================================


@dataclass
class ImportedScene:
    heading: str = ""
    title: str = "Untitled Scene"
    blocks: list[sb.ScreenplayBlock] = field(default_factory=list)

    def body_text(self) -> str:
        return sb.serialize_blocks(self.blocks)

    def to_dict(self) -> dict[str, Any]:
        return {"heading": self.heading, "title": self.title,
                "block_count": len(self.blocks),
                "blocks": [b.to_dict() for b in self.blocks]}


@dataclass
class FountainImportPreview:
    scenes: list[ImportedScene] = field(default_factory=list)
    title_page: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def scene_count(self) -> int:
        return len(self.scenes)

    @property
    def block_count(self) -> int:
        return sum(len(s.blocks) for s in self.scenes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenes": [s.to_dict() for s in self.scenes],
            "title_page": dict(self.title_page),
            "warnings": list(self.warnings),
            "scene_count": self.scene_count, "block_count": self.block_count,
        }


def _title_from_heading(heading: str, index: int) -> str:
    h = (heading or "").strip()
    if not h:
        return f"Imported Scene {index}"
    # Strip a leading INT./EXT. prefix for a friendlier title; keep it short.
    title = h
    for p in ("INT./EXT.", "INT.", "EXT.", "EST.", "I/E."):
        if title.upper().startswith(p):
            title = title[len(p):].strip(" .-")
            break
    return (title or h)[:80]


def parse_fountain_to_scenes(text: str) -> FountainImportPreview:
    """Parse ``.fountain`` text and group its blocks into scenes by heading.

    Block order is preserved; content before the first heading becomes a leading
    "Imported Scene" so nothing is lost. Read-only."""
    preview = FountainImportPreview()
    parsed = sf.parse_fountain_to_screenplay_blocks(text)
    preview.title_page = dict(parsed.title_page)
    preview.warnings = list(parsed.warnings)

    current: ImportedScene | None = None
    for b in parsed.blocks:
        if b.element_type == "scene_heading":
            if current is not None:
                preview.scenes.append(current)
            current = ImportedScene(heading=b.text, blocks=[b])
        else:
            if current is None:
                current = ImportedScene(heading="", blocks=[])
            current.blocks.append(b)
    if current is not None and current.blocks:
        preview.scenes.append(current)

    for i, scene in enumerate(preview.scenes, start=1):
        scene.title = _title_from_heading(scene.heading, i)
    if not preview.scenes:
        preview.warnings.append("No screenplay scenes detected in the Fountain input.")
    return preview


def build_import_preview(
    db, project_id: int, text: str, *, mode: str = IMPORT_INTO_PROJECT,
) -> FountainImportPreview:
    """Build an import preview. **No mutation** regardless of mode. The *mode*
    only annotates the preview's warnings with what apply *would* do."""
    preview = parse_fountain_to_scenes(text)
    if mode not in IMPORT_MODES:
        preview.warnings.append(f"Unknown import mode: {mode!r}.")
    return preview


# ===========================================================================
# Import — apply (requires explicit confirmation)
# ===========================================================================


def _apply_scene_body(db, project_id: int, scene_id: int, text: str,
                      *, apply_mode: str, confirmed: bool) -> dict:
    """Write a scene body through Controlled Apply (never an unconfirmed
    overwrite)."""
    from logosforge.controlled_apply.service import apply_operation
    return apply_operation(
        db, project_id, target_type="screenplay_block", target_id=scene_id,
        proposed_text=text, apply_mode=apply_mode, confirmed=confirmed,
        source_type="fountain_import")


def apply_fountain_import(
    db, project_id: int, source, *, mode: str = IMPORT_INTO_PROJECT,
    confirmed: bool = False, target_scene_id: int | None = None,
    act: str | None = None, chapter: str | None = None,
    new_project_title: str | None = None,
) -> dict:
    """Apply a Fountain import. **Requires ``confirmed=True``** — without it
    nothing is created or overwritten (the body/preview is returned untouched).

    *source* may be raw Fountain text or a :class:`FountainImportPreview`.

    Modes:
    * ``new_project`` — create a screenplay project and add the scenes.
    * ``into_project`` — add the scenes under a (created) Act/Chapter.
    * ``into_scene`` — append the import to ``target_scene_id``'s body.
    * ``replace_scene`` — replace ``target_scene_id``'s body.

    New scenes are created via ``story_structure.create_scene`` (always parented;
    never orphaned). Existing-scene writes route through Controlled Apply.
    """
    if mode not in IMPORT_MODES:
        return {"ok": False, "error": f"Unknown import mode: {mode!r}"}
    if not confirmed:
        return {"ok": False, "error": "Import requires explicit confirmation."}

    preview = source if isinstance(source, FountainImportPreview) else \
        parse_fountain_to_scenes(source)
    if not preview.scenes:
        return {"ok": False, "error": "No scenes to import."}

    from logosforge import story_structure as ss

    # -- Single-scene targets ------------------------------------------------
    if mode in (IMPORT_INTO_SCENE, IMPORT_REPLACE_SCENE):
        if target_scene_id is None:
            return {"ok": False, "error": "No target scene selected."}
        if db.get_scene_by_id(target_scene_id) is None:
            return {"ok": False, "error": "Target scene not found."}
        # All imported blocks flow into the one selected scene.
        body = "\n\n".join(s.body_text() for s in preview.scenes).strip()
        apply_mode = "append" if mode == IMPORT_INTO_SCENE else "replace"
        res = _apply_scene_body(db, project_id, target_scene_id, body,
                                apply_mode=apply_mode, confirmed=True)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error", "Apply failed."),
                    "conflicts": res.get("conflicts", [])}
        return {"ok": True, "mode": mode, "scene_id": target_scene_id,
                "scenes_created": 0, "warnings": list(preview.warnings)}

    # -- Whole-import targets (create scenes) --------------------------------
    if mode == IMPORT_NEW_PROJECT:
        title = (new_project_title or preview.title_page.get("title")
                 or "Imported Screenplay").strip() or "Imported Screenplay"
        project = db.create_project(title, narrative_engine="screenplay",
                                    default_writing_format="screenplay")
        target_pid = project.id
        act_name = act or ss.DEFAULT_ACT
        chapter_name = chapter or ss.DEFAULT_CHAPTER
    else:  # IMPORT_INTO_PROJECT
        target_pid = project_id
        act_name = act or "Imported"
        chapter_name = chapter or "Imported Scenes"

    created_ids: list[int] = []
    for scene in preview.scenes:
        created = ss.create_scene(
            db, target_pid, act=act_name, chapter=chapter_name,
            title=scene.title, content=scene.body_text())
        created_ids.append(getattr(created, "id", None))

    return {"ok": True, "mode": mode, "project_id": target_pid,
            "scenes_created": len(created_ids), "scene_ids": created_ids,
            "act": act_name, "chapter": chapter_name,
            "warnings": list(preview.warnings)}
