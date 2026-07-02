"""Export endpoint — structured story/project data + manuscript/screenplay export.

Reuses :mod:`logosforge.data_export` (structured json/markdown/csv) and
:mod:`logosforge.export` (manuscript/screenplay text + binary PDF/DOCX/FDX) so the
API never re-implements export logic — the same code paths the desktop File ▸
Export menu uses. Binary formats are written to a temp file, then returned as
base64 in ``content_base64`` (the client decodes + saves).
"""

from __future__ import annotations

import base64
import os
import re
import tempfile

from fastapi import APIRouter, Depends

from logosforge.api import schemas
from logosforge.api.deps import get_db, get_project
from logosforge.api.errors import ApiError, bad_request
from logosforge.db import Database

router = APIRouter(tags=["export"])

_VALID_TYPES = {"story_elements", "psyke_data", "full_project"}
_VALID_FORMATS = {"json", "markdown", "csv"}

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Manuscript / screenplay TEXT exports whose CONTENT is their own native format —
# each maps to (string-returning fn, native format label, file ext, mime type).
_TEXT_EXPORTS = {
    "manuscript": ("export_manuscript", "text", "txt", "text/plain"),
    "screenplay": ("export_screenplay", "text", "txt", "text/plain"),
    "screenplay_fountain": ("export_screenplay_fountain", "fountain", "fountain", "text/plain"),
    "production_fountain": ("export_production_fountain", "fountain", "fountain", "text/plain"),
}

# BINARY screenplay/manuscript exports — each maps to a path-writing fn, file ext,
# and mime type. Returned as base64 since binary can't ride in a JSON string.
_BINARY_EXPORTS = {
    "screenplay_pdf": ("export_screenplay_pdf", "pdf", "application/pdf"),
    "screenplay_docx": ("export_screenplay_docx", "docx", _DOCX_MIME),
    "manuscript_docx": ("export_docx_manuscript", "docx", _DOCX_MIME),
}


def _export_filename(db: Database, project_id: int, ext: str) -> str:
    project = db.get_project_by_id(project_id)
    title = (project.title if project else "") or "export"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_") or "export"
    return f"{safe}.{ext}"


def _render_binary(export_mod, fn_name: str, ext: str, db: Database, project_id: int) -> bytes:
    """Run a path-writing exporter into a temp file and return the raw bytes.

    Raises ``ApiError(502)`` when the optional dependency is missing (reportlab /
    python-docx) or the export reports failure / produces no output. The temp file
    is always cleaned up.
    """
    fd, path = tempfile.mkstemp(suffix="." + ext)
    try:
        os.close(fd)  # the exporter writes via `path`, not the fd
        try:
            result = getattr(export_mod, fn_name)(db, project_id, path)
        except Exception as exc:  # e.g. python-docx not installed (unguarded import)
            raise ApiError(502, f"Export tool unavailable: {exc}", code="export_unavailable")

        # Graceful-degradation results carry an ok flag (PDF -> dict, DOCX -> result
        # object); export_docx_manuscript returns None, where success == non-empty file.
        if isinstance(result, dict):
            ok = bool(result.get("ok", True))
            warnings = list(result.get("warnings") or [])
        elif result is not None:
            ok = bool(getattr(result, "ok", True))
            warnings = list(getattr(result, "warnings", []) or [])
        else:
            ok, warnings = True, []

        if not ok or not os.path.exists(path) or os.path.getsize(path) == 0:
            detail = "; ".join(warnings) or "no output produced"
            raise ApiError(502, f"Export failed: {detail}", code="export_failed")

        with open(path, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@router.post(
    "/projects/{project_id}/export",
    response_model=schemas.ExportResponseDTO,
)
def export_project(
    body: schemas.ExportRequestDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    from logosforge import data_export as de

    # Manuscript / screenplay TEXT exports (Fountain etc.) — rendered text in `content`.
    if body.export_type in _TEXT_EXPORTS:
        from logosforge import export as manuscript_export
        fn_name, native_fmt, ext, mime = _TEXT_EXPORTS[body.export_type]
        text = getattr(manuscript_export, fn_name)(db, project.id)
        return schemas.ExportResponseDTO(
            export_type=body.export_type, format=native_fmt, content=text,
            filename=_export_filename(db, project.id, ext), mime_type=mime,
        )

    # BINARY screenplay/manuscript exports (PDF/DOCX) — base64-encoded file bytes.
    if body.export_type in _BINARY_EXPORTS:
        from logosforge import export as manuscript_export
        fn_name, ext, mime = _BINARY_EXPORTS[body.export_type]
        raw = _render_binary(manuscript_export, fn_name, ext, db, project.id)
        return schemas.ExportResponseDTO(
            export_type=body.export_type, format=ext,
            content_base64=base64.b64encode(raw).decode("ascii"),
            filename=_export_filename(db, project.id, ext), mime_type=mime,
        )

    # FDX (Final Draft XML) — the exporter returns XML text behind an experimental
    # acknowledgement; treat it as a text export.
    if body.export_type == "screenplay_fdx":
        from logosforge import export as manuscript_export
        result = manuscript_export.export_screenplay_fdx_experimental(
            db, project.id, options={"experimental_export_acknowledged": True},
        )
        text = (getattr(result, "text", "") or "").strip()
        if not text:
            warnings = "; ".join(getattr(result, "warnings", []) or [])
            raise ApiError(502, f"FDX export produced no output: {warnings}", code="export_failed")
        return schemas.ExportResponseDTO(
            export_type="screenplay_fdx", format="fdx", content=text,
            filename=_export_filename(db, project.id, "fdx"), mime_type="application/xml",
        )

    if body.export_type not in _VALID_TYPES:
        raise bad_request(f"Unknown export_type: {body.export_type}")
    if body.format not in _VALID_FORMATS:
        raise bad_request(f"Unknown format: {body.format}")

    if body.export_type == "full_project":
        data = de.build_full_export(db, project.id)
    else:
        if body.export_type == "psyke_data":
            opts = de.psyke_data_options()
        else:
            opts = de.story_elements_options()
        # Apply optional per-request overrides.
        for field in (
            "include_outline", "include_plot", "include_timeline",
            "include_scenes", "include_psyke_entries", "include_psyke_relations",
            "include_psyke_progressions", "include_notes",
            "include_project_metadata", "include_ids",
            "include_internal_metadata", "summaries_only",
        ):
            value = getattr(body, field)
            if value is not None:
                setattr(opts, field, value)
        opts.fmt = body.format
        data = de.gather_export(db, project.id, opts)

    response = schemas.ExportResponseDTO(
        export_type=body.export_type, format=body.format,
    )
    if body.format == "json":
        response.payload = data
    elif body.format == "markdown":
        response.content = de.to_markdown(data)
    else:  # csv -> map of filename -> text
        response.files = de.to_csv_files(data)
    return response
