"""Portable, complete-project snapshots for Pro cloud-folder synchronization.

The Pro database contains every local project in one SQLite file, so copying
that file is not a safe multi-device synchronization strategy.  This module
serializes the relational row graph owned by one project and restores only
that graph.  Integer database ids are replaced by durable, project-scoped row
keys so a round trip remains byte-for-byte digest stable even when the target
database must allocate different ids.

Cloud provider credentials and paths deliberately do not belong here.  The
desktop shell stores snapshots in a user-selected provider-managed folder;
the core only owns the canonical project payload and its atomic application.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    func,
    or_,
    select,
    tuple_,
)
from sqlalchemy import Date as SqlDate
from sqlalchemy.sql.schema import Column, Table
from sqlmodel import Session, SQLModel

from logosforge.db.database import DB_SCHEMA_VERSION, Database
from logosforge.models.models import Project

SNAPSHOT_FORMAT = "logosforge-pro-project-snapshot"
SNAPSHOT_VERSION = "1.0"
MAX_SNAPSHOT_BYTES = 128 * 1024 * 1024
MAX_SNAPSHOT_ROWS = 250_000
MAX_VALUE_STRING_LENGTH = 64 * 1024 * 1024

_SYNC_SETTINGS_KEY = "_logosforge_cloud_sync"
_RESTORE_RECEIPTS_KEY = "_logosforge_cloud_restore_receipts"
_DEVICE_LOCAL_SETTING_KEYS = frozenset({"source_path", "cursor_scene_id"})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_JSON_REF_MARKER = "$logosforge_row_ref"
_JSON_SCENE_KEY_PREFIX = "$logosforge_scene_key:"
_SCENE_KEYED_PROJECT_SETTINGS = frozenset({
    "screenplay_beat_plans",
    "gn_page_breakdowns",
    "gn_panel_plans",
    "stage_beat_plans",
    "stage_blocking_plans",
})

# These rows close process-local retry/notification windows.  Replaying them
# on another device is incorrect and can acknowledge or deduplicate a command
# that the other device never issued.  The authoritative state produced by
# those commands is captured in the normal project tables.
_EXCLUDED_TABLES = frozenset({
    "apieventoutbox",
    "canvasplotcommandreceipt",
    "continuitycommandreceipt",
    "knowledgegraphcommandreceipt",
    "progressioncommandreceipt",
    "timelinecommandreceipt",
    "workflowcommandreceipt",
})

# Legacy models with authoritative row ids but no SQLite FK declaration.
_SOFT_FIXED_REFERENCES: dict[tuple[str, str], str] = {
    ("storylink", "source_scene_id"): "scene",
    ("storylink", "target_scene_id"): "scene",
    ("revisionimpactreport", "draft_id"): "productiondraft",
    ("revisionimpactreport", "revision_set_id"): "revisionset",
    ("revisionimpactreport", "source_revision_change_id"): "revisionchange",
    ("revisiondiffsnapshot", "revision_set_id"): "revisionset",
    ("rewritevariant", "impact_report_id"): "revisionimpactreport",
    ("rewriteapplyrecord", "created_stage_id"): "stage",
    ("controlledapplyoperation", "created_stage_id"): "stage",
    ("outlinenode", "parent_id"): "outlinenode",
    ("outlinenode", "scene_id"): "scene",
    ("chatsummary", "last_summarized_message_id"): "chatmessage",
}

_POLYMORPHIC_REFERENCE_COLUMNS: dict[tuple[str, str], str] = {
    ("rewritesession", "source_id"): "source_type",
    ("rewriteapplyrecord", "source_id"): "source_type",
    ("workflowrun", "source_id"): "source_type",
    ("workflowstepstate", "target_id"): "target_type",
    ("continuitycheckrun", "target_id"): "target_type",
    ("controlledapplyoperation", "source_id"): "source_type",
    ("controlledapplyoperation", "target_id"): "target_type",
    ("stage", "scope_id"): "scope_type",
}

_TYPE_TARGET_TABLES = {
    "scene": "scene",
    "screenplay_block": "scene",
    "manuscript": "scene",
    "character": "character",
    "place": "place",
    "note": "note",
    "psyke": "psykeentry",
    "psyke_entry": "psykeentry",
    "outline": "outlinenode",
    "outline_node": "outlinenode",
    "chapter": "chapter",
    "stage": "stage",
    "rewrite_variant": "rewritevariant",
    "rewrite_session": "rewritesession",
    "revision_impact_report": "revisionimpactreport",
    "production_draft": "productiondraft",
}


def _soft_reference_columns(table_name: str) -> set[str]:
    return {
        column_name
        for candidate_table, column_name in (
            set(_SOFT_FIXED_REFERENCES) | set(_POLYMORPHIC_REFERENCE_COLUMNS)
        )
        if candidate_table == table_name
    }


def _soft_reference_target(
    table_name: str,
    row: Mapping[str, Any],
    column_name: str,
) -> str | None:
    fixed = _SOFT_FIXED_REFERENCES.get((table_name, column_name))
    if fixed is not None:
        return fixed
    discriminator = _POLYMORPHIC_REFERENCE_COLUMNS.get((table_name, column_name))
    if discriminator is None:
        return None
    value = str(row.get(discriminator) or "").strip().lower()
    return _TYPE_TARGET_TABLES.get(value)


def _is_soft_null_literal(table_name: str, column_name: str, value: Any) -> bool:
    return (
        table_name == "chatsummary"
        and column_name == "last_summarized_message_id"
        and value == 0
    )


class ProjectCloudSnapshotError(ValueError):
    """The snapshot or local project graph is malformed or unsupported."""


class ProjectCloudSnapshotNotFound(LookupError):
    """The requested local project no longer exists."""


class ProjectCloudSnapshotConflict(RuntimeError):
    """A guarded restore no longer matches the local project generation."""


@dataclass(frozen=True)
class ProjectCloudApplyResult:
    project_id: int
    project_identity: str
    mode: Literal["replace", "import", "fork"]


def _canonical_json(value: Any) -> str:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProjectCloudSnapshotError(
            "The project snapshot contains a value that cannot be serialized."
        ) from exc
    if len(rendered.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise ProjectCloudSnapshotError(
            "The project snapshot is larger than the 128 MiB safety limit."
        )
    return rendered


def _digest_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_uuid(value: Any, label: str) -> str:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ProjectCloudSnapshotError(f"{label} must be a UUID.") from exc
    return str(parsed)


def _included_tables() -> dict[str, Table]:
    return {
        table.name: table
        for table in SQLModel.metadata.tables.values()
        if table.name not in _EXCLUDED_TABLES
    }


def _primary_key_tuple(table: Table, row: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(row[column.name] for column in table.primary_key.columns)


def _single_integer_id(table: Table) -> bool:
    columns = list(table.primary_key.columns)
    if len(columns) != 1 or columns[0].name != "id":
        return False
    try:
        return columns[0].type.python_type is int
    except NotImplementedError:
        return False


def _collect_owned_rows(
    session: Session,
    project_id: int,
) -> dict[str, list[dict[str, Any]]]:
    """Collect the complete FK-descendant graph rooted at one Project row."""
    tables = _included_tables()
    project_table = tables["project"]
    project_row = session.execute(
        select(project_table).where(project_table.c.id == int(project_id))
    ).mappings().first()
    if project_row is None:
        raise ProjectCloudSnapshotNotFound(f"Project {project_id} not found.")

    selected: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = {
        "project": {_primary_key_tuple(project_table, project_row): dict(project_row)}
    }

    # Direct project_id ownership seeds most tables. Repeated FK traversal then
    # reaches link/audit tables that intentionally have no project_id column.
    for _ in range(len(tables) + 1):
        changed = False
        for table in SQLModel.metadata.sorted_tables:
            if table.name == "project" or table.name not in tables:
                continue
            conditions = []
            if "project_id" in table.c:
                conditions.append(table.c.project_id == int(project_id))
            for foreign_key in table.foreign_keys:
                target = foreign_key.column.table
                target_rows = selected.get(target.name)
                if not target_rows:
                    continue
                values = {
                    row[foreign_key.column.name]
                    for row in target_rows.values()
                    if row[foreign_key.column.name] is not None
                }
                if values:
                    conditions.append(foreign_key.parent.in_(values))
            if not conditions:
                continue
            rows = session.execute(
                select(table).where(or_(*conditions))
            ).mappings().all()
            bucket = selected.setdefault(table.name, {})
            for row in rows:
                materialized = dict(row)
                key = _primary_key_tuple(table, materialized)
                if key not in bucket:
                    bucket[key] = materialized
                    changed = True
        if not changed:
            break
    else:  # pragma: no cover - bounded graph traversal guard
        raise ProjectCloudSnapshotError("The project row graph did not converge.")

    row_count = sum(len(rows) for rows in selected.values())
    if row_count > MAX_SNAPSHOT_ROWS:
        raise ProjectCloudSnapshotError(
            "The project contains more than 250,000 synchronized rows."
        )

    # A malformed cross-project edge must never make a snapshot silently absorb
    # another project's row or emit a dangling reference.
    for table_name, rows in selected.items():
        table = tables[table_name]
        for row in rows.values():
            if "project_id" in table.c and row.get("project_id") != project_id:
                raise ProjectCloudSnapshotError(
                    f"Table {table_name} contains a cross-project ownership edge."
                )
            for foreign_key in table.foreign_keys:
                value = row[foreign_key.parent.name]
                if value is None:
                    continue
                target_rows = selected.get(foreign_key.column.table.name, {})
                if not any(
                    candidate[foreign_key.column.name] == value
                    for candidate in target_rows.values()
                ):
                    raise ProjectCloudSnapshotError(
                        f"Table {table_name} contains a dangling or cross-project "
                        f"reference in {foreign_key.parent.name}."
                    )
            for column_name in _soft_reference_columns(table_name):
                value = row[column_name]
                if value is None or _is_soft_null_literal(table_name, column_name, value):
                    continue
                target_name = _soft_reference_target(table_name, row, column_name)
                if target_name is None:
                    # Unknown polymorphic kinds are opaque tokens, not assumed ids.
                    continue
                target_rows = selected.get(target_name, {})
                if not any(candidate.get("id") == value for candidate in target_rows.values()):
                    raise ProjectCloudSnapshotError(
                        f"Table {table_name} contains a dangling or cross-project "
                        f"soft reference in {column_name}."
                    )

    return {
        name: list(rows.values())
        for name, rows in selected.items()
    }


def _parse_settings(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}


def _sync_metadata(settings: Mapping[str, Any]) -> tuple[str | None, dict[str, dict[str, str]]]:
    raw = settings.get(_SYNC_SETTINGS_KEY)
    if not isinstance(raw, dict):
        return None, {}
    identity = raw.get("project_identity")
    try:
        identity = _canonical_uuid(identity, "Stored project identity")
    except ProjectCloudSnapshotError:
        identity = None
    stored_rows = raw.get("row_ids")
    row_ids: dict[str, dict[str, str]] = {}
    if isinstance(stored_rows, dict):
        for table_name, mapping in stored_rows.items():
            if not isinstance(table_name, str) or not isinstance(mapping, dict):
                continue
            clean: dict[str, str] = {}
            for local_id, portable_id in mapping.items():
                try:
                    clean[str(int(local_id))] = _canonical_uuid(
                        portable_id,
                        "Stored portable row identity",
                    )
                except (TypeError, ValueError, ProjectCloudSnapshotError):
                    continue
            if clean:
                row_ids[table_name] = clean
    return identity, row_ids


def _ensure_portable_identities(
    project_row: dict[str, Any],
    rows_by_table: Mapping[str, list[dict[str, Any]]],
) -> tuple[str, dict[str, dict[str, str]], str]:
    settings = _parse_settings(project_row.get("settings_json"))
    project_identity, existing = _sync_metadata(settings)
    if project_identity is None:
        project_identity = str(uuid4())

    row_ids: dict[str, dict[str, str]] = {}
    tables = _included_tables()
    for table_name, rows in rows_by_table.items():
        table = tables[table_name]
        if table_name == "project" or not _single_integer_id(table):
            continue
        old = existing.get(table_name, {})
        current: dict[str, str] = {}
        for row in rows:
            local_id = str(int(row["id"]))
            current[local_id] = old.get(local_id) or str(uuid4())
        if current:
            row_ids[table_name] = current

    settings[_SYNC_SETTINGS_KEY] = {
        "project_identity": project_identity,
        "row_ids": row_ids,
    }
    stored_settings = json.dumps(
        settings,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return project_identity, row_ids, stored_settings


def _encode_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProjectCloudSnapshotError(
                "The project contains a non-finite number that cannot be synchronized."
            )
        # JSON number rendering differs subtly between Python and JavaScript
        # (notably 1.0 versus 1). A tagged decimal string gives both runtimes
        # exactly the same canonical digest input and round-trips the IEEE value.
        return {"$logosforge_float": format(value, ".17g")}
    if isinstance(value, (str, int, bool)) or value is None:
        if isinstance(value, str) and len(value) > MAX_VALUE_STRING_LENGTH:
            raise ProjectCloudSnapshotError(
                "A project field is larger than the 64 MiB field safety limit."
            )
        return value
    raise ProjectCloudSnapshotError(
        f"Unsupported project field type: {type(value).__name__}."
    )


def _validate_encoded_value(value: Any) -> None:
    if isinstance(value, dict) and set(value) == {"$logosforge_float"}:
        raw = value["$logosforge_float"]
        if not isinstance(raw, str):
            raise ProjectCloudSnapshotError("A tagged project number is invalid.")
        try:
            parsed = float(raw)
        except ValueError as exc:
            raise ProjectCloudSnapshotError("A tagged project number is invalid.") from exc
        if not math.isfinite(parsed):
            raise ProjectCloudSnapshotError("A tagged project number is invalid.")
        return
    if isinstance(value, (str, int, bool)) or value is None:
        _encode_value(value)
        return
    raise ProjectCloudSnapshotError("A project row contains an invalid encoded value.")


def _validate_column_value(column: Column[Any], value: Any) -> None:
    """Fail closed when untrusted JSON does not match the SQLite column type."""
    _validate_encoded_value(value)
    if value is None:
        if not column.nullable:
            raise ProjectCloudSnapshotError(
                f"Required value {column.table.name}.{column.name} is null."
            )
        return

    column_type = column.type
    implementation = getattr(column_type, "impl", None)

    if isinstance(column_type, Boolean) or isinstance(implementation, Boolean):
        valid = type(value) is bool
    elif isinstance(column_type, Integer) or isinstance(implementation, Integer):
        valid = (
            type(value) is int
            and -(2 ** 63) <= value <= (2 ** 63) - 1
        )
    elif isinstance(column_type, Float) or isinstance(implementation, Float):
        valid = isinstance(value, dict) and set(value) == {"$logosforge_float"}
    elif isinstance(column_type, DateTime) or isinstance(implementation, DateTime):
        valid = isinstance(value, str)
        if valid:
            try:
                datetime.fromisoformat(value)
            except ValueError:
                valid = False
    elif isinstance(column_type, SqlDate) or isinstance(implementation, SqlDate):
        valid = isinstance(value, str)
        if valid:
            try:
                date.fromisoformat(value)
            except ValueError:
                valid = False
    elif isinstance(column_type, String) or isinstance(implementation, String):
        valid = isinstance(value, str)
        max_length = getattr(column_type, "length", None) or getattr(
            implementation,
            "length",
            None,
        )
        if valid and isinstance(max_length, int) and len(value) > max_length:
            valid = False
    else:  # pragma: no cover - a new model type must define its wire contract
        raise ProjectCloudSnapshotError(
            f"Unsupported synchronized column type for "
            f"{column.table.name}.{column.name}."
        )

    if not valid:
        raise ProjectCloudSnapshotError(
            f"Value {column.table.name}.{column.name} has the wrong type."
        )


def _validate_embedded_portable_json(
    table_name: str,
    column_name: str,
    raw: Any,
    all_keys: Mapping[str, set[str]],
) -> None:
    pair = (table_name, column_name)
    if pair not in {
        ("continuityissue", "related_scene_ids_json"),
        ("stagesnapshot", "data_json"),
    }:
        return
    if not isinstance(raw, str):  # column validation reports the primary error
        return
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProjectCloudSnapshotError(
            f"{table_name}.{column_name} is not valid JSON."
        ) from exc

    def require_reference(value: Any, target: str, label: str) -> None:
        if value is None:
            return
        if not isinstance(value, dict) or set(value) != {_JSON_REF_MARKER}:
            raise ProjectCloudSnapshotError(f"{label} must be a portable reference.")
        reference = value[_JSON_REF_MARKER]
        if (
            not isinstance(reference, dict)
            or set(reference) != {"table", "key"}
            or reference.get("table") != target
            or reference.get("key") not in all_keys.get(target, set())
        ):
            raise ProjectCloudSnapshotError(f"{label} is dangling or has the wrong type.")

    def validate_scene_data(value: Any) -> None:
        if not isinstance(value, dict):
            raise ProjectCloudSnapshotError("A Stage scene payload must be an object.")
        character_ids = value.get("character_ids")
        if character_ids is not None:
            if not isinstance(character_ids, list):
                raise ProjectCloudSnapshotError(
                    "Stage snapshot character ids must be a list."
                )
            for character_id in character_ids:
                require_reference(
                    character_id,
                    "character",
                    "A Stage snapshot character",
                )
        states = value.get("character_states")
        if states is not None:
            if not isinstance(states, list):
                raise ProjectCloudSnapshotError(
                    "Stage snapshot character states must be a list."
                )
            for state in states:
                if not isinstance(state, dict):
                    raise ProjectCloudSnapshotError(
                        "A Stage snapshot character state must be an object."
                    )
                if "character_id" in state:
                    require_reference(
                        state["character_id"],
                        "character",
                        "A Stage snapshot character state",
                    )

    def validate_psyke_data(value: Any) -> None:
        if not isinstance(value, dict):
            raise ProjectCloudSnapshotError("A Stage PSYKE payload must be an object.")
        entries = value.get("entries")
        if entries is None:
            return
        if not isinstance(entries, list):
            raise ProjectCloudSnapshotError("Stage snapshot PSYKE entries must be a list.")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ProjectCloudSnapshotError(
                    "A Stage snapshot PSYKE entry must be an object."
                )
            if "id" in entry:
                require_reference(
                    entry["id"],
                    "psykeentry",
                    "A Stage snapshot PSYKE entry",
                )

    def validate_all_markers(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                validate_all_markers(item)
            return
        if not isinstance(value, dict):
            return
        if set(value) == {_JSON_REF_MARKER}:
            reference = value[_JSON_REF_MARKER]
            if (
                not isinstance(reference, dict)
                or set(reference) != {"table", "key"}
                or not isinstance(reference.get("table"), str)
                or not isinstance(reference.get("key"), str)
                or reference["key"] not in all_keys.get(reference["table"], set())
            ):
                raise ProjectCloudSnapshotError(
                    "An embedded portable reference is invalid or dangling."
                )
            return
        for item in value.values():
            validate_all_markers(item)

    if pair == ("continuityissue", "related_scene_ids_json"):
        if parsed == {}:
            return
        if not isinstance(parsed, list):
            raise ProjectCloudSnapshotError(
                "Continuity issue scene ids must be a portable list."
            )
        for scene_id in parsed:
            require_reference(scene_id, "scene", "A Continuity issue scene")
        return

    if not isinstance(parsed, dict):
        raise ProjectCloudSnapshotError("A Stage snapshot payload must be an object.")
    scope_type = str(parsed.get("scope_type") or "").strip().lower()
    scope_target = _TYPE_TARGET_TABLES.get(scope_type)
    if scope_target is not None and "scope_id" in parsed:
        require_reference(parsed["scope_id"], scope_target, "A Stage snapshot scope")
    data = parsed.get("data")
    if data is not None:
        if not isinstance(data, dict):
            raise ProjectCloudSnapshotError("Stage snapshot data must be an object.")
        if scope_type == "scene":
            validate_scene_data(data)
        elif scope_type in {"chapter", "project"}:
            if scope_type == "chapter" and "chapter_id" in data:
                require_reference(
                    data["chapter_id"],
                    "chapter",
                    "A Stage snapshot chapter",
                )
            scenes = data.get("scenes")
            if scenes is not None:
                if not isinstance(scenes, list):
                    raise ProjectCloudSnapshotError(
                        "Stage snapshot scenes must be a list."
                    )
                for scene in scenes:
                    if not isinstance(scene, dict):
                        raise ProjectCloudSnapshotError(
                            "A Stage snapshot scene must be an object."
                        )
                    if "id" in scene:
                        require_reference(
                            scene["id"],
                            "scene",
                            "A Stage snapshot scene",
                        )
                    validate_scene_data(scene)
            if scope_type == "project" and "psyke" in data:
                validate_psyke_data(data["psyke"])
        elif scope_type == "psyke":
            validate_psyke_data(data)
    validate_all_markers(parsed)


def _sanitized_settings_json(raw: Any) -> str:
    settings = _parse_settings(raw)
    settings.pop(_SYNC_SETTINGS_KEY, None)
    settings.pop(_RESTORE_RECEIPTS_KEY, None)
    for key in _DEVICE_LOCAL_SETTING_KEYS:
        settings.pop(key, None)
    return json.dumps(
        settings,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _build_snapshot_from_rows(
    rows_by_table: dict[str, list[dict[str, Any]]],
    project_identity: str,
    row_ids: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    tables = _included_tables()

    def row_key(table: Table, row: Mapping[str, Any]) -> str:
        if table.name == "project":
            return project_identity
        if _single_integer_id(table):
            try:
                return row_ids[table.name][str(int(row["id"]))]
            except KeyError as exc:  # pragma: no cover - internal invariant
                raise ProjectCloudSnapshotError(
                    f"Missing portable identity for {table.name}.{row['id']}."
                ) from exc
        parts: list[Any] = []
        foreign_by_parent = {
            foreign_key.parent.name: foreign_key
            for foreign_key in table.foreign_keys
        }
        for column in table.primary_key.columns:
            foreign_key = foreign_by_parent.get(column.name)
            if foreign_key is not None:
                parts.append(reference_for(foreign_key, row[column.name]))
            elif column.name == "project_id":
                parts.append({"table": "project", "key": project_identity})
            else:
                parts.append(_encode_value(row[column.name]))
        material = {"table": table.name, "primary_key": parts}
        return "key:" + hashlib.sha256(
            _canonical_json(material).encode("utf-8")
        ).hexdigest()

    # Column lookup is safe because every declared FK must point at one selected
    # parent row (checked by _collect_owned_rows).
    selected_index: dict[tuple[str, str, Any], dict[str, Any]] = {}
    for table_name, rows in rows_by_table.items():
        table = tables[table_name]
        for row in rows:
            for column in table.columns:
                selected_index[(table_name, column.name, row[column.name])] = row

    def reference_for_target(
        target_table_name: str,
        target_column_name: str,
        value: Any,
    ) -> dict[str, str] | None:
        if value is None:
            return None
        target = selected_index.get(
            (target_table_name, target_column_name, value)
        )
        if target is None:  # pragma: no cover - checked during collection
            raise ProjectCloudSnapshotError("A project reference is not owned.")
        target_table = tables[target_table_name]
        return {"table": target_table_name, "key": row_key(target_table, target)}

    def reference_for(foreign_key, value: Any) -> dict[str, str] | None:
        return reference_for_target(
            foreign_key.column.table.name,
            foreign_key.column.name,
            value,
        )

    def json_target_for_key(key: str) -> str | None:
        normalized = key.strip().lower()
        if normalized == "project_id":
            return "project"
        if normalized.endswith("scene_id"):
            return "scene"
        if normalized.endswith("character_id"):
            return "character"
        if normalized.endswith("place_id"):
            return "place"
        if normalized.endswith("psyke_entry_id"):
            return "psykeentry"
        if normalized.endswith("outline_node_id"):
            return "outlinenode"
        if normalized.endswith("note_id"):
            return "note"
        return None

    def portable_json_value(value: Any, *, strict: bool) -> Any:
        if isinstance(value, list):
            return [portable_json_value(item, strict=strict) for item in value]
        if not isinstance(value, dict):
            return value
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                converted[key] = portable_json_value(item, strict=strict)
                continue
            target_name = json_target_for_key(key)
            if target_name is not None and isinstance(item, int) and not isinstance(item, bool):
                target_column = "id"
                try:
                    converted[key] = {
                        _JSON_REF_MARKER: reference_for_target(
                            target_name,
                            target_column,
                            item,
                        )
                    }
                except ProjectCloudSnapshotError:
                    if strict:
                        raise
                    converted[key] = item
                continue
            if (
                key.lower().endswith("scene_ids")
                and isinstance(item, list)
                and all(isinstance(candidate, int) and not isinstance(candidate, bool) for candidate in item)
            ):
                refs = []
                for candidate in item:
                    try:
                        refs.append({_JSON_REF_MARKER: reference_for_target("scene", "id", candidate)})
                    except ProjectCloudSnapshotError:
                        if strict:
                            raise
                        refs.append(candidate)
                converted[key] = refs
                continue
            converted[key] = portable_json_value(item, strict=strict)
        return converted

    def portable_json_string(
        table_name: str,
        column_name: str,
        raw: str,
    ) -> str:
        if (table_name, column_name) not in {
            ("project", "settings_json"),
            ("quantumstaterecord", "state_json"),
            ("continuityissue", "related_scene_ids_json"),
            ("stagesnapshot", "data_json"),
        }:
            return raw
        try:
            parsed = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            return raw

        def portable_id(target_name: str, value: Any, label: str) -> Any:
            if value is None:
                return None
            if not isinstance(value, int) or isinstance(value, bool):
                raise ProjectCloudSnapshotError(f"{label} is not a valid row id.")
            try:
                reference = reference_for_target(target_name, "id", value)
            except ProjectCloudSnapshotError as exc:
                raise ProjectCloudSnapshotError(
                    f"{label} refers to a row outside this project."
                ) from exc
            return {_JSON_REF_MARKER: reference}

        def portable_stage_scene_data(value: Any) -> Any:
            if not isinstance(value, dict):
                return value
            converted = dict(value)
            character_ids = converted.get("character_ids")
            if isinstance(character_ids, list):
                converted["character_ids"] = [
                    portable_id(
                        "character",
                        character_id,
                        "A Stage snapshot character",
                    )
                    for character_id in character_ids
                ]
            character_states = converted.get("character_states")
            if isinstance(character_states, list):
                converted_states = []
                for state in character_states:
                    if not isinstance(state, dict):
                        converted_states.append(state)
                        continue
                    converted_state = dict(state)
                    if "character_id" in converted_state:
                        converted_state["character_id"] = portable_id(
                            "character",
                            converted_state["character_id"],
                            "A Stage snapshot character state",
                        )
                    converted_states.append(converted_state)
                converted["character_states"] = converted_states
            return converted

        def portable_stage_psyke_data(value: Any) -> Any:
            if not isinstance(value, dict):
                return value
            converted = dict(value)
            entries = converted.get("entries")
            if not isinstance(entries, list):
                return converted
            converted_entries = []
            for entry in entries:
                if not isinstance(entry, dict):
                    converted_entries.append(entry)
                    continue
                converted_entry = dict(entry)
                if "id" in converted_entry:
                    converted_entry["id"] = portable_id(
                        "psykeentry",
                        converted_entry["id"],
                        "A Stage snapshot PSYKE entry",
                    )
                converted_entries.append(converted_entry)
            converted["entries"] = converted_entries
            return converted

        def portable_stage_payload(value: Any) -> Any:
            if not isinstance(value, dict):
                return value
            converted = dict(value)
            scope_type = str(converted.get("scope_type") or "").strip().lower()
            scope_target = _TYPE_TARGET_TABLES.get(scope_type)
            if scope_target is not None and "scope_id" in converted:
                converted["scope_id"] = portable_id(
                    scope_target,
                    converted["scope_id"],
                    "A Stage snapshot scope",
                )
            data = converted.get("data")
            if not isinstance(data, dict):
                return converted
            portable_data = dict(data)
            if scope_type == "scene":
                portable_data = portable_stage_scene_data(portable_data)
            elif scope_type in {"chapter", "project"}:
                if scope_type == "chapter" and "chapter_id" in portable_data:
                    portable_data["chapter_id"] = portable_id(
                        "chapter",
                        portable_data["chapter_id"],
                        "A Stage snapshot chapter",
                    )
                scenes = portable_data.get("scenes")
                if isinstance(scenes, list):
                    converted_scenes = []
                    for scene in scenes:
                        if not isinstance(scene, dict):
                            converted_scenes.append(scene)
                            continue
                        converted_scene = portable_stage_scene_data(scene)
                        if "id" in converted_scene:
                            converted_scene["id"] = portable_id(
                                "scene",
                                converted_scene["id"],
                                "A Stage snapshot scene",
                            )
                        converted_scenes.append(converted_scene)
                    portable_data["scenes"] = converted_scenes
                if scope_type == "project" and "psyke" in portable_data:
                    portable_data["psyke"] = portable_stage_psyke_data(
                        portable_data["psyke"]
                    )
            elif scope_type == "psyke":
                portable_data = portable_stage_psyke_data(portable_data)
            converted["data"] = portable_data
            return converted

        if (
            table_name == "continuityissue"
            and column_name == "related_scene_ids_json"
            and isinstance(parsed, list)
        ):
            parsed = [
                portable_id("scene", scene_id, "A Continuity issue scene")
                for scene_id in parsed
            ]
        elif table_name == "stagesnapshot" and column_name == "data_json":
            parsed = portable_stage_payload(parsed)
        if table_name == "project" and isinstance(parsed, dict):
            for setting_key in _SCENE_KEYED_PROJECT_SETTINGS:
                scene_map = parsed.get(setting_key)
                if not isinstance(scene_map, dict):
                    continue
                portable_map: dict[str, Any] = {}
                for scene_id, item in scene_map.items():
                    try:
                        numeric_id = int(scene_id)
                        reference = reference_for_target("scene", "id", numeric_id)
                    except (TypeError, ValueError, ProjectCloudSnapshotError):
                        portable_map[str(scene_id)] = portable_json_value(item, strict=False)
                    else:
                        portable_map[
                            _JSON_SCENE_KEY_PREFIX + reference["key"]
                        ] = portable_json_value(item, strict=False)
                parsed[setting_key] = portable_map
        portable = portable_json_value(
            parsed,
            strict=table_name == "quantumstaterecord",
        )
        return json.dumps(
            portable,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    serialized_tables: dict[str, list[dict[str, Any]]] = {}
    for table in SQLModel.metadata.sorted_tables:
        source_rows = rows_by_table.get(table.name)
        if not source_rows or table.name not in tables:
            continue
        foreign_by_parent = {
            foreign_key.parent.name: foreign_key
            for foreign_key in table.foreign_keys
        }
        encoded_rows = []
        for row in source_rows:
            values: dict[str, Any] = {}
            references: dict[str, Any] = {}
            omit_integer_id = _single_integer_id(table)
            for column in table.columns:
                if table.name == "project" and column.name == "id":
                    continue
                if omit_integer_id and column.name == "id":
                    continue
                foreign_key = foreign_by_parent.get(column.name)
                if foreign_key is not None:
                    references[column.name] = reference_for(
                        foreign_key,
                        row[column.name],
                    )
                    continue
                if column.name == "project_id":
                    references[column.name] = {
                        "table": "project",
                        "key": project_identity,
                    }
                    continue
                value = row[column.name]
                if column.name in _soft_reference_columns(table.name):
                    target_name = _soft_reference_target(table.name, row, column.name)
                    if value is None or _is_soft_null_literal(
                        table.name,
                        column.name,
                        value,
                    ):
                        references[column.name] = None
                    elif target_name is None:
                        # Unknown polymorphic kinds are deliberately opaque.
                        references[column.name] = {"literal": _encode_value(value)}
                    else:
                        references[column.name] = reference_for_target(
                            target_name,
                            "id",
                            value,
                        )
                    continue
                if table.name == "project" and column.name == "settings_json":
                    value = _sanitized_settings_json(value)
                if isinstance(value, str):
                    value = portable_json_string(table.name, column.name, value)
                values[column.name] = _encode_value(value)
            encoded_rows.append({
                "key": row_key(table, row),
                "values": values,
                "references": references,
            })
        serialized_tables[table.name] = sorted(
            encoded_rows,
            key=lambda item: item["key"],
        )

    project_values = serialized_tables["project"][0]["values"]
    payload: dict[str, Any] = {
        "format": SNAPSHOT_FORMAT,
        "version": SNAPSHOT_VERSION,
        "schema_version": DB_SCHEMA_VERSION,
        "project_identity": project_identity,
        # Small discovery summary consumed by the desktop cloud-folder index.
        # The relational project row below remains authoritative.
        "project": {
            "title": project_values.get("title") or "Untitled Project",
            "sync_id": project_identity,
        },
        "tables": serialized_tables,
    }
    return {**payload, "digest": _digest_payload(payload)}


def _snapshot_from_session(
    session: Session,
    project_id: int,
) -> dict[str, Any]:
    rows = _collect_owned_rows(session, project_id)
    project_row = rows["project"][0]
    project_identity, row_ids, stored_settings = _ensure_portable_identities(
        project_row,
        rows,
    )
    if project_row.get("settings_json") != stored_settings:
        session.execute(
            Project.__table__.update()
            .where(Project.__table__.c.id == int(project_id))
            .values(settings_json=stored_settings)
        )
        project_row["settings_json"] = stored_settings
    return _build_snapshot_from_rows(rows, project_identity, row_ids)


def build_project_cloud_snapshot(db: Database, project_id: int) -> dict[str, Any]:
    """Return a canonical complete-project envelope and durable content digest."""
    project_id = int(project_id)
    with db.structure_write_lock(project_id), Session(
        db._engine, expire_on_commit=False
    ) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        try:
            snapshot = _snapshot_from_session(session, project_id)
            session.commit()
            return snapshot
        except Exception:
            session.rollback()
            raise


def validate_project_cloud_snapshot(value: Any) -> dict[str, Any]:
    """Validate an untrusted snapshot and return its normalized JSON object."""
    serialized = _canonical_json(value)
    snapshot = json.loads(serialized)
    if not isinstance(snapshot, dict):
        raise ProjectCloudSnapshotError("The project snapshot must be an object.")
    if snapshot.get("format") != SNAPSHOT_FORMAT:
        raise ProjectCloudSnapshotError("Unsupported project snapshot format.")
    if snapshot.get("version") != SNAPSHOT_VERSION:
        raise ProjectCloudSnapshotError("Unsupported project snapshot version.")
    schema_version = snapshot.get("schema_version")
    if not isinstance(schema_version, int) or schema_version < 1:
        raise ProjectCloudSnapshotError("Invalid project snapshot schema version.")
    if schema_version > DB_SCHEMA_VERSION:
        raise ProjectCloudSnapshotError(
            "This project was saved by a newer LogosForge core."
        )
    project_identity = _canonical_uuid(
        snapshot.get("project_identity"),
        "Project identity",
    )
    project_summary = snapshot.get("project")
    if (
        not isinstance(project_summary, dict)
        or set(project_summary) != {"title", "sync_id"}
        or not isinstance(project_summary.get("title"), str)
        or not project_summary["title"].strip()
        or project_summary.get("sync_id") != project_identity
    ):
        raise ProjectCloudSnapshotError("The project discovery summary is invalid.")
    digest = snapshot.get("digest")
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise ProjectCloudSnapshotError("Invalid project snapshot digest.")
    digest_payload = {key: item for key, item in snapshot.items() if key != "digest"}
    if _digest_payload(digest_payload) != digest:
        raise ProjectCloudSnapshotError(
            "The project snapshot digest does not match its contents."
        )

    tables = snapshot.get("tables")
    allowed_tables = _included_tables()
    if not isinstance(tables, dict) or set(tables) - set(allowed_tables):
        raise ProjectCloudSnapshotError(
            "The project snapshot contains an unknown or operational table."
        )
    project_rows = tables.get("project")
    if not isinstance(project_rows, list) or len(project_rows) != 1:
        raise ProjectCloudSnapshotError(
            "The project snapshot must contain exactly one project row."
        )

    all_keys: dict[str, set[str]] = {}
    total_rows = 0
    for table_name, rows in tables.items():
        if not isinstance(rows, list):
            raise ProjectCloudSnapshotError(f"Table {table_name} is not a row list.")
        total_rows += len(rows)
        if total_rows > MAX_SNAPSHOT_ROWS:
            raise ProjectCloudSnapshotError(
                "The project snapshot contains more than 250,000 rows."
            )
        keys: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"key", "values", "references"}:
                raise ProjectCloudSnapshotError(f"Table {table_name} has an invalid row.")
            key = row.get("key")
            if not isinstance(key, str) or not key or len(key) > 128 or key in keys:
                raise ProjectCloudSnapshotError(
                    f"Table {table_name} has an invalid or duplicate row key."
                )
            keys.add(key)
        all_keys[table_name] = keys
    if project_rows[0]["key"] != project_identity:
        raise ProjectCloudSnapshotError("The project row identity is inconsistent.")

    for table_name, rows in tables.items():
        table = allowed_tables[table_name]
        foreign_columns = {fk.parent.name for fk in table.foreign_keys}
        foreign_columns.update(_soft_reference_columns(table_name))
        if "project_id" in table.c:
            foreign_columns.add("project_id")
        omitted_ids = {"id"} if table.name == "project" or _single_integer_id(table) else set()
        expected_values = {
            column.name
            for column in table.columns
            if column.name not in foreign_columns and column.name not in omitted_ids
        }
        for row in rows:
            values = row["values"]
            references = row["references"]
            if not isinstance(values, dict) or set(values) != expected_values:
                raise ProjectCloudSnapshotError(
                    f"Table {table_name} has missing or unknown value columns."
                )
            if not isinstance(references, dict) or set(references) != foreign_columns:
                raise ProjectCloudSnapshotError(
                    f"Table {table_name} has missing or unknown references."
                )
            for column_name, reference in references.items():
                column = table.c[column_name]
                if reference is None:
                    if (
                        not column.nullable
                        and not _is_soft_null_literal(table_name, column_name, 0)
                    ):
                        raise ProjectCloudSnapshotError(
                            f"Required reference {table_name}.{column_name} is null."
                        )
                    continue
                if isinstance(reference, dict) and set(reference) == {"literal"}:
                    if column_name not in _soft_reference_columns(table_name):
                        raise ProjectCloudSnapshotError(
                            f"Reference {table_name}.{column_name} cannot be literal."
                        )
                    _validate_column_value(column, reference["literal"])
                    if _soft_reference_target(table_name, values, column_name) is not None:
                        raise ProjectCloudSnapshotError(
                            f"Reference {table_name}.{column_name} must be portable."
                        )
                    continue
                if not isinstance(reference, dict) or set(reference) != {"table", "key"}:
                    raise ProjectCloudSnapshotError(
                        f"Reference {table_name}.{column_name} is invalid."
                    )
                target_table = reference.get("table")
                target_key = reference.get("key")
                if (
                    not isinstance(target_table, str)
                    or not isinstance(target_key, str)
                    or target_key not in all_keys.get(target_table, set())
                ):
                    raise ProjectCloudSnapshotError(
                        f"Reference {table_name}.{column_name} is dangling."
                    )
                declared = next(
                    (
                        fk.column.table.name
                        for fk in table.foreign_keys
                        if fk.parent.name == column_name
                    ),
                    "project" if column_name == "project_id" else None,
                )
                if declared is None:
                    declared = _soft_reference_target(table_name, values, column_name)
                if target_table != declared:
                    raise ProjectCloudSnapshotError(
                        f"Reference {table_name}.{column_name} targets the wrong table."
                    )
            for column_name, value_item in values.items():
                _validate_column_value(table.c[column_name], value_item)
                _validate_embedded_portable_json(
                    table_name,
                    column_name,
                    value_item,
                    all_keys,
                )

    return snapshot


def _delete_selected_rows(
    session: Session,
    rows_by_table: Mapping[str, list[dict[str, Any]]],
) -> None:
    tables = _included_tables()
    for table in reversed(SQLModel.metadata.sorted_tables):
        rows = rows_by_table.get(table.name)
        if not rows or table.name not in tables:
            continue
        primary_columns = list(table.primary_key.columns)
        keys = [_primary_key_tuple(table, row) for row in rows]
        for offset in range(0, len(keys), 400):
            chunk = keys[offset:offset + 400]
            if len(primary_columns) == 1:
                condition = primary_columns[0].in_([key[0] for key in chunk])
            else:
                condition = tuple_(*primary_columns).in_(chunk)
            session.execute(table.delete().where(condition))


def _delete_operational_rows(session: Session, project_id: int) -> None:
    """Drop device-local retry/notification state before replacing content."""
    for table_name in _EXCLUDED_TABLES:
        table = SQLModel.metadata.tables.get(table_name)
        if table is not None and "project_id" in table.c:
            session.execute(
                table.delete().where(table.c.project_id == int(project_id))
            )


def _decode_value(column: Column[Any], value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"$logosforge_float"}:
        value = float(value["$logosforge_float"])
    column_type = column.type
    is_datetime = isinstance(column_type, DateTime) or isinstance(
        getattr(column_type, "impl", None),
        DateTime,
    )
    if is_datetime:
        if not isinstance(value, str):
            raise ProjectCloudSnapshotError(
                f"{column.table.name}.{column.name} must be an ISO timestamp."
            )
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise ProjectCloudSnapshotError(
                f"{column.table.name}.{column.name} has an invalid timestamp."
            ) from exc
    is_date = isinstance(column_type, SqlDate) or isinstance(
        getattr(column_type, "impl", None),
        SqlDate,
    )
    if is_date:
        if not isinstance(value, str):
            raise ProjectCloudSnapshotError(
                f"{column.table.name}.{column.name} must be an ISO date."
            )
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ProjectCloudSnapshotError(
                f"{column.table.name}.{column.name} has an invalid date."
            ) from exc
    return value


def _restore_portable_json_string(
    table_name: str,
    column_name: str,
    raw: str,
    local_by_key: Mapping[tuple[str, str], Any],
) -> str:
    if (table_name, column_name) not in {
        ("project", "settings_json"),
        ("quantumstaterecord", "state_json"),
        ("continuityissue", "related_scene_ids_json"),
        ("stagesnapshot", "data_json"),
    }:
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return raw

    def restore(value: Any) -> Any:
        if isinstance(value, list):
            return [restore(item) for item in value]
        if not isinstance(value, dict):
            return value
        if set(value) == {_JSON_REF_MARKER}:
            reference = value[_JSON_REF_MARKER]
            if (
                not isinstance(reference, dict)
                or set(reference) != {"table", "key"}
            ):
                raise ProjectCloudSnapshotError("A portable JSON reference is invalid.")
            try:
                return local_by_key[(reference["table"], reference["key"])]
            except (KeyError, TypeError) as exc:
                raise ProjectCloudSnapshotError(
                    "A portable JSON reference is dangling."
                ) from exc
        restored: dict[str, Any] = {}
        for key, item in value.items():
            restored_key = key
            if isinstance(key, str) and key.startswith(_JSON_SCENE_KEY_PREFIX):
                portable_key = key[len(_JSON_SCENE_KEY_PREFIX):]
                try:
                    restored_key = str(local_by_key[("scene", portable_key)])
                except KeyError as exc:
                    raise ProjectCloudSnapshotError(
                        "A scene-keyed project setting is dangling."
                    ) from exc
            restored[restored_key] = restore(item)
        return restored

    return json.dumps(
        restore(parsed),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _known_project_identity(project_row: Mapping[str, Any]) -> str | None:
    identity, _ = _sync_metadata(_parse_settings(project_row.get("settings_json")))
    return identity


def _find_restore_receipt(
    session: Session,
    restore_id: str,
) -> tuple[int, str, dict[str, Any]] | None:
    for row in session.execute(select(Project.__table__)).mappings().all():
        settings = _parse_settings(row.get("settings_json"))
        receipts = settings.get(_RESTORE_RECEIPTS_KEY)
        if not isinstance(receipts, dict):
            continue
        receipt = receipts.get(restore_id)
        if not isinstance(receipt, dict):
            continue
        identity = _known_project_identity(row)
        if identity is None:
            raise ProjectCloudSnapshotError(
                "A cloud restore receipt has no project identity."
            )
        return int(row["id"]), identity, receipt
    return None


def apply_project_cloud_snapshot(
    db: Database,
    value: Any,
    *,
    mode: Literal["replace", "import", "fork"],
    target_project_id: int | None = None,
    expected_current_digest: str | None = None,
    restore_id: str,
) -> ProjectCloudApplyResult:
    """Atomically replace one project or import the snapshot as a new project.

    ``import`` preserves the portable project identity for first use on another
    device. ``fork`` creates an independent project identity. ``replace`` only
    touches ``target_project_id`` and preserves its device-local settings.
    """
    snapshot = validate_project_cloud_snapshot(value)
    restore_id = _canonical_uuid(restore_id, "Restore id")
    if mode == "replace" and target_project_id is None:
        raise ProjectCloudSnapshotError("A replace restore needs a target project.")
    if mode != "replace" and target_project_id is not None:
        raise ProjectCloudSnapshotError("Only replace restore accepts a target project.")
    if expected_current_digest is not None and not _DIGEST_RE.fullmatch(expected_current_digest):
        raise ProjectCloudSnapshotError("The expected local digest is invalid.")

    lock_key = int(target_project_id or 0)
    with db.structure_write_lock(lock_key), Session(
        db._engine, expire_on_commit=False
    ) as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        session.connection().exec_driver_sql("PRAGMA defer_foreign_keys = ON")
        try:
                existing_receipt = _find_restore_receipt(session, restore_id)
                if existing_receipt is not None:
                    receipt_project_id, receipt_identity, receipt = existing_receipt
                    if (
                        receipt.get("snapshot_digest") != snapshot["digest"]
                        or receipt.get("mode") != mode
                        or (
                            mode == "replace"
                            and receipt_project_id != int(target_project_id or 0)
                        )
                    ):
                        raise ProjectCloudSnapshotConflict(
                            "This restore id was already used for another operation."
                        )
                    session.rollback()
                    return ProjectCloudApplyResult(
                        project_id=receipt_project_id,
                        project_identity=receipt_identity,
                        mode=mode,
                    )

                if mode == "replace" and expected_current_digest is None:
                    raise ProjectCloudSnapshotError(
                        "A replace restore requires the expected local digest."
                    )

                current_rows: dict[str, list[dict[str, Any]]] | None = None
                local_settings: dict[str, Any] = {}
                if mode == "replace":
                    assert target_project_id is not None
                    current_rows = _collect_owned_rows(session, target_project_id)
                    current_project = current_rows["project"][0]
                    local_settings = _parse_settings(current_project.get("settings_json"))
                    if expected_current_digest is not None:
                        current_snapshot = _snapshot_from_session(session, target_project_id)
                        if current_snapshot["digest"] != expected_current_digest:
                            raise ProjectCloudSnapshotConflict(
                                "The local project changed after conflict review."
                            )

                source_identity = snapshot["project_identity"]
                output_identity = str(uuid4()) if mode == "fork" else source_identity

                # One portable identity must resolve to at most one local project.
                for row in session.execute(select(Project.__table__)).mappings().all():
                    local_id = int(row["id"])
                    if mode == "replace" and local_id == target_project_id:
                        continue
                    if _known_project_identity(row) == output_identity:
                        raise ProjectCloudSnapshotConflict(
                            "This cloud project already exists in the local library."
                        )

                if current_rows is not None:
                    _delete_selected_rows(session, current_rows)
                    _delete_operational_rows(session, int(target_project_id))

                snapshot_tables: dict[str, list[dict[str, Any]]] = snapshot["tables"]
                local_by_key: dict[tuple[str, str], Any] = {}

                if mode == "replace":
                    assert target_project_id is not None
                    new_project_id = int(target_project_id)
                else:
                    current_max = session.execute(
                        select(func.max(Project.__table__.c.id))
                    ).scalar_one_or_none()
                    new_project_id = int(current_max or 0) + 1
                local_by_key[("project", source_identity)] = new_project_id

                for table in SQLModel.metadata.sorted_tables:
                    if table.name == "project" or table.name not in snapshot_tables:
                        continue
                    if not _single_integer_id(table):
                        continue
                    current_max = session.execute(
                        select(func.max(table.c.id))
                    ).scalar_one_or_none()
                    next_id = int(current_max or 0) + 1
                    for row in snapshot_tables[table.name]:
                        local_by_key[(table.name, row["key"])] = next_id
                        next_id += 1

                inserts: dict[str, list[dict[str, Any]]] = {}
                restored_row_ids: dict[str, dict[str, str]] = {}
                for table in SQLModel.metadata.sorted_tables:
                    rows = snapshot_tables.get(table.name)
                    if not rows:
                        continue
                    materialized_rows: list[dict[str, Any]] = []
                    for row in rows:
                        values = {
                            column_name: _decode_value(table.c[column_name], item)
                            for column_name, item in row["values"].items()
                        }
                        for column_name, item in list(values.items()):
                            if isinstance(item, str):
                                values[column_name] = _restore_portable_json_string(
                                    table.name,
                                    column_name,
                                    item,
                                    local_by_key,
                                )
                        if table.name == "project":
                            values["id"] = new_project_id
                        elif _single_integer_id(table):
                            local_id = local_by_key[(table.name, row["key"])]
                            values["id"] = local_id
                            restored_row_ids.setdefault(table.name, {})[
                                str(local_id)
                            ] = row["key"]
                        for column_name, reference in row["references"].items():
                            if reference is None:
                                values[column_name] = (
                                    0
                                    if _is_soft_null_literal(table.name, column_name, 0)
                                    else None
                                )
                            elif set(reference) == {"literal"}:
                                values[column_name] = _decode_value(
                                    table.c[column_name],
                                    reference["literal"],
                                )
                            else:
                                values[column_name] = local_by_key[
                                    (reference["table"], reference["key"])
                                ]
                        materialized_rows.append(values)
                    inserts[table.name] = materialized_rows

                project_values = inserts["project"][0]
                synced_settings = _parse_settings(project_values.get("settings_json"))
                for key in _DEVICE_LOCAL_SETTING_KEYS:
                    if mode == "replace" and key in local_settings:
                        synced_settings[key] = local_settings[key]
                synced_settings[_SYNC_SETTINGS_KEY] = {
                    "project_identity": output_identity,
                    "row_ids": restored_row_ids,
                }
                receipts = (
                    local_settings.get(_RESTORE_RECEIPTS_KEY)
                    if mode == "replace"
                    else synced_settings.get(_RESTORE_RECEIPTS_KEY)
                )
                receipts = dict(receipts) if isinstance(receipts, dict) else {}
                receipts[restore_id] = {
                    "snapshot_digest": snapshot["digest"],
                    "mode": mode,
                }
                if len(receipts) > 64:
                    for stale_id in sorted(receipts)[:-64]:
                        receipts.pop(stale_id, None)
                synced_settings[_RESTORE_RECEIPTS_KEY] = receipts
                project_values["settings_json"] = json.dumps(
                    synced_settings,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )

                for table in SQLModel.metadata.sorted_tables:
                    rows = inserts.get(table.name)
                    if rows:
                        session.execute(table.insert(), rows)
                session.commit()
                return ProjectCloudApplyResult(
                    project_id=new_project_id,
                    project_identity=output_identity,
                    mode=mode,
                )
        except Exception:
            session.rollback()
            raise


__all__ = [
    "MAX_SNAPSHOT_BYTES",
    "SNAPSHOT_FORMAT",
    "SNAPSHOT_VERSION",
    "ProjectCloudApplyResult",
    "ProjectCloudSnapshotConflict",
    "ProjectCloudSnapshotError",
    "ProjectCloudSnapshotNotFound",
    "apply_project_cloud_snapshot",
    "build_project_cloud_snapshot",
    "validate_project_cloud_snapshot",
]
