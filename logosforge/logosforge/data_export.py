"""Structured data export for story elements and project data.

Unlike :mod:`logosforge.export` (which produces *manuscript* text in formats
like DOCX/PDF/Fountain), this module exports the *structured data* behind a
project — outline, plot, timeline, PSYKE bible, notes and project metadata — as
clean JSON, human-readable Markdown, or tabular CSV.

Three high-level entry points back the File ▸ Export menu items:

* :func:`build_story_elements` — project + outline + plot + timeline + PSYKE +
  notes, in a clean *nested* shape.
* :func:`build_psyke_data` — just the PSYKE bible (entries / relations /
  progressions), grouped by kind.
* :func:`build_full_export` — everything, in an *import-compatible* shape that
  round-trips through :mod:`logosforge.import_data`.

All builders read live from the :class:`~logosforge.db.Database`, which is the
same source of truth the UI sections use, so exports always reflect the current
(including not-yet-saved-to-disk) project state.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from logosforge.db import Database

SCHEMA_VERSION = 1

# PSYKE entry kinds, in the order they should be grouped/rendered.
PSYKE_KIND_ORDER = ("character", "place", "object", "lore", "theme", "other")
_PSYKE_KIND_LABELS = {
    "character": "Characters",
    "place": "Places",
    "object": "Objects",
    "lore": "Lore",
    "theme": "Themes",
    "other": "Other",
}


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


@dataclass
class ExportOptions:
    """User-selected sections, format and field-level toggles for an export."""

    # -- Sections ----------------------------------------------------------
    include_project_metadata: bool = True
    include_outline: bool = True
    include_plot: bool = True
    include_timeline: bool = True
    include_scenes: bool = False
    include_psyke_entries: bool = True
    include_psyke_relations: bool = True
    include_psyke_progressions: bool = True
    include_notes: bool = True

    # -- Field-level options ----------------------------------------------
    include_ids: bool = False
    include_internal_metadata: bool = False
    summaries_only: bool = False

    # -- Bookkeeping -------------------------------------------------------
    export_type: str = "story_elements"
    fmt: str = "json"  # json | markdown | csv

    def any_psyke(self) -> bool:
        return (
            self.include_psyke_entries
            or self.include_psyke_relations
            or self.include_psyke_progressions
        )


def story_elements_options() -> ExportOptions:
    return ExportOptions(
        include_scenes=False,
        export_type="story_elements",
    )


def psyke_data_options() -> ExportOptions:
    return ExportOptions(
        include_outline=False,
        include_plot=False,
        include_timeline=False,
        include_scenes=False,
        include_notes=False,
        export_type="psyke_data",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def sanitize_filename(name: str) -> str:
    """Turn an arbitrary project title into a safe filename stem."""
    name = (name or "").strip().lower()
    name = re.sub(r"[^\w\s-]", "", name)        # drop punctuation
    name = re.sub(r"[\s_-]+", "_", name)         # collapse whitespace/dashes
    name = name.strip("_")
    return name or "project"


def default_filename(project_title: str, export_type: str, ext: str) -> str:
    """e.g. ``("My Story", "story_elements", "json") -> my_story_story_elements.json``."""
    stem = sanitize_filename(project_title)
    suffix = {
        "story_elements": "story_elements",
        "psyke_data": "psyke_data",
        "full_project": "full_export",
    }.get(export_type, export_type)
    return f"{stem}_{suffix}.{ext}"


# ---------------------------------------------------------------------------
# Section builders (nested shape)
# ---------------------------------------------------------------------------


def _project_meta(db: Database, project_id: int, opts: ExportOptions) -> dict:
    from logosforge.project_compat import (
        get_project_narrative_engine,
        get_project_writing_format,
    )
    from logosforge.writing_modes import get_project_writing_mode

    project = db.get_project_by_id(project_id)
    meta: dict = {
        "title": project.title if project else "Untitled",
        "description": project.description if project else "",
        "format_mode": (project.format_mode if project else "novel") or "novel",
        "writing_mode": get_project_writing_mode(project),
        "narrative_engine": get_project_narrative_engine(project),
        "default_writing_format": get_project_writing_format(project),
    }
    if opts.include_ids and project is not None:
        meta["id"] = project.id
    if opts.include_internal_metadata and project is not None:
        meta["created_at"] = _isoformat(getattr(project, "created_at", None))
        meta["updated_at"] = _isoformat(getattr(project, "updated_at", None))
        meta["settings"] = db.get_project_settings(project_id)
    return meta


def _isoformat(value) -> str:
    if value is None:
        return ""
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def _outline(db: Database, project_id: int, opts: ExportOptions) -> list[dict]:
    nodes = db.get_outline_nodes(project_id)
    children_map: dict[int | None, list] = {}
    for node in nodes:
        children_map.setdefault(node.parent_id, []).append(node)

    def build(parent_id: int | None) -> list[dict]:
        kids = children_map.get(parent_id, [])
        kids.sort(key=lambda n: (n.sort_order, n.id or 0))
        out = []
        for index, n in enumerate(kids):
            item: dict = {
                "title": n.title,
                "summary": n.description,
                "order_index": index,
            }
            if opts.include_ids:
                item["id"] = n.id
                item["parent_id"] = n.parent_id
            item["children"] = build(n.id)
            out.append(item)
        return out

    return build(None)


def _plot(db: Database, project_id: int, opts: ExportOptions) -> list[dict]:
    """Plot blocks grouped by plotline — scene-derived, same source as the
    Multi-Plot view."""
    scenes = db.get_all_scenes(project_id)
    blocks: dict[str, list] = {}
    order: list[str] = []
    for scene in scenes:
        plotline = (scene.plotline or "").strip() or "Unassigned"
        if plotline not in blocks:
            blocks[plotline] = []
            order.append(plotline)
        entry: dict = {
            "title": scene.title,
            "act": scene.act,
            "summary": scene.summary,
            "beat": scene.beat,
            "color_label": scene.color_label,
            "order_index": scene.sort_order,
        }
        if opts.include_ids:
            entry["scene_id"] = scene.id
        blocks[plotline].append(entry)

    return [
        {"plotline": name, "scenes": blocks[name]}
        for name in order
    ]


def _timeline(db: Database, project_id: int, opts: ExportOptions) -> list[dict]:
    """Chronological scene events — scene-derived, same order as the Timeline
    view (sort_order then id)."""
    scenes = db.get_all_scenes(project_id)
    char_name_by_id = {c.id: c.name for c in db.get_all_characters(project_id)}
    events = []
    for index, scene in enumerate(scenes):
        duration = (
            scene.estimated_duration_minutes
            or getattr(scene, "performance_duration_minutes", 0)
        )
        event: dict = {
            "order_index": index + 1,
            "title": scene.title,
            "act": scene.act,
            "chapter": scene.chapter,
            "time_of_day": scene.time_of_day,
            "location": scene.location or scene.slugline,
            "duration_minutes": duration,
        }
        states = db.get_scene_character_states(scene.id)
        if states:
            event["character_states"] = [
                {"character": char_name_by_id.get(cid, str(cid)), "state": state}
                for cid, state in states
            ]
        if opts.include_ids:
            event["scene_id"] = scene.id
        events.append(event)
    return events


def _scenes(db: Database, project_id: int, opts: ExportOptions) -> list[dict]:
    scenes = db.get_all_scenes(project_id)
    char_name_by_id = {c.id: c.name for c in db.get_all_characters(project_id)}
    place_name_by_id = {p.id: p.name for p in db.get_all_places(project_id)}
    out = []
    for index, scene in enumerate(scenes):
        char_ids = db.get_scene_character_ids(scene.id)
        place_ids = db.get_scene_place_ids(scene.id)
        item: dict = {
            "order_index": index + 1,
            "title": scene.title,
            "summary": scene.summary,
            "synopsis": scene.synopsis,
            "act": scene.act,
            "chapter": scene.chapter,
            "plotline": scene.plotline,
            "beat": scene.beat,
            "tags": _split_csv(scene.tags),
            "characters": [char_name_by_id[c] for c in char_ids if c in char_name_by_id],
            "places": [place_name_by_id[p] for p in place_ids if p in place_name_by_id],
        }
        if not opts.summaries_only:
            item["content"] = scene.content
            item["goal"] = scene.goal
            item["conflict"] = scene.conflict
            item["outcome"] = scene.outcome
        if opts.include_ids:
            item["id"] = scene.id
        if opts.include_internal_metadata:
            item["sort_order"] = scene.sort_order
            item["color_label"] = scene.color_label
        out.append(item)
    return out


def _psyke(db: Database, project_id: int, opts: ExportOptions) -> dict:
    entries = db.get_all_psyke_entries(project_id)
    name_by_id = {e.id: e.name for e in entries}
    scene_title_by_id = {s.id: s.title for s in db.get_all_scenes(project_id)}
    psyke: dict = {}

    if opts.include_psyke_entries:
        entry_list = []
        for e in entries:
            item: dict = {
                "name": e.name,
                "type": e.entry_type,
                "aliases": _split_csv(e.aliases),
                "notes": e.notes,
                "is_global": e.is_global,
            }
            if not opts.summaries_only:
                item["details"] = db.get_psyke_entry_details(e.id)
            if opts.include_ids:
                item["id"] = e.id
            entry_list.append(item)
        psyke["entries"] = entry_list

    if opts.include_psyke_relations:
        relations = []
        seen: set[tuple] = set()
        for e in entries:
            for related, rtype in db.get_typed_related_psyke_entries(e.id):
                a, b = e.id, related.id
                key = (min(a, b), max(a, b), rtype)
                if key in seen:
                    continue
                seen.add(key)
                rel: dict = {
                    "source": e.name,
                    "target": related.name,
                    "relation_type": rtype,
                }
                if opts.include_ids:
                    rel["source_id"] = e.id
                    rel["target_id"] = related.id
                relations.append(rel)
        psyke["relations"] = relations

    if opts.include_psyke_progressions:
        progressions = []
        for e in entries:
            for prog in db.get_psyke_progressions(e.id):
                row: dict = {
                    "entry": e.name,
                    "sort_order": prog.sort_order,
                    "text": prog.text,
                    "scene_title": scene_title_by_id.get(prog.scene_id, "")
                    if prog.scene_id else "",
                }
                if opts.include_ids:
                    row["entry_id"] = e.id
                    row["scene_id"] = prog.scene_id
                progressions.append(row)
        psyke["progressions"] = progressions

    return psyke


def _notes(db: Database, project_id: int, opts: ExportOptions) -> list[dict]:
    notes = db.get_all_notes(project_id)
    psyke_name_by_id = {e.id: e.name for e in db.get_all_psyke_entries(project_id)}
    scene_title_by_id = {s.id: s.title for s in db.get_all_scenes(project_id)}
    out = []
    for n in notes:
        body = n.content or ""
        if opts.summaries_only and len(body) > 200:
            body = body[:200].rstrip() + "…"
        item: dict = {
            "title": n.title,
            "body": body,
            "tags": _split_csv(n.tags),
            "pinned": n.pinned,
            "psyke_links": [
                psyke_name_by_id[eid]
                for eid in db.get_note_psyke_links(n.id)
                if eid in psyke_name_by_id
            ],
            "scene_links": [
                scene_title_by_id[sid]
                for sid in db.get_note_scene_links(n.id)
                if sid in scene_title_by_id
            ],
            "structure_links": [
                {"type": ttype, "ref": ref}
                for ttype, ref in db.get_note_structure_links(n.id)
            ],
        }
        if opts.include_ids:
            item["id"] = n.id
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Top-level builders
# ---------------------------------------------------------------------------


def gather_export(db: Database, project_id: int, opts: ExportOptions) -> dict:
    """Assemble the clean nested export dict honouring *opts*."""
    data: dict = {
        "export_type": opts.export_type,
        "exported_at": _now_iso(),
        "schema_version": SCHEMA_VERSION,
    }
    if opts.include_project_metadata:
        data["project"] = _project_meta(db, project_id, opts)
    if opts.include_outline:
        data["outline"] = _outline(db, project_id, opts)
    if opts.include_plot:
        data["plot"] = _plot(db, project_id, opts)
    if opts.include_timeline:
        data["timeline"] = _timeline(db, project_id, opts)
    if opts.include_scenes:
        data["scenes"] = _scenes(db, project_id, opts)
    if opts.any_psyke():
        data["psyke"] = _psyke(db, project_id, opts)
    if opts.include_notes:
        data["notes"] = _notes(db, project_id, opts)
    return data


def build_story_elements(
    db: Database, project_id: int, opts: ExportOptions | None = None,
) -> dict:
    return gather_export(db, project_id, opts or story_elements_options())


def build_psyke_data(
    db: Database, project_id: int, opts: ExportOptions | None = None,
) -> dict:
    return gather_export(db, project_id, opts or psyke_data_options())


def build_full_export(db: Database, project_id: int) -> dict:
    """Everything, in an import-compatible shape.

    Reuses :func:`logosforge.export._gather_project_data` so the result keeps
    the flat keys (``project``/``characters``/``places``/``notes``/``scenes``/
    ``psyke_entries``/``outline``/``continuity``) that
    :func:`logosforge.import_data.import_json` understands, then layers on the
    derived ``plot``/``timeline`` views and project ``settings``.
    """
    from logosforge.export import _gather_project_data

    data = _gather_project_data(db, project_id)
    opts = ExportOptions(include_ids=True, include_internal_metadata=True)
    data["export_type"] = "full_project"
    data["exported_at"] = _now_iso()
    data["schema_version"] = SCHEMA_VERSION
    data["plot"] = _plot(db, project_id, opts)
    data["timeline"] = _timeline(db, project_id, opts)
    data["settings"] = db.get_project_settings(project_id)
    return data


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def to_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _md_project(lines: list[str], project: dict) -> None:
    lines.append(f"# {project.get('title', 'Untitled')}")
    if project.get("description"):
        lines.append("")
        lines.append(project["description"])
    meta_bits = []
    if project.get("narrative_engine"):
        meta_bits.append(f"**Engine:** {project['narrative_engine']}")
    if project.get("default_writing_format"):
        meta_bits.append(f"**Format:** {project['default_writing_format']}")
    if meta_bits:
        lines.append("")
        lines.append(" · ".join(meta_bits))


def _md_outline(lines: list[str], outline: list[dict]) -> None:
    lines.append("")
    lines.append("## Outline")

    def walk(items: list[dict], depth: int) -> None:
        for item in items:
            indent = "  " * depth
            lines.append(f"{indent}- **{item.get('title', '')}**")
            if item.get("summary"):
                lines.append(f"{indent}  {item['summary']}")
            walk(item.get("children", []), depth + 1)

    if outline:
        walk(outline, 0)
    else:
        lines.append("")
        lines.append("_No outline._")


def _md_plot(lines: list[str], plot: list[dict]) -> None:
    lines.append("")
    lines.append("## Plot")
    if not plot:
        lines.append("")
        lines.append("_No plot blocks._")
        return
    for block in plot:
        lines.append("")
        lines.append(f"### {block.get('plotline', 'Unassigned')}")
        for scene in block.get("scenes", []):
            bits = [scene.get("title", "")]
            if scene.get("act"):
                bits.append(f"({scene['act']})")
            lines.append(f"- {' '.join(bits)}")
            if scene.get("summary"):
                lines.append(f"  - {scene['summary']}")


def _md_timeline(lines: list[str], timeline: list[dict]) -> None:
    lines.append("")
    lines.append("## Timeline")
    if not timeline:
        lines.append("")
        lines.append("_No timeline events._")
        return
    for event in timeline:
        meta = []
        if event.get("act"):
            meta.append(event["act"])
        if event.get("time_of_day"):
            meta.append(event["time_of_day"])
        if event.get("location"):
            meta.append(event["location"])
        suffix = f" — {', '.join(meta)}" if meta else ""
        lines.append(f"{event.get('order_index', '')}. {event.get('title', '')}{suffix}")


def _md_named_list(lines: list[str], heading: str, items: list[dict]) -> None:
    lines.append("")
    lines.append(f"## {heading}")
    if not items:
        lines.append("")
        lines.append(f"_No {heading.lower()}._")
        return
    for item in items:
        name = item.get("name") or item.get("title", "")
        lines.append("")
        lines.append(f"### {name}")
        body = item.get("description") or item.get("notes") or item.get("body", "")
        if body:
            lines.append("")
            lines.append(body)


def _md_psyke(lines: list[str], psyke: dict) -> None:
    entries = psyke.get("entries", [])
    grouped: dict[str, list] = {}
    for entry in entries:
        grouped.setdefault(entry.get("type", "other"), []).append(entry)
    for kind in PSYKE_KIND_ORDER:
        if kind not in grouped:
            continue
        _md_named_list(lines, _PSYKE_KIND_LABELS[kind], grouped[kind])

    relations = psyke.get("relations", [])
    if relations:
        lines.append("")
        lines.append("## Relations")
        for rel in relations:
            rtype = rel.get("relation_type") or "related"
            lines.append(
                f"- {rel.get('source', '')} → {rel.get('target', '')} ({rtype})"
            )

    progressions = psyke.get("progressions", [])
    if progressions:
        lines.append("")
        lines.append("## Progressions")
        for prog in progressions:
            scene = f" @ {prog['scene_title']}" if prog.get("scene_title") else ""
            lines.append(f"- **{prog.get('entry', '')}**: {prog.get('text', '')}{scene}")


def _md_psyke_flat(lines: list[str], entries: list[dict]) -> None:
    """Render the flat ``psyke_entries`` list used by the full export."""
    grouped: dict[str, list] = {}
    for entry in entries:
        grouped.setdefault(entry.get("entry_type", "other"), []).append(entry)
    for kind in PSYKE_KIND_ORDER:
        if kind not in grouped:
            continue
        _md_named_list(lines, _PSYKE_KIND_LABELS[kind], grouped[kind])


def to_markdown(data: dict) -> str:
    """Render *data* (either nested or flat/full shape) as readable Markdown."""
    lines: list[str] = []
    if "project" in data:
        _md_project(lines, data["project"])
    if data.get("outline") is not None:
        _md_outline(lines, data["outline"])
    if data.get("plot") is not None:
        _md_plot(lines, data["plot"])
    if data.get("timeline") is not None:
        _md_timeline(lines, data["timeline"])
    # Characters/places only appear in the flat (full) shape.
    if "characters" in data:
        _md_named_list(lines, "Characters", data["characters"])
    if "places" in data:
        _md_named_list(lines, "Places", data["places"])
    if "psyke" in data:
        _md_psyke(lines, data["psyke"])
    elif "psyke_entries" in data:
        _md_psyke_flat(lines, data["psyke_entries"])
    if data.get("scenes") is not None:
        _md_named_list(lines, "Scenes", [
            {"name": f"{s.get('order_index', '')}. {s.get('title', '')}",
             "body": s.get("synopsis") or s.get("summary", "")}
            for s in data["scenes"]
        ])
    if data.get("notes") is not None:
        _md_named_list(lines, "Notes", data["notes"])
    lines.append("")
    return "\n".join(lines)


# -- CSV ---------------------------------------------------------------------


def _csv_from_rows(rows: list[dict]) -> str:
    if not rows:
        return ""
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _csv_cell(v) for k, v in row.items()})
    return buf.getvalue()


def _csv_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def _flatten_outline(outline: list[dict], parent: str = "") -> list[dict]:
    rows = []
    for item in outline:
        rows.append({
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "order_index": item.get("order_index", ""),
            "parent": parent,
        })
        rows.extend(_flatten_outline(item.get("children", []), item.get("title", "")))
    return rows


def to_csv_files(data: dict) -> dict[str, str]:
    """Return a mapping of ``filename -> csv text`` for the tabular sections."""
    files: dict[str, str] = {}

    if data.get("outline"):
        files["outline.csv"] = _csv_from_rows(_flatten_outline(data["outline"]))

    if data.get("plot"):
        rows = []
        for block in data["plot"]:
            for scene in block.get("scenes", []):
                rows.append({"plotline": block.get("plotline", ""), **scene})
        files["plot.csv"] = _csv_from_rows(rows)

    if data.get("timeline"):
        rows = [
            {k: v for k, v in event.items() if k != "character_states"}
            for event in data["timeline"]
        ]
        files["timeline.csv"] = _csv_from_rows(rows)

    if data.get("scenes"):
        files["scenes.csv"] = _csv_from_rows(data["scenes"])

    # PSYKE entries — split per kind into characters.csv / places.csv / ...
    psyke = data.get("psyke")
    entries = None
    if isinstance(psyke, dict):
        entries = psyke.get("entries")
    psyke_relations = psyke.get("relations") if isinstance(psyke, dict) else None
    psyke_progressions = psyke.get("progressions") if isinstance(psyke, dict) else None

    if entries is None and "psyke_entries" in data:
        # Flat/full shape — normalise key name to "type".
        entries = [
            {**e, "type": e.get("entry_type", e.get("type", "other"))}
            for e in data["psyke_entries"]
        ]

    if entries:
        grouped: dict[str, list] = {}
        for entry in entries:
            grouped.setdefault(entry.get("type", "other"), []).append(entry)
        for kind, rows in grouped.items():
            label = _PSYKE_KIND_LABELS.get(kind, kind).lower().replace(" ", "_")
            files[f"{label}.csv"] = _csv_from_rows(rows)

    if psyke_relations:
        files["psyke_relations.csv"] = _csv_from_rows(psyke_relations)
    if psyke_progressions:
        files["psyke_progressions.csv"] = _csv_from_rows(psyke_progressions)

    if data.get("notes"):
        files["notes.csv"] = _csv_from_rows(data["notes"])

    return files


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------


def serialize(data: dict, fmt: str) -> str | dict[str, str]:
    """Serialize *data* to a string (json/markdown) or a {file: text} map (csv)."""
    if fmt == "json":
        return to_json(data)
    if fmt == "markdown":
        return to_markdown(data)
    if fmt == "csv":
        return to_csv_files(data)
    raise ValueError(f"Unknown export format: {fmt!r}")


_EXT_FOR_FMT = {"json": "json", "markdown": "md", "csv": "csv"}


def write_export(data: dict, fmt: str, path: str) -> list[str]:
    """Write *data* in *fmt* to *path*; returns the list of files written.

    For CSV (which may produce several files) *path* is treated as a base
    location and the CSVs are written into a sibling folder, whose path is
    returned alongside the individual files.
    """
    import os

    if fmt in ("json", "markdown"):
        content = serialize(data, fmt)
        ext = "." + _EXT_FOR_FMT[fmt]
        if not path.endswith(ext):
            path += ext
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return [path]

    if fmt == "csv":
        files = serialize(data, fmt)
        if not files:
            raise ValueError("Nothing to export for the selected sections.")
        base = path
        for ext in (".csv", ".json", ".md"):
            if base.endswith(ext):
                base = base[: -len(ext)]
                break
        folder = base if not os.path.splitext(base)[1] else base + "_csv"
        os.makedirs(folder, exist_ok=True)
        written = []
        for name, text in files.items():
            file_path = os.path.join(folder, name)
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write(text)
            written.append(file_path)
        return written

    raise ValueError(f"Unknown export format: {fmt!r}")
