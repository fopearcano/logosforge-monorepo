"""Persistence layer — wraps SQLite via SQLModel.

Usage:
    db = Database("my_story.db")  # file-based
    db = Database()               # in-memory (for tests)
    db = Database(":memory:")      # equivalent explicit spelling

UI code should only call the public methods below (e.g. create_character,
get_all_places). All session management stays inside this module.
"""

import hashlib
import hmac
import json
import math
import os
import re
import shutil
import sqlite3
import threading
import time
from contextlib import closing, contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy import event, func, text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


DB_SCHEMA_VERSION = 6
SQLITE_BUSY_TIMEOUT_MS = 5000
BACKUP_INSTALL_WAIT_SECONDS = 10.0


class InMemoryTransactionReentryError(RuntimeError):
    """A nested Session tried to reuse the active in-memory SQLite handle."""


class _SerializedStaticPool(StaticPool):
    """StaticPool whose one connection cannot host overlapping transactions.

    Gating at pool checkout covers every SQLAlchemy caller, including modules
    that use :class:`sqlmodel.Session` directly rather than Database helpers.
    File-backed databases do not use this pool and retain normal WAL
    concurrency.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._logosforge_gate = threading.Lock()
        self._logosforge_state = threading.Lock()
        self._logosforge_owner: int | None = None

    def _do_get(self):
        thread_id = threading.get_ident()
        with self._logosforge_state:
            if self._logosforge_owner == thread_id:
                raise InMemoryTransactionReentryError(
                    "A nested database transaction cannot reuse the active "
                    "in-memory SQLite connection"
                )
        self._logosforge_gate.acquire()
        try:
            with self._logosforge_state:
                self._logosforge_owner = thread_id
            return super()._do_get()
        except BaseException:
            with self._logosforge_state:
                self._logosforge_owner = None
            self._logosforge_gate.release()
            raise

    def _do_return_conn(self, record) -> None:
        with self._logosforge_state:
            owner = self._logosforge_owner
            self._logosforge_owner = None
        if owner is None:
            raise RuntimeError(
                "In-memory SQLite connection returned without a checkout owner"
            )
        self._logosforge_gate.release()


class UnsupportedDatabaseVersionError(RuntimeError):
    """Raised before a newer database can be changed by an older core."""

    def __init__(self, found: int, supported: int) -> None:
        super().__init__(
            f"Database schema version {found} is newer than supported version {supported}"
        )
        self.found = found
        self.supported = supported


def _scene_locked(method):
    """Serialize mutations of one Scene inside a Database process."""
    @wraps(method)
    def wrapped(self, scene_id: int, *args, **kwargs):
        with self.scene_write_lock(scene_id):
            return method(self, scene_id, *args, **kwargs)
    return wrapped


def _read_user_version(path: Path) -> int:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _fsync_directory(path: Path) -> None:
    """Persist a newly-installed backup directory entry where supported."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _install_backup_once(tmp: Path, backup: Path) -> None:
    """Publish a complete backup without replacing another process's winner."""
    try:
        os.link(tmp, backup)
        _fsync_directory(backup.parent)
        return
    except FileExistsError:
        return
    except OSError:
        # Hard links may be disabled by the filesystem. Coordinate through a
        # sidecar lock, then atomically rename the already-complete same-directory
        # snapshot. Never expose the final backup path while bytes are still being
        # copied. A stale lock blocks migration rather than risking no backup.
        lock = backup.with_name(f".{backup.name}.installing")
        deadline = time.monotonic() + BACKUP_INSTALL_WAIT_SECONDS
        while True:
            if backup.exists():
                return
            try:
                fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    if backup.exists():
                        return
                    raise TimeoutError(
                        f"Timed out waiting to install migration backup: {backup}"
                    )
                time.sleep(0.01)
                continue
            else:
                os.close(fd)
                break
        try:
            if backup.exists():
                return
            os.replace(tmp, backup)
            _fsync_directory(backup.parent)
        finally:
            lock.unlink(missing_ok=True)


def _prepare_migration_backup(path: Path) -> Path | None:
    """Create one durable pre-upgrade copy before touching an older database."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        current_version = _read_user_version(path)
    except sqlite3.DatabaseError:
        current_version = 0  # preserve unreadable bytes before SQLAlchemy reports it
    if current_version >= DB_SCHEMA_VERSION:
        return None
    backup = path.with_name(path.name + f".pre-v{DB_SCHEMA_VERSION}.bak")
    if backup.exists():
        return backup
    tmp = backup.with_name(f".{backup.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        try:
            uri = f"file:{path.resolve().as_posix()}?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as source, closing(
                sqlite3.connect(tmp)
            ) as target:
                source.backup(target)  # consistent snapshot, including committed WAL pages
                target.commit()
        except sqlite3.DatabaseError:
            # If SQLite cannot open the source, preserve its raw bytes before
            # SQLAlchemy reports the corruption; never destroy forensic data.
            tmp.unlink(missing_ok=True)
            with path.open("rb") as source, tmp.open("xb") as target:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
        with tmp.open("r+b") as handle:
            os.fsync(handle.fileno())
        _install_backup_once(tmp, backup)
    finally:
        tmp.unlink(missing_ok=True)
    return backup


def _repair_character_psyke_foreign_key(conn) -> None:
    """Rebuild the one released legacy table whose added column lacked its FK."""
    rows = conn.execute(text("PRAGMA table_info(character)")).fetchall()
    columns = {row[1] for row in rows}
    if not rows or "psyke_entry_id" not in columns:
        return
    foreign_keys = {
        (row[2], row[3], row[4])
        for row in conn.execute(text("PRAGMA foreign_key_list(character)")).fetchall()
    }
    if ("psykeentry", "psyke_entry_id", "id") in foreign_keys:
        return
    if ("project", "project_id", "id") not in foreign_keys:
        # Some tests and early development databases used an intentionally
        # partial table definition. Preserve their existing best-effort
        # column-add behavior; the released schema lineage always has this FK.
        return

    # SQLite cannot add a foreign key to an existing column. Rebuild atomically,
    # preserving every row and detaching only already-orphaned optional links.
    conn.commit()
    conn.execute(text("PRAGMA foreign_keys=OFF"))
    conn.commit()
    try:
        # Python's sqlite3 driver does not start a transaction for DDL in its
        # legacy transaction mode. Begin explicitly so a failed copy or check
        # rolls the temporary table back along with the rest of the rebuild.
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            existing_temp = conn.execute(text(
                "SELECT 1 FROM sqlite_master"
                " WHERE type='table' AND name='character__logosforge_v2'"
            )).fetchone()
            if existing_temp:
                raise RuntimeError("Reserved migration table character__logosforge_v2 exists")
            before_count = conn.execute(text(
                'SELECT COUNT(*) FROM "character"'
            )).scalar_one()
            conn.execute(text(
                """
                CREATE TABLE character__logosforge_v2 (
                    id INTEGER NOT NULL,
                    project_id INTEGER NOT NULL,
                    name VARCHAR NOT NULL,
                    description VARCHAR NOT NULL,
                    color VARCHAR NOT NULL,
                    psyke_entry_id INTEGER,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(project_id) REFERENCES project (id),
                    FOREIGN KEY(psyke_entry_id) REFERENCES psykeentry (id)
                )
                """
            ))
            conn.execute(text(
                """
                INSERT INTO character__logosforge_v2 (
                    id, project_id, name, description, color,
                    psyke_entry_id, created_at
                )
                SELECT
                    c.id, c.project_id, c.name, c.description, c.color,
                    CASE
                        WHEN c.psyke_entry_id IS NULL THEN NULL
                        WHEN EXISTS (
                            SELECT 1 FROM psykeentry AS p
                            WHERE p.id = c.psyke_entry_id
                        ) THEN c.psyke_entry_id
                        ELSE NULL
                    END,
                    c.created_at
                FROM "character" AS c
                """
            ))
            conn.execute(text('DROP TABLE "character"'))
            conn.execute(text(
                "ALTER TABLE character__logosforge_v2 RENAME TO character"
            ))
            after_count = conn.execute(text(
                'SELECT COUNT(*) FROM "character"'
            )).scalar_one()
            if after_count != before_count:
                raise RuntimeError("Character FK migration changed the row count")
            violations = conn.execute(text(
                'PRAGMA foreign_key_check("character")'
            )).fetchall()
            if violations:
                raise RuntimeError(
                    f"Character FK migration left {len(violations)} foreign-key violation(s)"
                )
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()

# Sentinel for partial updates: distinguishes "argument not provided" (leave the
# column as-is) from an explicit ``None`` (clear a nullable column).
_UNSET: object = object()

from logosforge.comment_revision import comment_revision
from logosforge.models import (
    ChatMessage,
    ChatSummary,
    Character,
    Comment,
    CommentReply,
    GraphicNovelContinuityAppearance,
    GraphicNovelContinuityItem,
    GraphicNovelIssue,
    GraphicNovelPage,
    GraphicNovelPanel,
    GraphicNovelSequence,
    Note,
    NotePsykeLink,
    NoteSceneLink,
    NoteStructureLink,
    OutlineNode,
    Place,
    Project,
    PsykeEntry,
    VoiceGlossaryTerm,
    PsykeProgression,
    PsykeRelation,
    QuantumStateRecord,
    Scene,
    SceneCharacterLink,
    SceneCharacterState,
    ControlledApplyConflict,
    ControlledApplyOperation,
    ProductionDraft,
    ProductionSceneNumber,
    RevisionChange,
    RevisionDiffSnapshot,
    RevisionImpactItem,
    RevisionImpactReport,
    RevisionSet,
    RewriteApplyRecord,
    RewriteSession,
    RewriteVariant,
    ScenePlaceLink,
    SceneThemeLink,
    StoryLink,
    StageBusiness,
    StageCue,
    StageEntranceExit,
    Season,
    Episode,
    SeriesArc,
    EpisodePlotline,
    TimelineLane,
    TIMELINE_LINK_TYPES,
    TimelineCommandReceipt,
    TimelineLink,
    TimelineStructureLink,
    CanvasPlotCommandReceipt,
    CanvasPlotNode,
    CanvasPlotLink,
    CanvasPlotFrame,
    Chapter,
    Stage,
    StageBranch,
    StageSnapshot,
    StoryMemoryEntry,
    VoiceProfile,
    WorkflowRun,
    WorkflowStepState,
    WorkflowEvent,
    WorkflowCommandReceipt,
    KnowledgeGraphNode,
    KnowledgeGraphEdge,
    KnowledgeGraphCommandReceipt,
    KnowledgeGraphSnapshot,
    ContinuityIssue,
    ContinuityCommandReceipt,
    ContinuityCheckRun,
)


class CommentRevisionConflict(RuntimeError):
    """Raised when a guarded comment mutation targets an older thread state."""

    def __init__(self, expected: str, current: str) -> None:
        super().__init__("comment revision does not match the current thread")
        self.expected = expected
        self.current = current


class StoryStructureRevisionConflict(RuntimeError):
    """Raised when a structural command targets an older project state."""

    def __init__(self, expected: str, current: str) -> None:
        super().__init__("story-structure revision does not match")
        self.expected = expected
        self.current = current


class StoryStructurePlacementError(ValueError):
    """A requested structural mutation is invalid or ambiguous."""


class StoryStructureSceneNotFound(LookupError):
    """The source Scene is absent from the path-scoped project."""


class StoryStructureProjectNotFound(LookupError):
    """The path-scoped Project disappeared before the transaction began."""


class StoryStructureEpisodeNotFound(LookupError):
    """The requested Series Episode is absent from the scoped project."""


class TimelineRevisionConflict(RuntimeError):
    """Raised when a Timeline command targets an older board state."""

    def __init__(self, expected: str, current: str) -> None:
        super().__init__("timeline revision does not match")
        self.expected = expected
        self.current = current


class TimelineCommandError(ValueError):
    """A requested Timeline mutation is invalid or ambiguous."""


class TimelineIdempotencyKeyConflict(RuntimeError):
    """An Idempotency-Key was already committed for another command."""


class TimelineProjectNotFound(LookupError):
    """The path-scoped Project disappeared before the transaction began."""


class TimelineSceneNotFound(LookupError):
    """The requested Scene is absent from the path-scoped Project."""


class TimelineLaneNotFound(LookupError):
    """The requested lane is absent from the path-scoped Project."""


class TimelineLinkNotFound(LookupError):
    """The requested event link is absent from the path-scoped Project."""


class TimelineStructureLinkNotFound(LookupError):
    """The requested structure link is absent from the path-scoped Project."""


class TimelineStateCorrupt(RuntimeError):
    """Persisted Timeline rows violate project ownership or invariants."""


class CanvasPlotRevisionConflict(RuntimeError):
    """Raised when a Canvas Plot command targets an older board state."""

    def __init__(self, expected: str, current: str) -> None:
        super().__init__("canvas-plot revision does not match")
        self.expected = expected
        self.current = current


class CanvasPlotCommandError(ValueError):
    """A requested Canvas Plot mutation is invalid or ambiguous."""


class CanvasPlotIdempotencyKeyConflict(RuntimeError):
    """An Idempotency-Key was already committed for another Canvas command."""


class CanvasPlotProjectNotFound(LookupError):
    """The path-scoped Project disappeared before the transaction began."""


class CanvasPlotNodeNotFound(LookupError):
    """The requested node is absent from the path-scoped Project."""


class CanvasPlotLinkNotFound(LookupError):
    """The requested link is absent from the path-scoped Project."""


class CanvasPlotFrameNotFound(LookupError):
    """The requested frame is absent from the path-scoped Project."""


class CanvasPlotSceneNotFound(LookupError):
    """The requested Scene is absent from the path-scoped Project."""


class KnowledgeGraphRevisionConflict(RuntimeError):
    """Raised when an edge-review command targets older review state."""

    def __init__(self, expected: str, current: str) -> None:
        super().__init__("knowledge-graph review revision does not match")
        self.expected = expected
        self.current = current


class KnowledgeGraphCommandError(ValueError):
    """A graph edge-review command is malformed or unsupported."""


class KnowledgeGraphIdempotencyKeyConflict(RuntimeError):
    """An Idempotency-Key was committed for another graph command."""


class KnowledgeGraphProjectNotFound(LookupError):
    """The path-scoped Project disappeared before the transaction began."""


class KnowledgeGraphEdgeNotFound(LookupError):
    """The directed edge is absent from the freshly built project graph."""


class KnowledgeGraphReviewStateCorrupt(RuntimeError):
    """Persisted graph review rows violate canonical uniqueness."""


class ContinuityRevisionConflict(RuntimeError):
    """Raised when an issue-review command targets older review state."""

    def __init__(self, expected: str, current: str) -> None:
        super().__init__("continuity review revision does not match")
        self.expected = expected
        self.current = current


class ContinuityCommandError(ValueError):
    """A Continuity issue-review command is malformed or unsupported."""


class ContinuityIdempotencyKeyConflict(RuntimeError):
    """An Idempotency-Key was committed for another Continuity command."""


class ContinuityProjectNotFound(LookupError):
    """The path-scoped Project disappeared before the transaction began."""


class ContinuityIssueNotFound(LookupError):
    """The requested computed issue is absent from the current report."""


class ContinuityReviewStateCorrupt(RuntimeError):
    """Persisted Continuity review rows violate canonical uniqueness."""


class WorkflowRevisionConflict(RuntimeError):
    """Raised when a workflow command targets an older run revision."""

    def __init__(self, expected: str, current: str) -> None:
        super().__init__("guided-workflow revision does not match")
        self.expected = expected
        self.current = current


class WorkflowCommandError(ValueError):
    """A Guided Workflow command is malformed or unsupported."""


class WorkflowIdempotencyKeyConflict(RuntimeError):
    """An Idempotency-Key was committed for another workflow command."""


class WorkflowProjectNotFound(LookupError):
    """The path-scoped Project disappeared before the transaction began."""


class WorkflowRunNotFound(LookupError):
    """A run is missing or belongs to another project."""


class WorkflowStepNotFound(LookupError):
    """A step is missing or belongs to another workflow run."""


class WorkflowStateConflict(RuntimeError):
    """The requested transition is invalid for the current workflow state."""


@dataclass(frozen=True)
class ManuscriptReadSnapshot:
    """One coherent manuscript read detached from its SQLite transaction.

    Scene rows and every association that contributes to ``SceneDTO`` or its
    optimistic-concurrency revision are captured together.  Tuples/frozensets
    make the returned value safe to pass through serializers after the read
    transaction has closed.
    """

    project: Project
    scenes: tuple[Scene, ...]
    valid_character_ids: frozenset[int]
    valid_place_ids: frozenset[int]
    character_ids_by_scene: dict[int, tuple[int, ...]]
    place_ids_by_scene: dict[int, tuple[int, ...]]
    character_states_by_scene: dict[int, tuple[tuple[int, str], ...]]


@dataclass(frozen=True)
class StoryStructureReadSnapshot:
    """One coherent, detached canonical-structure read."""

    project: Project
    scenes: tuple[Scene, ...]
    revision: str


@dataclass(frozen=True)
class StoryStructurePlacementResult:
    """Committed placement state plus whether any row was changed."""

    snapshot: StoryStructureReadSnapshot
    changed: bool


@dataclass(frozen=True)
class StoryStructureCommandResult:
    """Committed command state plus navigation/invalidation metadata."""

    snapshot: StoryStructureReadSnapshot
    changed: bool
    created_scene_id: int | None = None
    affected_scene_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class TimelineReadSnapshot:
    """One coherent, detached read of every input to the Timeline board."""

    project: Project
    scenes: tuple[Scene, ...]
    lanes: tuple[TimelineLane, ...]
    links: tuple[TimelineLink, ...]
    structure_links: tuple[TimelineStructureLink, ...]
    settings: dict
    character_names_by_id: dict[int, str]
    character_states_by_scene: dict[int, tuple[tuple[int, str], ...]]
    revision: str


@dataclass(frozen=True)
class TimelineCommandResult:
    """Committed Timeline state plus focused invalidation metadata."""

    snapshot: TimelineReadSnapshot
    changed: bool
    affected_scene_ids: tuple[int, ...] = ()
    affected_link_ids: tuple[int, ...] = ()
    affected_structure_link_ids: tuple[int, ...] = ()
    created_link_id: int | None = None
    created_structure_link_id: int | None = None
    replayed: bool = False
    applied_revision: str = ""


@dataclass(frozen=True)
class TimelineCommandReceiptData:
    """Decoded durable receipt safe to expose through the typed API."""

    project_id: int
    request_digest: str
    kind: str
    expected_revision: str
    applied_revision: str
    original_changed: bool
    original_affected_scene_ids: tuple[int, ...]
    original_affected_link_ids: tuple[int, ...]
    original_affected_structure_link_ids: tuple[int, ...]
    original_created_link_id: int | None
    original_created_structure_link_id: int | None
    created_at: datetime


@dataclass(frozen=True)
class CanvasPlotReadSnapshot:
    """One coherent, detached read of the canonical Canvas Plot board."""

    project: Project
    nodes: tuple[CanvasPlotNode, ...]
    links: tuple[CanvasPlotLink, ...]
    frames: tuple[CanvasPlotFrame, ...]
    valid_scene_ids: frozenset[int]
    revision: str


@dataclass(frozen=True)
class CanvasPlotCommandResult:
    """Committed Canvas Plot state plus focused invalidation metadata."""

    snapshot: CanvasPlotReadSnapshot
    changed: bool
    affected_node_ids: tuple[int, ...] = ()
    affected_link_ids: tuple[int, ...] = ()
    affected_frame_ids: tuple[int, ...] = ()
    created_node_id: int | None = None
    created_link_id: int | None = None
    created_frame_id: int | None = None
    replayed: bool = False
    applied_revision: str = ""


@dataclass(frozen=True)
class CanvasPlotCommandReceiptData:
    """Decoded durable Canvas Plot receipt safe for the typed API."""

    project_id: int
    request_digest: str
    kind: str
    expected_revision: str
    applied_revision: str
    original_changed: bool
    original_affected_node_ids: tuple[int, ...]
    original_affected_link_ids: tuple[int, ...]
    original_affected_frame_ids: tuple[int, ...]
    original_created_node_id: int | None
    original_created_link_id: int | None
    original_created_frame_id: int | None
    created_at: datetime


@dataclass(frozen=True)
class KnowledgeGraphEdgeIdentity:
    """Public, directional identity of one graph edge proposal."""

    source: str
    target: str
    edge_type: str


@dataclass(frozen=True)
class KnowledgeGraphCommandResult:
    """Committed review revision plus exactly-once recovery metadata."""

    revision: str
    changed: bool
    affected_edge: KnowledgeGraphEdgeIdentity
    replayed: bool = False
    applied_revision: str = ""


@dataclass(frozen=True)
class KnowledgeGraphCommandReceiptData:
    """Decoded durable graph command receipt safe for the typed API."""

    project_id: int
    request_digest: str
    kind: str
    expected_revision: str
    applied_revision: str
    original_changed: bool
    original_affected_edge: KnowledgeGraphEdgeIdentity
    created_at: datetime


@dataclass(frozen=True)
class KnowledgeGraphReviewSnapshot:
    """One coherent persisted graph-review read detached from SQLite."""

    project: Project
    nodes: tuple[KnowledgeGraphNode, ...]
    edges: tuple[KnowledgeGraphEdge, ...]
    revision: str


@dataclass(frozen=True)
class ContinuityReviewSnapshot:
    """One coherent persisted Continuity-review read detached from SQLite."""

    project: Project
    issues: tuple[ContinuityIssue, ...]
    revision: str


@dataclass(frozen=True)
class ContinuityCommandResult:
    """Committed issue status plus exactly-once recovery metadata."""

    revision: str
    changed: bool
    issue_key: str
    previous_status: str
    status: str
    replayed: bool = False
    applied_revision: str = ""


@dataclass(frozen=True)
class ContinuityCommandReceiptData:
    """Decoded durable Continuity receipt safe for the typed API."""

    project_id: int
    request_digest: str
    kind: str
    expected_revision: str
    applied_revision: str
    issue_key: str
    expected_issue_fingerprint: str
    previous_status: str
    status: str
    original_changed: bool
    created_at: datetime


@dataclass(frozen=True)
class WorkflowRunSnapshot:
    """One coherent workflow run read detached from SQLite."""

    run: WorkflowRun
    steps: tuple[WorkflowStepState, ...]
    revision: str


@dataclass(frozen=True)
class WorkflowCommandResult:
    """Committed workflow state plus exactly-once recovery metadata."""

    snapshot: WorkflowRunSnapshot
    changed: bool
    replayed: bool = False
    applied_revision: str = ""


@dataclass(frozen=True)
class WorkflowCommandReceiptData:
    """Decoded durable Guided Workflow command receipt."""

    project_id: int
    request_digest: str
    kind: str
    expected_revision: str
    applied_revision: str
    original_changed: bool
    run_id: int
    created_at: datetime


_TIMELINE_RECEIPT_SCHEMA_VERSION = 2
_CANVAS_PLOT_RECEIPT_SCHEMA_VERSION = 1
_KNOWLEDGE_GRAPH_RECEIPT_SCHEMA_VERSION = 1
_CONTINUITY_RECEIPT_SCHEMA_VERSION = 2
_WORKFLOW_RECEIPT_SCHEMA_VERSION = 1
_TIMELINE_COMMAND_KINDS = frozenset({
    "create_lane",
    "update_lane",
    "delete_lane",
    "place_event",
    "remove_event",
    "set_order_mode",
    "create_link",
    "update_link",
    "delete_link",
    "create_structure_link",
    "update_structure_link",
    "delete_structure_link",
})
_TIMELINE_V1_COMMAND_KINDS = frozenset({
    "create_lane",
    "update_lane",
    "delete_lane",
    "place_event",
    "remove_event",
    "set_order_mode",
})
_CANVAS_PLOT_COMMAND_KINDS = frozenset({
    "create_node",
    "update_node",
    "delete_node",
    "create_link",
    "update_link",
    "delete_link",
    "create_frame",
    "update_frame",
    "delete_frame",
})
_KNOWLEDGE_GRAPH_COMMAND_KINDS = frozenset({
    "confirm_edge",
    "hide_edge",
    "unhide_edge",
})
_CONTINUITY_COMMAND_STATUSES = {
    "defer_issue": "deferred",
    "dismiss_issue": "dismissed",
    "resolve_issue": "resolved",
}
_WORKFLOW_COMMAND_KINDS = frozenset({
    "start_workflow",
    "complete_step",
    "skip_step",
    "advance",
    "refresh",
    "pause",
    "resume",
    "cancel",
})
_TIMELINE_IDEMPOTENCY_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$"
)
_CANVAS_PLOT_IDEMPOTENCY_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$"
)
_KNOWLEDGE_GRAPH_IDEMPOTENCY_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$"
)
_CONTINUITY_IDEMPOTENCY_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$"
)
_WORKFLOW_IDEMPOTENCY_KEY_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$"
)
_CONTINUITY_ISSUE_KEY_RE = re.compile(r"^[0-9a-f]{16}$")
_LOWER_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _timeline_idempotency_key_hash(value: str) -> str:
    """Validate and irreversibly identify one caller-supplied capability."""
    if not isinstance(value, str):
        raise TimelineCommandError("Idempotency-Key must be a string")
    if (
        value != value.strip()
        or _TIMELINE_IDEMPOTENCY_KEY_RE.fullmatch(value) is None
    ):
        raise TimelineCommandError(
            "Idempotency-Key must contain 16-128 safe ASCII characters"
        )
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _timeline_command_request_digest(
    project_id: int,
    kind: str,
    expected_revision: str,
    fields: dict,
) -> str:
    """Content-address the exact validated command bound to an idempotency key."""
    try:
        encoded = json.dumps(
            {
                "scope": "timeline-command-v1",
                "project_id": int(project_id),
                "kind": kind,
                "expected_revision": expected_revision,
                "fields": fields,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TimelineCommandError(
            "Timeline command contains a value that cannot be persisted"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _timeline_receipt_result_json(
    *,
    kind: str,
    expected_revision: str,
    applied_revision: str,
    original_changed: bool,
    original_affected_scene_ids: tuple[int, ...],
    original_affected_link_ids: tuple[int, ...],
    original_affected_structure_link_ids: tuple[int, ...],
    original_created_link_id: int | None,
    original_created_structure_link_id: int | None,
) -> str:
    return json.dumps(
        {
            "schema_version": _TIMELINE_RECEIPT_SCHEMA_VERSION,
            "kind": kind,
            "expected_revision": expected_revision,
            "applied_revision": applied_revision,
            "original_changed": original_changed,
            "original_affected_scene_ids": list(original_affected_scene_ids),
            "original_affected_link_ids": list(original_affected_link_ids),
            "original_affected_structure_link_ids": list(
                original_affected_structure_link_ids
            ),
            "original_created_link_id": original_created_link_id,
            "original_created_structure_link_id": (
                original_created_structure_link_id
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_timeline_command_receipt(
    row: TimelineCommandReceipt,
) -> TimelineCommandReceiptData:
    """Decode a receipt fail-closed; persisted corruption must never replay."""
    try:
        payload = json.loads(row.result_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("Timeline command receipt is corrupt") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Timeline command receipt is corrupt")
    schema_version = payload.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version not in {1, _TIMELINE_RECEIPT_SCHEMA_VERSION}
    ):
        raise RuntimeError("Timeline command receipt has an unsupported schema")
    kind = payload.get("kind")
    expected_revision = payload.get("expected_revision")
    applied_revision = payload.get("applied_revision")
    original_changed = payload.get("original_changed")
    affected = payload.get("original_affected_scene_ids")
    affected_links = (
        payload.get("original_affected_link_ids")
        if schema_version >= 2 else []
    )
    affected_structure_links = (
        payload.get("original_affected_structure_link_ids")
        if schema_version >= 2 else []
    )
    created_link_id = (
        payload.get("original_created_link_id")
        if schema_version >= 2 else None
    )
    created_structure_link_id = (
        payload.get("original_created_structure_link_id")
        if schema_version >= 2 else None
    )

    def valid_ids(value) -> bool:
        return (
            isinstance(value, list)
            and not any(
                isinstance(item, bool)
                or not isinstance(item, int)
                or item <= 0
                for item in value
            )
            and len(set(value)) == len(value)
        )

    def valid_optional_id(value) -> bool:
        return value is None or (
            not isinstance(value, bool)
            and isinstance(value, int)
            and value > 0
        )

    allowed_kinds = (
        _TIMELINE_V1_COMMAND_KINDS
        if schema_version == 1 else _TIMELINE_COMMAND_KINDS
    )
    if (
        not isinstance(kind, str)
        or kind not in allowed_kinds
        or not isinstance(expected_revision, str)
        or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
        or not isinstance(applied_revision, str)
        or _LOWER_SHA256_RE.fullmatch(applied_revision) is None
        or not isinstance(original_changed, bool)
        or not valid_ids(affected)
        or not valid_ids(affected_links)
        or not valid_ids(affected_structure_links)
        or not valid_optional_id(created_link_id)
        or not valid_optional_id(created_structure_link_id)
    ):
        raise RuntimeError("Timeline command receipt has invalid result data")
    link_command = kind in {"create_link", "update_link", "delete_link"}
    structure_link_command = kind in {
        "create_structure_link",
        "update_structure_link",
        "delete_structure_link",
    }
    no_op_kinds = {
        "update_lane",
        "place_event",
        "remove_event",
        "set_order_mode",
        "create_link",
        "update_link",
        "create_structure_link",
        "update_structure_link",
    }
    if schema_version >= 2 and (
        (original_changed and applied_revision == expected_revision)
        or (not original_changed and applied_revision != expected_revision)
        or (not original_changed and kind not in no_op_kinds)
        or (created_link_id is not None and kind != "create_link")
        or (
            created_structure_link_id is not None
            and kind != "create_structure_link"
        )
        or (
            created_link_id is not None
            and created_link_id not in affected_links
        )
        or (
            created_structure_link_id is not None
            and created_structure_link_id not in affected_structure_links
        )
        or (
            original_changed
            and link_command
            and not affected_links
        )
        or (
            original_changed
            and structure_link_command
            and not affected_structure_links
        )
        or (
            link_command
            and (affected or affected_structure_links)
        )
        or (
            structure_link_command
            and (affected or affected_links)
        )
        or (
            not link_command
            and not structure_link_command
            and (affected_links or affected_structure_links)
        )
        or (
            original_changed
            and kind == "create_link"
            and created_link_id is None
        )
        or (
            original_changed
            and kind == "create_structure_link"
            and created_structure_link_id is None
        )
        or (
            not original_changed
            and (
                affected
                or affected_links
                or affected_structure_links
                or created_link_id is not None
                or created_structure_link_id is not None
            )
        )
    ):
        raise RuntimeError("Timeline command receipt has invalid result data")
    if (
        _LOWER_SHA256_RE.fullmatch(row.idempotency_key_hash or "") is None
        or _LOWER_SHA256_RE.fullmatch(row.request_digest or "") is None
    ):
        raise RuntimeError("Timeline command receipt has invalid digest data")
    return TimelineCommandReceiptData(
        project_id=int(row.project_id),
        request_digest=row.request_digest,
        kind=kind,
        expected_revision=expected_revision,
        applied_revision=applied_revision,
        original_changed=original_changed,
        original_affected_scene_ids=tuple(affected),
        original_affected_link_ids=tuple(affected_links),
        original_affected_structure_link_ids=tuple(affected_structure_links),
        original_created_link_id=created_link_id,
        original_created_structure_link_id=created_structure_link_id,
        created_at=row.created_at,
    )


def _canvas_plot_idempotency_key_hash(value: str) -> str:
    """Validate and irreversibly identify one Canvas retry capability."""
    if not isinstance(value, str):
        raise CanvasPlotCommandError("Idempotency-Key must be a string")
    if (
        value != value.strip()
        or _CANVAS_PLOT_IDEMPOTENCY_KEY_RE.fullmatch(value) is None
    ):
        raise CanvasPlotCommandError(
            "Idempotency-Key must contain 16-128 safe ASCII characters"
        )
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _canvas_plot_command_request_digest(
    project_id: int,
    kind: str,
    expected_revision: str,
    fields: dict,
) -> str:
    """Content-address the exact Canvas command bound to a retry key."""
    try:
        encoded = json.dumps(
            {
                "scope": "canvas-plot-command-v1",
                "project_id": int(project_id),
                "kind": kind,
                "expected_revision": expected_revision,
                "fields": fields,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanvasPlotCommandError(
            "Canvas Plot command contains a value that cannot be persisted"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _canvas_plot_receipt_result_json(
    *,
    kind: str,
    expected_revision: str,
    applied_revision: str,
    original_changed: bool,
    original_affected_node_ids: tuple[int, ...],
    original_affected_link_ids: tuple[int, ...],
    original_affected_frame_ids: tuple[int, ...],
    original_created_node_id: int | None,
    original_created_link_id: int | None,
    original_created_frame_id: int | None,
) -> str:
    return json.dumps(
        {
            "schema_version": _CANVAS_PLOT_RECEIPT_SCHEMA_VERSION,
            "kind": kind,
            "expected_revision": expected_revision,
            "applied_revision": applied_revision,
            "original_changed": original_changed,
            "original_affected_node_ids": list(original_affected_node_ids),
            "original_affected_link_ids": list(original_affected_link_ids),
            "original_affected_frame_ids": list(original_affected_frame_ids),
            "original_created_node_id": original_created_node_id,
            "original_created_link_id": original_created_link_id,
            "original_created_frame_id": original_created_frame_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_canvas_plot_command_receipt(
    row: CanvasPlotCommandReceipt,
) -> CanvasPlotCommandReceiptData:
    """Decode a Canvas receipt fail-closed; corrupt proof cannot replay."""
    try:
        payload = json.loads(row.result_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("Canvas Plot command receipt is corrupt") from exc
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("schema_version"), int)
        or isinstance(payload.get("schema_version"), bool)
        or payload.get("schema_version") != _CANVAS_PLOT_RECEIPT_SCHEMA_VERSION
    ):
        raise RuntimeError(
            "Canvas Plot command receipt has an unsupported schema"
        )

    kind = payload.get("kind")
    expected_revision = payload.get("expected_revision")
    applied_revision = payload.get("applied_revision")
    original_changed = payload.get("original_changed")
    affected_node_ids = payload.get("original_affected_node_ids")
    affected_link_ids = payload.get("original_affected_link_ids")
    affected_frame_ids = payload.get("original_affected_frame_ids")
    created_node_id = payload.get("original_created_node_id")
    created_link_id = payload.get("original_created_link_id")
    created_frame_id = payload.get("original_created_frame_id")

    def valid_ids(value) -> bool:
        return (
            isinstance(value, list)
            and not any(
                isinstance(item, bool)
                or not isinstance(item, int)
                or item <= 0
                for item in value
            )
            and len(set(value)) == len(value)
        )

    def valid_optional_id(value) -> bool:
        return value is None or (
            not isinstance(value, bool)
            and isinstance(value, int)
            and value > 0
        )

    if (
        not isinstance(kind, str)
        or kind not in _CANVAS_PLOT_COMMAND_KINDS
        or not isinstance(expected_revision, str)
        or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
        or not isinstance(applied_revision, str)
        or _LOWER_SHA256_RE.fullmatch(applied_revision) is None
        or not isinstance(original_changed, bool)
        or not valid_ids(affected_node_ids)
        or not valid_ids(affected_link_ids)
        or not valid_ids(affected_frame_ids)
        or not valid_optional_id(created_node_id)
        or not valid_optional_id(created_link_id)
        or not valid_optional_id(created_frame_id)
    ):
        raise RuntimeError("Canvas Plot command receipt has invalid result data")

    created_ids = (created_node_id, created_link_id, created_frame_id)
    node_command = kind in {"create_node", "update_node", "delete_node"}
    link_command = kind in {"create_link", "update_link", "delete_link"}
    frame_command = kind in {"create_frame", "update_frame", "delete_frame"}
    no_op_kinds = {
        "update_node",
        "create_link",
        "update_link",
        "update_frame",
    }
    if (
        sum(value is not None for value in created_ids) > 1
        or (original_changed and applied_revision == expected_revision)
        or (
            not original_changed
            and applied_revision != expected_revision
        )
        or (not original_changed and kind not in no_op_kinds)
        or (
            not original_changed
            and (
                affected_node_ids
                or affected_link_ids
                or affected_frame_ids
                or any(value is not None for value in created_ids)
            )
        )
        or (
            original_changed
            and node_command
            and not affected_node_ids
        )
        or (
            original_changed
            and link_command
            and not affected_link_ids
        )
        or (
            original_changed
            and frame_command
            and not affected_frame_ids
        )
        or (node_command and affected_frame_ids)
        or (
            node_command
            and kind != "delete_node"
            and affected_link_ids
        )
        or (
            link_command
            and (affected_node_ids or affected_frame_ids)
        )
        or (
            frame_command
            and (affected_node_ids or affected_link_ids)
        )
        or (
            created_node_id is not None
            and (
                kind != "create_node"
                or created_node_id not in affected_node_ids
            )
        )
        or (
            created_link_id is not None
            and (
                kind != "create_link"
                or created_link_id not in affected_link_ids
            )
        )
        or (
            created_frame_id is not None
            and (
                kind != "create_frame"
                or created_frame_id not in affected_frame_ids
            )
        )
        or (
            kind not in {"create_node", "create_link", "create_frame"}
            and any(value is not None for value in created_ids)
        )
        or (
            original_changed
            and kind == "create_node"
            and created_node_id is None
        )
        or (
            original_changed
            and kind == "create_link"
            and created_link_id is None
        )
        or (
            original_changed
            and kind == "create_frame"
            and created_frame_id is None
        )
    ):
        raise RuntimeError("Canvas Plot command receipt has invalid result data")
    if (
        _LOWER_SHA256_RE.fullmatch(row.idempotency_key_hash or "") is None
        or _LOWER_SHA256_RE.fullmatch(row.request_digest or "") is None
    ):
        raise RuntimeError("Canvas Plot command receipt has invalid digest data")
    return CanvasPlotCommandReceiptData(
        project_id=int(row.project_id),
        request_digest=row.request_digest,
        kind=kind,
        expected_revision=expected_revision,
        applied_revision=applied_revision,
        original_changed=original_changed,
        original_affected_node_ids=tuple(affected_node_ids),
        original_affected_link_ids=tuple(affected_link_ids),
        original_affected_frame_ids=tuple(affected_frame_ids),
        original_created_node_id=created_node_id,
        original_created_link_id=created_link_id,
        original_created_frame_id=created_frame_id,
        created_at=row.created_at,
    )


def _knowledge_graph_idempotency_key_hash(value: str) -> str:
    """Validate and irreversibly identify one graph retry capability."""
    if not isinstance(value, str):
        raise KnowledgeGraphCommandError("Idempotency-Key must be a string")
    if (
        value != value.strip()
        or _KNOWLEDGE_GRAPH_IDEMPOTENCY_KEY_RE.fullmatch(value) is None
    ):
        raise KnowledgeGraphCommandError(
            "Idempotency-Key must contain 16-128 safe ASCII characters"
        )
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _knowledge_graph_edge_identity(
    source,
    target,
    edge_type,
) -> KnowledgeGraphEdgeIdentity:
    values = ((source, "source", 512), (target, "target", 512),
              (edge_type, "edge_type", 128))
    for value, label, maximum in values:
        if not isinstance(value, str) or not value or len(value) > maximum:
            raise KnowledgeGraphCommandError(
                f"{label} must contain 1-{maximum} characters"
            )
    return KnowledgeGraphEdgeIdentity(
        source=source,
        target=target,
        edge_type=edge_type,
    )


def _knowledge_graph_wire_key(value: str) -> str:
    """Mirror the public stable-key mapping without importing the API layer."""
    value = str(value)
    if len(value) <= 512:
        return value
    return f"kg:sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _knowledge_graph_command_request_digest(
    project_id: int,
    kind: str,
    expected_revision: str,
    identity: KnowledgeGraphEdgeIdentity,
) -> str:
    encoded = json.dumps(
        {
            "scope": "knowledge-graph-command-v1",
            "project_id": int(project_id),
            "kind": kind,
            "expected_revision": expected_revision,
            "source": identity.source,
            "target": identity.target,
            "edge_type": identity.edge_type,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _knowledge_graph_receipt_result_json(
    *,
    kind: str,
    expected_revision: str,
    applied_revision: str,
    original_changed: bool,
    affected_edge: KnowledgeGraphEdgeIdentity,
) -> str:
    return json.dumps(
        {
            "schema_version": _KNOWLEDGE_GRAPH_RECEIPT_SCHEMA_VERSION,
            "kind": kind,
            "expected_revision": expected_revision,
            "applied_revision": applied_revision,
            "original_changed": original_changed,
            "original_affected_edge": {
                "source": affected_edge.source,
                "target": affected_edge.target,
                "edge_type": affected_edge.edge_type,
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_knowledge_graph_command_receipt(
    row: KnowledgeGraphCommandReceipt,
) -> KnowledgeGraphCommandReceiptData:
    """Decode a graph receipt fail-closed; corrupt proof cannot replay."""
    try:
        payload = json.loads(row.result_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("Knowledge Graph command receipt is corrupt") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version")
        != _KNOWLEDGE_GRAPH_RECEIPT_SCHEMA_VERSION
        or isinstance(payload.get("schema_version"), bool)
    ):
        raise RuntimeError(
            "Knowledge Graph command receipt has an unsupported schema"
        )
    kind = payload.get("kind")
    expected_revision = payload.get("expected_revision")
    applied_revision = payload.get("applied_revision")
    original_changed = payload.get("original_changed")
    raw_edge = payload.get("original_affected_edge")
    try:
        identity = _knowledge_graph_edge_identity(
            raw_edge.get("source") if isinstance(raw_edge, dict) else None,
            raw_edge.get("target") if isinstance(raw_edge, dict) else None,
            raw_edge.get("edge_type") if isinstance(raw_edge, dict) else None,
        )
    except KnowledgeGraphCommandError as exc:
        raise RuntimeError(
            "Knowledge Graph command receipt has invalid edge identity"
        ) from exc
    if (
        not isinstance(kind, str)
        or kind not in _KNOWLEDGE_GRAPH_COMMAND_KINDS
        or not isinstance(expected_revision, str)
        or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
        or not isinstance(applied_revision, str)
        or _LOWER_SHA256_RE.fullmatch(applied_revision) is None
        or original_changed is not True
        or applied_revision == expected_revision
        or _LOWER_SHA256_RE.fullmatch(row.idempotency_key_hash or "") is None
        or _LOWER_SHA256_RE.fullmatch(row.request_digest or "") is None
    ):
        raise RuntimeError("Knowledge Graph command receipt has invalid result data")
    canonical_request_digest = _knowledge_graph_command_request_digest(
        int(row.project_id),
        kind,
        expected_revision,
        identity,
    )
    if not hmac.compare_digest(row.request_digest, canonical_request_digest):
        raise RuntimeError(
            "Knowledge Graph command receipt does not match its request digest"
        )
    return KnowledgeGraphCommandReceiptData(
        project_id=int(row.project_id),
        request_digest=row.request_digest,
        kind=kind,
        expected_revision=expected_revision,
        applied_revision=applied_revision,
        original_changed=original_changed,
        original_affected_edge=identity,
        created_at=row.created_at,
    )


def _continuity_idempotency_key_hash(value: str) -> str:
    """Validate and irreversibly identify one Continuity retry capability."""
    if not isinstance(value, str):
        raise ContinuityCommandError("Idempotency-Key must be a string")
    if (
        value != value.strip()
        or _CONTINUITY_IDEMPOTENCY_KEY_RE.fullmatch(value) is None
    ):
        raise ContinuityCommandError(
            "Idempotency-Key must contain 16-128 safe ASCII characters"
        )
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _continuity_command_request_digest(
    project_id: int,
    kind: str,
    expected_revision: str,
    issue_key: str,
    expected_issue_fingerprint: str,
) -> str:
    encoded = json.dumps(
        {
            "scope": "continuity-command-v1",
            "project_id": int(project_id),
            "kind": kind,
            "expected_revision": expected_revision,
            "issue_key": issue_key,
            "expected_issue_fingerprint": expected_issue_fingerprint,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _continuity_receipt_result_json(
    *,
    kind: str,
    expected_revision: str,
    applied_revision: str,
    issue_key: str,
    expected_issue_fingerprint: str,
    previous_status: str,
    status: str,
    original_changed: bool,
) -> str:
    return json.dumps(
        {
            "schema_version": _CONTINUITY_RECEIPT_SCHEMA_VERSION,
            "kind": kind,
            "expected_revision": expected_revision,
            "applied_revision": applied_revision,
            "issue_key": issue_key,
            "expected_issue_fingerprint": expected_issue_fingerprint,
            "previous_status": previous_status,
            "status": status,
            "original_changed": original_changed,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_continuity_command_receipt(
    row: ContinuityCommandReceipt,
) -> ContinuityCommandReceiptData:
    """Decode a Continuity receipt fail-closed; corrupt proof cannot replay."""
    try:
        payload = json.loads(row.result_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("Continuity command receipt is corrupt") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != _CONTINUITY_RECEIPT_SCHEMA_VERSION
        or isinstance(payload.get("schema_version"), bool)
    ):
        raise RuntimeError("Continuity command receipt has an unsupported schema")

    kind = payload.get("kind")
    expected_revision = payload.get("expected_revision")
    applied_revision = payload.get("applied_revision")
    issue_key = payload.get("issue_key")
    expected_issue_fingerprint = payload.get("expected_issue_fingerprint")
    previous_status = payload.get("previous_status")
    status = payload.get("status")
    original_changed = payload.get("original_changed")
    expected_status = _CONTINUITY_COMMAND_STATUSES.get(kind)
    if (
        not isinstance(kind, str)
        or expected_status is None
        or not isinstance(expected_revision, str)
        or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
        or not isinstance(applied_revision, str)
        or _LOWER_SHA256_RE.fullmatch(applied_revision) is None
        or not isinstance(issue_key, str)
        or _CONTINUITY_ISSUE_KEY_RE.fullmatch(issue_key) is None
        or not isinstance(expected_issue_fingerprint, str)
        or _LOWER_SHA256_RE.fullmatch(expected_issue_fingerprint) is None
        or previous_status != "open"
        or status != expected_status
        or original_changed is not True
        or applied_revision == expected_revision
        or _LOWER_SHA256_RE.fullmatch(row.idempotency_key_hash or "") is None
        or _LOWER_SHA256_RE.fullmatch(row.request_digest or "") is None
    ):
        raise RuntimeError("Continuity command receipt has invalid result data")
    canonical_request_digest = _continuity_command_request_digest(
        int(row.project_id), kind, expected_revision, issue_key,
        expected_issue_fingerprint,
    )
    if not hmac.compare_digest(row.request_digest, canonical_request_digest):
        raise RuntimeError(
            "Continuity command receipt does not match its request digest"
        )
    return ContinuityCommandReceiptData(
        project_id=int(row.project_id),
        request_digest=row.request_digest,
        kind=kind,
        expected_revision=expected_revision,
        applied_revision=applied_revision,
        issue_key=issue_key,
        expected_issue_fingerprint=expected_issue_fingerprint,
        previous_status=previous_status,
        status=status,
        original_changed=True,
        created_at=row.created_at,
    )


def _workflow_idempotency_key_hash(value: str) -> str:
    """Validate and irreversibly identify one workflow retry capability."""
    if not isinstance(value, str):
        raise WorkflowCommandError("Idempotency-Key must be a string")
    if (
        value != value.strip()
        or _WORKFLOW_IDEMPOTENCY_KEY_RE.fullmatch(value) is None
    ):
        raise WorkflowCommandError(
            "Idempotency-Key must contain 16-128 safe ASCII characters"
        )
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _normalize_workflow_command(
    kind: str,
    expected_revision: str,
    fields: dict,
) -> tuple[str, dict]:
    """Validate the Core command envelope before hashing or opening a write."""
    if kind not in _WORKFLOW_COMMAND_KINDS:
        raise WorkflowCommandError(
            f"Unsupported Guided Workflow command: {kind!r}"
        )
    allowed = {
        "start_workflow": {"template_id", "title"},
        "complete_step": {"run_id", "step_id", "notes"},
        "skip_step": {"run_id", "step_id", "notes"},
        "advance": {"run_id"},
        "refresh": {"run_id"},
        "pause": {"run_id"},
        "resume": {"run_id"},
        "cancel": {"run_id"},
    }[kind]
    unexpected = sorted(set(fields) - allowed)
    if unexpected:
        raise WorkflowCommandError(
            f"Unexpected field(s) for {kind}: {', '.join(unexpected)}"
        )

    normalized: dict = {}
    if kind == "start_workflow":
        if expected_revision not in ("", None):
            raise WorkflowCommandError(
                "start_workflow does not accept expected_revision"
            )
        template_id = fields.get("template_id")
        if (
            not isinstance(template_id, str)
            or not template_id.strip()
            or len(template_id.strip()) > 128
        ):
            raise WorkflowCommandError("template_id must be a non-empty string")
        normalized["template_id"] = template_id.strip()
        if "title" in fields and fields["title"] is not None:
            title = fields["title"]
            if (
                not isinstance(title, str)
                or not title.strip()
                or len(title.strip()) > 200
            ):
                raise WorkflowCommandError(
                    "title must be a non-empty string up to 200 characters"
                )
            normalized["title"] = title.strip()
        return "", normalized

    if (
        not isinstance(expected_revision, str)
        or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
    ):
        raise WorkflowCommandError(
            "expected_revision must be a lowercase SHA-256 digest"
        )
    run_id = fields.get("run_id")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        raise WorkflowCommandError("run_id must be a positive integer")
    normalized["run_id"] = run_id
    if kind in {"complete_step", "skip_step"}:
        step_id = fields.get("step_id")
        if (
            not isinstance(step_id, str)
            or not step_id.strip()
            or len(step_id.strip()) > 128
        ):
            raise WorkflowCommandError("step_id must be a non-empty string")
        normalized["step_id"] = step_id.strip()
        notes = fields.get("notes", "")
        if not isinstance(notes, str) or len(notes) > 4000:
            raise WorkflowCommandError(
                "notes must be a string up to 4000 characters"
            )
        normalized["notes"] = notes
    return expected_revision, normalized


def _workflow_command_request_digest(
    project_id: int,
    kind: str,
    expected_revision: str,
    fields: dict,
) -> str:
    encoded = json.dumps(
        {
            "scope": "guided-workflow-command-v1",
            "project_id": int(project_id),
            "kind": kind,
            "expected_revision": expected_revision,
            "fields": fields,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _workflow_receipt_result_json(
    *,
    kind: str,
    expected_revision: str,
    applied_revision: str,
    original_changed: bool,
    run_id: int,
) -> str:
    return json.dumps(
        {
            "schema_version": _WORKFLOW_RECEIPT_SCHEMA_VERSION,
            "kind": kind,
            "expected_revision": expected_revision,
            "applied_revision": applied_revision,
            "original_changed": original_changed,
            "run_id": int(run_id),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_workflow_command_receipt(
    row: WorkflowCommandReceipt,
) -> WorkflowCommandReceiptData:
    """Decode a workflow receipt fail-closed; corrupt proof cannot replay."""
    try:
        payload = json.loads(row.result_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("Guided Workflow command receipt is corrupt") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != _WORKFLOW_RECEIPT_SCHEMA_VERSION
        or isinstance(payload.get("schema_version"), bool)
    ):
        raise RuntimeError(
            "Guided Workflow command receipt has an unsupported schema"
        )
    kind = payload.get("kind")
    expected_revision = payload.get("expected_revision")
    applied_revision = payload.get("applied_revision")
    original_changed = payload.get("original_changed")
    run_id = payload.get("run_id")
    if (
        kind not in _WORKFLOW_COMMAND_KINDS
        or not isinstance(expected_revision, str)
        or (
            kind != "start_workflow"
            and _LOWER_SHA256_RE.fullmatch(expected_revision) is None
        )
        or (kind == "start_workflow" and expected_revision != "")
        or not isinstance(applied_revision, str)
        or _LOWER_SHA256_RE.fullmatch(applied_revision) is None
        or not isinstance(original_changed, bool)
        or isinstance(run_id, bool)
        or not isinstance(run_id, int)
        or run_id <= 0
        or _LOWER_SHA256_RE.fullmatch(row.idempotency_key_hash or "") is None
        or _LOWER_SHA256_RE.fullmatch(row.request_digest or "") is None
    ):
        raise RuntimeError(
            "Guided Workflow command receipt has invalid result data"
        )
    return WorkflowCommandReceiptData(
        project_id=int(row.project_id),
        request_digest=row.request_digest,
        kind=kind,
        expected_revision=expected_revision,
        applied_revision=applied_revision,
        original_changed=original_changed,
        run_id=run_id,
        created_at=row.created_at,
    )


def _workflow_completion_check_in_session(
    session: Session,
    project: Project,
    check_name: str,
) -> bool:
    """Evaluate only checks that can be proven in the current SQL snapshot.

    Complex graph/radar/export checks deliberately fail closed.  A refresh may
    under-complete and be retried; it must never permanently complete a step
    from a torn or stale multi-session report.
    """
    project_id = int(project.id)

    def scenes() -> tuple[Scene, ...]:
        return tuple(session.exec(
            select(Scene).where(Scene.project_id == project_id)
        ).all())

    if check_name == "project_has_title":
        return bool((project.title or "").strip()) and project.title != "Untitled"
    if check_name == "project_has_description":
        return bool((project.description or "").strip())
    if check_name == "has_scenes":
        return session.exec(
            select(func.count(Scene.id)).where(Scene.project_id == project_id)
        ).one() > 0
    if check_name == "all_scenes_have_summary":
        rows = scenes()
        return bool(rows) and all((row.summary or "").strip() for row in rows)
    if check_name == "all_scenes_have_chapter":
        rows = scenes()
        return bool(rows) and all((row.chapter or "").strip() for row in rows)
    if check_name == "has_outline_nodes":
        return session.exec(
            select(func.count(OutlineNode.id)).where(
                OutlineNode.project_id == project_id
            )
        ).one() > 0
    if check_name in {"psyke_has_entries", "psyke_notes_filled", "psyke_has_relations"}:
        entries = tuple(session.exec(
            select(PsykeEntry).where(PsykeEntry.project_id == project_id)
        ).all())
        if check_name == "psyke_has_entries":
            return bool(entries)
        if check_name == "psyke_notes_filled":
            return all((entry.notes or "").strip() for entry in entries)
        entry_ids = {int(entry.id) for entry in entries}
        if not entry_ids:
            return True
        related_ids: set[int] = set()
        for relation in session.exec(
            select(PsykeRelation).where(
                PsykeRelation.entry_id.in_(entry_ids),
                PsykeRelation.related_entry_id.in_(entry_ids),
            )
        ).all():
            related_ids.add(int(relation.entry_id))
            related_ids.add(int(relation.related_entry_id))
        return related_ids == entry_ids
    if check_name == "no_pending_apply":
        return session.exec(
            select(func.count(ControlledApplyOperation.id)).where(
                ControlledApplyOperation.project_id == project_id,
                ControlledApplyOperation.status.in_(("draft", "previewed")),
            )
        ).one() == 0
    if check_name == "no_preferred_rewrite":
        return session.exec(
            select(func.count(RewriteVariant.id)).where(
                RewriteVariant.project_id == project_id,
                RewriteVariant.status == "preferred",
            )
        ).one() == 0
    if check_name == "no_stale_rewrite":
        # Proving source freshness requires comparing live narrative content.
        # With no open session there is nothing that can be stale; otherwise
        # fail closed rather than auto-completing from an out-of-transaction
        # content read.
        return session.exec(
            select(func.count(RewriteSession.id)).where(
                RewriteSession.project_id == project_id,
                RewriteSession.status == "open",
            )
        ).one() == 0
    if check_name == "production_active":
        return session.exec(
            select(func.count(ProductionDraft.id)).where(
                ProductionDraft.project_id == project_id,
                ProductionDraft.is_active.is_(True),
            )
        ).one() > 0
    if check_name == "production_has_revision_set":
        active_ids = tuple(session.exec(
            select(ProductionDraft.id).where(
                ProductionDraft.project_id == project_id,
                ProductionDraft.is_active.is_(True),
            )
        ).all())
        return bool(active_ids) and session.exec(
            select(func.count(RevisionSet.id)).where(
                RevisionSet.project_id == project_id,
                RevisionSet.draft_id.in_(active_ids),
            )
        ).one() > 0

    # Graph isolation, Decision Radar and rendered export validation aggregate
    # non-SQL engines. They remain manual until those engines expose a coherent
    # session-bound snapshot token.
    return False


@dataclass(frozen=True)
class PlotBlockUpdateResult:
    """One committed Plot block mutation and its invalidation metadata."""

    scene_ids: tuple[int, ...]
    changed_scene_ids: tuple[int, ...]
    new_name: str
    timeline_changed: bool


# Inverse mapping for PSYKE typed relations. A "payoff" from A→B is stored as
# a "supports_setup" on B→A so direction is preserved when traversing.
_INVERSE_RELATION_TYPE: dict[str, str] = {
    "supports_setup": "payoff",
    "payoff": "supports_setup",
    # Symmetric relation types map to themselves
    "thematic_echo": "thematic_echo",
    "visual_motif": "visual_motif",
    "subtext_opposition": "subtext_opposition",
    # Theatre relation types — dominates/submits are a natural antonym pair;
    # the remaining directional types store the same type on the reverse
    # edge (the context layer dedupes by unordered pair).
    "dominates": "submits",
    "submits": "dominates",
}


# Continuity memory_type values for StoryMemoryEntry — track per-scene
# physical and mental state for continuity audits.
CONTINUITY_MEMORY_TYPES = (
    "continuity_wound",
    "continuity_prop",
    "continuity_costume",
    "continuity_emotional_state",
    "continuity_knowledge_state",
)


class Database:
    def __init__(self, path: Optional[str] = None) -> None:
        self._settings_lock = threading.RLock()
        self._comment_write_lock = threading.RLock()
        self._scene_locks_guard = threading.RLock()
        self._scene_write_locks: dict[int, threading.RLock] = {}
        self._plot_locks_guard = threading.RLock()
        self._plot_write_locks: dict[int, threading.RLock] = {}
        self._canvas_plot_locks_guard = threading.RLock()
        self._canvas_plot_write_locks: dict[int, threading.RLock] = {}
        self._knowledge_graph_locks_guard = threading.RLock()
        self._knowledge_graph_write_locks: dict[int, threading.RLock] = {}
        self._continuity_locks_guard = threading.RLock()
        self._continuity_write_locks: dict[int, threading.RLock] = {}
        self._workflow_locks_guard = threading.RLock()
        self._workflow_write_locks: dict[int, threading.RLock] = {}
        self._structure_locks_guard = threading.RLock()
        self._structure_write_locks: dict[int, threading.RLock] = {}
        # ``check_same_thread=False`` lets FastAPI's threadpool use pooled
        # connections. WAL permits concurrent readers; busy_timeout gives a
        # competing writer time to finish instead of surfacing a transient lock.
        file_based = bool(path and path != ":memory:")
        if file_based:
            db_path = Path(path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            if db_path.exists() and db_path.stat().st_size:
                try:
                    current_version = _read_user_version(db_path)
                except sqlite3.DatabaseError:
                    current_version = None
                if (
                    current_version is not None
                    and current_version > DB_SCHEMA_VERSION
                ):
                    raise UnsupportedDatabaseVersionError(
                        current_version,
                        DB_SCHEMA_VERSION,
                    )
            _prepare_migration_backup(db_path)
        if file_based:
            assert path is not None
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{path}"
            self._engine = create_engine(
                url, echo=False,
                connect_args={"check_same_thread": False, "timeout": 5.0},
            )
        else:
            # Both Database() and Database(":memory:") use one shared connection.
            # A serialized StaticPool keeps it visible across threads without
            # allowing overlapping transactions on the same sqlite3 handle.
            url = "sqlite://"
            self._engine = create_engine(
                url, echo=False,
                connect_args={"check_same_thread": False},
                poolclass=_SerializedStaticPool,
            )

        @event.listens_for(self._engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
                if file_based:
                    cursor.execute("PRAGMA journal_mode=WAL")
            finally:
                cursor.close()

        SQLModel.metadata.create_all(self._engine)
        self._migrate()

    @contextmanager
    def scene_write_lock(self, scene_id: int):
        """Hold the stable per-scene lock across read/compare/write sequences."""
        key = int(scene_id)
        with self._scene_locks_guard:
            lock = self._scene_write_locks.setdefault(key, threading.RLock())
        with lock:
            yield

    @contextmanager
    def plot_write_lock(self, project_id: int):
        """Serialize writers that can change Plot/Timeline lane membership.

        The global nesting order is Scene -> Plot topology -> project structure
        -> project settings.  Group mutations (Plot or Timeline lane renames)
        start at this project-scoped lock; single-Scene writers take their Scene
        lock first.  Keeping the group lock independent of member Scene locks
        avoids lock-set discovery races and multi-Scene deadlocks.
        """
        key = int(project_id)
        with self._plot_locks_guard:
            lock = self._plot_write_locks.setdefault(key, threading.RLock())
        with lock:
            yield

    @contextmanager
    def comment_write_lock(self):
        """Serialize comment transactions sharing an in-memory SQLite handle."""
        with self._comment_write_lock:
            yield

    @contextmanager
    def canvas_plot_write_lock(self, project_id: int):
        """Serialize Canvas Plot writers for one project inside this process."""
        key = int(project_id)
        with self._canvas_plot_locks_guard:
            lock = self._canvas_plot_write_locks.setdefault(key, threading.RLock())
        with lock:
            yield

    @contextmanager
    def knowledge_graph_write_lock(self, project_id: int):
        """Serialize Knowledge Graph review writers for one project."""
        key = int(project_id)
        with self._knowledge_graph_locks_guard:
            lock = self._knowledge_graph_write_locks.setdefault(
                key, threading.RLock(),
            )
        with lock:
            yield

    @contextmanager
    def continuity_write_lock(self, project_id: int):
        """Serialize one project's Continuity review commands in-process."""
        project_id = int(project_id)
        with self._continuity_locks_guard:
            lock = self._continuity_write_locks.setdefault(
                project_id, threading.RLock()
            )
        with lock:
            yield

    @contextmanager
    def workflow_write_lock(self, project_id: int):
        """Serialize Guided Workflow writers for one project in-process."""
        key = int(project_id)
        with self._workflow_locks_guard:
            lock = self._workflow_write_locks.setdefault(
                key, threading.RLock(),
            )
        with lock:
            yield

    @contextmanager
    def structure_write_lock(self, project_id: int):
        """Serialize project-structure writers inside this process."""
        key = int(project_id)
        with self._structure_locks_guard:
            lock = self._structure_write_locks.setdefault(key, threading.RLock())
        with lock:
            yield

    @contextmanager
    def _structure_write_session(self, project_id: int):
        """Open a serialized SQLite write transaction for structural rows.

        ``BEGIN IMMEDIATE`` must precede the caller's first read so a legacy
        whole-project reorder cannot calculate from a snapshot that another
        writer changes before the rewrite is flushed.
        """
        with self.structure_write_lock(project_id):
            with Session(self._engine, expire_on_commit=False) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    yield session
                except Exception:
                    session.rollback()
                    raise

    def _migrate(self) -> None:
        with self._engine.connect() as conn:
            current_version = int(
                conn.execute(text("PRAGMA user_version")).fetchone()[0]
            )
            if current_version > DB_SCHEMA_VERSION:
                raise UnsupportedDatabaseVersionError(
                    current_version,
                    DB_SCHEMA_VERSION,
                )
            rows = conn.execute(text("PRAGMA table_info(psykeentry)")).fetchall()
            columns = {row[1] for row in rows}
            if rows and "details_json" not in columns:
                conn.execute(
                    text("ALTER TABLE psykeentry ADD COLUMN details_json TEXT DEFAULT ''")
                )
                conn.commit()

            rows = conn.execute(text("PRAGMA table_info(project)")).fetchall()
            columns = {row[1] for row in rows}
            if rows and "format_mode" not in columns:
                conn.execute(
                    text("ALTER TABLE project ADD COLUMN format_mode TEXT DEFAULT 'novel'")
                )
                conn.commit()
            if rows and "settings_json" not in columns:
                conn.execute(
                    text("ALTER TABLE project ADD COLUMN settings_json TEXT DEFAULT ''")
                )
                conn.commit()
            if rows and "narrative_engine" not in columns:
                conn.execute(text(
                    "ALTER TABLE project ADD COLUMN"
                    " narrative_engine TEXT DEFAULT ''"
                ))
                conn.commit()
            if rows and "default_writing_format" not in columns:
                conn.execute(text(
                    "ALTER TABLE project ADD COLUMN"
                    " default_writing_format TEXT DEFAULT ''"
                ))
                conn.commit()
            # Backfill engine + format from legacy format_mode for rows
            # that haven't been touched by the new UI yet.
            from logosforge.project_compat import resolve_legacy_format
            existing = conn.execute(text(
                "SELECT id, format_mode, narrative_engine,"
                " default_writing_format FROM project"
            )).fetchall()
            for pid, fmode, engine, fmt in existing:
                if not (engine or "").strip() or not (fmt or "").strip():
                    e2, f2 = resolve_legacy_format(fmode or "")
                    conn.execute(
                        text(
                            "UPDATE project SET narrative_engine=:e,"
                            " default_writing_format=:f WHERE id=:i"
                        ),
                        {"e": engine or e2, "f": fmt or f2, "i": pid},
                    )
            conn.commit()

            rows = conn.execute(text("PRAGMA table_info(scene)")).fetchall()
            columns = {row[1] for row in rows}
            if rows and "color_label" not in columns:
                conn.execute(
                    text("ALTER TABLE scene ADD COLUMN color_label TEXT DEFAULT ''")
                )
                conn.commit()

            # Outline node → manuscript scene hard link (nullable FK-ish int).
            rows = conn.execute(text("PRAGMA table_info(outlinenode)")).fetchall()
            columns = {row[1] for row in rows}
            if rows and "scene_id" not in columns:
                conn.execute(text("ALTER TABLE outlinenode ADD COLUMN scene_id INTEGER"))
                conn.commit()

            # Screenplay-engine fields — added safely; existing rows pick up
            # the defaults and Novel projects simply ignore them.
            _screenplay_text_fields = (
                "slugline", "location", "interior_exterior", "time_of_day",
                "visual_objective", "dramatic_turn", "blocking_notes",
                "subtext_notes", "setup_payoff_links", "montage_group",
                "cinematic_pacing", "continuity_notes",
                # PSYKE-screenplay extensions (cinematic + performative)
                "visible_conflict", "hidden_conflict", "emotional_turn",
                "who_knows_what", "physical_action", "visual_symbolism",
            )
            if rows:
                columns = {row[1] for row in conn.execute(
                    text("PRAGMA table_info(scene)")).fetchall()}
                for col in _screenplay_text_fields:
                    if col not in columns:
                        conn.execute(text(
                            f"ALTER TABLE scene ADD COLUMN {col} TEXT DEFAULT ''"
                        ))
                if "estimated_duration_minutes" not in columns:
                    conn.execute(text(
                        "ALTER TABLE scene ADD COLUMN"
                        " estimated_duration_minutes INTEGER DEFAULT 0"
                    ))
                conn.commit()

            # Stage-script scene fields — added safely; existing rows pick up
            # the defaults and other engines simply ignore them. time_of_day,
            # dramatic_turn, blocking_notes and continuity_notes are reused
            # from the screenplay set above.
            _stage_text_fields = (
                "stage_location", "set_description", "scene_objective",
                "entrance_exit_notes", "prop_notes", "cue_notes",
                "offstage_events", "audience_visibility_notes",
            )
            if rows:
                columns = {row[1] for row in conn.execute(
                    text("PRAGMA table_info(scene)")).fetchall()}
                for col in _stage_text_fields:
                    if col not in columns:
                        conn.execute(text(
                            f"ALTER TABLE scene ADD COLUMN {col} TEXT DEFAULT ''"
                        ))
                if "performance_duration_minutes" not in columns:
                    conn.execute(text(
                        "ALTER TABLE scene ADD COLUMN"
                        " performance_duration_minutes INTEGER DEFAULT 0"
                    ))
                conn.commit()

            # PSYKE relation typing — adds relation_type for screenplay
            # extensions (setup/payoff/thematic_echo/visual_motif/etc.)
            rel_rows = conn.execute(
                text("PRAGMA table_info(psykerelation)"),
            ).fetchall()
            rel_columns = {row[1] for row in rel_rows}
            if rel_rows and "relation_type" not in rel_columns:
                conn.execute(text(
                    "ALTER TABLE psykerelation ADD COLUMN"
                    " relation_type TEXT DEFAULT ''"
                ))
                conn.commit()

            # GraphicNovelPage.issue_id — the page table shipped before
            # Issues existed, so old DB files need the nullable column added.
            # (New DBs already get it from create_all(), skipping this.)
            page_rows = conn.execute(
                text("PRAGMA table_info(graphicnovelpage)"),
            ).fetchall()
            page_columns = {row[1] for row in page_rows}
            if page_rows and "issue_id" not in page_columns:
                conn.execute(text(
                    "ALTER TABLE graphicnovelpage ADD COLUMN issue_id INTEGER"
                ))
                conn.commit()

            # Scene.episode_id — the Series Season -> Episode -> Act -> Chapter
            # -> Scene hierarchy links each Series scene to an Episode. The
            # column is nullable; NULL preserves every pre-existing scene's
            # behaviour (non-Series modes and legacy Series alike), so this is a
            # purely additive, back-compatible migration.
            scene_rows = conn.execute(
                text("PRAGMA table_info(scene)"),
            ).fetchall()
            scene_columns = {row[1] for row in scene_rows}
            if scene_rows and "episode_id" not in scene_columns:
                conn.execute(text(
                    "ALTER TABLE scene ADD COLUMN episode_id INTEGER"
                ))
                conn.commit()

            # Scene.gn_page_start — Graphic Novel act-wide page coordinate
            # (Act -> Page -> Scene -> Panel outline). Nullable; NULL keeps
            # the legacy auto-chained layout, so this is purely additive.
            if scene_rows and "gn_page_start" not in scene_columns:
                conn.execute(text(
                    "ALTER TABLE scene ADD COLUMN gn_page_start INTEGER"
                ))
                conn.commit()

            # Character.psyke_entry_id — links a manuscript Character to its PSYKE
            # 'character' bible entry. The character table shipped before this
            # column existed, so old DB files need the nullable column added.
            # (New DBs already get it from create_all(), skipping this.)
            char_rows = conn.execute(
                text("PRAGMA table_info(character)"),
            ).fetchall()
            char_columns = {row[1] for row in char_rows}
            if char_rows and "psyke_entry_id" not in char_columns:
                conn.execute(text(
                    "ALTER TABLE character ADD COLUMN psyke_entry_id INTEGER"
                ))
                conn.commit()
            _repair_character_psyke_foreign_key(conn)

            conn.execute(text(f"PRAGMA user_version = {DB_SCHEMA_VERSION}"))
            conn.commit()

    # -- Projects ------------------------------------------------------------

    def get_project_by_id(self, project_id: int) -> Project | None:
        with Session(self._engine) as session:
            return session.get(Project, project_id)

    def get_all_projects(self) -> list[Project]:
        with Session(self._engine) as session:
            return list(session.exec(select(Project)).all())

    def delete_project(self, project_id: int) -> None:
        """Serialize project deletion with every structural writer."""
        with self.structure_write_lock(project_id):
            self._delete_project_rows(project_id)

    def _delete_project_rows(self, project_id: int) -> None:
        """Delete a project and ALL of its data (generic cascade). Collects every
        parent id the project owns, then sweeps each table that references the
        project — by ``project_id`` or by a parent-id FK column — and finally removes
        the project row. Tables are processed child-first so SQLite foreign-key
        enforcement can remain enabled. Safe to call on a missing id (no-op)."""
        from sqlalchemy import or_

        def _ids(getter):
            try:
                return {r.id for r in getter(project_id) if getattr(r, "id", None) is not None}
            except Exception:
                return set()

        scene_ids = _ids(self.get_all_scenes)
        entry_ids = _ids(self.get_all_psyke_entries)
        char_ids = _ids(self.get_all_characters)
        place_ids = _ids(self.get_all_places)
        page_ids = _ids(self.get_gn_pages)
        item_ids = _ids(self.get_gn_continuity_items)
        season_ids = _ids(self.get_seasons)
        ep_ids = _ids(self.get_episodes)
        panel_ids: set[int] = set()
        for pgid in page_ids:
            try:
                panel_ids |= {p.id for p in self.get_gn_panels_for_page(pgid)}
            except Exception:
                pass

        # child FK column -> the owned parent ids it may reference
        fk = {
            "scene_id": scene_ids,
            "entry_id": entry_ids, "related_entry_id": entry_ids,
            "psyke_entry_id": entry_ids, "prop_psyke_entry_id": entry_ids,
            "linked_psyke_entry_id": entry_ids,
            "character_id": char_ids, "place_id": place_ids,
            "page_id": page_ids, "panel_id": panel_ids,
            "continuity_item_id": item_ids,
            "season_id": season_ids, "episode_id": ep_ids,
        }
        with Session(self._engine) as session:
            for table in reversed(SQLModel.metadata.sorted_tables):
                if table.name == "project":
                    continue
                conds = []
                if "project_id" in table.c:
                    conds.append(table.c.project_id == project_id)
                for col, ids in fk.items():
                    if ids and col in table.c:
                        conds.append(table.c[col].in_(ids))
                if conds:
                    session.execute(table.delete().where(or_(*conds)))
            proj = session.get(Project, project_id)
            if proj is not None:
                session.delete(proj)
            session.commit()

    def create_project(
        self,
        title: str,
        format_mode: str | None = None,
        *,
        narrative_engine: str = "",
        default_writing_format: str = "",
    ) -> Project:
        from logosforge.project_compat import (
            default_format_for_engine,
            resolve_legacy_format,
        )
        engine = (narrative_engine or "").strip()
        fmt = (default_writing_format or "").strip()
        legacy_provided = format_mode is not None
        legacy = (format_mode or "novel").strip()

        # Derive whichever new field is missing.
        if not engine and not fmt:
            engine, fmt = resolve_legacy_format(legacy)
        elif not engine:
            engine = resolve_legacy_format(legacy)[0]
        elif not fmt:
            fmt = default_format_for_engine(engine)

        # When the caller explicitly passed a legacy format_mode (e.g.
        # imports, legacy tests, or `_make_project(db, "series")`), keep
        # it exactly so round-trips stay faithful. Otherwise mirror the
        # chosen writing format into format_mode so back-compat readers
        # see the new selection.
        stored_format_mode = legacy if legacy_provided else fmt

        with Session(self._engine) as session:
            project = Project(
                title=title,
                format_mode=stored_format_mode,
                narrative_engine=engine,
                default_writing_format=fmt,
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            return project

    def update_project(
        self,
        project_id: int,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        """Update a project's title and/or description (None = leave unchanged)."""
        with Session(self._engine) as session:
            project = session.get(Project, project_id)
            if project is None:
                return
            if title is not None:
                project.title = title
            if description is not None:
                project.description = description
            session.commit()

    def update_project_format(self, project_id: int, format_mode: str) -> None:
        """Legacy: change the writing format and keep new fields in sync."""
        with self._structure_write_session(project_id) as session:
            project = session.get(Project, project_id)
            if project:
                project.format_mode = format_mode
                if format_mode:
                    project.default_writing_format = format_mode
                session.commit()

    def update_project_narrative_engine(
        self, project_id: int, engine: str,
    ) -> None:
        with self._structure_write_session(project_id) as session:
            project = session.get(Project, project_id)
            if project and engine:
                project.narrative_engine = engine
                session.commit()

    def update_project_mode(
        self, project_id: int, engine: str, writing_format: str,
    ) -> None:
        """Atomically keep the canonical engine and both format fields aligned."""
        with self._structure_write_session(project_id) as session:
            project = session.get(Project, project_id)
            if project is None or not engine or not writing_format:
                return
            project.narrative_engine = engine
            project.default_writing_format = writing_format
            # Legacy readers still use format_mode, so the three fields must move
            # together whenever the project-level writing mode changes.
            project.format_mode = writing_format
            session.commit()

    def update_project_writing_format(
        self, project_id: int, writing_format: str,
    ) -> None:
        with self._structure_write_session(project_id) as session:
            project = session.get(Project, project_id)
            if project and writing_format:
                project.default_writing_format = writing_format
                # Keep legacy format_mode in sync so the manuscript editor
                # and exporters that still read format_mode keep working.
                project.format_mode = writing_format
                session.commit()

    def get_project_settings(self, project_id: int) -> dict:
        import json
        with self._settings_lock:
            with Session(self._engine) as session:
                project = session.get(Project, project_id)
                if project and project.settings_json:
                    try:
                        return json.loads(project.settings_json)
                    except (json.JSONDecodeError, TypeError):
                        return {}
                return {}

    def save_project_settings(self, project_id: int, settings: dict) -> None:
        import json
        with self._settings_lock:
            with Session(self._engine) as session:
                project = session.get(Project, project_id)
                if project:
                    project.settings_json = json.dumps(settings)
                    session.commit()

    def patch_project_settings(self, project_id: int, changes: dict) -> dict:
        """Atomically merge settings and return the complete stored object."""
        import json
        with self._settings_lock:
            with Session(self._engine) as session:
                project = session.get(Project, project_id)
                if project is None:
                    return {}
                try:
                    current = json.loads(project.settings_json or "{}")
                except (json.JSONDecodeError, TypeError):
                    current = {}
                if not isinstance(current, dict):
                    current = {}
                current.update(changes)
                project.settings_json = json.dumps(current)
                session.commit()
                return current

    def get_project_by_source_path(self, source_path: str) -> int | None:
        """Return the id of the project imported from *source_path*, if any.

        Used to AVOID re-importing a project file as a duplicate every time it
        is opened (or on each app launch). The source path is tagged into the
        project's settings when it is first imported."""
        import json
        target = str(source_path)
        with Session(self._engine) as session:
            for project in session.exec(select(Project)).all():
                if not project.settings_json:
                    continue
                try:
                    settings = json.loads(project.settings_json)
                except (json.JSONDecodeError, TypeError):
                    continue
                if settings.get("source_path") == target:
                    return project.id
            return None

    def set_project_source_path(self, project_id: int, source_path: str) -> None:
        """Tag the file a project was imported from (for open de-duplication)."""
        settings = self.get_project_settings(project_id)
        settings["source_path"] = str(source_path)
        self.save_project_settings(project_id, settings)

    def get_scoring_weights(self, project_id: int) -> dict[str, float]:
        from logosforge.quantum_outliner.scoring import DEFAULT_WEIGHTS
        settings = self.get_project_settings(project_id)
        stored = settings.get("scoring_weights")
        if isinstance(stored, dict) and all(k in stored for k in DEFAULT_WEIGHTS):
            return {k: float(stored[k]) for k in DEFAULT_WEIGHTS}
        return dict(DEFAULT_WEIGHTS)

    def set_scoring_weights(self, project_id: int, weights: dict[str, float]) -> None:
        settings = self.get_project_settings(project_id)
        settings["scoring_weights"] = weights
        self.save_project_settings(project_id, settings)

    def get_scoring_preset(self, project_id: int) -> str:
        settings = self.get_project_settings(project_id)
        return settings.get("scoring_preset", "Balanced")

    def set_scoring_preset(self, project_id: int, preset: str) -> None:
        settings = self.get_project_settings(project_id)
        settings["scoring_preset"] = preset
        self.save_project_settings(project_id, settings)

    def get_weight_learning(self, project_id: int) -> bool:
        settings = self.get_project_settings(project_id)
        return settings.get("weight_learning", True)

    def set_weight_learning(self, project_id: int, enabled: bool) -> None:
        settings = self.get_project_settings(project_id)
        settings["weight_learning"] = enabled
        self.save_project_settings(project_id, settings)

    def get_constraints(self, project_id: int) -> list[str]:
        settings = self.get_project_settings(project_id)
        raw = settings.get("constraints")
        if isinstance(raw, list):
            return [str(c) for c in raw if c]
        return []

    def set_constraints(self, project_id: int, constraints: list[str]) -> None:
        settings = self.get_project_settings(project_id)
        settings["constraints"] = constraints
        self.save_project_settings(project_id, settings)

    def add_constraint(self, project_id: int, constraint: str) -> None:
        constraints = self.get_constraints(project_id)
        constraint = constraint.strip()
        if constraint and constraint not in constraints:
            constraints.append(constraint)
            self.set_constraints(project_id, constraints)

    def remove_constraint(self, project_id: int, constraint: str) -> None:
        constraints = self.get_constraints(project_id)
        constraint = constraint.strip()
        if constraint in constraints:
            constraints.remove(constraint)
            self.set_constraints(project_id, constraints)

    def get_show_tradeoffs(self, project_id: int) -> bool:
        settings = self.get_project_settings(project_id)
        return settings.get("show_tradeoffs", False)

    def set_show_tradeoffs(self, project_id: int, enabled: bool) -> None:
        settings = self.get_project_settings(project_id)
        settings["show_tradeoffs"] = enabled
        self.save_project_settings(project_id, settings)

    def get_selection_mode(self, project_id: int) -> str:
        settings = self.get_project_settings(project_id)
        mode = settings.get("selection_mode", "weighted")
        if mode not in ("weighted", "pareto"):
            return "weighted"
        return mode

    def set_selection_mode(self, project_id: int, mode: str) -> None:
        if mode not in ("weighted", "pareto"):
            mode = "weighted"
        settings = self.get_project_settings(project_id)
        settings["selection_mode"] = mode
        self.save_project_settings(project_id, settings)

    def get_ensemble_alpha(self, project_id: int) -> float:
        settings = self.get_project_settings(project_id)
        val = settings.get("ensemble_alpha", 0.7)
        try:
            return max(0.0, min(float(val), 1.0))
        except (TypeError, ValueError):
            return 0.7

    def set_ensemble_alpha(self, project_id: int, alpha: float) -> None:
        settings = self.get_project_settings(project_id)
        settings["ensemble_alpha"] = max(0.0, min(float(alpha), 1.0))
        self.save_project_settings(project_id, settings)

    def get_quantum_goals(self, project_id: int) -> "QuantumGoals":
        from logosforge.quantum_outliner.scoring import QuantumGoals
        settings = self.get_project_settings(project_id)
        raw = settings.get("quantum_goals")
        if isinstance(raw, dict):
            return QuantumGoals(
                objectives=raw.get("objectives", {}),
                min_constraints=raw.get("min_constraints", {}),
                horizon=raw.get("horizon", 1),
            ).validate()
        return QuantumGoals()

    def set_quantum_goals(self, project_id: int, goals: "QuantumGoals") -> None:
        goals.validate()
        settings = self.get_project_settings(project_id)
        settings["quantum_goals"] = {
            "objectives": goals.objectives,
            "min_constraints": goals.min_constraints,
            "horizon": goals.horizon,
        }
        self.save_project_settings(project_id, settings)
        from logosforge.quantum_outliner.lookahead_cache import invalidate_lookahead
        invalidate_lookahead()

    # -- Characters ----------------------------------------------------------

    def get_character_by_id(self, character_id: int) -> Character | None:
        with Session(self._engine) as session:
            return session.get(Character, character_id)

    def get_all_characters(self, project_id: int) -> list[Character]:
        with Session(self._engine) as session:
            stmt = select(Character).where(Character.project_id == project_id)
            return list(session.exec(stmt).all())

    def create_character(
        self, project_id: int, name: str, description: str = ""
    ) -> Character:
        with Session(self._engine) as session:
            character = Character(
                project_id=project_id, name=name, description=description
            )
            session.add(character)
            session.commit()
            session.refresh(character)
            return character

    def update_character(
        self, character_id: int, name: str, description: str = ""
    ) -> Character:
        with Session(self._engine) as session:
            character = session.get(Character, character_id)
            character.name = name
            character.description = description
            session.commit()
            session.refresh(character)
            return character

    def set_character_psyke_entry(
        self, character_id: int, entry_id: int | None,
    ) -> None:
        """Bind a manuscript Character to its PSYKE 'character' bible entry (or clear
        with None). The stable id link survives renames/aliases/typos that name-
        matching would later miss."""
        with Session(self._engine) as session:
            character = session.get(Character, character_id)
            if character is not None:
                character.psyke_entry_id = entry_id
                session.commit()

    def backfill_character_psyke_links(self, project_id: int) -> int:
        """Link any still-unlinked Characters to their PSYKE 'character' entry by
        name, reusing the conservative reconciler. Idempotent: fills only NULLs,
        never overwrites/creates/removes; returns the count newly written."""
        from logosforge.name_reconcile import _match_id

        entries = [
            e for e in self.get_all_psyke_entries(project_id)
            if (e.entry_type or "").lower() == "character"
        ]
        if not entries:
            return 0
        items = [(e.id, e.name, e.aliases or "") for e in entries]
        written = 0
        with Session(self._engine) as session:
            unlinked = session.exec(
                select(Character).where(
                    Character.project_id == project_id,
                    Character.psyke_entry_id.is_(None),
                )
            ).all()
            for character in unlinked:
                eid = _match_id(character.name, items)
                if eid is not None:
                    character.psyke_entry_id = eid
                    written += 1
            if written:
                session.commit()
        return written

    def delete_character(self, character_id: int) -> None:
        with Session(self._engine) as session:
            # Remove owned child rows; optional stage references are preserved
            # but detached from the deleted cast member.
            for link in session.exec(
                select(SceneCharacterLink).where(
                    SceneCharacterLink.character_id == character_id
                )
            ).all():
                session.delete(link)
            for state in session.exec(
                select(SceneCharacterState).where(
                    SceneCharacterState.character_id == character_id
                )
            ).all():
                session.delete(state)
            for profile in session.exec(
                select(VoiceProfile).where(VoiceProfile.character_id == character_id)
            ).all():
                session.delete(profile)
            for entrance in session.exec(
                select(StageEntranceExit).where(
                    StageEntranceExit.character_id == character_id
                )
            ).all():
                entrance.character_id = None
            for business in session.exec(
                select(StageBusiness).where(StageBusiness.character_id == character_id)
            ).all():
                business.character_id = None
            session.flush()
            character = session.get(Character, character_id)
            if character:
                session.delete(character)
            session.commit()

    # -- Voice Profiles --------------------------------------------------------

    def get_voice_profile(self, character_id: int) -> VoiceProfile | None:
        with Session(self._engine) as session:
            stmt = select(VoiceProfile).where(
                VoiceProfile.character_id == character_id,
            )
            return session.exec(stmt).first()

    def create_voice_profile(
        self,
        character_id: int,
        *,
        tone: str = "neutral",
        sentence_length: str = "medium",
        vocabulary_level: str = "standard",
        quirks: list[str] | None = None,
        punctuation_style: dict | None = None,
        dialogue_markers: list[str] | None = None,
    ) -> VoiceProfile:
        import json
        with Session(self._engine) as session:
            profile = VoiceProfile(
                character_id=character_id,
                tone=tone,
                sentence_length=sentence_length,
                vocabulary_level=vocabulary_level,
                quirks_json=json.dumps(quirks or []),
                punctuation_style_json=json.dumps(punctuation_style or {}),
                dialogue_markers_json=json.dumps(dialogue_markers or []),
            )
            session.add(profile)
            session.commit()
            session.refresh(profile)
            return profile

    def update_voice_profile(
        self,
        character_id: int,
        *,
        tone: str | None = None,
        sentence_length: str | None = None,
        vocabulary_level: str | None = None,
        quirks: list[str] | None = None,
        punctuation_style: dict | None = None,
        dialogue_markers: list[str] | None = None,
    ) -> VoiceProfile | None:
        import json
        from datetime import datetime, timezone
        with Session(self._engine) as session:
            stmt = select(VoiceProfile).where(
                VoiceProfile.character_id == character_id,
            )
            profile = session.exec(stmt).first()
            if profile is None:
                return None
            if tone is not None:
                profile.tone = tone
            if sentence_length is not None:
                profile.sentence_length = sentence_length
            if vocabulary_level is not None:
                profile.vocabulary_level = vocabulary_level
            if quirks is not None:
                profile.quirks_json = json.dumps(quirks)
            if punctuation_style is not None:
                profile.punctuation_style_json = json.dumps(punctuation_style)
            if dialogue_markers is not None:
                profile.dialogue_markers_json = json.dumps(dialogue_markers)
            profile.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(profile)
            return profile

    def delete_voice_profile(self, character_id: int) -> None:
        with Session(self._engine) as session:
            stmt = select(VoiceProfile).where(
                VoiceProfile.character_id == character_id,
            )
            profile = session.exec(stmt).first()
            if profile:
                session.delete(profile)
                session.commit()

    def get_voice_profile_data(self, character_id: int) -> dict | None:
        """Return deserialized voice profile as a plain dict, or None."""
        import json
        profile = self.get_voice_profile(character_id)
        if profile is None:
            return None
        return {
            "character_id": profile.character_id,
            "tone": profile.tone,
            "sentence_length": profile.sentence_length,
            "vocabulary_level": profile.vocabulary_level,
            "quirks": json.loads(profile.quirks_json),
            "punctuation_style": json.loads(profile.punctuation_style_json),
            "dialogue_markers": json.loads(profile.dialogue_markers_json),
            "last_updated": profile.updated_at.isoformat(),
        }

    def sync_voice_to_psyke(self, character_id: int, project_id: int) -> None:
        """Write a voice-profile summary into the character's PSYKE entry."""
        import json
        from logosforge.voice_learner import voice_profile_summary

        data = self.get_voice_profile_data(character_id)
        if data is None:
            return
        summary = voice_profile_summary(data)
        if not summary:
            return
        char = self.get_character_by_id(character_id)
        if char is None:
            return
        entry = self._find_character_psyke_entry(project_id, char.name)
        if entry is None:
            return
        details = self.get_psyke_entry_details(entry.id)
        details["voice"] = summary
        self.update_psyke_entry(
            entry.id,
            name=entry.name,
            entry_type=entry.entry_type,
            aliases=entry.aliases,
            notes=entry.notes,
            is_global=entry.is_global,
            details=details,
        )

    def _find_character_psyke_entry(
        self, project_id: int, character_name: str,
    ) -> PsykeEntry | None:
        with Session(self._engine) as session:
            stmt = (
                select(PsykeEntry)
                .where(PsykeEntry.project_id == project_id)
                .where(PsykeEntry.entry_type == "character")
                .where(PsykeEntry.name == character_name)
            )
            return session.exec(stmt).first()

    # -- Places --------------------------------------------------------------

    def get_place_by_id(self, place_id: int) -> Place | None:
        with Session(self._engine) as session:
            return session.get(Place, place_id)

    def get_all_places(self, project_id: int) -> list[Place]:
        with Session(self._engine) as session:
            stmt = select(Place).where(Place.project_id == project_id)
            return list(session.exec(stmt).all())

    def create_place(
        self, project_id: int, name: str, description: str = ""
    ) -> Place:
        with Session(self._engine) as session:
            place = Place(
                project_id=project_id, name=name, description=description
            )
            session.add(place)
            session.commit()
            session.refresh(place)
            return place

    def update_place(
        self, place_id: int, name: str, description: str = ""
    ) -> Place:
        with Session(self._engine) as session:
            place = session.get(Place, place_id)
            place.name = name
            place.description = description
            session.commit()
            session.refresh(place)
            return place

    def delete_place(self, place_id: int) -> None:
        with Session(self._engine) as session:
            # Remove scene links
            for link in session.exec(
                select(ScenePlaceLink).where(
                    ScenePlaceLink.place_id == place_id
                )
            ).all():
                session.delete(link)
            place = session.get(Place, place_id)
            if place:
                session.delete(place)
            session.commit()

    # -- Notes ---------------------------------------------------------------

    def get_note_by_id(self, note_id: int) -> Note | None:
        with Session(self._engine) as session:
            return session.get(Note, note_id)

    def get_all_notes(self, project_id: int) -> list[Note]:
        with Session(self._engine) as session:
            stmt = select(Note).where(Note.project_id == project_id)
            return list(session.exec(stmt).all())

    def create_note(
        self,
        project_id: int,
        title: str,
        content: str = "",
        tags: str = "",
        pinned: bool = False,
    ) -> Note:
        with Session(self._engine) as session:
            note = Note(
                project_id=project_id,
                title=title,
                content=content,
                tags=tags,
                pinned=pinned,
            )
            session.add(note)
            session.commit()
            session.refresh(note)
            return note

    def update_note(
        self,
        note_id: int,
        title: str,
        content: str = "",
        tags: str = "",
        pinned: bool = False,
    ) -> Note:
        with Session(self._engine) as session:
            note = session.get(Note, note_id)
            note.title = title
            note.content = content
            note.tags = tags
            note.pinned = pinned
            session.commit()
            session.refresh(note)
            return note

    def delete_note(self, note_id: int) -> None:
        with Session(self._engine) as session:
            note = session.get(Note, note_id)
            if note:
                stmt = select(NotePsykeLink).where(NotePsykeLink.note_id == note_id)
                for link in session.exec(stmt).all():
                    session.delete(link)
                stmt = select(NoteSceneLink).where(NoteSceneLink.note_id == note_id)
                for link in session.exec(stmt).all():
                    session.delete(link)
                stmt = select(NoteStructureLink).where(
                    NoteStructureLink.note_id == note_id,
                )
                for link in session.exec(stmt).all():
                    session.delete(link)
                # No ORM relationships declare delete ordering; flush every
                # child row before deleting the FK-protected parent Note.
                session.flush()
                session.delete(note)
            session.commit()

    # -- Inline comments -----------------------------------------------------

    def get_comment_by_id(self, comment_id: int) -> Comment | None:
        with Session(self._engine) as session:
            return session.get(Comment, comment_id)

    def get_all_comments(self, project_id: int) -> list[Comment]:
        with Session(self._engine) as session:
            stmt = (
                select(Comment)
                .where(Comment.project_id == project_id)
                .order_by(Comment.created_at, Comment.id)
            )
            return list(session.exec(stmt).all())

    def get_comment_replies(self, comment_id: int) -> list[CommentReply]:
        with Session(self._engine) as session:
            stmt = (
                select(CommentReply)
                .where(CommentReply.comment_id == comment_id)
                .order_by(CommentReply.sort_order, CommentReply.id)
            )
            return list(session.exec(stmt).all())

    def get_comment_reply_by_id(self, reply_id: int) -> CommentReply | None:
        with Session(self._engine) as session:
            return session.get(CommentReply, reply_id)

    def create_comment_with_replies(
        self,
        project_id: int,
        *,
        source_id: str = "",
        start_scene_id: int,
        start_field: str,
        from_offset: int,
        end_scene_id: int,
        end_field: str,
        to_offset: int,
        quote: str,
        prefix: str = "",
        suffix: str = "",
        body: str = "",
        resolved: bool = False,
        replies: list[dict] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> Comment:
        """Create a root and all nested replies in one transaction."""
        now = datetime.now(timezone.utc)
        with Session(self._engine) as session:
            comment = Comment(
                project_id=project_id,
                source_id=source_id,
                start_scene_id=start_scene_id,
                start_field=start_field,
                from_offset=from_offset,
                end_scene_id=end_scene_id,
                end_field=end_field,
                to_offset=to_offset,
                quote=quote,
                prefix=prefix,
                suffix=suffix,
                body=body,
                resolved=resolved,
                created_at=created_at or now,
                updated_at=updated_at or created_at or now,
            )
            session.add(comment)
            session.flush()
            for index, data in enumerate(replies or []):
                order = data.get("sort_order")
                session.add(CommentReply(
                    project_id=project_id,
                    comment_id=comment.id,
                    source_id=str(data.get("source_id") or ""),
                    body=str(data.get("body") or ""),
                    author=str(data.get("author") or "you"),
                    sort_order=index if order is None else int(order),
                    created_at=data.get("created_at") or now,
                ))
            session.commit()
            session.refresh(comment)
            return comment

    def update_comment(
        self,
        comment_id: int,
        *,
        anchor: dict | None = None,
        quote: object = _UNSET,
        body: object = _UNSET,
        resolved: object = _UNSET,
        expected_revision: str | None = None,
    ) -> Comment | None:
        with self.comment_write_lock(), Session(self._engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                comment = session.get(Comment, comment_id)
                if comment is None:
                    session.rollback()
                    return None
                replies = list(session.exec(
                    select(CommentReply)
                    .where(CommentReply.comment_id == comment_id)
                    .order_by(CommentReply.sort_order, CommentReply.id)
                ).all())
                if expected_revision is not None:
                    current_revision = comment_revision(comment, replies)
                    if not hmac.compare_digest(expected_revision, current_revision):
                        raise CommentRevisionConflict(
                            expected_revision, current_revision,
                        )
                if anchor is not None:
                    comment.start_scene_id = int(anchor["start_scene_id"])
                    comment.start_field = str(anchor["start_field"])
                    comment.from_offset = int(anchor["from_offset"])
                    comment.end_scene_id = int(anchor["end_scene_id"])
                    comment.end_field = str(anchor["end_field"])
                    comment.to_offset = int(anchor["to_offset"])
                    comment.prefix = str(anchor.get("prefix") or "")
                    comment.suffix = str(anchor.get("suffix") or "")
                if quote is not _UNSET:
                    comment.quote = str(quote or "")
                if body is not _UNSET:
                    comment.body = str(body or "")
                if resolved is not _UNSET:
                    comment.resolved = bool(resolved)
                comment.updated_at = datetime.now(timezone.utc)
                session.add(comment)
                session.commit()
                session.refresh(comment)
                return comment
            except Exception:
                session.rollback()
                raise

    def delete_comment(self, comment_id: int) -> bool:
        with self.comment_write_lock(), Session(self._engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                comment = session.get(Comment, comment_id)
                if comment is None:
                    session.rollback()
                    return False
                for reply in session.exec(
                    select(CommentReply).where(CommentReply.comment_id == comment_id)
                ).all():
                    session.delete(reply)
                session.flush()
                session.delete(comment)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise

    def add_comment_reply(
        self,
        project_id: int,
        comment_id: int,
        *,
        source_id: str = "",
        body: str = "",
        author: str = "you",
        sort_order: int | None = None,
        created_at: datetime | None = None,
        expected_revision: str | None = None,
    ) -> CommentReply:
        with self.comment_write_lock(), Session(self._engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                comment = session.get(Comment, comment_id)
                if comment is None or comment.project_id != project_id:
                    raise ValueError("comment does not belong to project")
                existing = list(session.exec(
                    select(CommentReply)
                    .where(CommentReply.comment_id == comment_id)
                    .order_by(CommentReply.sort_order, CommentReply.id)
                ).all())
                if expected_revision is not None:
                    current_revision = comment_revision(comment, existing)
                    if not hmac.compare_digest(expected_revision, current_revision):
                        raise CommentRevisionConflict(
                            expected_revision, current_revision,
                        )
                if sort_order is None:
                    sort_order = max(
                        (reply.sort_order for reply in existing), default=-1,
                    ) + 1
                reply = CommentReply(
                    project_id=project_id,
                    comment_id=comment_id,
                    source_id=source_id,
                    body=body,
                    author=author,
                    sort_order=sort_order,
                    created_at=created_at or datetime.now(timezone.utc),
                )
                session.add(reply)
                comment.updated_at = datetime.now(timezone.utc)
                session.add(comment)
                session.commit()
                session.refresh(reply)
                return reply
            except Exception:
                session.rollback()
                raise

    def delete_comment_reply(self, reply_id: int) -> bool:
        with self.comment_write_lock(), Session(self._engine) as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                reply = session.get(CommentReply, reply_id)
                if reply is None:
                    session.rollback()
                    return False
                comment = session.get(Comment, reply.comment_id)
                session.delete(reply)
                if comment is not None:
                    comment.updated_at = datetime.now(timezone.utc)
                    session.add(comment)
                session.commit()
                return True
            except Exception:
                session.rollback()
                raise

    # -- Note linking ----------------------------------------------------------

    def link_note_to_psyke(self, note_id: int, psyke_entry_id: int) -> None:
        with Session(self._engine) as session:
            existing = session.get(NotePsykeLink, (note_id, psyke_entry_id))
            if existing:
                return
            session.add(NotePsykeLink(note_id=note_id, psyke_entry_id=psyke_entry_id))
            session.commit()

    def unlink_note_from_psyke(self, note_id: int, psyke_entry_id: int) -> None:
        with Session(self._engine) as session:
            link = session.get(NotePsykeLink, (note_id, psyke_entry_id))
            if link:
                session.delete(link)
                session.commit()

    def get_note_psyke_links(self, note_id: int) -> list[int]:
        with Session(self._engine) as session:
            stmt = select(NotePsykeLink.psyke_entry_id).where(
                NotePsykeLink.note_id == note_id,
            )
            return list(session.exec(stmt).all())

    def get_psyke_note_links(self, psyke_entry_id: int) -> list[int]:
        with Session(self._engine) as session:
            stmt = select(NotePsykeLink.note_id).where(
                NotePsykeLink.psyke_entry_id == psyke_entry_id,
            )
            return list(session.exec(stmt).all())

    def link_note_to_scene(self, note_id: int, scene_id: int) -> None:
        with Session(self._engine) as session:
            existing = session.get(NoteSceneLink, (note_id, scene_id))
            if existing:
                return
            session.add(NoteSceneLink(note_id=note_id, scene_id=scene_id))
            session.commit()

    def unlink_note_from_scene(self, note_id: int, scene_id: int) -> None:
        with Session(self._engine) as session:
            link = session.get(NoteSceneLink, (note_id, scene_id))
            if link:
                session.delete(link)
                session.commit()

    def get_note_scene_links(self, note_id: int) -> list[int]:
        with Session(self._engine) as session:
            stmt = select(NoteSceneLink.scene_id).where(
                NoteSceneLink.note_id == note_id,
            )
            return list(session.exec(stmt).all())

    def get_scene_note_links(self, scene_id: int) -> list[int]:
        with Session(self._engine) as session:
            stmt = select(NoteSceneLink.note_id).where(
                NoteSceneLink.scene_id == scene_id,
            )
            return list(session.exec(stmt).all())

    # -- Note ↔ structure (Act / Chapter) links --------------------------------

    def add_note_structure_link(
        self, note_id: int, project_id: int, target_type: str, target_ref: str,
    ) -> None:
        """Link a note to an Act/Chapter (keyed by name). Idempotent."""
        if target_type not in ("act", "chapter") or not (target_ref or "").strip():
            return
        with Session(self._engine) as session:
            existing = session.exec(
                select(NoteStructureLink).where(
                    NoteStructureLink.note_id == note_id,
                    NoteStructureLink.target_type == target_type,
                    NoteStructureLink.target_ref == target_ref,
                )
            ).first()
            if existing:
                return
            session.add(NoteStructureLink(
                note_id=note_id, target_type=target_type,
                target_ref=target_ref, project_id=project_id,
            ))
            session.commit()

    def remove_note_structure_link(
        self, note_id: int, target_type: str, target_ref: str,
    ) -> None:
        with Session(self._engine) as session:
            for link in session.exec(
                select(NoteStructureLink).where(
                    NoteStructureLink.note_id == note_id,
                    NoteStructureLink.target_type == target_type,
                    NoteStructureLink.target_ref == target_ref,
                )
            ).all():
                session.delete(link)
            session.commit()

    def get_note_structure_links(self, note_id: int) -> list[tuple[str, str]]:
        """Return [(target_type, target_ref), ...] for a note (act/chapter)."""
        with Session(self._engine) as session:
            stmt = select(
                NoteStructureLink.target_type, NoteStructureLink.target_ref,
            ).where(NoteStructureLink.note_id == note_id)
            return [(t, r) for t, r in session.exec(stmt).all()]

    def get_structure_note_count(
        self, project_id: int, target_type: str, target_ref: str,
    ) -> int:
        """How many notes are linked to a given Act/Chapter in this project."""
        with Session(self._engine) as session:
            stmt = select(NoteStructureLink.note_id).where(
                NoteStructureLink.project_id == project_id,
                NoteStructureLink.target_type == target_type,
                NoteStructureLink.target_ref == target_ref,
            )
            return len(list(session.exec(stmt).all()))

    def get_scene_acts(self, project_id: int) -> list[str]:
        """Distinct non-empty Act labels for the project, in first-seen order."""
        seen: list[str] = []
        for scene in self.get_all_scenes(project_id):
            act = (scene.act or "").strip()
            if act and act not in seen:
                seen.append(act)
        return seen

    # -- Scenes --------------------------------------------------------------

    def get_scene_by_id(self, scene_id: int) -> Scene | None:
        with Session(self._engine) as session:
            return session.get(Scene, scene_id)

    def get_all_scenes(
        self,
        project_id: int,
        chapter: str | None = None,
        plotline: str | None = None,
        tag: str | None = None,
    ) -> list[Scene]:
        with Session(self._engine) as session:
            stmt = select(Scene).where(Scene.project_id == project_id)
            if chapter is not None:
                stmt = stmt.where(Scene.chapter == chapter)
            if plotline is not None:
                stmt = stmt.where(Scene.plotline == plotline)
            stmt = stmt.order_by(Scene.sort_order, Scene.id)
            scenes = list(session.exec(stmt).all())
            if tag is not None:
                tag_lower = tag.lower()
                scenes = [
                    s for s in scenes
                    if any(t.strip().lower() == tag_lower for t in s.tags.split(","))
                ]
            return scenes

    def read_story_structure_snapshot(
        self, project_id: int,
    ) -> StoryStructureReadSnapshot | None:
        """Read the compact structure inputs and revision atomically."""
        from logosforge import story_structure

        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                project = session.get(Project, project_id)
                if project is None:
                    return None
                scenes = list(session.exec(
                    select(Scene)
                    .where(Scene.project_id == project_id)
                    .order_by(Scene.sort_order, Scene.id)
                ).all())
                revision = story_structure.structure_revision_from_scenes(
                    project, scenes,
                )
                session.expunge_all()
                snapshot = StoryStructureReadSnapshot(
                    project=project,
                    scenes=tuple(scenes),
                    revision=revision,
                )
            finally:
                session.rollback()
        return snapshot

    def _timeline_snapshot_in_session(
        self, session: Session, project_id: int,
    ) -> TimelineReadSnapshot | None:
        """Build one Timeline snapshot without opening a nested Session."""
        from logosforge.timeline import parse_project_settings, timeline_revision

        project = session.get(Project, project_id)
        if project is None:
            return None
        scenes = list(session.exec(
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.sort_order, Scene.id)
        ).all())
        lanes = list(session.exec(
            select(TimelineLane)
            .where(TimelineLane.project_id == project_id)
            .order_by(TimelineLane.order_index, TimelineLane.id)
        ).all())
        links = list(session.exec(
            select(TimelineLink)
            .where(TimelineLink.project_id == project_id)
            .order_by(TimelineLink.id)
        ).all())
        structure_links = list(session.exec(
            select(TimelineStructureLink)
            .where(TimelineStructureLink.project_id == project_id)
            .order_by(TimelineStructureLink.id)
        ).all())
        scene_ids = {int(scene.id) for scene in scenes}
        link_pairs: set[tuple[int, int]] = set()
        for link in links:
            source_id = int(link.source_scene_id)
            target_id = int(link.target_scene_id)
            pair = tuple(sorted((source_id, target_id)))
            if (
                source_id == target_id
                or source_id not in scene_ids
                or target_id not in scene_ids
                or link.link_type not in TIMELINE_LINK_TYPES
                or pair in link_pairs
            ):
                raise TimelineStateCorrupt(
                    "Timeline link state violates project ownership or uniqueness"
                )
            link_pairs.add(pair)
        structure_identities: set[tuple[int, str, str]] = set()
        for link in structure_links:
            source_id = int(link.source_scene_id)
            target_type = link.target_type or ""
            target_ref = (link.target_ref or "").strip()
            identity = (source_id, target_type, target_ref)
            if (
                source_id not in scene_ids
                or target_type not in {"act", "chapter"}
                or not target_ref
                or identity in structure_identities
            ):
                raise TimelineStateCorrupt(
                    "Timeline structure-link state violates project ownership "
                    "or uniqueness"
                )
            structure_identities.add(identity)
        characters = list(session.exec(
            select(Character)
            .where(Character.project_id == project_id)
            .order_by(Character.id)
        ).all())
        character_names = {int(row.id): row.name for row in characters}
        states_by_scene: dict[int, list[tuple[int, str]]] = {
            int(scene.id): [] for scene in scenes
        }
        scene_ids = list(states_by_scene)
        if scene_ids:
            states = session.exec(
                select(SceneCharacterState)
                .where(SceneCharacterState.scene_id.in_(scene_ids))
                .order_by(
                    SceneCharacterState.scene_id,
                    SceneCharacterState.character_id,
                    SceneCharacterState.id,
                )
            ).all()
            for row in states:
                # Ignore corrupt/foreign character links at the API boundary.
                if row.character_id in character_names:
                    states_by_scene[int(row.scene_id)].append(
                        (int(row.character_id), row.state or "")
                    )
        settings = parse_project_settings(project.settings_json)
        return TimelineReadSnapshot(
            project=project,
            scenes=tuple(scenes),
            lanes=tuple(lanes),
            links=tuple(links),
            structure_links=tuple(structure_links),
            settings=settings,
            character_names_by_id=character_names,
            character_states_by_scene={
                scene_id: tuple(rows)
                for scene_id, rows in states_by_scene.items()
            },
            revision=timeline_revision(
                project,
                scenes,
                lanes,
                settings,
                links=links,
                structure_links=structure_links,
            ),
        )

    def read_timeline_snapshot(
        self, project_id: int,
    ) -> TimelineReadSnapshot | None:
        """Read every Timeline projection input in one SQLite snapshot."""
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                snapshot = self._timeline_snapshot_in_session(session, project_id)
                if snapshot is not None:
                    session.expunge_all()
            finally:
                session.rollback()
        return snapshot

    def get_timeline_command_receipt(
        self,
        project_id: int,
        idempotency_key: str,
    ) -> TimelineCommandReceiptData | None:
        """Return one completed Timeline command receipt, scoped to its project."""
        key_hash = _timeline_idempotency_key_hash(idempotency_key)
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                if session.get(Project, project_id) is None:
                    return None
                row = session.get(
                    TimelineCommandReceipt,
                    (int(project_id), key_hash),
                )
                if row is None:
                    return None
                receipt = _decode_timeline_command_receipt(row)
            finally:
                session.rollback()
        return receipt

    def update_plot_block(
        self,
        project_id: int,
        block_id: str,
        *,
        plotline: str | None = None,
        color_label: str | None = None,
    ) -> PlotBlockUpdateResult | None:
        """Atomically update a scene-derived Plot block and its persisted lane.

        Plot block ids are the trimmed ``Scene.plotline`` projection used by the
        API.  A matching persisted Timeline lane is name-keyed metadata for the
        same logical block, so a rename must move both in one transaction.  If
        the destination lane already exists, the blocks merge and its metadata
        wins; obsolete source lane rows are removed.

        Timeline settings contain Scene ids rather than lane names, so no JSON
        key migration is required.  The settings lock is still taken last to
        serialize this revision-changing write with Timeline commands.
        """

        def block_name(value: str | None) -> str:
            return (value or "").strip() or "Unassigned"

        requested_name = plotline.strip() if plotline is not None else None
        with (
            self.plot_write_lock(project_id),
            self.structure_write_lock(project_id),
            self._settings_lock,
        ):
            with Session(self._engine, expire_on_commit=False) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    members = list(session.exec(
                        select(Scene)
                        .where(Scene.project_id == project_id)
                        .order_by(Scene.sort_order, Scene.id)
                    ).all())
                    members = [
                        scene for scene in members
                        if block_name(scene.plotline) == block_id
                    ]
                    if not members:
                        session.rollback()
                        return None

                    lanes = list(session.exec(
                        select(TimelineLane)
                        .where(TimelineLane.project_id == project_id)
                        .order_by(TimelineLane.order_index, TimelineLane.id)
                    ).all())
                    source_lanes = [
                        lane for lane in lanes
                        if block_name(lane.name) == block_id
                    ]
                    changed_scene_ids: list[int] = []
                    lane_changed = False
                    removed_lane_ids: set[int] = set()
                    new_name = block_id

                    if requested_name is not None:
                        persisted_name = requested_name
                        if requested_name:
                            source_ids = {int(lane.id) for lane in source_lanes}
                            destination = next(
                                (
                                    lane for lane in lanes
                                    if int(lane.id) not in source_ids
                                    and (lane.name or "").strip().casefold()
                                    == requested_name.casefold()
                                ),
                                None,
                            )
                            if destination is not None:
                                # Timeline lane names are case-insensitively
                                # unique at the command boundary.  Preserve the
                                # destination's canonical spelling on a merge.
                                persisted_name = (destination.name or "").strip()
                                for lane in source_lanes:
                                    session.delete(lane)
                                    removed_lane_ids.add(int(lane.id))
                                    lane_changed = True
                            elif source_lanes:
                                primary, *duplicates = source_lanes
                                if primary.name != persisted_name:
                                    primary.name = persisted_name
                                    lane_changed = True
                                for lane in duplicates:
                                    session.delete(lane)
                                    removed_lane_ids.add(int(lane.id))
                                    lane_changed = True
                        else:
                            # An empty plotline means the virtual Unassigned
                            # block; it has no persisted TimelineLane row.
                            for lane in source_lanes:
                                session.delete(lane)
                                removed_lane_ids.add(int(lane.id))
                                lane_changed = True

                        for scene in members:
                            if (scene.plotline or "") != persisted_name:
                                scene.plotline = persisted_name
                                changed_scene_ids.append(int(scene.id))
                        new_name = block_name(persisted_name)

                    if color_label is not None:
                        normalized_color = color_label or ""
                        for scene in members:
                            if (scene.color_label or "") != normalized_color:
                                scene.color_label = normalized_color
                                changed_scene_ids.append(int(scene.id))

                    if removed_lane_ids:
                        remaining_lanes = [
                            lane for lane in lanes
                            if int(lane.id) not in removed_lane_ids
                        ]
                        for index, lane in enumerate(remaining_lanes):
                            lane.order_index = index

                    changed_scene_ids = list(dict.fromkeys(changed_scene_ids))
                    session.commit()
                    return PlotBlockUpdateResult(
                        scene_ids=tuple(int(scene.id) for scene in members),
                        changed_scene_ids=tuple(changed_scene_ids),
                        new_name=new_name,
                        timeline_changed=bool(changed_scene_ids or lane_changed),
                    )
                except Exception:
                    session.rollback()
                    raise

    def execute_timeline_command(
        self,
        project_id: int,
        *,
        kind: str,
        expected_revision: str,
        idempotency_key: str | None = None,
        **fields,
    ) -> TimelineCommandResult:
        """Apply one revision-guarded Timeline command atomically.

        The Scene lock (when one Scene is targeted), Plot topology lock,
        project structure lock, and settings lock are acquired in the same
        global order used by Scene PATCH and story-structure commands.
        ``BEGIN IMMEDIATE`` then precedes the guarded read, so revision
        comparison and every related row/settings mutation belong to one
        SQLite transaction.
        """
        from logosforge.timeline import project_timeline

        if kind not in _TIMELINE_COMMAND_KINDS:
            raise TimelineCommandError(f"Unsupported Timeline command: {kind!r}")

        key_hash: str | None = None
        request_digest: str | None = None
        if idempotency_key is not None:
            key_hash = _timeline_idempotency_key_hash(idempotency_key)
            request_digest = _timeline_command_request_digest(
                project_id,
                kind,
                expected_revision,
                fields,
            )

        scene_id = fields.get("scene_id")
        scene_guard = (
            self.scene_write_lock(int(scene_id))
            if kind in {"place_event", "remove_event"} and scene_id is not None
            else nullcontext()
        )

        # Scene -> Plot topology -> structure -> settings is the global order.
        with (
            scene_guard,
            self.plot_write_lock(project_id),
            self.structure_write_lock(project_id),
            self._settings_lock,
        ):
            with Session(self._engine, expire_on_commit=False) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    current = self._timeline_snapshot_in_session(session, project_id)
                    if current is None:
                        raise TimelineProjectNotFound(project_id)
                    if key_hash is not None:
                        receipt_row = session.get(
                            TimelineCommandReceipt,
                            (int(project_id), key_hash),
                        )
                        if receipt_row is not None:
                            receipt = _decode_timeline_command_receipt(receipt_row)
                            assert request_digest is not None
                            if not hmac.compare_digest(
                                receipt.request_digest,
                                request_digest,
                            ):
                                raise TimelineIdempotencyKeyConflict(
                                    "Idempotency-Key was already used for a "
                                    "different Timeline command"
                                )
                            session.expunge_all()
                            session.rollback()
                            return TimelineCommandResult(
                                snapshot=current,
                                changed=False,
                                affected_scene_ids=(),
                                replayed=True,
                                applied_revision=receipt.applied_revision,
                            )
                    if expected_revision != current.revision:
                        raise TimelineRevisionConflict(
                            expected_revision, current.revision,
                        )

                    project = current.project
                    scenes = list(current.scenes)
                    lanes = list(current.lanes)
                    links = list(current.links)
                    structure_links = list(current.structure_links)
                    settings = dict(current.settings)
                    affected_scene_ids: list[int] = []
                    affected_link_ids: list[int] = []
                    affected_structure_link_ids: list[int] = []
                    created_link_id: int | None = None
                    created_structure_link_id: int | None = None
                    # A successful exact no-op still needs a durable receipt.
                    # Isolate all command writes in a savepoint so that branch
                    # can discard incidental ORM/settings normalization while
                    # retaining the outer BEGIN IMMEDIATE for receipt commit.
                    command_savepoint = session.begin_nested()

                    def scene_or_error(value) -> Scene:
                        if isinstance(value, bool) or not isinstance(value, int):
                            raise TimelineCommandError("scene_id must be an integer")
                        scene = next((row for row in scenes if row.id == value), None)
                        if scene is None:
                            raise TimelineSceneNotFound(value)
                        return scene

                    def lane_or_error(value) -> TimelineLane:
                        if isinstance(value, bool) or not isinstance(value, int):
                            raise TimelineCommandError("lane_id must be an integer")
                        lane = next((row for row in lanes if row.id == value), None)
                        if lane is None:
                            raise TimelineLaneNotFound(value)
                        return lane

                    def link_or_error(value) -> TimelineLink:
                        if isinstance(value, bool) or not isinstance(value, int):
                            raise TimelineCommandError("link_id must be an integer")
                        link = next((row for row in links if row.id == value), None)
                        if link is None:
                            raise TimelineLinkNotFound(value)
                        return link

                    def structure_link_or_error(
                        value,
                    ) -> TimelineStructureLink:
                        if isinstance(value, bool) or not isinstance(value, int):
                            raise TimelineCommandError(
                                "structure_link_id must be an integer"
                            )
                        link = next(
                            (row for row in structure_links if row.id == value),
                            None,
                        )
                        if link is None:
                            raise TimelineStructureLinkNotFound(value)
                        return link

                    def checked_index(value, maximum: int, label: str) -> int:
                        if isinstance(value, bool) or not isinstance(value, int):
                            raise TimelineCommandError(f"{label} must be an integer")
                        if value < 0 or value > maximum:
                            raise TimelineCommandError(
                                f"{label} is outside the available range"
                            )
                        return value

                    def checked_name(value) -> str:
                        if not isinstance(value, str) or not value.strip():
                            raise TimelineCommandError("Lane name cannot be empty")
                        return value.strip()

                    def checked_text(
                        value,
                        label: str,
                        *,
                        maximum: int,
                        allow_empty: bool = True,
                        strip: bool = False,
                    ) -> str:
                        if not isinstance(value, str):
                            raise TimelineCommandError(f"{label} must be a string")
                        normalized = value.strip() if strip else value
                        if not allow_empty and not normalized:
                            raise TimelineCommandError(f"{label} cannot be empty")
                        if len(normalized) > maximum:
                            raise TimelineCommandError(
                                f"{label} cannot exceed {maximum} characters"
                            )
                        return normalized

                    def checked_link_type(value) -> str:
                        link_type = checked_text(
                            value, "link_type", maximum=100, allow_empty=False,
                        )
                        if link_type not in TIMELINE_LINK_TYPES:
                            raise TimelineCommandError(
                                "link_type is not a supported Timeline link type"
                            )
                        return link_type

                    def checked_structure_target(
                        target_type_value,
                        target_ref_value,
                    ) -> tuple[str, str]:
                        if target_type_value not in {"act", "chapter"}:
                            raise TimelineCommandError(
                                "target_type must be 'act' or 'chapter'"
                            )
                        target_ref = checked_text(
                            target_ref_value,
                            "target_ref",
                            maximum=500,
                            allow_empty=False,
                            strip=True,
                        )
                        existing_targets = {
                            str(getattr(scene, target_type_value, "") or "").strip()
                            for scene in scenes
                        }
                        existing_targets.discard("")
                        if target_ref not in existing_targets:
                            raise TimelineCommandError(
                                f"The target {target_type_value} does not exist"
                            )
                        return target_type_value, target_ref

                    def duplicate_lane(name: str, exclude_id: int | None = None):
                        key = name.casefold()
                        return next(
                            (
                                lane for lane in lanes
                                if lane.id != exclude_id
                                and (lane.name or "").strip().casefold() == key
                            ),
                            None,
                        )

                    def dense_lane_order(ordered_lanes: list[TimelineLane]) -> None:
                        for index, lane in enumerate(ordered_lanes):
                            lane.order_index = index

                    if kind == "create_lane":
                        name = checked_name(fields.get("name"))
                        if duplicate_lane(name) is not None:
                            raise TimelineCommandError(
                                f"A Timeline lane named {name!r} already exists"
                            )
                        lane = TimelineLane(
                            project_id=project_id,
                            name=name,
                            color_label=str(fields.get("color_label", "") or ""),
                            order_index=len(lanes),
                            collapsed=False,
                        )
                        session.add(lane)
                        session.flush()
                        insertion = fields.get("index")
                        if insertion is None:
                            insertion = len(lanes)
                        insertion = checked_index(
                            insertion, len(lanes), "Lane index",
                        )
                        lanes.insert(insertion, lane)
                        dense_lane_order(lanes)

                    elif kind == "update_lane":
                        lane = lane_or_error(fields.get("lane_id"))
                        updates = {
                            key for key in ("name", "color_label", "collapsed", "index")
                            if key in fields
                        }
                        if not updates:
                            raise TimelineCommandError(
                                "update_lane must change at least one field"
                            )
                        if "name" in updates:
                            name = checked_name(fields["name"])
                            if duplicate_lane(name, int(lane.id)) is not None:
                                raise TimelineCommandError(
                                    f"A Timeline lane named {name!r} already exists"
                                )
                            old_name = lane.name
                            if name != old_name:
                                lane.name = name
                                old_key = (old_name or "").strip()
                                for scene in scenes:
                                    if (scene.plotline or "").strip() == old_key:
                                        scene.plotline = name
                                        affected_scene_ids.append(int(scene.id))
                        if "color_label" in updates:
                            value = fields["color_label"]
                            if not isinstance(value, str):
                                raise TimelineCommandError(
                                    "color_label must be a string"
                                )
                            lane.color_label = value
                        if "collapsed" in updates:
                            value = fields["collapsed"]
                            if not isinstance(value, bool):
                                raise TimelineCommandError(
                                    "collapsed must be a boolean"
                                )
                            lane.collapsed = value
                        if "index" in updates:
                            ordered = [row for row in lanes if row.id != lane.id]
                            insertion = checked_index(
                                fields["index"], len(ordered), "Lane index",
                            )
                            ordered.insert(insertion, lane)
                            lanes = ordered
                        dense_lane_order(lanes)

                    elif kind == "delete_lane":
                        lane = lane_or_error(fields.get("lane_id"))
                        projection = project_timeline(scenes, settings)
                        explicit_ids = set(projection.explicit_event_ids)
                        lane_key = (lane.name or "").strip()
                        for scene in scenes:
                            if (scene.plotline or "").strip() == lane_key:
                                explicit_ids.add(int(scene.id))
                                scene.plotline = ""
                                affected_scene_ids.append(int(scene.id))
                        settings["timeline_event_ids"] = sorted(explicit_ids)
                        session.delete(lane)
                        lanes = [row for row in lanes if row.id != lane.id]
                        dense_lane_order(lanes)

                    elif kind == "place_event":
                        scene = scene_or_error(fields.get("scene_id"))
                        if "lane_id" not in fields:
                            raise TimelineCommandError(
                                "place_event requires lane_id (null means Unassigned)"
                            )
                        lane_id = fields.get("lane_id")
                        lane = None if lane_id is None else lane_or_error(lane_id)
                        projection = project_timeline(scenes, settings)
                        explicit_ids = set(projection.explicit_event_ids)
                        explicit_ids.add(int(scene.id))
                        settings["timeline_event_ids"] = sorted(explicit_ids)
                        desired_plotline = lane.name if lane is not None else ""
                        if (scene.plotline or "") != desired_plotline:
                            scene.plotline = desired_plotline
                            affected_scene_ids.append(int(scene.id))

                        after_membership = project_timeline(scenes, settings)
                        current_order = list(after_membership.effective_order)
                        insertion = fields.get("index")
                        if insertion is not None:
                            remaining = [
                                value for value in current_order
                                if value != int(scene.id)
                            ]
                            insertion = checked_index(
                                insertion, len(remaining), "Event index",
                            )
                            requested_order = list(remaining)
                            requested_order.insert(insertion, int(scene.id))
                            # Supplying an index is an explicit request to own
                            # Timeline order, even when that index currently
                            # matches the structural projection.
                            settings["timeline_order_mode"] = "custom"
                            settings["timeline_order"] = requested_order
                        elif after_membership.order_mode == "custom":
                            # Persist the effective appended order so subsequent
                            # additions cannot resurrect stale legacy positions.
                            settings["timeline_order"] = current_order

                    elif kind == "remove_event":
                        scene = scene_or_error(fields.get("scene_id"))
                        projection = project_timeline(scenes, settings)
                        explicit_ids = set(projection.explicit_event_ids)
                        explicit_ids.discard(int(scene.id))
                        settings["timeline_event_ids"] = sorted(explicit_ids)
                        settings["timeline_order"] = [
                            value for value in projection.stored_custom_order
                            if value != int(scene.id)
                        ]
                        if scene.plotline:
                            scene.plotline = ""
                            affected_scene_ids.append(int(scene.id))

                    elif kind == "set_order_mode":
                        order_mode = fields.get("mode")
                        if order_mode not in {"structural", "custom"}:
                            raise TimelineCommandError(
                                "mode must be 'structural' or 'custom'"
                            )
                        projection = project_timeline(scenes, settings)
                        settings["timeline_order_mode"] = order_mode
                        if order_mode == "custom" and projection.order_mode != "custom":
                            settings["timeline_order"] = list(
                                projection.effective_order
                            )

                    elif kind == "create_link":
                        source = scene_or_error(fields.get("source_scene_id"))
                        target = scene_or_error(fields.get("target_scene_id"))
                        if int(source.id) == int(target.id):
                            raise TimelineCommandError(
                                "A Timeline event cannot link to itself"
                            )
                        membership = set(
                            project_timeline(scenes, settings).event_ids
                        )
                        if (
                            int(source.id) not in membership
                            or int(target.id) not in membership
                        ):
                            raise TimelineCommandError(
                                "Both scenes must currently be Timeline events"
                            )
                        link_type = checked_link_type(
                            fields.get("link_type", "custom")
                        )
                        color_label = checked_text(
                            fields.get("color_label", "gray"),
                            "color_label",
                            maximum=100,
                        )
                        label = checked_text(
                            fields.get("label", ""),
                            "label",
                            maximum=500,
                        )
                        pair = frozenset((int(source.id), int(target.id)))
                        duplicate = next(
                            (
                                row for row in links
                                if frozenset((
                                    int(row.source_scene_id),
                                    int(row.target_scene_id),
                                )) == pair
                            ),
                            None,
                        )
                        if duplicate is None:
                            link = TimelineLink(
                                project_id=project_id,
                                source_scene_id=int(source.id),
                                target_scene_id=int(target.id),
                                link_type=link_type,
                                color_label=color_label,
                                label=label,
                            )
                            session.add(link)
                            session.flush()
                            assert link.id is not None
                            links.append(link)
                            created_link_id = int(link.id)
                            affected_link_ids.append(int(link.id))

                    elif kind == "update_link":
                        link = link_or_error(fields.get("link_id"))
                        updates = {
                            key for key in ("link_type", "color_label", "label")
                            if key in fields
                        }
                        if not updates:
                            raise TimelineCommandError(
                                "update_link must change at least one field"
                            )
                        changed_link = False
                        if "link_type" in updates:
                            value = checked_link_type(fields["link_type"])
                            if link.link_type != value:
                                link.link_type = value
                                changed_link = True
                        if "color_label" in updates:
                            value = checked_text(
                                fields["color_label"],
                                "color_label",
                                maximum=100,
                            )
                            if link.color_label != value:
                                link.color_label = value
                                changed_link = True
                        if "label" in updates:
                            value = checked_text(
                                fields["label"], "label", maximum=500,
                            )
                            if link.label != value:
                                link.label = value
                                changed_link = True
                        if changed_link:
                            affected_link_ids.append(int(link.id))

                    elif kind == "delete_link":
                        link = link_or_error(fields.get("link_id"))
                        affected_link_ids.append(int(link.id))
                        session.delete(link)
                        links = [row for row in links if row.id != link.id]

                    elif kind == "create_structure_link":
                        source = scene_or_error(fields.get("source_scene_id"))
                        if int(source.id) not in set(
                            project_timeline(scenes, settings).event_ids
                        ):
                            raise TimelineCommandError(
                                "The source scene must currently be a Timeline event"
                            )
                        target_type, target_ref = checked_structure_target(
                            fields.get("target_type"), fields.get("target_ref")
                        )
                        duplicate = next(
                            (
                                row for row in structure_links
                                if int(row.source_scene_id) == int(source.id)
                                and row.target_type == target_type
                                and row.target_ref == target_ref
                            ),
                            None,
                        )
                        if duplicate is None:
                            structure_link = TimelineStructureLink(
                                project_id=project_id,
                                source_scene_id=int(source.id),
                                target_type=target_type,
                                target_ref=target_ref,
                            )
                            session.add(structure_link)
                            session.flush()
                            assert structure_link.id is not None
                            structure_links.append(structure_link)
                            created_structure_link_id = int(structure_link.id)
                            affected_structure_link_ids.append(
                                int(structure_link.id)
                            )

                    elif kind == "update_structure_link":
                        structure_link = structure_link_or_error(
                            fields.get("structure_link_id")
                        )
                        updates = {
                            key for key in ("target_type", "target_ref")
                            if key in fields
                        }
                        if not updates:
                            raise TimelineCommandError(
                                "update_structure_link must change at least one field"
                            )
                        target_type, target_ref = checked_structure_target(
                            fields.get("target_type", structure_link.target_type),
                            fields.get("target_ref", structure_link.target_ref),
                        )
                        duplicate = next(
                            (
                                row for row in structure_links
                                if row.id != structure_link.id
                                and int(row.source_scene_id)
                                == int(structure_link.source_scene_id)
                                and row.target_type == target_type
                                and row.target_ref == target_ref
                            ),
                            None,
                        )
                        if duplicate is not None:
                            raise TimelineCommandError(
                                "That Timeline structure link already exists"
                            )
                        if (
                            structure_link.target_type != target_type
                            or structure_link.target_ref != target_ref
                        ):
                            structure_link.target_type = target_type
                            structure_link.target_ref = target_ref
                            affected_structure_link_ids.append(
                                int(structure_link.id)
                            )

                    elif kind == "delete_structure_link":
                        structure_link = structure_link_or_error(
                            fields.get("structure_link_id")
                        )
                        affected_structure_link_ids.append(int(structure_link.id))
                        session.delete(structure_link)
                        structure_links = [
                            row for row in structure_links
                            if row.id != structure_link.id
                        ]

                    project.settings_json = json.dumps(
                        settings, ensure_ascii=False, sort_keys=True,
                    )
                    session.flush()
                    updated = self._timeline_snapshot_in_session(session, project_id)
                    assert updated is not None
                    if updated.revision == current.revision:
                        command_savepoint.rollback()
                        stable = self._timeline_snapshot_in_session(
                            session, project_id,
                        )
                        assert stable is not None
                        if key_hash is not None:
                            assert request_digest is not None
                            session.add(TimelineCommandReceipt(
                                project_id=project_id,
                                idempotency_key_hash=key_hash,
                                request_digest=request_digest,
                                result_json=_timeline_receipt_result_json(
                                    kind=kind,
                                    expected_revision=expected_revision,
                                    applied_revision=stable.revision,
                                    original_changed=False,
                                    original_affected_scene_ids=(),
                                    original_affected_link_ids=(),
                                    original_affected_structure_link_ids=(),
                                    original_created_link_id=None,
                                    original_created_structure_link_id=None,
                                ),
                            ))
                            session.commit()
                            session.expunge_all()
                        else:
                            session.expunge_all()
                            session.rollback()
                        return TimelineCommandResult(
                            snapshot=stable,
                            changed=False,
                            applied_revision=stable.revision,
                        )

                    command_savepoint.commit()
                    unique_affected = tuple(dict.fromkeys(affected_scene_ids))
                    unique_affected_links = tuple(
                        dict.fromkeys(affected_link_ids)
                    )
                    unique_affected_structure_links = tuple(
                        dict.fromkeys(affected_structure_link_ids)
                    )
                    if key_hash is not None:
                        assert request_digest is not None
                        session.add(TimelineCommandReceipt(
                            project_id=project_id,
                            idempotency_key_hash=key_hash,
                            request_digest=request_digest,
                            result_json=_timeline_receipt_result_json(
                                kind=kind,
                                expected_revision=expected_revision,
                                applied_revision=updated.revision,
                                original_changed=True,
                                original_affected_scene_ids=unique_affected,
                                original_affected_link_ids=unique_affected_links,
                                original_affected_structure_link_ids=(
                                    unique_affected_structure_links
                                ),
                                original_created_link_id=created_link_id,
                                original_created_structure_link_id=(
                                    created_structure_link_id
                                ),
                            ),
                        ))
                    session.commit()
                    session.expunge_all()
                    return TimelineCommandResult(
                        snapshot=updated,
                        changed=True,
                        affected_scene_ids=unique_affected,
                        affected_link_ids=unique_affected_links,
                        affected_structure_link_ids=(
                            unique_affected_structure_links
                        ),
                        created_link_id=created_link_id,
                        created_structure_link_id=created_structure_link_id,
                        applied_revision=updated.revision,
                    )
                except Exception:
                    session.rollback()
                    raise

    def place_scene_in_structure(
        self,
        project_id: int,
        scene_id: int,
        *,
        expected_revision: str,
        act: str,
        chapter: str,
        index: int,
        episode_id: int | None = None,
        update_episode: bool = False,
    ) -> StoryStructurePlacementResult:
        """Atomically move/reparent one Scene in the canonical hierarchy.

        ``index`` is zero-based among destination siblings *after* removing the
        source.  For Series projects a sibling also shares the destination
        Episode.  A cross-parent destination must already contain a sibling;
        scene-derived empty Acts/Chapters have no stable ordering anchor.

        ``BEGIN IMMEDIATE`` is issued before every project, scene, revision, or
        destination read.  The optimistic comparison and the dense global
        ``sort_order`` rewrite therefore share one SQLite write transaction.
        """
        from logosforge import story_structure
        from logosforge.project_compat import (
            ENGINE_SERIES,
            get_project_narrative_engine,
        )

        if index < 0:
            raise StoryStructurePlacementError(
                "Destination index must be zero or greater"
            )

        target_act = story_structure.act_key((act or "").strip())
        target_chapter = story_structure.chapter_key((chapter or "").strip())

        # Match the HTTP Scene PATCH lock order: the source-scene lock is
        # outermost.  PATCH reads/merges/writes through multiple Sessions; this
        # prevents a stale PATCH that began first from restoring old parent
        # labels after a placement commits.
        with self.scene_write_lock(scene_id), self.structure_write_lock(project_id):
            with Session(self._engine, expire_on_commit=False) as session:
                # This must remain the first database statement.  In WAL mode
                # it prevents another writer from changing the structure after
                # the revision check but before our rewrite.
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    project = session.get(Project, project_id)
                    if project is None:
                        raise StoryStructureProjectNotFound(project_id)

                    raw_scenes = list(session.exec(
                        select(Scene)
                        .where(Scene.project_id == project_id)
                        .order_by(Scene.sort_order, Scene.id)
                    ).all())
                    current_revision = (
                        story_structure.structure_revision_from_scenes(
                            project, raw_scenes,
                        )
                    )
                    if expected_revision != current_revision:
                        raise StoryStructureRevisionConflict(
                            expected_revision, current_revision,
                        )

                    source = next(
                        (scene for scene in raw_scenes if scene.id == scene_id),
                        None,
                    )
                    if source is None:
                        # A foreign id is indistinguishable from a missing id.
                        raise StoryStructureSceneNotFound(scene_id)

                    mode = get_project_narrative_engine(project)
                    is_series = mode == ENGINE_SERIES
                    target_episode_id = (
                        episode_id if update_episode else source.episode_id
                    )

                    if update_episode and episode_id is not None and not is_series:
                        raise StoryStructurePlacementError(
                            "Only Series projects can place a scene in an Episode"
                        )

                    if is_series and target_episode_id is not None:
                        episode = session.get(Episode, target_episode_id)
                        season = (
                            session.get(Season, episode.season_id)
                            if episode is not None
                            else None
                        )
                        if (
                            episode is None
                            or episode.project_id != project_id
                            or season is None
                            or season.project_id != project_id
                        ):
                            raise StoryStructureEpisodeNotFound(target_episode_id)

                    current_tree = story_structure.build_structure_tree_from_scenes(
                        raw_scenes,
                    )
                    # Series containers are Episode-scoped even though the read
                    # DTO is a project-global label projection. Flattening that
                    # projection would merge equal labels across Episodes and
                    # overwrite each Episode's independent Act order. Use the
                    # persisted raw order as the placement workspace for Series.
                    current_order = (
                        list(raw_scenes)
                        if is_series
                        else [
                            scene
                            for _act, chapters in current_tree
                            for _chapter, scenes in chapters
                            for scene in scenes
                        ]
                    )

                    def parent_key(scene) -> tuple[str, str, int | None]:
                        return (
                            (scene.act or "").strip(),
                            (scene.chapter or "").strip(),
                            scene.episode_id if is_series else None,
                        )

                    source_parent = parent_key(source)
                    target_parent = (
                        target_act,
                        target_chapter,
                        target_episode_id if is_series else None,
                    )
                    current_siblings = [
                        scene for scene in current_order
                        if parent_key(scene) == source_parent
                    ]
                    current_index = next(
                        i for i, scene in enumerate(current_siblings)
                        if scene.id == scene_id
                    )

                    remaining = [
                        scene for scene in current_order if scene.id != scene_id
                    ]
                    target_siblings = [
                        scene for scene in remaining
                        if parent_key(scene) == target_parent
                    ]
                    if index > len(target_siblings):
                        raise StoryStructurePlacementError(
                            "Destination index is outside the sibling group"
                        )
                    if not target_siblings and source_parent != target_parent:
                        raise StoryStructurePlacementError(
                            "The destination Act/Chapter group does not exist"
                        )

                    same_episode = target_episode_id == source.episode_id
                    no_op = (
                        source_parent == target_parent
                        and same_episode
                        and current_index == index
                    )
                    if no_op:
                        session.expunge_all()
                        snapshot = StoryStructureReadSnapshot(
                            project=project,
                            scenes=tuple(raw_scenes),
                            revision=current_revision,
                        )
                        session.rollback()
                        return StoryStructurePlacementResult(
                            snapshot=snapshot,
                            changed=False,
                        )

                    # Locate insertion against immutable destination siblings.
                    # Non-Series projects then rebuild through canonical
                    # grouping; Series must preserve the raw cross-Episode order.
                    if index < len(target_siblings):
                        anchor = target_siblings[index]
                        insertion = remaining.index(anchor)
                    elif target_siblings:
                        anchor = target_siblings[-1]
                        insertion = remaining.index(anchor) + 1
                    else:
                        # The only valid empty group is the source's own sole-
                        # sibling group, which was already handled as a no-op.
                        raise StoryStructurePlacementError(
                            "The destination group has no ordering anchor"
                        )

                    source.act = target_act
                    source.chapter = target_chapter
                    if update_episode:
                        source.episode_id = episode_id
                    remaining.insert(insertion, source)

                    if is_series:
                        final_scenes = list(remaining)
                    else:
                        final_tree = (
                            story_structure.build_structure_tree_from_scenes(
                                remaining,
                            )
                        )
                        final_scenes = [
                            scene
                            for _act, chapters in final_tree
                            for _chapter, scenes in chapters
                            for scene in scenes
                        ]
                    for raw_index, scene in enumerate(final_scenes):
                        scene.sort_order = raw_index

                    session.flush()
                    revision = story_structure.structure_revision_from_scenes(
                        project, final_scenes,
                    )
                    session.commit()
                    session.expunge_all()
                    snapshot = StoryStructureReadSnapshot(
                        project=project,
                        scenes=tuple(final_scenes),
                        revision=revision,
                    )
                    return StoryStructurePlacementResult(
                        snapshot=snapshot,
                        changed=True,
                    )
                except Exception:
                    session.rollback()
                    raise

    def execute_story_structure_command(
        self,
        project_id: int,
        *,
        kind: str,
        expected_revision: str,
        act: str | None = None,
        chapter: str | None = None,
        new_name: str | None = None,
        title: str = "Untitled Scene",
        index: int | None = None,
        episode_id: int | None = None,
        scene_id: int | None = None,
    ) -> StoryStructureCommandResult:
        """Execute one canonical structure authoring command atomically.

        Every command uses the same project lock and starts ``BEGIN IMMEDIATE``
        before its first read.  The revision comparison, ownership checks,
        dependent-row cleanup, dense ordering rewrite, and returned snapshot
        are consequently one committed SQLite state.
        """
        import json

        from logosforge import story_structure
        from logosforge.project_compat import (
            ENGINE_SERIES,
            get_project_narrative_engine,
        )

        create_kinds = {"create_scene", "create_act", "create_chapter"}
        group_kinds = {
            "rename_act",
            "rename_chapter",
            "detach_act",
            "detach_chapter",
        }
        episode_scoped_kinds = create_kinds | group_kinds
        supported_kinds = episode_scoped_kinds | {
            "delete_scene",
            "repair_orphans",
        }
        if kind not in supported_kinds:
            raise StoryStructurePlacementError(
                f"Unknown story-structure command: {kind}"
            )

        def named_label(value: str | None, noun: str) -> str:
            label = (value or "").strip()
            if not label:
                raise StoryStructurePlacementError(f"{noun} name cannot be empty")
            if label in {
                story_structure.UNASSIGNED_ACT,
                story_structure.UNASSIGNED_CHAPTER,
            }:
                raise StoryStructurePlacementError(
                    f"{label!r} is reserved for detached scenes"
                )
            return label

        scene_guard = (
            self.scene_write_lock(scene_id)
            if kind == "delete_scene" and scene_id is not None
            else nullcontext()
        )
        settings_guard = (
            self._settings_lock
            if kind in group_kinds | {"delete_scene"}
            else nullcontext()
        )
        # Lock order is always Scene -> project structure -> project settings.
        # Settings-only writers take just the final lock, so a rename cannot
        # lose its name-keyed metadata migration to a concurrent settings PATCH.
        with (
            scene_guard,
            self.structure_write_lock(project_id),
            settings_guard,
        ):
            with Session(self._engine, expire_on_commit=False) as session:
                # Must be the first database statement. This serializes both
                # compare-and-write sequences and independent SQLite processes.
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    project = session.get(Project, project_id)
                    if project is None:
                        raise StoryStructureProjectNotFound(project_id)

                    raw_scenes = list(session.exec(
                        select(Scene)
                        .where(Scene.project_id == project_id)
                        .order_by(Scene.sort_order, Scene.id)
                    ).all())
                    current_revision = (
                        story_structure.structure_revision_from_scenes(
                            project, raw_scenes,
                        )
                    )
                    if expected_revision != current_revision:
                        raise StoryStructureRevisionConflict(
                            expected_revision, current_revision,
                        )

                    mode = get_project_narrative_engine(project)
                    is_series = mode == ENGINE_SERIES
                    chapter_level = mode == "novel"
                    requires_chapter = chapter_level or is_series
                    if episode_id is not None and kind not in episode_scoped_kinds:
                        raise StoryStructurePlacementError(
                            f"{kind} does not accept an Episode scope"
                        )
                    if kind in episode_scoped_kinds and episode_id is not None:
                        if not is_series:
                            raise StoryStructurePlacementError(
                                "Only Series story-structure commands accept an Episode"
                            )
                        episode = session.get(Episode, episode_id)
                        season = (
                            session.get(Season, episode.season_id)
                            if episode is not None
                            else None
                        )
                        if (
                            episode is None
                            or episode.project_id != project_id
                            or season is None
                            or season.project_id != project_id
                        ):
                            raise StoryStructureEpisodeNotFound(episode_id)

                    projection_tree = story_structure.build_structure_tree_from_scenes(
                        raw_scenes,
                    )
                    # Series hierarchy is Episode-scoped. The public structure DTO
                    # remains a global label projection, but using that projection
                    # as the write order would merge equal labels from independent
                    # Episodes. Preserve raw manuscript order for Series commands.
                    canonical_scenes = (
                        list(raw_scenes)
                        if is_series
                        else [
                            scene
                            for _act_name, chapter_rows in projection_tree
                            for _chapter_name, scene_rows in chapter_rows
                            for scene in scene_rows
                        ]
                    )
                    scope_scenes = (
                        [
                            scene for scene in canonical_scenes
                            if scene.episode_id == episode_id
                        ]
                        if is_series
                        else list(canonical_scenes)
                    )
                    scope_tree = story_structure.build_structure_tree_from_scenes(
                        scope_scenes,
                    )

                    def labels(scene: Scene) -> tuple[str, str]:
                        return (
                            (scene.act or "").strip(),
                            (scene.chapter or "").strip(),
                        )

                    def unchanged() -> StoryStructureCommandResult:
                        session.expunge_all()
                        snapshot = StoryStructureReadSnapshot(
                            project=project,
                            scenes=tuple(raw_scenes),
                            revision=current_revision,
                        )
                        session.rollback()
                        return StoryStructureCommandResult(
                            snapshot=snapshot,
                            changed=False,
                        )

                    working_scenes = list(canonical_scenes)
                    created_scene_id: int | None = None
                    affected_scene_ids: tuple[int, ...] = ()

                    def label_is_still_referenced(
                        target_type: str, target_ref: str,
                    ) -> bool:
                        if target_type == "act":
                            return any(
                                labels(scene)[0] == target_ref
                                for scene in working_scenes
                            )
                        return any(
                            labels(scene)[1] == target_ref
                            for scene in working_scenes
                        )

                    def migrate_name_keyed_metadata(
                        target_type: str,
                        old_ref: str,
                        replacement_ref: str | None,
                    ) -> None:
                        """Move/remove global label metadata once its old key is unused.

                        Series commands mutate one Episode, while summaries and
                        structure links predate Episode scoping and are keyed only
                        by the label. Keep the old global key while any Episode
                        still references it; once the last use is gone, migrate or
                        remove it in this same transaction.
                        """
                        if label_is_still_referenced(target_type, old_ref):
                            return

                        summary_key = f"{target_type}_summaries"
                        try:
                            settings = json.loads(project.settings_json or "{}")
                        except (json.JSONDecodeError, TypeError):
                            settings = {}
                        if not isinstance(settings, dict):
                            settings = {}
                        raw_summaries = settings.get(summary_key, {})
                        summaries = (
                            dict(raw_summaries)
                            if isinstance(raw_summaries, dict)
                            else {}
                        )
                        if old_ref in summaries:
                            old_summary = summaries.pop(old_ref)
                            # A pre-existing destination is already the global
                            # summary for that name; never clobber it.
                            if replacement_ref and replacement_ref not in summaries:
                                summaries[replacement_ref] = old_summary
                            settings[summary_key] = summaries
                            project.settings_json = json.dumps(settings)

                        note_links = list(session.exec(
                            select(NoteStructureLink).where(
                                NoteStructureLink.project_id == project_id,
                                NoteStructureLink.target_type == target_type,
                                NoteStructureLink.target_ref == old_ref,
                            )
                        ).all())
                        timeline_links = list(session.exec(
                            select(TimelineStructureLink).where(
                                TimelineStructureLink.project_id == project_id,
                                TimelineStructureLink.target_type == target_type,
                                TimelineStructureLink.target_ref == old_ref,
                            )
                        ).all())
                        if not replacement_ref:
                            for link in (*note_links, *timeline_links):
                                session.delete(link)
                            return

                        for link in note_links:
                            duplicate = session.exec(
                                select(NoteStructureLink).where(
                                    NoteStructureLink.project_id == project_id,
                                    NoteStructureLink.note_id == link.note_id,
                                    NoteStructureLink.target_type == target_type,
                                    NoteStructureLink.target_ref == replacement_ref,
                                )
                            ).first()
                            if duplicate is not None:
                                session.delete(link)
                            else:
                                link.target_ref = replacement_ref
                        for link in timeline_links:
                            duplicate = session.exec(
                                select(TimelineStructureLink).where(
                                    TimelineStructureLink.project_id == project_id,
                                    TimelineStructureLink.source_scene_id
                                    == link.source_scene_id,
                                    TimelineStructureLink.target_type == target_type,
                                    TimelineStructureLink.target_ref
                                    == replacement_ref,
                                )
                            ).first()
                            if duplicate is not None:
                                session.delete(link)
                            else:
                                link.target_ref = replacement_ref

                    if kind == "create_scene":
                        target_act = named_label(act, "Act")
                        target_chapter = (chapter or "").strip()
                        if target_chapter == story_structure.UNASSIGNED_CHAPTER:
                            target_chapter = ""
                        if requires_chapter:
                            target_chapter = named_label(target_chapter, "Chapter")
                        destination = [
                            scene for scene in scope_scenes
                            if labels(scene) == (target_act, target_chapter)
                        ]
                        if not destination:
                            if is_series:
                                message = (
                                    "The destination Act/Chapter group does not "
                                    "exist in the selected Episode; create its "
                                    "container first"
                                )
                            else:
                                message = (
                                    "The destination Act/Chapter group does not "
                                    "exist; create its container first"
                                )
                            raise StoryStructurePlacementError(
                                message
                            )
                        siblings = destination
                        assert index is not None
                        if index > len(siblings):
                            raise StoryStructurePlacementError(
                                "Destination index is outside the sibling group"
                            )
                        if index < len(siblings):
                            insertion = working_scenes.index(siblings[index])
                        else:
                            insertion = working_scenes.index(siblings[-1]) + 1
                        created = Scene(
                            project_id=project_id,
                            title=(title or "").strip() or "Untitled Scene",
                            act=target_act,
                            chapter=target_chapter,
                            episode_id=episode_id,
                            sort_order=len(raw_scenes),
                        )
                        session.add(created)
                        session.flush()
                        working_scenes.insert(insertion, created)
                        created_scene_id = int(created.id)
                        affected_scene_ids = (created_scene_id,)

                    elif kind == "create_act":
                        target_act = named_label(act, "Act")
                        target_chapter = (
                            story_structure.DEFAULT_CHAPTER
                            if chapter is None and requires_chapter
                            else (chapter or "").strip()
                        )
                        if target_chapter == story_structure.UNASSIGNED_CHAPTER:
                            target_chapter = ""
                        if requires_chapter:
                            target_chapter = named_label(target_chapter, "Chapter")
                        named_acts = [
                            (act_name, chapter_rows)
                            for act_name, chapter_rows in scope_tree
                            if act_name != story_structure.UNASSIGNED_ACT
                        ]
                        if any(act_name == target_act for act_name, _ in named_acts):
                            raise StoryStructurePlacementError(
                                f"Act {target_act!r} already exists"
                            )
                        assert index is not None
                        if index > len(named_acts):
                            raise StoryStructurePlacementError(
                                "Act index is outside the structure"
                            )
                        if index < len(named_acts):
                            insertion = working_scenes.index(
                                named_acts[index][1][0][1][0]
                            )
                        else:
                            unassigned = next(
                                (
                                    chapter_rows
                                    for act_name, chapter_rows in scope_tree
                                    if act_name == story_structure.UNASSIGNED_ACT
                                ),
                                None,
                            )
                            insertion = (
                                working_scenes.index(unassigned[0][1][0])
                                if unassigned
                                else (
                                    working_scenes.index(scope_scenes[-1]) + 1
                                    if scope_scenes
                                    else len(working_scenes)
                                )
                            )
                        created = Scene(
                            project_id=project_id,
                            title=(title or "").strip() or "Untitled Scene",
                            act=target_act,
                            chapter=target_chapter,
                            episode_id=episode_id,
                            sort_order=len(raw_scenes),
                        )
                        session.add(created)
                        session.flush()
                        working_scenes.insert(insertion, created)
                        created_scene_id = int(created.id)
                        affected_scene_ids = (created_scene_id,)

                    elif kind == "create_chapter":
                        if not requires_chapter:
                            raise StoryStructurePlacementError(
                                "Only Novel and Series projects have authorable "
                                "Chapters"
                            )
                        target_act = named_label(act, "Act")
                        target_chapter = named_label(chapter, "Chapter")
                        act_row = next(
                            (
                                chapter_rows
                                for act_name, chapter_rows in scope_tree
                                if act_name == target_act
                            ),
                            None,
                        )
                        if act_row is None:
                            raise StoryStructurePlacementError(
                                f"Act {target_act!r} does not exist"
                            )
                        named_chapters = [
                            (chapter_name, scene_rows)
                            for chapter_name, scene_rows in act_row
                            if chapter_name != story_structure.UNASSIGNED_CHAPTER
                        ]
                        if any(
                            chapter_name == target_chapter
                            for chapter_name, _ in named_chapters
                        ):
                            raise StoryStructurePlacementError(
                                f"Chapter {target_chapter!r} already exists in "
                                f"Act {target_act!r}"
                            )
                        assert index is not None
                        if index > len(named_chapters):
                            raise StoryStructurePlacementError(
                                "Chapter index is outside the Act"
                            )
                        if index < len(named_chapters):
                            insertion = working_scenes.index(
                                named_chapters[index][1][0]
                            )
                        else:
                            loose_chapter = next(
                                (
                                    scene_rows for chapter_name, scene_rows in act_row
                                    if chapter_name
                                    == story_structure.UNASSIGNED_CHAPTER
                                ),
                                None,
                            )
                            if loose_chapter:
                                insertion = working_scenes.index(loose_chapter[0])
                            else:
                                last_in_act = act_row[-1][1][-1]
                                insertion = working_scenes.index(last_in_act) + 1
                        created = Scene(
                            project_id=project_id,
                            title=(title or "").strip() or "Untitled Scene",
                            act=target_act,
                            chapter=target_chapter,
                            episode_id=episode_id,
                            sort_order=len(raw_scenes),
                        )
                        session.add(created)
                        session.flush()
                        working_scenes.insert(insertion, created)
                        created_scene_id = int(created.id)
                        affected_scene_ids = (created_scene_id,)

                    elif kind == "rename_act":
                        source_act = named_label(act, "Act")
                        replacement = named_label(new_name, "Act")
                        members = [
                            scene for scene in scope_scenes
                            if labels(scene)[0] == source_act
                        ]
                        if not members:
                            raise StoryStructurePlacementError(
                                f"Act {source_act!r} does not exist"
                            )
                        if replacement == source_act:
                            return unchanged()
                        if any(
                            labels(scene)[0] == replacement
                            for scene in scope_scenes
                        ):
                            raise StoryStructurePlacementError(
                                f"Act {replacement!r} already exists; rename "
                                "cannot merge Acts"
                            )
                        affected_scene_ids = tuple(int(scene.id) for scene in members)
                        for scene in members:
                            scene.act = replacement
                        migrate_name_keyed_metadata(
                            "act", source_act, replacement,
                        )

                    elif kind == "rename_chapter":
                        source_act = named_label(act, "Act")
                        source_chapter = named_label(chapter, "Chapter")
                        replacement = named_label(new_name, "Chapter")
                        members = [
                            scene for scene in scope_scenes
                            if labels(scene) == (source_act, source_chapter)
                        ]
                        if not members:
                            raise StoryStructurePlacementError(
                                f"Chapter {source_chapter!r} does not exist in "
                                f"Act {source_act!r}"
                            )
                        if replacement == source_chapter:
                            return unchanged()
                        if any(
                            labels(scene) == (source_act, replacement)
                            for scene in scope_scenes
                        ):
                            raise StoryStructurePlacementError(
                                f"Chapter {replacement!r} already exists in "
                                f"Act {source_act!r}; rename cannot merge Chapters"
                            )
                        affected_scene_ids = tuple(int(scene.id) for scene in members)
                        for scene in members:
                            scene.chapter = replacement
                        migrate_name_keyed_metadata(
                            "chapter", source_chapter, replacement,
                        )

                    elif kind == "detach_act":
                        source_act = named_label(act, "Act")
                        members = [
                            scene for scene in scope_scenes
                            if labels(scene)[0] == source_act
                        ]
                        if not members:
                            raise StoryStructurePlacementError(
                                f"Act {source_act!r} does not exist"
                            )
                        affected_scene_ids = tuple(int(scene.id) for scene in members)
                        for scene in members:
                            # Preserve Chapter labels and all manuscript fields.
                            scene.act = ""
                        migrate_name_keyed_metadata("act", source_act, None)

                    elif kind == "detach_chapter":
                        source_act = named_label(act, "Act")
                        source_chapter = named_label(chapter, "Chapter")
                        members = [
                            scene for scene in scope_scenes
                            if labels(scene) == (source_act, source_chapter)
                        ]
                        if not members:
                            raise StoryStructurePlacementError(
                                f"Chapter {source_chapter!r} does not exist in "
                                f"Act {source_act!r}"
                            )
                        affected_scene_ids = tuple(int(scene.id) for scene in members)
                        for scene in members:
                            # Preserve Act labels and all manuscript fields.
                            scene.chapter = ""
                        migrate_name_keyed_metadata(
                            "chapter", source_chapter, None,
                        )

                    elif kind == "delete_scene":
                        assert scene_id is not None
                        source = next(
                            (
                                scene for scene in canonical_scenes
                                if scene.id == scene_id
                            ),
                            None,
                        )
                        if source is None:
                            # Foreign ids are deliberately indistinguishable.
                            raise StoryStructureSceneNotFound(scene_id)
                        working_scenes.remove(source)
                        scrubbed_scene_ids = self._delete_scene_rows(
                            session, int(source.id),
                        )
                        affected_scene_ids = (
                            int(source.id),
                            *scrubbed_scene_ids,
                        )

                    elif kind == "repair_orphans":
                        repaired: list[int] = []
                        for scene in canonical_scenes:
                            scene_act, scene_chapter = labels(scene)
                            if scene_act and (scene_chapter or not requires_chapter):
                                continue
                            if not scene_act:
                                scene.act = story_structure.RECOVERED_ACT
                            if requires_chapter and not scene_chapter:
                                scene.chapter = story_structure.RECOVERED_CHAPTER
                            repaired.append(int(scene.id))
                        if not repaired:
                            return unchanged()
                        affected_scene_ids = tuple(repaired)

                    if is_series:
                        final_scenes = list(working_scenes)
                    else:
                        final_tree = (
                            story_structure.build_structure_tree_from_scenes(
                                working_scenes,
                            )
                        )
                        final_scenes = [
                            scene
                            for _act_name, chapter_rows in final_tree
                            for _chapter_name, scene_rows in chapter_rows
                            for scene in scene_rows
                        ]
                    for sort_order, scene in enumerate(final_scenes):
                        scene.sort_order = sort_order

                    session.flush()
                    revision = story_structure.structure_revision_from_scenes(
                        project, final_scenes,
                    )
                    session.commit()
                    session.expunge_all()
                    return StoryStructureCommandResult(
                        snapshot=StoryStructureReadSnapshot(
                            project=project,
                            scenes=tuple(final_scenes),
                            revision=revision,
                        ),
                        changed=True,
                        created_scene_id=created_scene_id,
                        affected_scene_ids=affected_scene_ids,
                    )
                except Exception:
                    session.rollback()
                    raise

    def read_manuscript_snapshot(
        self, project_id: int,
    ) -> ManuscriptReadSnapshot | None:
        """Read a project's full manuscript DTO inputs in one transaction.

        SQLite's legacy driver does not necessarily open a transaction for a
        plain ``SELECT``, so issue ``BEGIN`` explicitly before the first read.
        The scene rows, project mode, valid project-owned character/place ids,
        links, and character states therefore all come from one database
        snapshot even if another connection commits while serialization is in
        progress.  No ORM object returned here remains attached to the Session.
        """
        with Session(self._engine, expire_on_commit=False) as session:
            # ``session.connection()`` checks out the handle only after the
            # in-memory guard is held; BEGIN then creates a real SQLite read
            # transaction rather than only SQLAlchemy's logical transaction.
            session.connection().exec_driver_sql("BEGIN")
            try:
                project = session.get(Project, project_id)
                if project is None:
                    return None

                scenes = list(session.exec(
                    select(Scene)
                    .where(Scene.project_id == project_id)
                    .order_by(Scene.sort_order, Scene.id)
                ).all())
                scene_ids = [scene.id for scene in scenes]

                valid_character_ids = frozenset(int(value) for value in session.exec(
                    select(Character.id)
                    .where(Character.project_id == project_id)
                    .order_by(Character.id)
                ).all())
                valid_place_ids = frozenset(int(value) for value in session.exec(
                    select(Place.id)
                    .where(Place.project_id == project_id)
                    .order_by(Place.id)
                ).all())

                character_ids_by_scene: dict[int, list[int]] = {
                    int(scene_id): [] for scene_id in scene_ids
                }
                place_ids_by_scene: dict[int, list[int]] = {
                    int(scene_id): [] for scene_id in scene_ids
                }
                character_states_by_scene: dict[int, list[tuple[int, str]]] = {
                    int(scene_id): [] for scene_id in scene_ids
                }

                if scene_ids:
                    character_links = session.exec(
                        select(SceneCharacterLink)
                        .where(SceneCharacterLink.scene_id.in_(scene_ids))
                        .order_by(
                            SceneCharacterLink.scene_id,
                            SceneCharacterLink.character_id,
                        )
                    ).all()
                    for link in character_links:
                        character_ids_by_scene[link.scene_id].append(link.character_id)

                    place_links = session.exec(
                        select(ScenePlaceLink)
                        .where(ScenePlaceLink.scene_id.in_(scene_ids))
                        .order_by(ScenePlaceLink.scene_id, ScenePlaceLink.place_id)
                    ).all()
                    for link in place_links:
                        place_ids_by_scene[link.scene_id].append(link.place_id)

                    character_states = session.exec(
                        select(SceneCharacterState)
                        .where(SceneCharacterState.scene_id.in_(scene_ids))
                        .order_by(
                            SceneCharacterState.scene_id,
                            SceneCharacterState.character_id,
                            SceneCharacterState.id,
                        )
                    ).all()
                    for state in character_states:
                        character_states_by_scene[state.scene_id].append(
                            (state.character_id, state.state)
                        )

                # Detach loaded Project/Scene rows before the read transaction
                # is rolled back and the pooled connection is released.
                session.expunge_all()
                snapshot = ManuscriptReadSnapshot(
                    project=project,
                    scenes=tuple(scenes),
                    valid_character_ids=valid_character_ids,
                    valid_place_ids=valid_place_ids,
                    character_ids_by_scene={
                        scene_id: tuple(values)
                        for scene_id, values in character_ids_by_scene.items()
                    },
                    place_ids_by_scene={
                        scene_id: tuple(values)
                        for scene_id, values in place_ids_by_scene.items()
                    },
                    character_states_by_scene={
                        scene_id: tuple(values)
                        for scene_id, values in character_states_by_scene.items()
                    },
                )
            finally:
                session.rollback()
        return snapshot

    def get_scene_chapters(self, project_id: int) -> list[str]:
        """Distinct non-empty Chapter labels for the project, in first-seen
        order. Mirrors :meth:`get_scene_acts`: whitespace is stripped so
        " Ch1 " and "Ch1" don't surface as two separate chapters."""
        seen: list[str] = []
        for scene in self.get_all_scenes(project_id):
            chapter = (scene.chapter or "").strip()
            if chapter and chapter not in seen:
                seen.append(chapter)
        return seen

    def get_scene_plotlines(self, project_id: int) -> list[str]:
        with Session(self._engine) as session:
            stmt = (
                select(Scene.plotline)
                .where(Scene.project_id == project_id)
                .where(Scene.plotline != "")
                .distinct()
            )
            return list(session.exec(stmt).all())

    def get_scene_tags(self, project_id: int) -> list[str]:
        with Session(self._engine) as session:
            stmt = (
                select(Scene.tags)
                .where(Scene.project_id == project_id)
                .where(Scene.tags != "")
            )
            raw = list(session.exec(stmt).all())
        tags: set[str] = set()
        for csv_tags in raw:
            for tag in csv_tags.split(","):
                tag = tag.strip()
                if tag:
                    tags.add(tag)
        return sorted(tags)

    def create_scene(
        self,
        project_id: int,
        title: str,
        summary: str = "",
        synopsis: str = "",
        goal: str = "",
        conflict: str = "",
        outcome: str = "",
        beat: str = "",
        tags: str = "",
        act: str = "",
        content: str = "",
        chapter: str = "",
        plotline: str = "",
        color_label: str = "",
        # -- Screenplay-engine fields ------------------------------------
        slugline: str = "",
        location: str = "",
        interior_exterior: str = "",
        time_of_day: str = "",
        estimated_duration_minutes: int = 0,
        visual_objective: str = "",
        dramatic_turn: str = "",
        blocking_notes: str = "",
        subtext_notes: str = "",
        setup_payoff_links: str = "",
        montage_group: str = "",
        cinematic_pacing: str = "",
        continuity_notes: str = "",
        # -- Screenplay PSYKE extensions --------------------------------
        visible_conflict: str = "",
        hidden_conflict: str = "",
        emotional_turn: str = "",
        who_knows_what: str = "",
        physical_action: str = "",
        visual_symbolism: str = "",
        # -- Stage-script fields -----------------------------------------
        stage_location: str = "",
        set_description: str = "",
        scene_objective: str = "",
        entrance_exit_notes: str = "",
        prop_notes: str = "",
        cue_notes: str = "",
        offstage_events: str = "",
        audience_visibility_notes: str = "",
        performance_duration_minutes: int = 0,
        episode_id: int | None = None,
        character_ids: list[int] | None = None,
        place_ids: list[int] | None = None,
        character_states: list[tuple[int, str]] | None = None,
    ) -> Scene:
        # A non-empty plotline joins Plot/Timeline topology at creation time.
        # The Plot lock gives creation and block/lane renames one total order;
        # an explicit create that begins later may still intentionally recreate
        # a previously used plotline name.
        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            # Assign next sort_order
            from sqlalchemy import func

            max_order = session.exec(
                select(func.max(Scene.sort_order)).where(
                    Scene.project_id == project_id
                )
            ).one()
            next_order = (max_order or 0) + 1

            scene = Scene(
                project_id=project_id,
                title=title,
                summary=summary,
                synopsis=synopsis,
                goal=goal,
                conflict=conflict,
                outcome=outcome,
                beat=beat,
                tags=tags,
                act=act,
                content=content,
                chapter=chapter,
                plotline=plotline,
                color_label=color_label,
                slugline=slugline,
                location=location,
                interior_exterior=interior_exterior,
                time_of_day=time_of_day,
                estimated_duration_minutes=estimated_duration_minutes,
                visual_objective=visual_objective,
                dramatic_turn=dramatic_turn,
                blocking_notes=blocking_notes,
                subtext_notes=subtext_notes,
                setup_payoff_links=setup_payoff_links,
                montage_group=montage_group,
                cinematic_pacing=cinematic_pacing,
                continuity_notes=continuity_notes,
                visible_conflict=visible_conflict,
                hidden_conflict=hidden_conflict,
                emotional_turn=emotional_turn,
                who_knows_what=who_knows_what,
                physical_action=physical_action,
                visual_symbolism=visual_symbolism,
                stage_location=stage_location,
                set_description=set_description,
                scene_objective=scene_objective,
                entrance_exit_notes=entrance_exit_notes,
                prop_notes=prop_notes,
                cue_notes=cue_notes,
                offstage_events=offstage_events,
                audience_visibility_notes=audience_visibility_notes,
                performance_duration_minutes=performance_duration_minutes,
                episode_id=episode_id,
                sort_order=next_order,
            )
            session.add(scene)
            session.flush()

            for cid in character_ids or []:
                session.add(SceneCharacterLink(scene_id=scene.id, character_id=cid))
            for pid in place_ids or []:
                session.add(ScenePlaceLink(scene_id=scene.id, place_id=pid))
            for char_id, state in character_states or []:
                session.add(SceneCharacterState(
                    scene_id=scene.id, character_id=char_id, state=state,
                ))

            session.commit()
            session.refresh(scene)
            return scene

    @_scene_locked
    def update_scene(
        self,
        scene_id: int,
        title: str,
        summary: str = "",
        synopsis: str = "",
        goal: str = "",
        conflict: str = "",
        outcome: str = "",
        beat: str = "",
        tags: str = "",
        act: str | object = _UNSET,
        content: str = "",
        chapter: str | object = _UNSET,
        plotline: str = "",
        color_label: str | None = None,
        # -- Screenplay-engine fields (None = leave unchanged) -----------
        slugline: str | None = None,
        location: str | None = None,
        interior_exterior: str | None = None,
        time_of_day: str | None = None,
        estimated_duration_minutes: int | None = None,
        visual_objective: str | None = None,
        dramatic_turn: str | None = None,
        blocking_notes: str | None = None,
        subtext_notes: str | None = None,
        setup_payoff_links: str | None = None,
        montage_group: str | None = None,
        cinematic_pacing: str | None = None,
        continuity_notes: str | None = None,
        # -- Screenplay PSYKE extensions (None = leave unchanged) -------
        visible_conflict: str | None = None,
        hidden_conflict: str | None = None,
        emotional_turn: str | None = None,
        who_knows_what: str | None = None,
        physical_action: str | None = None,
        visual_symbolism: str | None = None,
        # -- Stage-script fields (None = leave unchanged) ---------------
        stage_location: str | None = None,
        set_description: str | None = None,
        scene_objective: str | None = None,
        entrance_exit_notes: str | None = None,
        prop_notes: str | None = None,
        cue_notes: str | None = None,
        offstage_events: str | None = None,
        audience_visibility_notes: str | None = None,
        performance_duration_minutes: int | None = None,
        character_ids: list[int] | None = None,
        place_ids: list[int] | None = None,
        character_states: list[tuple[int, str]] | None = None,
    ) -> Scene:
        # ``update_scene`` always writes the merged plotline value, even when
        # the caller changed only prose or metadata.  Resolve the owning project
        # while the decorator's Scene lock is held, then follow the global lock
        # order so a lane rename cannot be overwritten by a stale merge.
        with Session(self._engine) as read_session:
            current = read_session.get(Scene, scene_id)
            if current is None:
                return None
            project_id = current.project_id

        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            scene = session.get(Scene, scene_id)
            if scene is None or scene.project_id != project_id:
                return None
            scene.title = title
            scene.summary = summary
            scene.synopsis = synopsis
            scene.goal = goal
            scene.conflict = conflict
            scene.outcome = outcome
            scene.beat = beat
            scene.tags = tags
            if act is not _UNSET:
                scene.act = str(act)
            scene.content = content
            if chapter is not _UNSET:
                scene.chapter = str(chapter)
            scene.plotline = plotline
            if color_label is not None:
                scene.color_label = color_label
            if slugline is not None:
                scene.slugline = slugline
            if location is not None:
                scene.location = location
            if interior_exterior is not None:
                scene.interior_exterior = interior_exterior
            if time_of_day is not None:
                scene.time_of_day = time_of_day
            if estimated_duration_minutes is not None:
                scene.estimated_duration_minutes = estimated_duration_minutes
            if visual_objective is not None:
                scene.visual_objective = visual_objective
            if dramatic_turn is not None:
                scene.dramatic_turn = dramatic_turn
            if blocking_notes is not None:
                scene.blocking_notes = blocking_notes
            if subtext_notes is not None:
                scene.subtext_notes = subtext_notes
            if setup_payoff_links is not None:
                scene.setup_payoff_links = setup_payoff_links
            if montage_group is not None:
                scene.montage_group = montage_group
            if cinematic_pacing is not None:
                scene.cinematic_pacing = cinematic_pacing
            if continuity_notes is not None:
                scene.continuity_notes = continuity_notes
            if visible_conflict is not None:
                scene.visible_conflict = visible_conflict
            if hidden_conflict is not None:
                scene.hidden_conflict = hidden_conflict
            if emotional_turn is not None:
                scene.emotional_turn = emotional_turn
            if who_knows_what is not None:
                scene.who_knows_what = who_knows_what
            if physical_action is not None:
                scene.physical_action = physical_action
            if visual_symbolism is not None:
                scene.visual_symbolism = visual_symbolism
            if stage_location is not None:
                scene.stage_location = stage_location
            if set_description is not None:
                scene.set_description = set_description
            if scene_objective is not None:
                scene.scene_objective = scene_objective
            if entrance_exit_notes is not None:
                scene.entrance_exit_notes = entrance_exit_notes
            if prop_notes is not None:
                scene.prop_notes = prop_notes
            if cue_notes is not None:
                scene.cue_notes = cue_notes
            if offstage_events is not None:
                scene.offstage_events = offstage_events
            if audience_visibility_notes is not None:
                scene.audience_visibility_notes = audience_visibility_notes
            if performance_duration_minutes is not None:
                scene.performance_duration_minutes = performance_duration_minutes

            # Replace character links
            old_char_links = session.exec(
                select(SceneCharacterLink).where(
                    SceneCharacterLink.scene_id == scene_id
                )
            ).all()
            for link in old_char_links:
                session.delete(link)
            for cid in character_ids or []:
                session.add(SceneCharacterLink(scene_id=scene_id, character_id=cid))

            # Replace place links
            old_place_links = session.exec(
                select(ScenePlaceLink).where(
                    ScenePlaceLink.scene_id == scene_id
                )
            ).all()
            for link in old_place_links:
                session.delete(link)
            for pid in place_ids or []:
                session.add(ScenePlaceLink(scene_id=scene_id, place_id=pid))

            # Replace character states
            old_states = session.exec(
                select(SceneCharacterState).where(
                    SceneCharacterState.scene_id == scene_id
                )
            ).all()
            for st in old_states:
                session.delete(st)
            for char_id, state in character_states or []:
                session.add(SceneCharacterState(
                    scene_id=scene_id, character_id=char_id, state=state,
                ))

            session.commit()
            session.refresh(scene)
            return scene

    @staticmethod
    def _delete_scene_rows(session: Session, scene_id: int) -> tuple[int, ...]:
        """Delete one Scene and apply the legacy-safe association policy.

        The helper deliberately does not commit so guarded structure commands
        can delete the Scene, clean every dependent row, and rewrite canonical
        order in the same SQLite transaction.
        """
        scene = session.get(Scene, scene_id)
        if scene is None:
            return ()

        # Timeline membership and custom order are stored outside the Scene
        # table. SQLite may reuse a deleted maximum row id, so leaving either
        # reference behind could silently place an unrelated future Scene on
        # the Timeline. Preserve unrelated/legacy settings while removing
        # every numeric representation of this exact Scene id.
        project = session.get(Project, scene.project_id)
        if project is not None:
            try:
                settings = json.loads(project.settings_json or "{}")
            except (json.JSONDecodeError, TypeError):
                settings = {}
            if not isinstance(settings, dict):
                settings = {}

            settings_changed = False
            for key in ("timeline_event_ids", "timeline_order"):
                raw_ids = settings.get(key)
                if not isinstance(raw_ids, list):
                    continue
                scrubbed_ids = []
                for raw_id in raw_ids:
                    # ``bool`` is an ``int`` subclass in Python, but it is not
                    # a Scene id. Preserve it (and all other malformed legacy
                    # values) while removing only numeric representations of
                    # this exact id.
                    if isinstance(raw_id, bool):
                        scrubbed_ids.append(raw_id)
                        continue
                    try:
                        referenced_id = int(raw_id)
                    except (TypeError, ValueError):
                        scrubbed_ids.append(raw_id)
                        continue
                    if referenced_id != scene_id:
                        scrubbed_ids.append(raw_id)
                if scrubbed_ids != raw_ids:
                    settings[key] = scrubbed_ids
                    settings_changed = True
            if settings_changed:
                project.settings_json = json.dumps(
                    settings, ensure_ascii=False, sort_keys=True,
                )

        # setup_payoff_links is legacy CSV storage. Remove only exact numeric
        # tokens so deleting Scene 2 never corrupts Scene 20 or free-text notes.
        scrubbed_scene_ids: list[int] = []
        scene_ref = str(scene_id)
        for survivor in session.exec(
            select(Scene).where(
                Scene.project_id == scene.project_id,
                Scene.id != scene_id,
            ).order_by(Scene.id)
        ).all():
            raw_links = survivor.setup_payoff_links or ""
            tokens = raw_links.split(",")
            if not any(token.strip() == scene_ref for token in tokens):
                continue
            survivor.setup_payoff_links = ", ".join(
                token.strip()
                for token in tokens
                if token.strip() and token.strip() != scene_ref
            )
            scrubbed_scene_ids.append(int(survivor.id))

        for model in (
            SceneCharacterLink,
            ScenePlaceLink,
            SceneThemeLink,
            SceneCharacterState,
            NoteSceneLink,
        ):
            for row in session.exec(
                select(model).where(model.scene_id == scene_id)
            ).all():
                session.delete(row)

        # A range may begin or end in this scene. Inline-comment anchors are
        # meaningless once either edge disappears, so remove the whole thread.
        comments = list(session.exec(
            select(Comment).where(
                (Comment.start_scene_id == scene_id)
                | (Comment.end_scene_id == scene_id)
            )
        ).all())
        for comment in comments:
            for reply in session.exec(
                select(CommentReply).where(CommentReply.comment_id == comment.id)
            ).all():
                session.delete(reply)
        session.flush()
        for comment in comments:
            session.delete(comment)

        for link in session.exec(
            select(TimelineLink).where(
                (TimelineLink.source_scene_id == scene_id)
                | (TimelineLink.target_scene_id == scene_id)
            )
        ).all():
            session.delete(link)
        for link in session.exec(
            select(TimelineStructureLink).where(
                TimelineStructureLink.source_scene_id == scene_id
            )
        ).all():
            session.delete(link)

        # Story links can point at a Scene through the normalized numeric
        # columns, through their legacy typed string endpoint, or both. Detach
        # every exact reference while preserving any still-meaningful opposite
        # endpoint and the user's evidence/status metadata.
        story_links = session.exec(
            select(StoryLink).where(
                StoryLink.project_id == scene.project_id,
                (
                    (StoryLink.source_scene_id == scene_id)
                    | (StoryLink.target_scene_id == scene_id)
                    | (
                        (func.trim(func.lower(StoryLink.source_type)) == "scene")
                        & (func.trim(StoryLink.source_id) == scene_ref)
                    )
                    | (
                        (func.trim(func.lower(StoryLink.target_type)) == "scene")
                        & (func.trim(StoryLink.target_id) == scene_ref)
                    )
                ),
            )
        ).all()
        for link in story_links:
            changed = False
            if link.source_scene_id == scene_id:
                link.source_scene_id = None
                link.source_block_index = None
                changed = True
            if (
                (link.source_type or "").strip().lower() == "scene"
                and (link.source_id or "").strip() == scene_ref
            ):
                link.source_type = ""
                link.source_id = ""
                link.source_block_index = None
                changed = True
            if link.target_scene_id == scene_id:
                link.target_scene_id = None
                link.target_block_index = None
                changed = True
            if (
                (link.target_type or "").strip().lower() == "scene"
                and (link.target_id or "").strip() == scene_ref
            ):
                link.target_type = ""
                link.target_id = ""
                link.target_block_index = None
                changed = True
            if changed:
                link.updated_at = datetime.now(timezone.utc)

        # Scene-owned rows disappear with the scene.
        for model in (StageEntranceExit, StageCue, StageBusiness, StoryMemoryEntry):
            for row in session.exec(
                select(model).where(model.scene_id == scene_id)
            ).all():
                session.delete(row)

        # Historical/planning rows survive, but lose their optional anchor.
        for model in (
            PsykeProgression,
            ProductionSceneNumber,
            RevisionChange,
            RevisionDiffSnapshot,
            RevisionImpactReport,
            CanvasPlotNode,
            OutlineNode,
        ):
            for row in session.exec(
                select(model).where(model.scene_id == scene_id)
            ).all():
                row.scene_id = None

        session.flush()
        session.delete(scene)
        return tuple(scrubbed_scene_ids)

    @_scene_locked
    def delete_scene(self, scene_id: int) -> tuple[int, ...]:
        with Session(self._engine) as read_session:
            scene = read_session.get(Scene, scene_id)
            if scene is None:
                return ()
            project_id = scene.project_id
        # Lock order remains Scene (decorator) -> structure -> settings, matching
        # guarded structure and Timeline commands. Timeline settings cleanup and
        # Scene deletion then commit as one SQLite transaction.
        with (
            self.structure_write_lock(project_id),
            self._settings_lock,
            Session(self._engine) as session,
        ):
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                scene = session.get(Scene, scene_id)
                if scene is None or scene.project_id != project_id:
                    session.rollback()
                    return ()
                scrubbed_scene_ids = self._delete_scene_rows(session, scene_id)
                session.commit()
                return scrubbed_scene_ids
            except Exception:
                session.rollback()
                raise

    @_scene_locked
    def move_scene_up(self, scene_id: int) -> None:
        """Swap sort_order with the scene directly above (lower sort_order)."""
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return

            project_id = scene.project_id

        with self._structure_write_session(project_id) as session:
            scene = session.get(Scene, scene_id)
            if scene is None or scene.project_id != project_id:
                return
            # Find the scene just before this one
            stmt = (
                select(Scene)
                .where(Scene.project_id == scene.project_id)
                .where(
                    (Scene.sort_order < scene.sort_order)
                    | (
                        (Scene.sort_order == scene.sort_order)
                        & (Scene.id < scene.id)
                    )
                )
                .order_by(Scene.sort_order.desc(), Scene.id.desc())
            )
            prev_scene = session.exec(stmt).first()
            if prev_scene is None:
                return  # already first

            # Swap sort_order values
            scene.sort_order, prev_scene.sort_order = (
                prev_scene.sort_order,
                scene.sort_order,
            )
            session.commit()

    @_scene_locked
    def move_scene_down(self, scene_id: int) -> None:
        """Swap sort_order with the scene directly below (higher sort_order)."""
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return

            project_id = scene.project_id

        with self._structure_write_session(project_id) as session:
            scene = session.get(Scene, scene_id)
            if scene is None or scene.project_id != project_id:
                return
            # Find the scene just after this one
            stmt = (
                select(Scene)
                .where(Scene.project_id == scene.project_id)
                .where(
                    (Scene.sort_order > scene.sort_order)
                    | (
                        (Scene.sort_order == scene.sort_order)
                        & (Scene.id > scene.id)
                    )
                )
                .order_by(Scene.sort_order, Scene.id)
            )
            next_scene = session.exec(stmt).first()
            if next_scene is None:
                return  # already last

            # Swap sort_order values
            scene.sort_order, next_scene.sort_order = (
                next_scene.sort_order,
                scene.sort_order,
            )
            session.commit()

    @_scene_locked
    def update_scene_plotline(self, scene_id: int, plotline: str) -> None:
        with Session(self._engine) as read_session:
            current = read_session.get(Scene, scene_id)
            if current is None:
                return
            project_id = current.project_id
        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            scene = session.get(Scene, scene_id)
            if scene is None or scene.project_id != project_id:
                return
            scene.plotline = plotline
            session.commit()

    # -- Timeline lanes (plot/subplot rows) ---------------------------------

    def get_timeline_lanes(self, project_id: int) -> list["TimelineLane"]:
        with Session(self._engine) as session:
            stmt = (
                select(TimelineLane)
                .where(TimelineLane.project_id == project_id)
                .order_by(TimelineLane.order_index, TimelineLane.id)
            )
            return list(session.exec(stmt).all())

    def create_timeline_lane(
        self, project_id: int, name: str, color_label: str = "",
        order_index: int | None = None,
    ) -> "TimelineLane":
        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            if order_index is None:
                from sqlalchemy import func
                max_order = session.exec(
                    select(func.max(TimelineLane.order_index)).where(
                        TimelineLane.project_id == project_id
                    )
                ).one()
                order_index = (max_order or 0) + 1
            lane = TimelineLane(
                project_id=project_id, name=name,
                color_label=color_label or "", order_index=order_index,
            )
            session.add(lane)
            session.commit()
            session.refresh(lane)
            return lane

    def ensure_timeline_lanes(self, project_id: int) -> list["TimelineLane"]:
        """Materialise a lane row for each distinct ``Scene.plotline`` value that
        doesn't have one yet, so existing plot data appears as editable lanes.

        Lane membership is ``Scene.plotline`` matched case-sensitively, so
        plotlines differing only in case or surrounding whitespace ("Main" vs
        "main" vs " Main ") would otherwise fragment into separate lanes — and a
        scene whose plotline differs only in case from its lane name would
        render as "Unassigned". To keep one logical plotline on a single lane we
        dedupe case-insensitively (preferring the casing of any pre-existing
        lane, else the first scene value seen in narrative order) and re-point
        off-case / untrimmed ``Scene.plotline`` values to the canonical lane
        name. Returns the full ordered lane list. Additive, idempotent, and
        backward-compatible."""
        from sqlalchemy import func

        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            # Canonical display name per case-insensitive key. Existing lanes
            # win the casing so we never rename what the user already created.
            existing_lanes = session.exec(
                select(TimelineLane)
                .where(TimelineLane.project_id == project_id)
                .order_by(TimelineLane.order_index, TimelineLane.id)
            ).all()
            canonical: dict[str, str] = {}
            for ln in existing_lanes:
                canonical.setdefault((ln.name or "").strip().lower(), ln.name)
            next_order = session.exec(
                select(func.max(TimelineLane.order_index)).where(
                    TimelineLane.project_id == project_id
                )
            ).one() or 0
            # Walk scenes in narrative order: create one lane per new key and
            # re-point any plotline that doesn't exactly match its canonical name
            # so the off-case/untrimmed scene lands on the lane, not Unassigned.
            scenes = session.exec(
                select(Scene)
                .where(Scene.project_id == project_id)
                .where(Scene.plotline != "")
                .order_by(Scene.sort_order, Scene.id)
            ).all()
            for s in scenes:
                name = (s.plotline or "").strip()
                if not name:
                    continue
                key = name.lower()
                if key not in canonical:
                    next_order += 1
                    session.add(TimelineLane(
                        project_id=project_id, name=name,
                        color_label="", order_index=next_order,
                    ))
                    canonical[key] = name
                if s.plotline != canonical[key]:
                    s.plotline = canonical[key]   # heal off-case / untrimmed
            session.commit()
        return self.get_timeline_lanes(project_id)

    def rename_timeline_lane(self, lane_id: int, name: str) -> None:
        """Rename a lane and re-point its member scenes' plotline to match."""
        with Session(self._engine) as read_session:
            current = read_session.get(TimelineLane, lane_id)
            if current is None:
                return
            project_id = current.project_id
        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            lane = session.get(TimelineLane, lane_id)
            if lane is None or lane.project_id != project_id:
                return
            old_name = lane.name
            lane.name = name
            if old_name and old_name != name:
                scenes = session.exec(
                    select(Scene)
                    .where(Scene.project_id == lane.project_id)
                ).all()
                for s in scenes:
                    if (s.plotline or "").strip() == (old_name or "").strip():
                        s.plotline = name
            session.commit()

    def set_timeline_lane_color(self, lane_id: int, color_label: str) -> None:
        with Session(self._engine) as read_session:
            current = read_session.get(TimelineLane, lane_id)
            if current is None:
                return
            project_id = current.project_id
        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            lane = session.get(TimelineLane, lane_id)
            if lane is None or lane.project_id != project_id:
                return
            lane.color_label = color_label or ""
            session.commit()

    def set_timeline_lane_collapsed(self, lane_id: int, collapsed: bool) -> None:
        with Session(self._engine) as read_session:
            current = read_session.get(TimelineLane, lane_id)
            if current is None:
                return
            project_id = current.project_id
        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            lane = session.get(TimelineLane, lane_id)
            if lane is None or lane.project_id != project_id:
                return
            lane.collapsed = bool(collapsed)
            session.commit()

    def reorder_timeline_lane(self, lane_id: int, new_index: int) -> None:
        with Session(self._engine) as read_session:
            current = read_session.get(TimelineLane, lane_id)
            if current is None:
                return
            project_id = current.project_id
        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            lane = session.get(TimelineLane, lane_id)
            if lane is None or lane.project_id != project_id:
                return
            lanes = list(session.exec(
                select(TimelineLane)
                .where(TimelineLane.project_id == lane.project_id)
                .order_by(TimelineLane.order_index, TimelineLane.id)
            ).all())
            old = next((i for i, ln in enumerate(lanes) if ln.id == lane_id), None)
            if old is None:
                return
            moved = lanes.pop(old)
            new_index = max(0, min(new_index, len(lanes)))
            lanes.insert(new_index, moved)
            for i, ln in enumerate(lanes):
                ln.order_index = i
            session.commit()

    def delete_timeline_lane(self, lane_id: int) -> None:
        """Delete a lane row. Member scenes are NOT deleted — they are simply
        unassigned (plotline cleared) so no story content is ever lost."""
        with Session(self._engine) as read_session:
            current = read_session.get(TimelineLane, lane_id)
            if current is None:
                return
            project_id = current.project_id
        with (
            self.plot_write_lock(project_id),
            self._structure_write_session(project_id) as session,
        ):
            lane = session.get(TimelineLane, lane_id)
            if lane is None or lane.project_id != project_id:
                return
            scenes = session.exec(
                select(Scene)
                .where(Scene.project_id == lane.project_id)
            ).all()
            for s in scenes:
                if (s.plotline or "").strip() == (lane.name or "").strip():
                    s.plotline = ""
            session.delete(lane)
            session.commit()

    # -- Timeline event order (timeline-specific; independent of Outline) -----

    def get_timeline_order(self, project_id: int) -> list[int]:
        """Timeline-specific event order (scene ids). Stored in project settings
        so it is project-scoped and never touches Scene.sort_order — moving a
        Timeline block must NOT reorder the Outline/Manuscript."""
        settings = self.get_project_settings(project_id)
        raw = settings.get("timeline_order", [])
        if not isinstance(raw, list):
            return []
        out: list[int] = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out

    def set_timeline_order(self, project_id: int, ordered_ids: list[int]) -> None:
        settings = self.get_project_settings(project_id)
        settings["timeline_order"] = [int(x) for x in ordered_ids]
        self.save_project_settings(project_id, settings)

    def get_timeline_order_mode(self, project_id: int) -> str:
        """Timeline column-ordering mode: "structural" (default — follow the
        canonical Outline order) or "custom" (timeline-local order)."""
        mode = self.get_project_settings(project_id).get(
            "timeline_order_mode", "structural")
        return "custom" if mode == "custom" else "structural"

    def set_timeline_order_mode(self, project_id: int, mode: str) -> None:
        settings = self.get_project_settings(project_id)
        settings["timeline_order_mode"] = (
            "custom" if mode == "custom" else "structural")
        self.save_project_settings(project_id, settings)

    # -- Timeline event membership (which scenes are Timeline events) ---------
    # A scene is a Timeline event iff it has a lane (non-empty plotline) OR its
    # id is in this explicit set. The set keeps a scene as an event after its
    # lane is deleted (so it lands in "Unassigned Events" rather than vanishing),
    # without auto-promoting every Outline scene. Stored in project settings —
    # additive, project-scoped, no schema migration.

    def get_timeline_event_ids(self, project_id: int) -> set[int]:
        raw = self.get_project_settings(project_id).get("timeline_event_ids", [])
        out: set[int] = set()
        if isinstance(raw, list):
            for x in raw:
                try:
                    out.add(int(x))
                except (TypeError, ValueError):
                    continue
        return out

    def add_timeline_event(self, project_id: int, scene_id: int) -> None:
        ids = self.get_timeline_event_ids(project_id)
        if scene_id not in ids:
            ids.add(scene_id)
            settings = self.get_project_settings(project_id)
            settings["timeline_event_ids"] = sorted(ids)
            self.save_project_settings(project_id, settings)

    def remove_timeline_event(self, project_id: int, scene_id: int) -> None:
        ids = self.get_timeline_event_ids(project_id)
        if scene_id in ids:
            ids.discard(scene_id)
            settings = self.get_project_settings(project_id)
            settings["timeline_event_ids"] = sorted(ids)
            self.save_project_settings(project_id, settings)

    # -- Timeline links (event ↔ event) -------------------------------------

    def get_timeline_links(self, project_id: int) -> list["TimelineLink"]:
        with Session(self._engine) as session:
            stmt = (
                select(TimelineLink)
                .where(TimelineLink.project_id == project_id)
                .order_by(TimelineLink.id)
            )
            return list(session.exec(stmt).all())

    def add_timeline_link(
        self, project_id: int, source_scene_id: int, target_scene_id: int,
        color_label: str = "gray", link_type: str = "custom", label: str = "",
    ) -> "TimelineLink | None":
        """Create a link between two events. No-op (returns existing) if the
        pair already exists in either direction, or if source == target."""
        if source_scene_id == target_scene_id:
            return None
        with Session(self._engine) as session:
            existing = session.exec(
                select(TimelineLink)
                .where(TimelineLink.project_id == project_id)
                .where(TimelineLink.source_scene_id.in_(
                    [source_scene_id, target_scene_id]))
                .where(TimelineLink.target_scene_id.in_(
                    [source_scene_id, target_scene_id]))
            ).first()
            if existing is not None:
                return existing
            link = TimelineLink(
                project_id=project_id,
                source_scene_id=source_scene_id,
                target_scene_id=target_scene_id,
                color_label=color_label or "gray",
                link_type=link_type or "custom",
                label=label or "",
            )
            session.add(link)
            session.commit()
            session.refresh(link)
            return link

    def set_timeline_link_color(self, link_id: int, color_label: str) -> None:
        with Session(self._engine) as session:
            link = session.get(TimelineLink, link_id)
            if link is None:
                return
            link.color_label = color_label or "gray"
            session.commit()

    def set_timeline_link_type(self, link_id: int, link_type: str) -> None:
        with Session(self._engine) as session:
            link = session.get(TimelineLink, link_id)
            if link is None:
                return
            link.link_type = link_type or "custom"
            session.commit()

    def set_timeline_link_label(self, link_id: int, label: str) -> None:
        with Session(self._engine) as session:
            link = session.get(TimelineLink, link_id)
            if link is None:
                return
            link.label = label or ""
            session.commit()

    def remove_timeline_link(self, link_id: int) -> None:
        """Delete a link row only — never the linked scenes."""
        with Session(self._engine) as session:
            link = session.get(TimelineLink, link_id)
            if link is not None:
                session.delete(link)
                session.commit()

    # -- Timeline event ↔ structure (Act / Chapter) links --------------------

    def add_timeline_structure_link(
        self, project_id: int, source_scene_id: int,
        target_type: str, target_ref: str,
    ) -> "TimelineStructureLink | None":
        """Link a Timeline event (scene) to an Act/Chapter (by name). Idempotent."""
        if target_type not in ("act", "chapter") or not (target_ref or "").strip():
            return None
        with Session(self._engine) as session:
            existing = session.exec(
                select(TimelineStructureLink).where(
                    TimelineStructureLink.source_scene_id == source_scene_id,
                    TimelineStructureLink.target_type == target_type,
                    TimelineStructureLink.target_ref == target_ref,
                )
            ).first()
            if existing is not None:
                return existing
            link = TimelineStructureLink(
                project_id=project_id, source_scene_id=source_scene_id,
                target_type=target_type, target_ref=target_ref,
            )
            session.add(link)
            session.commit()
            session.refresh(link)
            return link

    def remove_timeline_structure_link(self, link_id: int) -> None:
        with Session(self._engine) as session:
            link = session.get(TimelineStructureLink, link_id)
            if link is not None:
                session.delete(link)
                session.commit()

    def get_timeline_structure_links(
        self, source_scene_id: int,
    ) -> list["TimelineStructureLink"]:
        with Session(self._engine) as session:
            stmt = select(TimelineStructureLink).where(
                TimelineStructureLink.source_scene_id == source_scene_id,
            ).order_by(TimelineStructureLink.id)
            return list(session.exec(stmt).all())

    def get_all_timeline_structure_links(
        self, project_id: int,
    ) -> list["TimelineStructureLink"]:
        with Session(self._engine) as session:
            stmt = select(TimelineStructureLink).where(
                TimelineStructureLink.project_id == project_id,
            ).order_by(TimelineStructureLink.id)
            return list(session.exec(stmt).all())

    # -- Canvas Plot (free visual board; project-owned, not scene-derived) ---

    def _canvas_plot_snapshot_in_session(
        self, session: Session, project_id: int,
    ) -> CanvasPlotReadSnapshot | None:
        """Build one Canvas Plot snapshot without opening a nested Session."""
        from logosforge.canvas_plot import canvas_plot_revision

        project = session.get(Project, project_id)
        if project is None:
            return None
        nodes = list(session.exec(
            select(CanvasPlotNode)
            .where(CanvasPlotNode.project_id == project_id)
            .order_by(CanvasPlotNode.sort_order, CanvasPlotNode.id)
        ).all())
        raw_links = list(session.exec(
            select(CanvasPlotLink)
            .where(CanvasPlotLink.project_id == project_id)
            .order_by(CanvasPlotLink.id)
        ).all())
        # Legacy direct CRUD did not validate endpoint ownership, self-links,
        # or duplicates. Canonical reads fail closed by exposing only the first
        # valid undirected pair and never returning a foreign node id.
        node_ids = {int(node.id) for node in nodes}
        links: list[CanvasPlotLink] = []
        seen_pairs: set[tuple[int, int]] = set()
        for link in raw_links:
            source_id = int(link.source_node_id)
            target_id = int(link.target_node_id)
            pair = tuple(sorted((source_id, target_id)))
            if (
                source_id == target_id
                or source_id not in node_ids
                or target_id not in node_ids
                or pair in seen_pairs
            ):
                continue
            seen_pairs.add(pair)
            links.append(link)
        frames = list(session.exec(
            select(CanvasPlotFrame)
            .where(CanvasPlotFrame.project_id == project_id)
            .order_by(CanvasPlotFrame.id)
        ).all())
        valid_scene_ids = frozenset(int(value) for value in session.exec(
            select(Scene.id).where(Scene.project_id == project_id)
        ).all())
        return CanvasPlotReadSnapshot(
            project=project,
            nodes=tuple(nodes),
            links=tuple(links),
            frames=tuple(frames),
            valid_scene_ids=valid_scene_ids,
            revision=canvas_plot_revision(
                project,
                nodes,
                links,
                frames,
                valid_scene_ids=valid_scene_ids,
            ),
        )

    def read_canvas_plot_snapshot(
        self, project_id: int,
    ) -> CanvasPlotReadSnapshot | None:
        """Read every canonical Canvas Plot row in one SQLite snapshot."""
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                snapshot = self._canvas_plot_snapshot_in_session(
                    session, project_id,
                )
                if snapshot is not None:
                    session.expunge_all()
            finally:
                session.rollback()
        return snapshot

    def get_canvas_plot_command_receipt(
        self,
        project_id: int,
        idempotency_key: str,
    ) -> CanvasPlotCommandReceiptData | None:
        """Return one completed Canvas command receipt in its project scope."""
        key_hash = _canvas_plot_idempotency_key_hash(idempotency_key)
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                if session.get(Project, project_id) is None:
                    return None
                row = session.get(
                    CanvasPlotCommandReceipt,
                    (int(project_id), key_hash),
                )
                if row is None:
                    return None
                receipt = _decode_canvas_plot_command_receipt(row)
            finally:
                session.rollback()
        return receipt

    def execute_canvas_plot_command(
        self,
        project_id: int,
        *,
        kind: str,
        expected_revision: str,
        idempotency_key: str | None = None,
        **fields,
    ) -> CanvasPlotCommandResult:
        """Apply one revision-guarded Canvas Plot mutation atomically."""
        if kind not in _CANVAS_PLOT_COMMAND_KINDS:
            raise CanvasPlotCommandError(
                f"Unsupported Canvas Plot command: {kind!r}"
            )

        allowed_fields = {
            "create_node": {
                "title", "body", "x", "y", "width", "height",
                "color_label", "group_label", "scene_id", "index",
            },
            "update_node": {
                "node_id", "title", "body", "x", "y", "width", "height",
                "color_label", "group_label", "scene_id", "index",
            },
            "delete_node": {"node_id"},
            "create_link": {
                "source_node_id", "target_node_id", "label", "color_label",
                "link_type",
            },
            "update_link": {"link_id", "label", "color_label", "link_type"},
            "delete_link": {"link_id"},
            "create_frame": {
                "title", "color_label", "x", "y", "width", "height",
            },
            "update_frame": {
                "frame_id", "title", "color_label", "x", "y", "width",
                "height",
            },
            "delete_frame": {"frame_id"},
        }
        unexpected = set(fields).difference(allowed_fields[kind])
        if unexpected:
            raise CanvasPlotCommandError(
                "Unexpected Canvas Plot command fields: "
                + ", ".join(sorted(unexpected))
            )

        key_hash: str | None = None
        request_digest: str | None = None
        if idempotency_key is not None:
            key_hash = _canvas_plot_idempotency_key_hash(idempotency_key)
            request_digest = _canvas_plot_command_request_digest(
                project_id,
                kind,
                expected_revision,
                fields,
            )

        with self.canvas_plot_write_lock(project_id):
            with Session(self._engine, expire_on_commit=False) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    current = self._canvas_plot_snapshot_in_session(
                        session, project_id,
                    )
                    if current is None:
                        raise CanvasPlotProjectNotFound(project_id)
                    if key_hash is not None:
                        receipt_row = session.get(
                            CanvasPlotCommandReceipt,
                            (int(project_id), key_hash),
                        )
                        if receipt_row is not None:
                            receipt = _decode_canvas_plot_command_receipt(
                                receipt_row,
                            )
                            assert request_digest is not None
                            if not hmac.compare_digest(
                                receipt.request_digest,
                                request_digest,
                            ):
                                raise CanvasPlotIdempotencyKeyConflict(
                                    "Idempotency-Key was already used for a "
                                    "different Canvas Plot command"
                                )
                            session.expunge_all()
                            session.rollback()
                            return CanvasPlotCommandResult(
                                snapshot=current,
                                changed=False,
                                replayed=True,
                                applied_revision=receipt.applied_revision,
                            )
                    if expected_revision != current.revision:
                        raise CanvasPlotRevisionConflict(
                            expected_revision, current.revision,
                        )

                    nodes = list(current.nodes)
                    links = list(current.links)
                    frames = list(current.frames)
                    changed = False
                    affected_node_ids: list[int] = []
                    affected_link_ids: list[int] = []
                    affected_frame_ids: list[int] = []
                    created_node_id: int | None = None
                    created_link_id: int | None = None
                    created_frame_id: int | None = None
                    # Even an exact no-op must commit its receipt. Keep command
                    # writes behind a savepoint so the no-op branch can discard
                    # incidental ORM normalization while retaining the outer
                    # transaction for the receipt insert.
                    command_savepoint = session.begin_nested()

                    def checked_id(value, label: str) -> int:
                        if (
                            isinstance(value, bool)
                            or not isinstance(value, int)
                            or value <= 0
                        ):
                            raise CanvasPlotCommandError(
                                f"{label} must be a positive integer"
                            )
                        return value

                    def checked_string(
                        value, label: str, maximum: int,
                    ) -> str:
                        if not isinstance(value, str):
                            raise CanvasPlotCommandError(
                                f"{label} must be a string"
                            )
                        if len(value) > maximum:
                            raise CanvasPlotCommandError(
                                f"{label} cannot exceed {maximum} characters"
                            )
                        return value

                    def checked_number(value, label: str) -> float:
                        if (
                            isinstance(value, bool)
                            or not isinstance(value, (int, float))
                            or not math.isfinite(float(value))
                        ):
                            raise CanvasPlotCommandError(
                                f"{label} must be a finite number"
                            )
                        return float(value)

                    def checked_dimension(value, label: str) -> float:
                        number = checked_number(value, label)
                        if number <= 0:
                            raise CanvasPlotCommandError(
                                f"{label} must be greater than zero"
                            )
                        return number

                    def checked_index(value, maximum: int) -> int:
                        if (
                            isinstance(value, bool)
                            or not isinstance(value, int)
                            or value < 0
                            or value > maximum
                        ):
                            raise CanvasPlotCommandError(
                                "Node index is outside the available range"
                            )
                        return value

                    def node_or_error(value) -> CanvasPlotNode:
                        node_id = checked_id(value, "node_id")
                        node = next(
                            (row for row in nodes if row.id == node_id), None,
                        )
                        if node is None:
                            raise CanvasPlotNodeNotFound(node_id)
                        return node

                    def link_or_error(value) -> CanvasPlotLink:
                        link_id = checked_id(value, "link_id")
                        link = next(
                            (row for row in links if row.id == link_id), None,
                        )
                        if link is None:
                            raise CanvasPlotLinkNotFound(link_id)
                        return link

                    def frame_or_error(value) -> CanvasPlotFrame:
                        frame_id = checked_id(value, "frame_id")
                        frame = next(
                            (row for row in frames if row.id == frame_id), None,
                        )
                        if frame is None:
                            raise CanvasPlotFrameNotFound(frame_id)
                        return frame

                    def scene_reference(value) -> int | None:
                        if value is None:
                            return None
                        scene_id = checked_id(value, "scene_id")
                        scene = session.get(Scene, scene_id)
                        if scene is None or scene.project_id != project_id:
                            raise CanvasPlotSceneNotFound(scene_id)
                        return scene_id

                    def dense_node_order(ordered: list[CanvasPlotNode]) -> None:
                        for index, row in enumerate(ordered):
                            row.sort_order = index

                    if kind == "create_node":
                        title = checked_string(
                            fields.get("title", ""), "title", 500,
                        )
                        body = checked_string(
                            fields.get("body", ""), "body", 100_000,
                        )
                        color_label = checked_string(
                            fields.get("color_label", ""), "color_label", 100,
                        )
                        group_label = checked_string(
                            fields.get("group_label", ""), "group_label", 500,
                        )
                        node = CanvasPlotNode(
                            project_id=project_id,
                            title=title,
                            body=body,
                            x=checked_number(fields.get("x", 0.0), "x"),
                            y=checked_number(fields.get("y", 0.0), "y"),
                            width=checked_dimension(
                                fields.get("width", 180.0), "width",
                            ),
                            height=checked_dimension(
                                fields.get("height", 110.0), "height",
                            ),
                            color_label=color_label,
                            group_label=group_label,
                            scene_id=scene_reference(fields.get("scene_id")),
                            sort_order=max(
                                (int(row.sort_order or 0) for row in nodes),
                                default=0,
                            ) + 1,
                        )
                        session.add(node)
                        session.flush()
                        requested_index = fields.get("index")
                        insertion = (
                            len(nodes)
                            if requested_index is None
                            else checked_index(requested_index, len(nodes))
                        )
                        nodes.insert(insertion, node)
                        dense_node_order(nodes)
                        created_node_id = int(node.id)
                        affected_node_ids.append(created_node_id)
                        changed = True

                    elif kind == "update_node":
                        node = node_or_error(fields.get("node_id"))
                        updates = set(fields).difference({"node_id"})
                        if not updates:
                            raise CanvasPlotCommandError(
                                "update_node must change at least one field"
                            )
                        string_fields = {
                            "title": 500,
                            "body": 100_000,
                            "color_label": 100,
                            "group_label": 500,
                        }
                        for field, maximum in string_fields.items():
                            if field in updates:
                                value = checked_string(
                                    fields[field], field, maximum,
                                )
                                if getattr(node, field) != value:
                                    setattr(node, field, value)
                                    changed = True
                        for field in ("x", "y"):
                            if field in updates:
                                value = checked_number(fields[field], field)
                                if getattr(node, field) != value:
                                    setattr(node, field, value)
                                    changed = True
                        for field in ("width", "height"):
                            if field in updates:
                                value = checked_dimension(fields[field], field)
                                if getattr(node, field) != value:
                                    setattr(node, field, value)
                                    changed = True
                        if "scene_id" in updates:
                            value = scene_reference(fields["scene_id"])
                            if node.scene_id != value:
                                node.scene_id = value
                                changed = True
                        if "index" in updates:
                            old_index = nodes.index(node)
                            new_index = checked_index(
                                fields["index"], len(nodes) - 1,
                            )
                            if old_index != new_index:
                                nodes.pop(old_index)
                                nodes.insert(new_index, node)
                                dense_node_order(nodes)
                                changed = True
                        if changed:
                            affected_node_ids.append(int(node.id))

                    elif kind == "delete_node":
                        node = node_or_error(fields.get("node_id"))
                        canonical_incident_ids = {
                            int(link.id) for link in links
                            if link.source_node_id == node.id
                            or link.target_node_id == node.id
                        }
                        all_incident = list(session.exec(
                            select(CanvasPlotLink)
                            .where(
                                (CanvasPlotLink.source_node_id == node.id)
                                | (CanvasPlotLink.target_node_id == node.id)
                            )
                        ).all())
                        # A malformed legacy row owned by another project must
                        # never be mutated through this project-scoped command.
                        # It also prevents the node delete under SQLite's FK
                        # policy, so reject before staging any local cleanup.
                        if any(
                            link.project_id != project_id
                            for link in all_incident
                        ):
                            raise CanvasPlotCommandError(
                                "Canvas Plot node cannot be deleted because "
                                "the board contains inconsistent link ownership"
                            )
                        incident = [
                            link for link in all_incident
                            if link.project_id == project_id
                        ]
                        for link in incident:
                            if int(link.id) in canonical_incident_ids:
                                affected_link_ids.append(int(link.id))
                            session.delete(link)
                        affected_node_ids.append(int(node.id))
                        session.delete(node)
                        nodes.remove(node)
                        dense_node_order(nodes)
                        changed = True

                    elif kind == "create_link":
                        source = node_or_error(fields.get("source_node_id"))
                        target = node_or_error(fields.get("target_node_id"))
                        if source.id == target.id:
                            raise CanvasPlotCommandError(
                                "A Canvas Plot node cannot link to itself"
                            )
                        duplicate = next((
                            row for row in links
                            if {
                                int(row.source_node_id), int(row.target_node_id),
                            } == {int(source.id), int(target.id)}
                        ), None)
                        if duplicate is None:
                            link = CanvasPlotLink(
                                project_id=project_id,
                                source_node_id=int(source.id),
                                target_node_id=int(target.id),
                                label=checked_string(
                                    fields.get("label", ""), "label", 500,
                                ),
                                color_label=checked_string(
                                    fields.get("color_label", "gray"),
                                    "color_label", 100,
                                ) or "gray",
                                link_type=checked_string(
                                    fields.get("link_type", ""),
                                    "link_type", 100,
                                ),
                            )
                            session.add(link)
                            session.flush()
                            created_link_id = int(link.id)
                            affected_link_ids.append(created_link_id)
                            changed = True

                    elif kind == "update_link":
                        link = link_or_error(fields.get("link_id"))
                        updates = set(fields).difference({"link_id"})
                        if not updates:
                            raise CanvasPlotCommandError(
                                "update_link must change at least one field"
                            )
                        for field, maximum in (
                            ("label", 500),
                            ("color_label", 100),
                            ("link_type", 100),
                        ):
                            if field in updates:
                                value = checked_string(
                                    fields[field], field, maximum,
                                )
                                if field == "color_label":
                                    value = value or "gray"
                                if getattr(link, field) != value:
                                    setattr(link, field, value)
                                    changed = True
                        if changed:
                            affected_link_ids.append(int(link.id))

                    elif kind == "delete_link":
                        link = link_or_error(fields.get("link_id"))
                        # One canonical link represents an undirected pair.
                        # Delete any hidden legacy duplicates in either direction.
                        duplicates = list(session.exec(
                            select(CanvasPlotLink)
                            .where(CanvasPlotLink.project_id == project_id)
                            .where(
                                (
                                    (CanvasPlotLink.source_node_id == link.source_node_id)
                                    & (CanvasPlotLink.target_node_id == link.target_node_id)
                                )
                                | (
                                    (CanvasPlotLink.source_node_id == link.target_node_id)
                                    & (CanvasPlotLink.target_node_id == link.source_node_id)
                                )
                            )
                        ).all())
                        for duplicate in duplicates:
                            affected_link_ids.append(int(duplicate.id))
                            session.delete(duplicate)
                        changed = True

                    elif kind == "create_frame":
                        frame = CanvasPlotFrame(
                            project_id=project_id,
                            title=checked_string(
                                fields.get("title", ""), "title", 500,
                            ),
                            color_label=checked_string(
                                fields.get("color_label", ""),
                                "color_label", 100,
                            ),
                            x=checked_number(fields.get("x", 0.0), "x"),
                            y=checked_number(fields.get("y", 0.0), "y"),
                            width=checked_dimension(
                                fields.get("width", 360.0), "width",
                            ),
                            height=checked_dimension(
                                fields.get("height", 260.0), "height",
                            ),
                        )
                        session.add(frame)
                        session.flush()
                        created_frame_id = int(frame.id)
                        affected_frame_ids.append(created_frame_id)
                        changed = True

                    elif kind == "update_frame":
                        frame = frame_or_error(fields.get("frame_id"))
                        updates = set(fields).difference({"frame_id"})
                        if not updates:
                            raise CanvasPlotCommandError(
                                "update_frame must change at least one field"
                            )
                        for field, maximum in (
                            ("title", 500), ("color_label", 100),
                        ):
                            if field in updates:
                                value = checked_string(
                                    fields[field], field, maximum,
                                )
                                if getattr(frame, field) != value:
                                    setattr(frame, field, value)
                                    changed = True
                        for field in ("x", "y"):
                            if field in updates:
                                value = checked_number(fields[field], field)
                                if getattr(frame, field) != value:
                                    setattr(frame, field, value)
                                    changed = True
                        for field in ("width", "height"):
                            if field in updates:
                                value = checked_dimension(fields[field], field)
                                if getattr(frame, field) != value:
                                    setattr(frame, field, value)
                                    changed = True
                        if changed:
                            affected_frame_ids.append(int(frame.id))

                    elif kind == "delete_frame":
                        frame = frame_or_error(fields.get("frame_id"))
                        affected_frame_ids.append(int(frame.id))
                        session.delete(frame)
                        changed = True

                    if not changed:
                        command_savepoint.rollback()
                        stable = self._canvas_plot_snapshot_in_session(
                            session, project_id,
                        )
                        assert stable is not None
                        if key_hash is not None:
                            assert request_digest is not None
                            session.add(CanvasPlotCommandReceipt(
                                project_id=project_id,
                                idempotency_key_hash=key_hash,
                                request_digest=request_digest,
                                result_json=_canvas_plot_receipt_result_json(
                                    kind=kind,
                                    expected_revision=expected_revision,
                                    applied_revision=stable.revision,
                                    original_changed=False,
                                    original_affected_node_ids=(),
                                    original_affected_link_ids=(),
                                    original_affected_frame_ids=(),
                                    original_created_node_id=None,
                                    original_created_link_id=None,
                                    original_created_frame_id=None,
                                ),
                            ))
                            session.commit()
                            session.expunge_all()
                        else:
                            session.expunge_all()
                            session.rollback()
                        return CanvasPlotCommandResult(
                            snapshot=stable,
                            changed=False,
                            applied_revision=stable.revision,
                        )

                    session.flush()
                    updated = self._canvas_plot_snapshot_in_session(
                        session, project_id,
                    )
                    assert updated is not None
                    if updated.revision == current.revision:
                        raise RuntimeError(
                            "Canvas Plot mutation did not advance its revision"
                        )
                    command_savepoint.commit()
                    unique_node_ids = tuple(dict.fromkeys(affected_node_ids))
                    unique_link_ids = tuple(dict.fromkeys(affected_link_ids))
                    unique_frame_ids = tuple(dict.fromkeys(affected_frame_ids))
                    if key_hash is not None:
                        assert request_digest is not None
                        session.add(CanvasPlotCommandReceipt(
                            project_id=project_id,
                            idempotency_key_hash=key_hash,
                            request_digest=request_digest,
                            result_json=_canvas_plot_receipt_result_json(
                                kind=kind,
                                expected_revision=expected_revision,
                                applied_revision=updated.revision,
                                original_changed=True,
                                original_affected_node_ids=unique_node_ids,
                                original_affected_link_ids=unique_link_ids,
                                original_affected_frame_ids=unique_frame_ids,
                                original_created_node_id=created_node_id,
                                original_created_link_id=created_link_id,
                                original_created_frame_id=created_frame_id,
                            ),
                        ))
                    session.commit()
                    session.expunge_all()
                    return CanvasPlotCommandResult(
                        snapshot=updated,
                        changed=True,
                        affected_node_ids=unique_node_ids,
                        affected_link_ids=unique_link_ids,
                        affected_frame_ids=unique_frame_ids,
                        created_node_id=created_node_id,
                        created_link_id=created_link_id,
                        created_frame_id=created_frame_id,
                        applied_revision=updated.revision,
                    )
                except Exception:
                    session.rollback()
                    raise

    def get_canvas_plot_nodes(self, project_id: int) -> list["CanvasPlotNode"]:
        with Session(self._engine) as session:
            stmt = (
                select(CanvasPlotNode)
                .where(CanvasPlotNode.project_id == project_id)
                .order_by(CanvasPlotNode.sort_order, CanvasPlotNode.id)
            )
            return list(session.exec(stmt).all())

    def create_canvas_plot_node(
        self, project_id: int, title: str = "", body: str = "",
        x: float = 0.0, y: float = 0.0, width: float = 180.0,
        height: float = 110.0, color_label: str = "", group_label: str = "",
        scene_id: int | None = None,
    ) -> "CanvasPlotNode":
        with Session(self._engine) as session:
            from sqlalchemy import func
            max_order = session.exec(
                select(func.max(CanvasPlotNode.sort_order)).where(
                    CanvasPlotNode.project_id == project_id
                )
            ).one()
            node = CanvasPlotNode(
                project_id=project_id, title=title, body=body, x=x, y=y,
                width=width, height=height, color_label=color_label or "",
                group_label=group_label or "", scene_id=scene_id,
                sort_order=(max_order or 0) + 1,
            )
            session.add(node)
            session.commit()
            session.refresh(node)
            return node

    def update_canvas_plot_node(
        self, node_id: int, *, title: str | None = None, body: str | None = None,
        x: float | None = None, y: float | None = None,
        width: float | None = None, height: float | None = None,
        color_label: str | None = None, group_label: str | None = None,
        sort_order: int | None = None,
    ) -> None:
        with Session(self._engine) as session:
            node = session.get(CanvasPlotNode, node_id)
            if node is None:
                return
            if title is not None:
                node.title = title
            if body is not None:
                node.body = body
            if x is not None:
                node.x = x
            if y is not None:
                node.y = y
            if width is not None:
                node.width = width
            if height is not None:
                node.height = height
            if color_label is not None:
                node.color_label = color_label
            if group_label is not None:
                node.group_label = group_label
            if sort_order is not None:
                node.sort_order = sort_order
            session.commit()

    def delete_canvas_plot_node(self, node_id: int) -> None:
        """Delete a block and any connection lines touching it (no orphans)."""
        with Session(self._engine) as session:
            node = session.get(CanvasPlotNode, node_id)
            if node is None:
                return
            links = session.exec(
                select(CanvasPlotLink).where(
                    (CanvasPlotLink.source_node_id == node_id)
                    | (CanvasPlotLink.target_node_id == node_id)
                )
            ).all()
            for link in links:
                session.delete(link)
            session.delete(node)
            session.commit()

    # -- Canvas Plot connection lines ---------------------------------------

    def get_canvas_plot_links(self, project_id: int) -> list["CanvasPlotLink"]:
        with Session(self._engine) as session:
            stmt = (
                select(CanvasPlotLink)
                .where(CanvasPlotLink.project_id == project_id)
                .order_by(CanvasPlotLink.id)
            )
            return list(session.exec(stmt).all())

    def add_canvas_plot_link(
        self, project_id: int, source_node_id: int, target_node_id: int,
        color_label: str = "gray", label: str = "", link_type: str = "",
    ) -> "CanvasPlotLink | None":
        """Connect two blocks. No-op (returns existing) if the pair already
        exists in either direction; rejects self-links."""
        if source_node_id == target_node_id:
            return None
        with Session(self._engine) as session:
            existing = session.exec(
                select(CanvasPlotLink)
                .where(CanvasPlotLink.project_id == project_id)
                .where(CanvasPlotLink.source_node_id.in_(
                    [source_node_id, target_node_id]))
                .where(CanvasPlotLink.target_node_id.in_(
                    [source_node_id, target_node_id]))
            ).first()
            if existing is not None:
                return existing
            link = CanvasPlotLink(
                project_id=project_id, source_node_id=source_node_id,
                target_node_id=target_node_id, color_label=color_label or "gray",
                label=label or "", link_type=link_type or "",
            )
            session.add(link)
            session.commit()
            session.refresh(link)
            return link

    def set_canvas_plot_link_color(self, link_id: int, color_label: str) -> None:
        with Session(self._engine) as session:
            link = session.get(CanvasPlotLink, link_id)
            if link is not None:
                link.color_label = color_label or "gray"
                session.commit()

    def set_canvas_plot_link_label(self, link_id: int, label: str) -> None:
        with Session(self._engine) as session:
            link = session.get(CanvasPlotLink, link_id)
            if link is not None:
                link.label = label or ""
                session.commit()

    def remove_canvas_plot_link(self, link_id: int) -> None:
        """Delete a connection line only — never the blocks it joined."""
        with Session(self._engine) as session:
            link = session.get(CanvasPlotLink, link_id)
            if link is not None:
                session.delete(link)
                session.commit()

    # -- Canvas Plot frames (lightweight visual groups) ---------------------

    def get_canvas_plot_frames(self, project_id: int) -> list["CanvasPlotFrame"]:
        with Session(self._engine) as session:
            stmt = (
                select(CanvasPlotFrame)
                .where(CanvasPlotFrame.project_id == project_id)
                .order_by(CanvasPlotFrame.id)
            )
            return list(session.exec(stmt).all())

    def create_canvas_plot_frame(
        self, project_id: int, title: str = "", color_label: str = "",
        x: float = 0.0, y: float = 0.0, width: float = 360.0, height: float = 260.0,
    ) -> "CanvasPlotFrame":
        with Session(self._engine) as session:
            frame = CanvasPlotFrame(
                project_id=project_id, title=title, color_label=color_label or "",
                x=x, y=y, width=width, height=height,
            )
            session.add(frame)
            session.commit()
            session.refresh(frame)
            return frame

    def update_canvas_plot_frame(
        self, frame_id: int, *, title: str | None = None,
        color_label: str | None = None, x: float | None = None,
        y: float | None = None, width: float | None = None,
        height: float | None = None,
    ) -> None:
        with Session(self._engine) as session:
            frame = session.get(CanvasPlotFrame, frame_id)
            if frame is None:
                return
            if title is not None:
                frame.title = title
            if color_label is not None:
                frame.color_label = color_label
            if x is not None:
                frame.x = x
            if y is not None:
                frame.y = y
            if width is not None:
                frame.width = width
            if height is not None:
                frame.height = height
            session.commit()

    def delete_canvas_plot_frame(self, frame_id: int) -> None:
        with Session(self._engine) as session:
            frame = session.get(CanvasPlotFrame, frame_id)
            if frame is not None:
                session.delete(frame)
                session.commit()

    # -- Chapters (Novel primary writing unit; additive, never touches scenes) --

    def get_chapters(self, project_id: int) -> list["Chapter"]:
        with Session(self._engine) as session:
            stmt = (
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.order_index, Chapter.id)
            )
            return list(session.exec(stmt).all())

    def get_chapter_by_id(self, chapter_id: int) -> "Chapter | None":
        with Session(self._engine) as session:
            return session.get(Chapter, chapter_id)

    def create_chapter(
        self, project_id: int, title: str = "", summary: str = "",
        content: str = "", act: str = "", order_index: int | None = None,
    ) -> "Chapter":
        with Session(self._engine) as session:
            if order_index is None:
                from sqlalchemy import func
                max_order = session.exec(
                    select(func.max(Chapter.order_index)).where(
                        Chapter.project_id == project_id
                    )
                ).one()
                order_index = (max_order or 0) + 1
            chapter = Chapter(
                project_id=project_id, title=title, summary=summary,
                content=content, act=act, order_index=order_index,
            )
            session.add(chapter)
            session.commit()
            session.refresh(chapter)
            return chapter

    def update_chapter(
        self, chapter_id: int, *, title: str | None = None,
        summary: str | None = None, content: str | None = None,
        act: str | None = None,
    ) -> None:
        with Session(self._engine) as session:
            chapter = session.get(Chapter, chapter_id)
            if chapter is None:
                return
            if title is not None:
                chapter.title = title
            if summary is not None:
                chapter.summary = summary
            if content is not None:
                chapter.content = content
            if act is not None:
                chapter.act = act
            from datetime import datetime, timezone
            chapter.updated_at = datetime.now(timezone.utc)
            session.commit()

    def reorder_chapter(self, chapter_id: int, new_index: int) -> None:
        with Session(self._engine) as session:
            chapter = session.get(Chapter, chapter_id)
            if chapter is None:
                return
            chapters = list(session.exec(
                select(Chapter)
                .where(Chapter.project_id == chapter.project_id)
                .order_by(Chapter.order_index, Chapter.id)
            ).all())
            old = next((i for i, c in enumerate(chapters) if c.id == chapter_id), None)
            if old is None:
                return
            moved = chapters.pop(old)
            new_index = max(0, min(new_index, len(chapters)))
            chapters.insert(new_index, moved)
            for i, c in enumerate(chapters):
                c.order_index = i
            session.commit()

    def delete_chapter(self, chapter_id: int) -> None:
        with Session(self._engine) as session:
            chapter = session.get(Chapter, chapter_id)
            if chapter is not None:
                session.delete(chapter)
                session.commit()

    def clear_canvas_plot(self, project_id: int) -> None:
        """Remove all Canvas Plot nodes for a project (project-scoped)."""
        with Session(self._engine) as session:
            nodes = session.exec(
                select(CanvasPlotNode).where(
                    CanvasPlotNode.project_id == project_id
                )
            ).all()
            for node in nodes:
                session.delete(node)
            session.commit()

    @_scene_locked
    def update_scene_content(self, scene_id: int, content: str) -> None:
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return
            scene.content = content
            session.commit()

    @_scene_locked
    def set_scene_offstage_events(self, scene_id: int, text: str) -> None:
        """Set just the stage 'offstage_events' field without blanking the rest of the
        scene (update_scene defaults-blanks unspecified fields)."""
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return
            scene.offstage_events = text
            session.commit()

    @_scene_locked
    def update_scene_synopsis(self, scene_id: int, synopsis: str) -> None:
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return
            scene.synopsis = synopsis
            session.commit()

    @_scene_locked
    def update_scene_color(self, scene_id: int, color_label: str) -> None:
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return
            scene.color_label = color_label or ""
            session.commit()

    @_scene_locked
    def update_scene_summary(self, scene_id: int, summary: str) -> None:
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return
            scene.summary = summary
            session.commit()

    @_scene_locked
    def update_scene_title(self, scene_id: int, title: str) -> None:
        """Targeted title update that preserves links (unlike full update_scene)."""
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return
            scene.title = title
            session.commit()

    @_scene_locked
    def update_scene_tags(self, scene_id: int, tags: str) -> None:
        """Targeted tags update that preserves links (unlike full update_scene)."""
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return
            scene.tags = tags or ""
            session.commit()

    @_scene_locked
    def reorder_scene(self, scene_id: int, new_index: int) -> None:
        """Move a scene to a new position (0-based) among all project scenes."""
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return

            project_id = scene.project_id

        with self._structure_write_session(project_id) as session:
            scene = session.get(Scene, scene_id)
            if scene is None or scene.project_id != project_id:
                return
            stmt = (
                select(Scene)
                .where(Scene.project_id == project_id)
                .order_by(Scene.sort_order, Scene.id)
            )
            all_scenes = list(session.exec(stmt).all())

            old_index = next(
                (i for i, s in enumerate(all_scenes) if s.id == scene_id), None
            )
            if old_index is None:
                return

            moved = all_scenes.pop(old_index)
            new_index = max(0, min(new_index, len(all_scenes)))
            all_scenes.insert(new_index, moved)

            for i, s in enumerate(all_scenes):
                s.sort_order = i
            session.commit()

    @_scene_locked
    def set_scene_structure(
        self, scene_id: int, act: str, chapter: str,
    ) -> None:
        """Set a scene's Act/Chapter labels only.

        Touches structural labels exclusively — never the manuscript body,
        summary, tags, plotline, links, or sort order. Used by the Outline
        planner when a card is moved between Acts/Chapters.
        """
        with Session(self._engine) as read_session:
            scene = read_session.get(Scene, scene_id)
            if scene is None:
                return
            project_id = scene.project_id
        with self._structure_write_session(project_id) as session:
            scene = session.get(Scene, scene_id)
            if scene is None or scene.project_id != project_id:
                return
            scene.act = act or ""
            scene.chapter = chapter or ""
            session.commit()

    @_scene_locked
    def set_scene_episode(self, scene_id: int, episode_id: int | None) -> None:
        """Assign (or clear, with ``None``) a scene's Series Episode link.

        Touches only ``episode_id`` — never the body, summary, labels, links or
        sort order. Used by the Series Navigator to move a scene between
        Episodes (and by the legacy-series migration). ``None`` unassigns it.
        """
        with Session(self._engine) as read_session:
            scene = read_session.get(Scene, scene_id)
            if scene is None:
                return
            project_id = scene.project_id
        with self._structure_write_session(project_id) as session:
            scene = session.get(Scene, scene_id)
            if scene is None or scene.project_id != project_id:
                return
            scene.episode_id = episode_id
            session.commit()

    @_scene_locked
    def set_scene_gn_page_start(self, scene_id: int,
                                start: int | None) -> None:
        """Pin (or clear, with ``None``) a Graphic Novel scene's act-wide
        start page (``gn_page_start``). Touches only that offset — never the
        body, labels, links or sort order. ``None`` returns the scene to the
        auto-chained page layout."""
        with Session(self._engine) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return
            scene.gn_page_start = start
            session.commit()

    def get_scenes_for_episode(self, episode_id: int) -> list[Scene]:
        """Scenes linked to one Episode, in canonical ``sort_order``."""
        with Session(self._engine) as session:
            stmt = (
                select(Scene)
                .where(Scene.episode_id == episode_id)
                .order_by(Scene.sort_order, Scene.id)
            )
            return list(session.exec(stmt).all())

    def get_unassigned_series_scenes(self, project_id: int) -> list[Scene]:
        """Project scenes with no Episode link (``episode_id`` IS NULL).

        In a Series project these are scenes not yet placed in any Episode; the
        Navigator surfaces them in an "Unassigned Scenes" bucket so a body is
        never hidden. (In non-Series projects every scene is unassigned — this
        is only meaningful in Series context.)
        """
        with Session(self._engine) as session:
            stmt = (
                select(Scene)
                .where(Scene.project_id == project_id)
                .where(Scene.episode_id.is_(None))
                .order_by(Scene.sort_order, Scene.id)
            )
            return list(session.exec(stmt).all())

    def reorder_scenes(
        self, project_id: int, ordered_scene_ids: list[int],
    ) -> None:
        """Assign ``sort_order`` from the position of each id in
        *ordered_scene_ids*. Any project scene not listed keeps its relative
        order *after* the listed ones (defensive against partial input). Only
        ``sort_order`` is written — ids, bodies and labels are untouched.
        """
        with self._structure_write_session(project_id) as session:
            stmt = (
                select(Scene)
                .where(Scene.project_id == project_id)
                .order_by(Scene.sort_order, Scene.id)
            )
            all_scenes = list(session.exec(stmt).all())
            by_id = {s.id: s for s in all_scenes}
            ordered: list[Scene] = []
            seen: set[int] = set()
            for sid in ordered_scene_ids:
                s = by_id.get(sid)
                if s is not None and s.id not in seen:
                    ordered.append(s)
                    seen.add(s.id)
            # Append any scenes the caller did not mention, preserving order.
            for s in all_scenes:
                if s.id not in seen:
                    ordered.append(s)
            for i, s in enumerate(ordered):
                s.sort_order = i
            session.commit()

    def get_scene_character_ids(self, scene_id: int) -> list[int]:
        with Session(self._engine) as session:
            stmt = select(SceneCharacterLink.character_id).where(
                SceneCharacterLink.scene_id == scene_id
            )
            return list(session.exec(stmt).all())

    def get_scene_place_ids(self, scene_id: int) -> list[int]:
        with Session(self._engine) as session:
            stmt = select(ScenePlaceLink.place_id).where(
                ScenePlaceLink.scene_id == scene_id
            )
            return list(session.exec(stmt).all())

    # -- Scene <-> Theme links (structured theme presence) -------------------

    def get_scene_theme_ids(self, scene_id: int) -> list[int]:
        """Theme PSYKE entry ids structurally tagged to a scene."""
        with Session(self._engine) as session:
            stmt = select(SceneThemeLink.psyke_entry_id).where(
                SceneThemeLink.scene_id == scene_id
            )
            return list(session.exec(stmt).all())

    def get_theme_scene_ids(self, entry_id: int) -> list[int]:
        """Scene ids a theme PSYKE entry is structurally tagged in."""
        with Session(self._engine) as session:
            stmt = select(SceneThemeLink.scene_id).where(
                SceneThemeLink.psyke_entry_id == entry_id
            )
            return list(session.exec(stmt).all())

    def add_scene_theme_link(self, scene_id: int, entry_id: int) -> None:
        with Session(self._engine) as session:
            if session.get(SceneThemeLink, (scene_id, entry_id)) is None:
                session.add(SceneThemeLink(scene_id=scene_id, psyke_entry_id=entry_id))
                session.commit()

    def remove_scene_theme_link(self, scene_id: int, entry_id: int) -> None:
        with Session(self._engine) as session:
            link = session.get(SceneThemeLink, (scene_id, entry_id))
            if link is not None:
                session.delete(link)
                session.commit()

    def set_theme_scenes(self, entry_id: int, scene_ids: list[int]) -> None:
        """Replace the full set of scenes a theme is tagged in (idempotent)."""
        want = set(scene_ids)
        with Session(self._engine) as session:
            existing = {
                link.scene_id: link
                for link in session.exec(
                    select(SceneThemeLink).where(SceneThemeLink.psyke_entry_id == entry_id)
                ).all()
            }
            for sid, link in existing.items():
                if sid not in want:
                    session.delete(link)
            for sid in want:
                if sid not in existing:
                    session.add(SceneThemeLink(scene_id=sid, psyke_entry_id=entry_id))
            session.commit()

    def get_scene_character_states(
        self, scene_id: int
    ) -> list[tuple[int, str]]:
        with Session(self._engine) as session:
            stmt = select(SceneCharacterState).where(
                SceneCharacterState.scene_id == scene_id
            )
            return [
                (s.character_id, s.state)
                for s in session.exec(stmt).all()
            ]

    def get_character_arc(
        self, project_id: int, character_id: int
    ) -> list[tuple[int, str, int, str]]:
        scenes = self.get_all_scenes(project_id)
        arc: list[tuple[int, str, int, str]] = []
        for idx, scene in enumerate(scenes):
            for cid, state in self.get_scene_character_states(scene.id):
                if cid == character_id:
                    arc.append((scene.id, scene.title, idx + 1, state))
        return arc

    def get_character_arc_by_name(
        self, project_id: int, name: str
    ) -> list[tuple[int, str, int, str]]:
        """Arc for a character identified by name.

        The Arcs selector is sourced from PSYKE character entries (the
        source of truth), but scene character-states are keyed by
        Character-table id. This resolves the PSYKE entry name to any
        matching Character rows (case-insensitive) and returns their
        combined arc. Returns [] when the character has no recorded scene
        states yet.
        """
        name_l = (name or "").strip().lower()
        if not name_l:
            return []
        char_ids = {
            c.id for c in self.get_all_characters(project_id)
            if (c.name or "").strip().lower() == name_l
        }
        if not char_ids:
            return []
        scenes = self.get_all_scenes(project_id)
        arc: list[tuple[int, str, int, str]] = []
        for idx, scene in enumerate(scenes):
            for cid, state in self.get_scene_character_states(scene.id):
                if cid in char_ids:
                    arc.append((scene.id, scene.title, idx + 1, state))
        return arc

    # -- Graphic Novel: sequences / pages / panels --------------------------
    # Hierarchy: Sequence -> Pages -> Panels. List-valued panel fields are
    # stored as CSV; create/update accept Python lists and join them.

    @staticmethod
    def _csv_join(values) -> str:
        if values is None:
            return ""
        if isinstance(values, str):
            return values
        return ",".join(str(v).strip() for v in values if str(v).strip())

    @staticmethod
    def csv_split(value: str) -> list[str]:
        return [v.strip() for v in (value or "").split(",") if v.strip()]

    # Issues ----------------------------------------------------------------

    def create_gn_issue(
        self, project_id: int, *, issue_number: int | None = None,
        title: str = "", summary: str = "", status: str = "",
        notes: str = "", sort_order: int | None = None,
    ) -> GraphicNovelIssue:
        with Session(self._engine) as session:
            siblings = session.exec(
                select(GraphicNovelIssue).where(
                    GraphicNovelIssue.project_id == project_id,
                )
            ).all()
            if issue_number is None:
                issue_number = len(siblings) + 1
            if sort_order is None:
                sort_order = len(siblings)
            issue = GraphicNovelIssue(
                project_id=project_id, issue_number=issue_number,
                title=title, summary=summary, status=status, notes=notes,
                sort_order=sort_order,
            )
            session.add(issue)
            session.commit()
            session.refresh(issue)
            return issue

    def get_gn_issues(self, project_id: int) -> list[GraphicNovelIssue]:
        with Session(self._engine) as session:
            stmt = (
                select(GraphicNovelIssue)
                .where(GraphicNovelIssue.project_id == project_id)
                .order_by(GraphicNovelIssue.sort_order, GraphicNovelIssue.id)
            )
            return list(session.exec(stmt).all())

    def get_gn_issue_by_id(self, issue_id: int) -> GraphicNovelIssue | None:
        with Session(self._engine) as session:
            return session.get(GraphicNovelIssue, issue_id)

    def update_gn_issue(self, issue_id: int, **fields) -> None:
        self._patch_row(GraphicNovelIssue, issue_id, fields)

    def reorder_gn_issues(
        self, project_id: int, ordered_issue_ids: list[int],
    ) -> None:
        """Renumber project issues to match *ordered_issue_ids* (issue_number
        + sort_order both follow the given order, 1-based numbers)."""
        with Session(self._engine) as session:
            for idx, iid in enumerate(ordered_issue_ids):
                issue = session.get(GraphicNovelIssue, iid)
                if issue and issue.project_id == project_id:
                    issue.issue_number = idx + 1
                    issue.sort_order = idx
            session.commit()

    def delete_gn_issue(self, issue_id: int, *, force: bool = False) -> bool:
        """Delete an Issue. Safe by default: refuses to delete an Issue that
        still owns pages (returns False) so pages are never silently lost.

        Pass force=True to detach — pages are moved to unassigned
        (issue_id = None), never deleted — then the Issue is removed.
        Returns True if the Issue was deleted, False if it was kept.
        """
        with Session(self._engine) as session:
            issue = session.get(GraphicNovelIssue, issue_id)
            if issue is None:
                return False
            pages = session.exec(
                select(GraphicNovelPage).where(
                    GraphicNovelPage.issue_id == issue_id,
                )
            ).all()
            if pages and not force:
                return False
            for page in pages:
                page.issue_id = None      # detach, never delete pages
            session.delete(issue)
            session.commit()
            return True

    def get_gn_pages_for_issue(self, issue_id: int) -> list[GraphicNovelPage]:
        with Session(self._engine) as session:
            stmt = (
                select(GraphicNovelPage)
                .where(GraphicNovelPage.issue_id == issue_id)
                .order_by(GraphicNovelPage.page_number, GraphicNovelPage.id)
            )
            return list(session.exec(stmt).all())

    def assign_gn_page_to_issue(
        self, page_id: int, issue_id: int | None,
    ) -> None:
        """Assign a page to an Issue (or None to unassign)."""
        self._patch_row(GraphicNovelPage, page_id, {"issue_id": issue_id})

    # Sequences -------------------------------------------------------------

    def create_gn_sequence(
        self, project_id: int, *, title: str = "", summary: str = "",
        dramatic_purpose: str = "", visual_purpose: str = "",
        emotional_beat: str = "", issue: str = "", chapter: str = "",
        sort_order: int | None = None,
    ) -> GraphicNovelSequence:
        with Session(self._engine) as session:
            if sort_order is None:
                existing = session.exec(
                    select(GraphicNovelSequence).where(
                        GraphicNovelSequence.project_id == project_id,
                    )
                ).all()
                sort_order = len(existing)
            seq = GraphicNovelSequence(
                project_id=project_id, title=title, summary=summary,
                dramatic_purpose=dramatic_purpose, visual_purpose=visual_purpose,
                emotional_beat=emotional_beat, issue=issue, chapter=chapter,
                sort_order=sort_order,
            )
            session.add(seq)
            session.commit()
            session.refresh(seq)
            return seq

    def get_gn_sequences(self, project_id: int) -> list[GraphicNovelSequence]:
        with Session(self._engine) as session:
            stmt = (
                select(GraphicNovelSequence)
                .where(GraphicNovelSequence.project_id == project_id)
                .order_by(GraphicNovelSequence.sort_order, GraphicNovelSequence.id)
            )
            return list(session.exec(stmt).all())

    def get_gn_sequence_by_id(self, sequence_id: int) -> GraphicNovelSequence | None:
        with Session(self._engine) as session:
            return session.get(GraphicNovelSequence, sequence_id)

    def update_gn_sequence(self, sequence_id: int, **fields) -> None:
        self._patch_row(GraphicNovelSequence, sequence_id, fields)

    # Pages -----------------------------------------------------------------

    def create_gn_page(
        self, project_id: int, *, sequence_id: int | None = None,
        issue_id: int | None = None,
        page_number: int | None = None, summary: str = "",
        emotional_beat: str = "", density_level: str = "",
        reveal_type: str = "", splash_page: bool = False, notes: str = "",
        sort_order: int | None = None,
    ) -> GraphicNovelPage:
        with Session(self._engine) as session:
            siblings = session.exec(
                select(GraphicNovelPage).where(
                    GraphicNovelPage.project_id == project_id,
                )
            ).all()
            if page_number is None:
                page_number = len(siblings) + 1
            if sort_order is None:
                sort_order = len(siblings)
            page = GraphicNovelPage(
                project_id=project_id, sequence_id=sequence_id,
                issue_id=issue_id,
                page_number=page_number, summary=summary,
                emotional_beat=emotional_beat, density_level=density_level,
                reveal_type=reveal_type, splash_page=splash_page,
                notes=notes, sort_order=sort_order,
            )
            session.add(page)
            session.commit()
            session.refresh(page)
            return page

    def get_gn_pages(self, project_id: int) -> list[GraphicNovelPage]:
        with Session(self._engine) as session:
            stmt = (
                select(GraphicNovelPage)
                .where(GraphicNovelPage.project_id == project_id)
                .order_by(GraphicNovelPage.page_number, GraphicNovelPage.id)
            )
            return list(session.exec(stmt).all())

    def get_gn_pages_for_sequence(self, sequence_id: int) -> list[GraphicNovelPage]:
        with Session(self._engine) as session:
            stmt = (
                select(GraphicNovelPage)
                .where(GraphicNovelPage.sequence_id == sequence_id)
                .order_by(GraphicNovelPage.page_number, GraphicNovelPage.id)
            )
            return list(session.exec(stmt).all())

    def get_gn_page_by_id(self, page_id: int) -> GraphicNovelPage | None:
        with Session(self._engine) as session:
            return session.get(GraphicNovelPage, page_id)

    def update_gn_page(self, page_id: int, **fields) -> None:
        self._patch_row(GraphicNovelPage, page_id, fields)

    def assign_gn_page_to_sequence(self, page_id: int, sequence_id: int | None) -> None:
        self._patch_row(GraphicNovelPage, page_id, {"sequence_id": sequence_id})

    def reorder_gn_pages(self, project_id: int, ordered_page_ids: list[int]) -> None:
        """Renumber project pages to match *ordered_page_ids* (page_number +
        sort_order both follow the given order, 1-based page numbers)."""
        with Session(self._engine) as session:
            for idx, pid in enumerate(ordered_page_ids):
                page = session.get(GraphicNovelPage, pid)
                if page and page.project_id == project_id:
                    page.page_number = idx + 1
                    page.sort_order = idx
            session.commit()

    def delete_gn_page(self, page_id: int) -> None:
        with Session(self._engine) as session:
            panels = session.exec(
                select(GraphicNovelPanel).where(
                    GraphicNovelPanel.page_id == page_id,
                )
            ).all()
            panel_ids = [panel.id for panel in panels if panel.id is not None]
            appearance_query = (
                GraphicNovelContinuityAppearance.page_id == page_id
            )
            if panel_ids:
                appearance_query = appearance_query | (
                    GraphicNovelContinuityAppearance.panel_id.in_(panel_ids)
                )
            for appearance in session.exec(
                select(GraphicNovelContinuityAppearance).where(appearance_query)
            ).all():
                session.delete(appearance)
            for panel in panels:
                session.delete(panel)
            session.flush()
            page = session.get(GraphicNovelPage, page_id)
            if page:
                session.delete(page)
            session.commit()

    # Panels ----------------------------------------------------------------

    def create_gn_panel(
        self, page_id: int, *, project_id: int | None = None,
        panel_number: int | None = None, description: str = "",
        camera_angle: str = "", shot_type: str = "", emotional_tone: str = "",
        action: str = "", characters_present=None, dialogue_refs=None,
        visual_motifs=None, reading_priority: int = 0,
        transition_type: str = "", sort_order: int | None = None,
    ) -> GraphicNovelPanel:
        with Session(self._engine) as session:
            if project_id is None:
                page = session.get(GraphicNovelPage, page_id)
                project_id = page.project_id if page else 0
            siblings = session.exec(
                select(GraphicNovelPanel).where(
                    GraphicNovelPanel.page_id == page_id,
                )
            ).all()
            if panel_number is None:
                panel_number = len(siblings) + 1
            if sort_order is None:
                sort_order = len(siblings)
            panel = GraphicNovelPanel(
                page_id=page_id, project_id=project_id,
                panel_number=panel_number, description=description,
                camera_angle=camera_angle, shot_type=shot_type,
                emotional_tone=emotional_tone, action=action,
                characters_present=self._csv_join(characters_present),
                dialogue_refs=self._csv_join(dialogue_refs),
                visual_motifs=self._csv_join(visual_motifs),
                reading_priority=reading_priority,
                transition_type=transition_type, sort_order=sort_order,
            )
            session.add(panel)
            session.commit()
            session.refresh(panel)
            return panel

    def get_gn_panels_for_page(self, page_id: int) -> list[GraphicNovelPanel]:
        with Session(self._engine) as session:
            stmt = (
                select(GraphicNovelPanel)
                .where(GraphicNovelPanel.page_id == page_id)
                .order_by(GraphicNovelPanel.panel_number, GraphicNovelPanel.id)
            )
            return list(session.exec(stmt).all())

    def get_gn_panel_by_id(self, panel_id: int) -> GraphicNovelPanel | None:
        with Session(self._engine) as session:
            return session.get(GraphicNovelPanel, panel_id)

    def update_gn_panel(self, panel_id: int, **fields) -> None:
        # Normalize list-valued fields to CSV.
        for key in ("characters_present", "dialogue_refs", "visual_motifs"):
            if key in fields and not isinstance(fields[key], str):
                fields[key] = self._csv_join(fields[key])
        self._patch_row(GraphicNovelPanel, panel_id, fields)

    def reorder_gn_panels(self, page_id: int, ordered_panel_ids: list[int]) -> None:
        with Session(self._engine) as session:
            for idx, pid in enumerate(ordered_panel_ids):
                panel = session.get(GraphicNovelPanel, pid)
                if panel and panel.page_id == page_id:
                    panel.panel_number = idx + 1
                    panel.sort_order = idx
            session.commit()

    def delete_gn_panel(self, panel_id: int) -> None:
        with Session(self._engine) as session:
            for appearance in session.exec(
                select(GraphicNovelContinuityAppearance).where(
                    GraphicNovelContinuityAppearance.panel_id == panel_id,
                )
            ).all():
                session.delete(appearance)
            session.flush()
            panel = session.get(GraphicNovelPanel, panel_id)
            if panel:
                session.delete(panel)
                session.commit()

    # Continuity ------------------------------------------------------------

    def create_gn_continuity_item(
        self, project_id: int, name: str, *, item_type: str = "other",
        description: str = "", linked_psyke_entry_id: int | None = None,
        notes: str = "",
    ) -> GraphicNovelContinuityItem:
        with Session(self._engine) as session:
            item = GraphicNovelContinuityItem(
                project_id=project_id, name=name, item_type=item_type,
                description=description,
                linked_psyke_entry_id=linked_psyke_entry_id, notes=notes,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return item

    def get_gn_continuity_items(self, project_id: int) -> list[GraphicNovelContinuityItem]:
        with Session(self._engine) as session:
            stmt = (
                select(GraphicNovelContinuityItem)
                .where(GraphicNovelContinuityItem.project_id == project_id)
                .order_by(GraphicNovelContinuityItem.id)
            )
            return list(session.exec(stmt).all())

    def get_gn_continuity_item_by_id(
        self, item_id: int,
    ) -> GraphicNovelContinuityItem | None:
        with Session(self._engine) as session:
            return session.get(GraphicNovelContinuityItem, item_id)

    def add_gn_continuity_appearance(
        self, continuity_item_id: int, *, page_id: int | None = None,
        panel_id: int | None = None, state_description: str = "",
        continuity_status: str = "consistent",
    ) -> GraphicNovelContinuityAppearance:
        with Session(self._engine) as session:
            existing = session.exec(
                select(GraphicNovelContinuityAppearance).where(
                    GraphicNovelContinuityAppearance.continuity_item_id
                    == continuity_item_id,
                )
            ).all()
            appearance = GraphicNovelContinuityAppearance(
                continuity_item_id=continuity_item_id, page_id=page_id,
                panel_id=panel_id, state_description=state_description,
                continuity_status=continuity_status, sort_order=len(existing),
            )
            session.add(appearance)
            session.commit()
            session.refresh(appearance)
            return appearance

    def get_gn_continuity_appearances(
        self, continuity_item_id: int,
    ) -> list[GraphicNovelContinuityAppearance]:
        with Session(self._engine) as session:
            stmt = (
                select(GraphicNovelContinuityAppearance)
                .where(
                    GraphicNovelContinuityAppearance.continuity_item_id
                    == continuity_item_id,
                )
                .order_by(
                    GraphicNovelContinuityAppearance.sort_order,
                    GraphicNovelContinuityAppearance.id,
                )
            )
            return list(session.exec(stmt).all())

    def get_gn_continuity_appearance_by_id(
        self, appearance_id: int,
    ) -> GraphicNovelContinuityAppearance | None:
        with Session(self._engine) as session:
            return session.get(GraphicNovelContinuityAppearance, appearance_id)

    def _patch_row(self, model, row_id: int, fields: dict) -> None:
        """Set provided attributes on a row, ignoring unknown keys."""
        with Session(self._engine) as session:
            row = session.get(model, row_id)
            if row is None:
                return
            for key, value in fields.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            session.add(row)
            session.commit()

    # -- Stage Script: entrances/exits, cues, stage business ----------------

    def create_stage_entrance_exit(
        self, scene_id: int, *, character_id: int | None = None,
        type: str = "entrance", moment_order: int | None = None,
        cue_text: str = "", notes: str = "",
    ) -> StageEntranceExit:
        with Session(self._engine) as session:
            if moment_order is None:
                existing = session.exec(
                    select(StageEntranceExit).where(
                        StageEntranceExit.scene_id == scene_id,
                    )
                ).all()
                moment_order = len(existing)
            row = StageEntranceExit(
                scene_id=scene_id, character_id=character_id, type=type,
                moment_order=moment_order, cue_text=cue_text, notes=notes,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_stage_entrances_exits(self, scene_id: int) -> list[StageEntranceExit]:
        with Session(self._engine) as session:
            stmt = (
                select(StageEntranceExit)
                .where(StageEntranceExit.scene_id == scene_id)
                .order_by(StageEntranceExit.moment_order, StageEntranceExit.id)
            )
            return list(session.exec(stmt).all())

    def get_stage_entrance_exit_by_id(self, row_id: int) -> StageEntranceExit | None:
        with Session(self._engine) as session:
            return session.get(StageEntranceExit, row_id)

    def delete_stage_entrance_exit(self, row_id: int) -> None:
        with Session(self._engine) as session:
            row = session.get(StageEntranceExit, row_id)
            if row:
                session.delete(row)
                session.commit()

    def create_stage_cue(
        self, scene_id: int, *, cue_type: str = "other",
        moment_order: int | None = None, cue_text: str = "", notes: str = "",
    ) -> StageCue:
        with Session(self._engine) as session:
            if moment_order is None:
                existing = session.exec(
                    select(StageCue).where(StageCue.scene_id == scene_id)
                ).all()
                moment_order = len(existing)
            row = StageCue(
                scene_id=scene_id, cue_type=cue_type,
                moment_order=moment_order, cue_text=cue_text, notes=notes,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_stage_cues(self, scene_id: int) -> list[StageCue]:
        with Session(self._engine) as session:
            stmt = (
                select(StageCue)
                .where(StageCue.scene_id == scene_id)
                .order_by(StageCue.moment_order, StageCue.id)
            )
            return list(session.exec(stmt).all())

    def get_stage_cue_by_id(self, row_id: int) -> StageCue | None:
        with Session(self._engine) as session:
            return session.get(StageCue, row_id)

    def delete_stage_cue(self, row_id: int) -> None:
        with Session(self._engine) as session:
            row = session.get(StageCue, row_id)
            if row:
                session.delete(row)
                session.commit()

    def create_stage_business(
        self, scene_id: int, *, prop_psyke_entry_id: int | None = None,
        character_id: int | None = None, stage_action: str = "",
        continuity_note: str = "", moment_order: int | None = None,
    ) -> StageBusiness:
        with Session(self._engine) as session:
            if moment_order is None:
                existing = session.exec(
                    select(StageBusiness).where(
                        StageBusiness.scene_id == scene_id,
                    )
                ).all()
                moment_order = len(existing)
            row = StageBusiness(
                scene_id=scene_id, prop_psyke_entry_id=prop_psyke_entry_id,
                character_id=character_id, stage_action=stage_action,
                continuity_note=continuity_note, moment_order=moment_order,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_stage_business(self, scene_id: int) -> list[StageBusiness]:
        with Session(self._engine) as session:
            stmt = (
                select(StageBusiness)
                .where(StageBusiness.scene_id == scene_id)
                .order_by(StageBusiness.moment_order, StageBusiness.id)
            )
            return list(session.exec(stmt).all())

    def get_stage_business_by_id(self, row_id: int) -> StageBusiness | None:
        with Session(self._engine) as session:
            return session.get(StageBusiness, row_id)

    # -- Series: seasons / episodes / arcs / plotlines ----------------------

    def create_season(
        self, project_id: int, *, season_number: int | None = None,
        title: str = "", summary: str = "", season_arc: str = "",
        central_question: str = "", finale_payoff: str = "", status: str = "",
        order_index: int | None = None,
    ) -> Season:
        with Session(self._engine) as session:
            siblings = session.exec(
                select(Season).where(Season.project_id == project_id)
            ).all()
            if season_number is None:
                season_number = len(siblings) + 1
            if order_index is None:
                order_index = len(siblings)
            row = Season(
                project_id=project_id, season_number=season_number,
                title=title, summary=summary, season_arc=season_arc,
                central_question=central_question, finale_payoff=finale_payoff,
                status=status, order_index=order_index,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_seasons(self, project_id: int) -> list[Season]:
        with Session(self._engine) as session:
            stmt = (
                select(Season)
                .where(Season.project_id == project_id)
                .order_by(Season.order_index, Season.id)
            )
            return list(session.exec(stmt).all())

    def get_season_by_id(self, season_id: int) -> Season | None:
        with Session(self._engine) as session:
            return session.get(Season, season_id)

    def update_season(self, season_id: int, **fields) -> None:
        self._patch_row(Season, season_id, fields)

    def create_episode(
        self, season_id: int, *, project_id: int | None = None,
        episode_number: int | None = None, title: str = "", logline: str = "",
        summary: str = "", episode_engine: str = "", teaser: str = "",
        act_breaks: str = "", cliffhanger: str = "", status: str = "",
        estimated_runtime_minutes: int = 0, order_index: int | None = None,
    ) -> Episode:
        with Session(self._engine) as session:
            if project_id is None:
                season = session.get(Season, season_id)
                project_id = season.project_id if season else 0
            siblings = session.exec(
                select(Episode).where(Episode.season_id == season_id)
            ).all()
            if episode_number is None:
                episode_number = len(siblings) + 1
            if order_index is None:
                order_index = len(siblings)
            row = Episode(
                season_id=season_id, project_id=project_id,
                episode_number=episode_number, title=title, logline=logline,
                summary=summary, episode_engine=episode_engine, teaser=teaser,
                act_breaks=act_breaks, cliffhanger=cliffhanger, status=status,
                estimated_runtime_minutes=estimated_runtime_minutes,
                order_index=order_index,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_episodes_for_season(self, season_id: int) -> list[Episode]:
        with Session(self._engine) as session:
            stmt = (
                select(Episode)
                .where(Episode.season_id == season_id)
                .order_by(Episode.episode_number, Episode.id)
            )
            return list(session.exec(stmt).all())

    def get_episodes(self, project_id: int) -> list[Episode]:
        with Session(self._engine) as session:
            stmt = (
                select(Episode)
                .where(Episode.project_id == project_id)
                .order_by(Episode.order_index, Episode.id)
            )
            return list(session.exec(stmt).all())

    def get_episode_by_id(self, episode_id: int) -> Episode | None:
        with Session(self._engine) as session:
            return session.get(Episode, episode_id)

    def update_episode(self, episode_id: int, **fields) -> None:
        self._patch_row(Episode, episode_id, fields)

    def delete_episode(self, episode_id: int) -> None:
        """Delete an Episode row and **unlink** (never delete) its scenes.

        Scenes that pointed at the episode have ``episode_id`` reset to NULL so
        their bodies survive as unassigned Series scenes — deleting structure
        must not destroy manuscript text. Episode plotlines (a child table) are
        removed with the episode.
        """
        with Session(self._engine) as read_session:
            episode = read_session.get(Episode, episode_id)
            if episode is None:
                return
            project_id = episode.project_id
        with self._structure_write_session(project_id) as session:
            for sc in session.exec(
                select(Scene).where(Scene.episode_id == episode_id)
            ).all():
                sc.episode_id = None
                session.add(sc)
            for pl in session.exec(
                select(EpisodePlotline).where(
                    EpisodePlotline.episode_id == episode_id)
            ).all():
                session.delete(pl)
            for arc in session.exec(
                select(SeriesArc).where(
                    (SeriesArc.setup_episode_id == episode_id)
                    | (SeriesArc.payoff_episode_id == episode_id)
                )
            ).all():
                if arc.setup_episode_id == episode_id:
                    arc.setup_episode_id = None
                if arc.payoff_episode_id == episode_id:
                    arc.payoff_episode_id = None
            session.flush()
            row = session.get(Episode, episode_id)
            if row is not None:
                session.delete(row)
            session.commit()

    def delete_season(self, season_id: int) -> None:
        """Delete a Season, its Episodes, and **unlink** (never delete) scenes.

        Cascades to the season's episodes (and their plotlines); every scene
        that belonged to those episodes has ``episode_id`` reset to NULL so its
        body survives as an unassigned Series scene.
        """
        with Session(self._engine) as read_session:
            season = read_session.get(Season, season_id)
            if season is None:
                return
            project_id = season.project_id
        with self._structure_write_session(project_id) as session:
            episodes = session.exec(
                select(Episode).where(Episode.season_id == season_id)
            ).all()
            ep_ids = [e.id for e in episodes]
            if ep_ids:
                for sc in session.exec(
                    select(Scene).where(Scene.episode_id.in_(ep_ids))
                ).all():
                    sc.episode_id = None
                    session.add(sc)
                for pl in session.exec(
                    select(EpisodePlotline).where(
                        EpisodePlotline.episode_id.in_(ep_ids))
                ).all():
                    session.delete(pl)
                for arc in session.exec(
                    select(SeriesArc).where(
                        (SeriesArc.setup_episode_id.in_(ep_ids))
                        | (SeriesArc.payoff_episode_id.in_(ep_ids))
                    )
                ).all():
                    if arc.setup_episode_id in ep_ids:
                        arc.setup_episode_id = None
                    if arc.payoff_episode_id in ep_ids:
                        arc.payoff_episode_id = None
                for e in episodes:
                    session.delete(e)
                session.flush()
            row = session.get(Season, season_id)
            if row is not None:
                session.delete(row)
            session.commit()

    def reorder_seasons(self, project_id: int, ordered_ids: list[int]) -> None:
        """Assign ``order_index`` from the position of each id in *ordered_ids*.

        Seasons not listed keep their relative order after the listed ones. Only
        ``order_index`` is written.
        """
        with Session(self._engine) as session:
            rows = list(session.exec(
                select(Season)
                .where(Season.project_id == project_id)
                .order_by(Season.order_index, Season.id)
            ).all())
            self._apply_order(session, rows, ordered_ids)
            session.commit()

    def reorder_episodes(self, season_id: int, ordered_ids: list[int]) -> None:
        """Assign ``order_index`` (and ``episode_number``) from the position of
        each id in *ordered_ids*, within one season. Episodes not listed keep
        their relative order after the listed ones."""
        with Session(self._engine) as session:
            rows = list(session.exec(
                select(Episode)
                .where(Episode.season_id == season_id)
                .order_by(Episode.order_index, Episode.id)
            ).all())
            ordered = self._apply_order(session, rows, ordered_ids)
            for i, e in enumerate(ordered, start=1):
                e.episode_number = i
                session.add(e)
            session.commit()

    @staticmethod
    def _apply_order(session, rows, ordered_ids):
        by_id = {r.id: r for r in rows}
        ordered = []
        seen: set[int] = set()
        for rid in ordered_ids:
            r = by_id.get(rid)
            if r is not None and r.id not in seen:
                ordered.append(r)
                seen.add(r.id)
        for r in rows:
            if r.id not in seen:
                ordered.append(r)
        for i, r in enumerate(ordered):
            r.order_index = i
            session.add(r)
        return ordered

    def create_series_arc(
        self, project_id: int, *, scope: str = "series", title: str = "",
        summary: str = "", setup_episode_id: int | None = None,
        payoff_episode_id: int | None = None, status: str = "active",
        linked_psyke_entries=None, notes: str = "",
    ) -> SeriesArc:
        with Session(self._engine) as session:
            row = SeriesArc(
                project_id=project_id, scope=scope, title=title,
                summary=summary, setup_episode_id=setup_episode_id,
                payoff_episode_id=payoff_episode_id, status=status,
                linked_psyke_entries=self._csv_join(linked_psyke_entries),
                notes=notes,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_series_arcs(self, project_id: int) -> list[SeriesArc]:
        with Session(self._engine) as session:
            stmt = (
                select(SeriesArc)
                .where(SeriesArc.project_id == project_id)
                .order_by(SeriesArc.id)
            )
            return list(session.exec(stmt).all())

    def get_series_arc_by_id(self, arc_id: int) -> SeriesArc | None:
        with Session(self._engine) as session:
            return session.get(SeriesArc, arc_id)

    def update_series_arc(self, arc_id: int, **fields) -> None:
        if "linked_psyke_entries" in fields and not isinstance(
            fields["linked_psyke_entries"], str
        ):
            fields["linked_psyke_entries"] = self._csv_join(
                fields["linked_psyke_entries"]
            )
        self._patch_row(SeriesArc, arc_id, fields)

    def create_episode_plotline(
        self, episode_id: int, *, type: str = "A", title: str = "",
        summary: str = "", characters=None, resolution_state: str = "",
        order_index: int | None = None,
    ) -> EpisodePlotline:
        with Session(self._engine) as session:
            if order_index is None:
                existing = session.exec(
                    select(EpisodePlotline).where(
                        EpisodePlotline.episode_id == episode_id
                    )
                ).all()
                order_index = len(existing)
            row = EpisodePlotline(
                episode_id=episode_id, type=type, title=title,
                summary=summary, characters=self._csv_join(characters),
                resolution_state=resolution_state, order_index=order_index,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_episode_plotlines(self, episode_id: int) -> list[EpisodePlotline]:
        with Session(self._engine) as session:
            stmt = (
                select(EpisodePlotline)
                .where(EpisodePlotline.episode_id == episode_id)
                .order_by(EpisodePlotline.order_index, EpisodePlotline.id)
            )
            return list(session.exec(stmt).all())

    def get_episode_plotline_by_id(self, plotline_id: int) -> EpisodePlotline | None:
        with Session(self._engine) as session:
            return session.get(EpisodePlotline, plotline_id)

    # -- Format-structure single-row update/delete completions --------------
    # These entities previously had create/get only (no in-app way to correct or
    # prune a wrong row); thin _patch_row/delete wrappers, same style as the
    # GN page / season / episode methods above.
    def delete_series_arc(self, arc_id: int) -> None:
        with Session(self._engine) as session:
            row = session.get(SeriesArc, arc_id)
            if row:
                session.delete(row)
                session.commit()

    def update_episode_plotline(self, plotline_id: int, **fields) -> None:
        if "characters" in fields and not isinstance(fields["characters"], str):
            fields["characters"] = self._csv_join(fields["characters"])
        self._patch_row(EpisodePlotline, plotline_id, fields)

    def delete_episode_plotline(self, plotline_id: int) -> None:
        with Session(self._engine) as session:
            row = session.get(EpisodePlotline, plotline_id)
            if row:
                session.delete(row)
                session.commit()

    def update_gn_continuity_item(self, item_id: int, **fields) -> None:
        self._patch_row(GraphicNovelContinuityItem, item_id, fields)

    def delete_gn_continuity_item(self, item_id: int) -> None:
        with Session(self._engine) as session:
            for app in session.exec(
                select(GraphicNovelContinuityAppearance).where(
                    GraphicNovelContinuityAppearance.continuity_item_id == item_id,
                )
            ).all():
                session.delete(app)
            session.flush()
            row = session.get(GraphicNovelContinuityItem, item_id)
            if row:
                session.delete(row)
            session.commit()

    def update_gn_continuity_appearance(self, appearance_id: int, **fields) -> None:
        self._patch_row(GraphicNovelContinuityAppearance, appearance_id, fields)

    def delete_gn_continuity_appearance(self, appearance_id: int) -> None:
        with Session(self._engine) as session:
            row = session.get(GraphicNovelContinuityAppearance, appearance_id)
            if row:
                session.delete(row)
                session.commit()

    def update_stage_cue(self, row_id: int, **fields) -> None:
        self._patch_row(StageCue, row_id, fields)

    def update_stage_entrance_exit(self, row_id: int, **fields) -> None:
        self._patch_row(StageEntranceExit, row_id, fields)

    def delete_stage_business(self, row_id: int) -> None:
        with Session(self._engine) as session:
            row = session.get(StageBusiness, row_id)
            if row:
                session.delete(row)
                session.commit()

    # -- Continuity note single-row update/delete (StoryMemoryEntry) ---------
    def update_continuity_memory(self, memory_id: int, **fields) -> None:
        """Edit a single pinned continuity note (value/target)."""
        self._patch_row(StoryMemoryEntry, memory_id, fields)

    def delete_continuity_memory(self, memory_id: int) -> None:
        with Session(self._engine) as session:
            row = session.get(StoryMemoryEntry, memory_id)
            if row:
                session.delete(row)
                session.commit()

    # -- PSYKE (Story Bible) ------------------------------------------------

    def get_psyke_entry_by_id(self, entry_id: int) -> PsykeEntry | None:
        with Session(self._engine) as session:
            return session.get(PsykeEntry, entry_id)

    def get_all_psyke_entries(self, project_id: int) -> list[PsykeEntry]:
        with Session(self._engine) as session:
            stmt = select(PsykeEntry).where(
                PsykeEntry.project_id == project_id
            )
            return list(session.exec(stmt).all())

    # -- Voice glossary (Phase 7): project-scoped dictation terms ----------
    def get_voice_glossary_terms(self, project_id: int) -> list[VoiceGlossaryTerm]:
        with Session(self._engine) as session:
            stmt = select(VoiceGlossaryTerm).where(
                VoiceGlossaryTerm.project_id == project_id)
            return list(session.exec(stmt).all())

    def create_voice_glossary_term(
        self, project_id: int, canonical_text: str, *,
        spoken_forms: str = "", common_misrecognitions: str = "",
        category: str = "custom", source: str = "manual",
        case_sensitive: bool = False, whole_word_only: bool = True,
        enabled: bool = True, priority: int = 0, notes: str = "",
        language: str = "",
    ) -> VoiceGlossaryTerm:
        with Session(self._engine) as session:
            term = VoiceGlossaryTerm(
                project_id=project_id, canonical_text=canonical_text,
                spoken_forms=spoken_forms,
                common_misrecognitions=common_misrecognitions,
                category=category, source=source,
                case_sensitive=case_sensitive,
                whole_word_only=whole_word_only, enabled=enabled,
                priority=priority, notes=notes, language=language)
            session.add(term)
            session.commit()
            session.refresh(term)
            return term

    def update_voice_glossary_term(self, term_id: int,
                                   **fields) -> VoiceGlossaryTerm | None:
        from datetime import datetime, timezone
        with Session(self._engine) as session:
            term = session.get(VoiceGlossaryTerm, term_id)
            if term is None:
                return None
            for key, value in fields.items():
                if hasattr(term, key) and key not in ("id", "project_id",
                                                      "created_at"):
                    setattr(term, key, value)
            term.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(term)
            return term

    def delete_voice_glossary_term(self, term_id: int) -> None:
        with Session(self._engine) as session:
            term = session.get(VoiceGlossaryTerm, term_id)
            if term is not None:
                session.delete(term)
                session.commit()

    def create_psyke_entry(
        self,
        project_id: int,
        name: str,
        entry_type: str = "other",
        aliases: str = "",
        notes: str = "",
        is_global: bool = False,
        details: dict | None = None,
    ) -> PsykeEntry:
        import json
        with Session(self._engine) as session:
            # Idempotent: a same-named entry of the same type in this project
            # already covers this — return it instead of duplicating the bible.
            # (Repeated extraction / create calls used to pile up duplicates,
            # e.g. two identical "SmokeHero" character rows.)
            existing = session.exec(
                select(PsykeEntry).where(
                    PsykeEntry.project_id == project_id,
                    PsykeEntry.entry_type == entry_type,
                    PsykeEntry.name == name,
                )
            ).first()
            if existing is not None:
                return existing
            entry = PsykeEntry(
                project_id=project_id,
                name=name,
                entry_type=entry_type,
                aliases=aliases,
                notes=notes,
                is_global=is_global,
                details_json=json.dumps(details) if details else "",
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            from logosforge.quantum_outliner.lookahead_cache import invalidate_lookahead
            invalidate_lookahead()
            return entry

    def update_psyke_entry(
        self,
        entry_id: int,
        name: str,
        entry_type: str = "other",
        aliases: str = "",
        notes: str = "",
        is_global: bool = False,
        details: dict | None = None,
    ) -> PsykeEntry:
        import json
        with Session(self._engine) as session:
            entry = session.get(PsykeEntry, entry_id)
            entry.name = name
            entry.entry_type = entry_type
            entry.aliases = aliases
            entry.notes = notes
            entry.is_global = is_global
            if details is not None:
                entry.details_json = json.dumps(details)
            session.commit()
            session.refresh(entry)
            from logosforge.quantum_outliner.lookahead_cache import invalidate_lookahead
            invalidate_lookahead()
            return entry

    def get_psyke_entry_details(self, entry_id: int) -> dict:
        import json
        entry = self.get_psyke_entry_by_id(entry_id)
        if entry is None:
            return {}
        try:
            return json.loads(entry.details_json) if entry.details_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    # -- PSYKE visual memory (Graphic Novel) --------------------------------
    # Visual storytelling metadata lives under details_json["visual"] so it
    # extends PSYKE without a schema change and merges in place (other
    # details keys are preserved).

    def get_psyke_visual_memory(self, entry_id: int) -> dict:
        return self._get_psyke_detail_section(entry_id, "visual")

    def set_psyke_visual_memory(self, entry_id: int, visual: dict) -> None:
        self._set_psyke_detail_section(entry_id, "visual", visual)

    def get_psyke_theatre_memory(self, entry_id: int) -> dict:
        return self._get_psyke_detail_section(entry_id, "theatre")

    def set_psyke_theatre_memory(self, entry_id: int, theatre: dict) -> None:
        self._set_psyke_detail_section(entry_id, "theatre", theatre)

    def get_psyke_series_memory(self, entry_id: int) -> dict:
        return self._get_psyke_detail_section(entry_id, "series")

    def set_psyke_series_memory(self, entry_id: int, series: dict) -> None:
        self._set_psyke_detail_section(entry_id, "series", series)

    def _get_psyke_detail_section(self, entry_id: int, section: str) -> dict:
        data = self.get_psyke_entry_details(entry_id).get(section)
        return data if isinstance(data, dict) else {}

    def _set_psyke_detail_section(
        self, entry_id: int, section: str, values: dict,
    ) -> None:
        """Merge *values* into details_json[section] (empty value clears)."""
        import json
        with Session(self._engine) as session:
            entry = session.get(PsykeEntry, entry_id)
            if entry is None:
                return
            try:
                details = json.loads(entry.details_json) if entry.details_json else {}
            except (json.JSONDecodeError, TypeError):
                details = {}
            if not isinstance(details, dict):
                details = {}
            current = details.get(section)
            if not isinstance(current, dict):
                current = {}
            for key, value in values.items():
                if value in (None, ""):
                    current.pop(key, None)
                else:
                    current[key] = value
            details[section] = current
            entry.details_json = json.dumps(details)
            session.commit()

    def delete_psyke_entry(self, entry_id: int) -> None:
        with Session(self._engine) as session:
            for rel in session.exec(
                select(PsykeRelation).where(
                    (PsykeRelation.entry_id == entry_id)
                    | (PsykeRelation.related_entry_id == entry_id)
                )
            ).all():
                session.delete(rel)
            for prog in session.exec(
                select(PsykeProgression).where(
                    PsykeProgression.entry_id == entry_id
                )
            ).all():
                session.delete(prog)
            for npl in session.exec(
                select(NotePsykeLink).where(
                    NotePsykeLink.psyke_entry_id == entry_id,
                )
            ).all():
                session.delete(npl)
            # Drop any scene<->theme links for this entry (no dangling structured presence).
            for stl in session.exec(
                select(SceneThemeLink).where(SceneThemeLink.psyke_entry_id == entry_id)
            ).all():
                session.delete(stl)
            # Unlink (do NOT delete) any manuscript Character bound to this entry,
            # so deleting a bible entry never leaves a dangling Character.psyke_entry_id.
            for char in session.exec(
                select(Character).where(Character.psyke_entry_id == entry_id)
            ).all():
                char.psyke_entry_id = None
            for item in session.exec(
                select(GraphicNovelContinuityItem).where(
                    GraphicNovelContinuityItem.linked_psyke_entry_id == entry_id
                )
            ).all():
                item.linked_psyke_entry_id = None
            for business in session.exec(
                select(StageBusiness).where(
                    StageBusiness.prop_psyke_entry_id == entry_id
                )
            ).all():
                business.prop_psyke_entry_id = None
            session.flush()
            entry = session.get(PsykeEntry, entry_id)
            if entry:
                session.delete(entry)
            session.commit()

    # -- PSYKE Relations -----------------------------------------------------

    def get_related_psyke_entries(self, entry_id: int) -> list[PsykeEntry]:
        with Session(self._engine) as session:
            stmt = select(PsykeRelation.related_entry_id).where(
                PsykeRelation.entry_id == entry_id
            )
            related_ids = list(session.exec(stmt).all())
            if not related_ids:
                return []
            return list(
                session.exec(
                    select(PsykeEntry).where(PsykeEntry.id.in_(related_ids))
                ).all()
            )

    def add_psyke_relation(
        self,
        entry_id: int,
        related_entry_id: int,
        relation_type: str = "",
    ) -> None:
        """Add a bidirectional PSYKE relation.

        Screenplay extensions use typed relations to express
        setup/payoff/echo/motif/opposition links. A "payoff" from A→B is
        stored as a "supports_setup" inverse on B→A so direction is preserved.
        """
        if entry_id == related_entry_id:
            return
        inverse = _INVERSE_RELATION_TYPE.get(relation_type, relation_type)
        with Session(self._engine) as session:
            existing = session.get(PsykeRelation, (entry_id, related_entry_id))
            if existing:
                if relation_type and existing.relation_type != relation_type:
                    existing.relation_type = relation_type
                    rev = session.get(PsykeRelation, (related_entry_id, entry_id))
                    if rev:
                        rev.relation_type = inverse
                    session.commit()
                return
            session.add(PsykeRelation(
                entry_id=entry_id,
                related_entry_id=related_entry_id,
                relation_type=relation_type,
            ))
            session.add(PsykeRelation(
                entry_id=related_entry_id,
                related_entry_id=entry_id,
                relation_type=inverse,
            ))
            session.commit()
            from logosforge.quantum_outliner.lookahead_cache import invalidate_lookahead
            invalidate_lookahead()

    def get_psyke_relation_type(
        self, entry_id: int, related_entry_id: int,
    ) -> str:
        with Session(self._engine) as session:
            rel = session.get(PsykeRelation, (entry_id, related_entry_id))
            return rel.relation_type if rel else ""

    def get_typed_related_psyke_entries(
        self, entry_id: int,
    ) -> list[tuple[PsykeEntry, str]]:
        """Return (related_entry, relation_type) tuples for an entry."""
        with Session(self._engine) as session:
            stmt = select(PsykeRelation).where(
                PsykeRelation.entry_id == entry_id,
            )
            rels = list(session.exec(stmt).all())
            if not rels:
                return []
            related_ids = [r.related_entry_id for r in rels]
            entries = list(
                session.exec(
                    select(PsykeEntry).where(PsykeEntry.id.in_(related_ids))
                ).all()
            )
            by_id = {e.id: e for e in entries}
            return [
                (by_id[r.related_entry_id], r.relation_type)
                for r in rels
                if r.related_entry_id in by_id
            ]

    def remove_psyke_relation(self, entry_id: int, related_entry_id: int) -> None:
        with Session(self._engine) as session:
            for a, b in [(entry_id, related_entry_id), (related_entry_id, entry_id)]:
                rel = session.get(PsykeRelation, (a, b))
                if rel:
                    session.delete(rel)
            session.commit()

    # -- PSYKE Progressions --------------------------------------------------

    def get_psyke_progression_by_id(self, progression_id: int) -> PsykeProgression | None:
        with Session(self._engine) as session:
            return session.get(PsykeProgression, progression_id)

    def get_psyke_progressions(self, entry_id: int) -> list[PsykeProgression]:
        with Session(self._engine) as session:
            stmt = (
                select(PsykeProgression)
                .where(PsykeProgression.entry_id == entry_id)
                .order_by(PsykeProgression.sort_order, PsykeProgression.id)
            )
            return list(session.exec(stmt).all())

    def create_psyke_progression(
        self,
        entry_id: int,
        text: str,
        scene_id: int | None = None,
    ) -> PsykeProgression:
        with Session(self._engine) as session:
            from sqlalchemy import func

            max_order = session.exec(
                select(func.max(PsykeProgression.sort_order)).where(
                    PsykeProgression.entry_id == entry_id
                )
            ).one()
            next_order = (max_order or 0) + 1

            prog = PsykeProgression(
                entry_id=entry_id,
                text=text,
                scene_id=scene_id,
                sort_order=next_order,
            )
            session.add(prog)
            session.commit()
            session.refresh(prog)
            from logosforge.quantum_outliner.lookahead_cache import invalidate_lookahead
            invalidate_lookahead()
            return prog

    def update_psyke_progression(
        self,
        progression_id: int,
        text: str,
        scene_id: int | None = None,
    ) -> PsykeProgression:
        with Session(self._engine) as session:
            prog = session.get(PsykeProgression, progression_id)
            prog.text = text
            prog.scene_id = scene_id
            session.commit()
            session.refresh(prog)
            from logosforge.quantum_outliner.lookahead_cache import invalidate_lookahead
            invalidate_lookahead()
            return prog

    def delete_psyke_progression(self, progression_id: int) -> None:
        with Session(self._engine) as session:
            prog = session.get(PsykeProgression, progression_id)
            if prog:
                session.delete(prog)
            session.commit()

    # -- Search --------------------------------------------------------------

    def search_project(
        self, project_id: int, query: str
    ) -> list[dict]:
        query_lower = query.lower()
        results: list[dict] = []

        for char in self.get_all_characters(project_id):
            if self._matches(query_lower, char.name, char.description):
                results.append(
                    {"type": "Character", "id": char.id, "label": char.name,
                     "preview": char.description}
                )

        for place in self.get_all_places(project_id):
            if self._matches(query_lower, place.name, place.description):
                results.append(
                    {"type": "Place", "id": place.id, "label": place.name,
                     "preview": place.description}
                )

        for note in self.get_all_notes(project_id):
            if self._matches(query_lower, note.title, note.content):
                results.append(
                    {"type": "Note", "id": note.id, "label": note.title,
                     "preview": note.content}
                )

        for scene in self.get_all_scenes(project_id):
            if self._matches(
                query_lower, scene.title, scene.summary,
                scene.chapter, scene.plotline, scene.beat, scene.tags,
            ):
                results.append(
                    {"type": "Scene", "id": scene.id, "label": scene.title,
                     "preview": scene.summary,
                     "chapter": scene.chapter, "plotline": scene.plotline,
                     "tags": scene.tags}
                )

        for entry in self.get_all_psyke_entries(project_id):
            if self._matches(query_lower, entry.name, entry.aliases, entry.notes):
                results.append(
                    {"type": "PSYKE", "id": entry.id, "label": entry.name,
                     "preview": entry.notes}
                )

        return results

    def resolve_link(
        self, project_id: int, name: str
    ) -> tuple[str, int] | None:
        name_lower = name.strip().lower()
        for entry in self.get_all_psyke_entries(project_id):
            if entry.name.lower() == name_lower:
                return ("PsykeEntry", entry.id)
            if entry.aliases:
                for alias in entry.aliases.split(","):
                    if alias.strip().lower() == name_lower:
                        return ("PsykeEntry", entry.id)
        for char in self.get_all_characters(project_id):
            if char.name.lower() == name_lower:
                return ("Character", char.id)
        for place in self.get_all_places(project_id):
            if place.name.lower() == name_lower:
                return ("Place", place.id)
        for scene in self.get_all_scenes(project_id):
            if scene.title.lower() == name_lower:
                return ("Scene", scene.id)
        for note in self.get_all_notes(project_id):
            if note.title.lower() == name_lower:
                return ("Note", note.id)
        return None

    def find_backlinks(
        self, project_id: int, name: str
    ) -> list[tuple[str, int, str]]:
        import re
        pattern = re.compile(
            r"\[\[" + re.escape(name) + r"\]\]", re.IGNORECASE
        )
        results: list[tuple[str, int, str]] = []

        for scene in self.get_all_scenes(project_id):
            fields = (
                scene.summary, scene.synopsis, scene.goal,
                scene.conflict, scene.outcome,
            )
            if any(pattern.search(f) for f in fields if f):
                results.append(("Scene", scene.id, scene.title))

        for note in self.get_all_notes(project_id):
            if note.content and pattern.search(note.content):
                results.append(("Note", note.id, note.title))

        return results

    def build_link_graph(
        self, project_id: int
    ) -> tuple[list[tuple[str, int, str]], list[tuple[str, str]]]:
        import re
        link_pat = re.compile(r"\[\[(.+?)\]\]")

        entity_info: dict[str, tuple[str, int, str]] = {}
        for char in self.get_all_characters(project_id):
            entity_info[char.name.lower()] = ("Character", char.id, char.name)
        for place in self.get_all_places(project_id):
            entity_info[place.name.lower()] = ("Place", place.id, place.name)
        for scene in self.get_all_scenes(project_id):
            entity_info[scene.title.lower()] = ("Scene", scene.id, scene.title)
        for note in self.get_all_notes(project_id):
            entity_info[note.title.lower()] = ("Note", note.id, note.title)

        edges: list[tuple[str, str]] = []
        connected: set[str] = set()

        def _scan(source_name: str, *fields: str) -> None:
            for field in fields:
                if not field:
                    continue
                for match in link_pat.finditer(field):
                    target = match.group(1)
                    if target.lower() in entity_info:
                        edges.append((source_name, target))
                        connected.add(source_name.lower())
                        connected.add(target.lower())

        for scene in self.get_all_scenes(project_id):
            _scan(
                scene.title,
                scene.summary, scene.synopsis, scene.goal,
                scene.conflict, scene.outcome,
            )
        for note in self.get_all_notes(project_id):
            _scan(note.title, note.content)

        nodes: list[tuple[str, int, str]] = []
        for key in sorted(connected):
            if key in entity_info:
                nodes.append(entity_info[key])

        return nodes, edges

    # -- Story Memory -----------------------------------------------------------

    def add_memory(
        self,
        project_id: int,
        scene_id: int,
        memory_type: str,
        target: str,
        value: str,
    ) -> StoryMemoryEntry:
        with Session(self._engine) as session:
            entry = StoryMemoryEntry(
                project_id=project_id,
                scene_id=scene_id,
                memory_type=memory_type,
                target=target,
                value=value,
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry

    def get_memories(
        self, project_id: int, scene_id: int | None = None
    ) -> list[StoryMemoryEntry]:
        with Session(self._engine) as session:
            stmt = select(StoryMemoryEntry).where(
                StoryMemoryEntry.project_id == project_id
            )
            if scene_id is not None:
                stmt = stmt.where(StoryMemoryEntry.scene_id == scene_id)
            stmt = stmt.order_by(StoryMemoryEntry.scene_id, StoryMemoryEntry.id)
            return list(session.exec(stmt).all())

    def get_story_memory_by_id(
        self, memory_id: int,
    ) -> StoryMemoryEntry | None:
        """Return one narrative-memory row without assuming project ownership."""
        with Session(self._engine) as session:
            return session.get(StoryMemoryEntry, memory_id)

    def get_memories_by_type(
        self, project_id: int, memory_type: str
    ) -> list[StoryMemoryEntry]:
        with Session(self._engine) as session:
            stmt = (
                select(StoryMemoryEntry)
                .where(StoryMemoryEntry.project_id == project_id)
                .where(StoryMemoryEntry.memory_type == memory_type)
                .order_by(StoryMemoryEntry.scene_id, StoryMemoryEntry.id)
            )
            return list(session.exec(stmt).all())

    def delete_memories_for_scene(self, scene_id: int) -> None:
        with Session(self._engine) as session:
            stmt = select(StoryMemoryEntry).where(
                StoryMemoryEntry.scene_id == scene_id
            )
            for entry in session.exec(stmt).all():
                session.delete(entry)
            session.commit()

    def memory_exists(
        self, scene_id: int, memory_type: str, target: str
    ) -> bool:
        with Session(self._engine) as session:
            stmt = (
                select(StoryMemoryEntry)
                .where(StoryMemoryEntry.scene_id == scene_id)
                .where(StoryMemoryEntry.memory_type == memory_type)
                .where(StoryMemoryEntry.target == target)
            )
            return session.exec(stmt).first() is not None

    # -- Continuity Tracking (Screenplay) -----------------------------------

    def add_continuity_item(
        self,
        project_id: int,
        scene_id: int,
        category: str,
        target: str,
        value: str,
    ) -> StoryMemoryEntry:
        """Track a continuity item for a scene.

        category is one of: "wound", "prop", "costume", "emotional_state",
        "knowledge_state". target is the character/object name; value is
        the state description.
        """
        memory_type = f"continuity_{category}"
        if memory_type not in CONTINUITY_MEMORY_TYPES:
            raise ValueError(
                f"Unknown continuity category: {category!r}. "
                f"Expected one of: wound, prop, costume, "
                f"emotional_state, knowledge_state."
            )
        return self.add_memory(
            project_id, scene_id, memory_type, target, value,
        )

    def get_continuity_for_scene(
        self, scene_id: int,
    ) -> list[StoryMemoryEntry]:
        with Session(self._engine) as session:
            stmt = (
                select(StoryMemoryEntry)
                .where(StoryMemoryEntry.scene_id == scene_id)
                .where(StoryMemoryEntry.memory_type.in_(
                    CONTINUITY_MEMORY_TYPES,
                ))
                .order_by(StoryMemoryEntry.memory_type, StoryMemoryEntry.id)
            )
            return list(session.exec(stmt).all())

    def get_continuity_by_category(
        self, project_id: int, category: str,
    ) -> list[StoryMemoryEntry]:
        memory_type = f"continuity_{category}"
        return self.get_memories_by_type(project_id, memory_type)

    # -- Outline Nodes -------------------------------------------------------

    def get_outline_nodes(self, project_id: int) -> list[OutlineNode]:
        with Session(self._engine) as session:
            stmt = (
                select(OutlineNode)
                .where(OutlineNode.project_id == project_id)
                .order_by(OutlineNode.sort_order, OutlineNode.id)
            )
            return list(session.exec(stmt).all())

    def get_outline_node_by_id(self, node_id: int) -> OutlineNode | None:
        with Session(self._engine) as session:
            return session.get(OutlineNode, node_id)

    def get_outline_children(
        self, project_id: int, parent_id: int | None,
    ) -> list[OutlineNode]:
        with Session(self._engine) as session:
            stmt = (
                select(OutlineNode)
                .where(OutlineNode.project_id == project_id)
                .where(OutlineNode.parent_id == parent_id)
                .order_by(OutlineNode.sort_order, OutlineNode.id)
            )
            return list(session.exec(stmt).all())

    def create_outline_node(
        self,
        project_id: int,
        title: str,
        description: str = "",
        parent_id: int | None = None,
        sort_order: int = 0,
        scene_id: int | None = None,
    ) -> OutlineNode:
        with Session(self._engine) as session:
            node = OutlineNode(
                project_id=project_id,
                parent_id=parent_id,
                title=title,
                description=description,
                sort_order=sort_order,
                scene_id=scene_id,
            )
            session.add(node)
            session.commit()
            session.refresh(node)
            return node

    def update_outline_node(
        self,
        node_id: int,
        title: str | None = None,
        description: str | None = None,
        sort_order: int | None = None,
        scene_id: "int | None | object" = _UNSET,
    ) -> None:
        with Session(self._engine) as session:
            node = session.get(OutlineNode, node_id)
            if node is None:
                return
            if title is not None:
                node.title = title
            if description is not None:
                node.description = description
            if sort_order is not None:
                node.sort_order = sort_order
            if scene_id is not _UNSET:   # explicit set/clear of the scene link
                node.scene_id = scene_id  # type: ignore[assignment]
            session.commit()

    def delete_outline_node(self, node_id: int) -> None:
        with Session(self._engine) as session:
            # Collect the subtree in this Session rather than recursively
            # opening nested Sessions. Besides being cheaper, this preserves
            # the single-transaction guarantee of in-memory Database instances.
            pending = [node_id]
            seen: set[int] = set()
            nodes: list[OutlineNode] = []
            while pending:
                current_id = pending.pop()
                if current_id in seen:
                    continue
                seen.add(current_id)
                node = session.get(OutlineNode, current_id)
                if node is None:
                    continue
                nodes.append(node)
                children = session.exec(
                    select(OutlineNode.id).where(
                        OutlineNode.parent_id == current_id
                    )
                ).all()
                pending.extend(int(child_id) for child_id in children)
            for node in reversed(nodes):
                session.delete(node)
            if nodes:
                session.commit()

    def delete_all_outline_nodes(self, project_id: int) -> None:
        with Session(self._engine) as session:
            nodes = session.exec(
                select(OutlineNode)
                .where(OutlineNode.project_id == project_id)
            ).all()
            for node in nodes:
                session.delete(node)
            session.commit()

    # -- Decision Log --------------------------------------------------------

    def get_decision_log(self, project_id: int) -> list[dict]:
        settings = self.get_project_settings(project_id)
        raw = settings.get("decision_log")
        if isinstance(raw, list):
            return raw
        return []

    def append_decision(self, project_id: int, entry: dict) -> None:
        settings = self.get_project_settings(project_id)
        log = settings.get("decision_log")
        if not isinstance(log, list):
            log = []
        log.append(entry)
        settings["decision_log"] = log
        self.save_project_settings(project_id, settings)

    def clear_decision_log(self, project_id: int) -> None:
        settings = self.get_project_settings(project_id)
        settings["decision_log"] = []
        self.save_project_settings(project_id, settings)

    # -- Quantum State --------------------------------------------------------

    def get_quantum_state_json(self, project_id: int) -> str:
        with Session(self._engine) as session:
            record = session.get(QuantumStateRecord, project_id)
            return record.state_json if record else ""

    def save_quantum_state_json(self, project_id: int, state_json: str) -> None:
        from datetime import datetime, timezone
        with Session(self._engine) as session:
            record = session.get(QuantumStateRecord, project_id)
            if record is None:
                record = QuantumStateRecord(
                    project_id=project_id,
                    state_json=state_json,
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(record)
            else:
                record.state_json = state_json
                record.updated_at = datetime.now(timezone.utc)
            session.commit()

    # -- Chat -----------------------------------------------------------------

    def add_chat_message(
        self,
        project_id: int,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessage:
        import json
        with Session(self._engine) as session:
            msg = ChatMessage(
                project_id=project_id,
                role=role,
                content=content,
                metadata_json=json.dumps(metadata) if metadata else "",
            )
            session.add(msg)
            session.commit()
            session.refresh(msg)
            return msg

    def get_chat_messages(
        self, project_id: int, limit: int | None = None,
    ) -> list[ChatMessage]:
        with Session(self._engine) as session:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.project_id == project_id)
                .order_by(ChatMessage.id)
            )
            results = list(session.exec(stmt).all())
            if limit is not None and limit > 0:
                results = results[-limit:]
            return results

    def get_chat_messages_after(
        self, project_id: int, after_id: int,
    ) -> list[ChatMessage]:
        with Session(self._engine) as session:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.project_id == project_id)
                .where(ChatMessage.id > after_id)
                .order_by(ChatMessage.id)
            )
            return list(session.exec(stmt).all())

    def clear_chat_messages(self, project_id: int) -> None:
        with Session(self._engine) as session:
            stmt = select(ChatMessage).where(
                ChatMessage.project_id == project_id,
            )
            for m in session.exec(stmt).all():
                session.delete(m)
            summary = session.get(ChatSummary, project_id)
            if summary is not None:
                session.delete(summary)
            session.commit()

    def get_chat_summary(self, project_id: int) -> ChatSummary | None:
        with Session(self._engine) as session:
            return session.get(ChatSummary, project_id)

    def update_chat_summary(
        self, project_id: int, summary_text: str, last_id: int,
    ) -> ChatSummary:
        from datetime import datetime, timezone
        with Session(self._engine) as session:
            record = session.get(ChatSummary, project_id)
            if record is None:
                record = ChatSummary(
                    project_id=project_id,
                    summary=summary_text,
                    last_summarized_message_id=last_id,
                )
                session.add(record)
            else:
                record.summary = summary_text
                record.last_summarized_message_id = last_id
                record.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(record)
            return record

    def get_chat_message_metadata(self, message_id: int) -> dict:
        import json
        with Session(self._engine) as session:
            msg = session.get(ChatMessage, message_id)
            if msg is None or not msg.metadata_json:
                return {}
            try:
                return json.loads(msg.metadata_json)
            except (json.JSONDecodeError, TypeError):
                return {}

    def update_chat_message_metadata(
        self, message_id: int, metadata: dict,
    ) -> None:
        import json
        with Session(self._engine) as session:
            msg = session.get(ChatMessage, message_id)
            if msg is None:
                return
            msg.metadata_json = json.dumps(metadata) if metadata else ""
            session.commit()

    # -- Stages ---------------------------------------------------------------

    def create_stage(
        self,
        project_id: int,
        name: str,
        *,
        description: str = "",
        parent_stage_id: int | None = None,
        scope_type: str = "project",
        scope_id: int | None = None,
        status: str = "alternate",
        metadata: dict | None = None,
    ) -> Stage:
        import json
        with Session(self._engine) as session:
            stage = Stage(
                project_id=project_id,
                name=name,
                description=description,
                parent_stage_id=parent_stage_id,
                scope_type=scope_type,
                scope_id=scope_id,
                status=status,
                metadata_json=json.dumps(metadata) if metadata else "",
            )
            session.add(stage)
            session.commit()
            session.refresh(stage)
            return stage

    def get_stage(self, stage_id: int) -> Stage | None:
        with Session(self._engine) as session:
            return session.get(Stage, stage_id)

    def get_all_stages(self, project_id: int) -> list[Stage]:
        with Session(self._engine) as session:
            stmt = (
                select(Stage)
                .where(Stage.project_id == project_id)
                .order_by(Stage.created_at)
            )
            return list(session.exec(stmt).all())

    def get_child_stages(self, stage_id: int) -> list[Stage]:
        with Session(self._engine) as session:
            stmt = (
                select(Stage)
                .where(Stage.parent_stage_id == stage_id)
                .order_by(Stage.created_at)
            )
            return list(session.exec(stmt).all())

    def update_stage(
        self,
        stage_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        metadata: dict | None = None,
    ) -> Stage | None:
        import json
        from datetime import datetime, timezone
        with Session(self._engine) as session:
            stage = session.get(Stage, stage_id)
            if stage is None:
                return None
            if name is not None:
                stage.name = name
            if description is not None:
                stage.description = description
            if status is not None:
                stage.status = status
            if metadata is not None:
                stage.metadata_json = json.dumps(metadata)
            stage.updated_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(stage)
            return stage

    def set_stage_status(
        self, stage_id: int, status: str,
    ) -> Stage | None:
        if status not in ("active", "archived", "canonical", "alternate"):
            return None
        stage = self.get_stage(stage_id)
        if stage is None:
            return None
        if status == "canonical" and stage.scope_type == "project":
            for other in self.get_all_stages(stage.project_id):
                if (
                    other.id != stage_id
                    and other.scope_type == "project"
                    and other.status == "canonical"
                ):
                    self.update_stage(other.id, status="alternate")
        if status == "canonical" and stage.scope_type == "scene" and stage.scope_id is not None:
            for other in self.get_all_stages(stage.project_id):
                if (
                    other.id != stage_id
                    and other.scope_type == "scene"
                    and other.scope_id == stage.scope_id
                    and other.status == "canonical"
                ):
                    self.update_stage(other.id, status="alternate")
        return self.update_stage(stage_id, status=status)

    def delete_stage(self, stage_id: int) -> None:
        with Session(self._engine) as session:
            for snap in session.exec(
                select(StageSnapshot).where(StageSnapshot.stage_id == stage_id)
            ).all():
                session.delete(snap)
            for br in session.exec(
                select(StageBranch).where(
                    (StageBranch.source_stage_id == stage_id)
                    | (StageBranch.target_stage_id == stage_id)
                )
            ).all():
                session.delete(br)
            stage = session.get(Stage, stage_id)
            if stage is not None:
                session.delete(stage)
            session.commit()

    def get_stage_metadata(self, stage_id: int) -> dict:
        import json
        stage = self.get_stage(stage_id)
        if stage is None or not stage.metadata_json:
            return {}
        try:
            return json.loads(stage.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    # -- Stage snapshots ------------------------------------------------------

    def create_stage_snapshot(
        self,
        stage_id: int,
        data_json: str,
        *,
        label: str = "",
        reason: str = "",
        summary: str = "",
    ) -> StageSnapshot:
        with Session(self._engine) as session:
            snap = StageSnapshot(
                stage_id=stage_id,
                label=label,
                reason=reason,
                summary=summary,
                data_json=data_json,
            )
            session.add(snap)
            session.commit()
            session.refresh(snap)
            return snap

    def get_stage_snapshots(self, stage_id: int) -> list[StageSnapshot]:
        with Session(self._engine) as session:
            stmt = (
                select(StageSnapshot)
                .where(StageSnapshot.stage_id == stage_id)
                .order_by(StageSnapshot.created_at)
            )
            return list(session.exec(stmt).all())

    def get_snapshot(self, snapshot_id: int) -> StageSnapshot | None:
        with Session(self._engine) as session:
            return session.get(StageSnapshot, snapshot_id)

    # -- Stage branches -------------------------------------------------------

    def create_stage_branch(
        self,
        source_stage_id: int,
        target_stage_id: int,
        branch_reason: str = "",
    ) -> StageBranch:
        with Session(self._engine) as session:
            br = StageBranch(
                source_stage_id=source_stage_id,
                target_stage_id=target_stage_id,
                branch_reason=branch_reason,
            )
            session.add(br)
            session.commit()
            session.refresh(br)
            return br

    def get_branches_from(self, stage_id: int) -> list[StageBranch]:
        with Session(self._engine) as session:
            stmt = select(StageBranch).where(
                StageBranch.source_stage_id == stage_id,
            )
            return list(session.exec(stmt).all())

    # -- Screenplay story links (Phase 10E) ----------------------------------

    def create_story_link(self, project_id: int, **fields) -> StoryLink:
        """Persist a confirmed/tracked story link. Never called automatically —
        only on explicit user confirmation."""
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        link = StoryLink(project_id=project_id, **fields)
        link.updated_at = _now()
        with Session(self._engine) as session:
            session.add(link)
            session.commit()
            session.refresh(link)
            return link

    def get_story_links(
        self, project_id: int, *, status: str | None = None,
        link_type: str | None = None,
    ) -> list[StoryLink]:
        with Session(self._engine) as session:
            stmt = select(StoryLink).where(StoryLink.project_id == project_id)
            if status is not None:
                stmt = stmt.where(StoryLink.status == status)
            if link_type is not None:
                stmt = stmt.where(StoryLink.link_type == link_type)
            return list(session.exec(stmt).all())

    def get_story_link_by_id(self, link_id: int) -> "StoryLink | None":
        with Session(self._engine) as session:
            return session.get(StoryLink, link_id)

    def update_story_link_status(self, link_id: int, status: str) -> "StoryLink | None":
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            link = session.get(StoryLink, link_id)
            if link is None:
                return None
            link.status = status
            link.updated_at = _now()
            session.add(link)
            session.commit()
            session.refresh(link)
            return link

    def delete_story_link(self, link_id: int) -> bool:
        with Session(self._engine) as session:
            link = session.get(StoryLink, link_id)
            if link is None:
                return False
            session.delete(link)
            session.commit()
            return True

    # -- Production drafts (Phase 10J) ---------------------------------------

    def create_production_draft(self, project_id: int, **fields) -> ProductionDraft:
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        draft = ProductionDraft(project_id=project_id, **fields)
        draft.updated_at = _now()
        with Session(self._engine) as session:
            session.add(draft)
            session.commit()
            session.refresh(draft)
            return draft

    def get_production_drafts(self, project_id: int) -> list[ProductionDraft]:
        with Session(self._engine) as session:
            stmt = select(ProductionDraft).where(
                ProductionDraft.project_id == project_id)
            return list(session.exec(stmt).all())

    def get_active_production_draft(self, project_id: int) -> "ProductionDraft | None":
        with Session(self._engine) as session:
            stmt = select(ProductionDraft).where(
                ProductionDraft.project_id == project_id,
                ProductionDraft.is_active == True,  # noqa: E712
            )
            return session.exec(stmt).first()

    def update_production_draft(self, draft_id: int, **fields) -> "ProductionDraft | None":
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            draft = session.get(ProductionDraft, draft_id)
            if draft is None:
                return None
            for k, v in fields.items():
                if hasattr(draft, k):
                    setattr(draft, k, v)
            draft.updated_at = _now()
            session.add(draft)
            session.commit()
            session.refresh(draft)
            return draft

    # Scene numbers.
    def set_production_scene_number(self, project_id: int, draft_id: int,
                                    scene_id: int, **fields) -> ProductionSceneNumber:
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            stmt = select(ProductionSceneNumber).where(
                ProductionSceneNumber.draft_id == draft_id,
                ProductionSceneNumber.scene_id == scene_id)
            row = session.exec(stmt).first()
            if row is None:
                row = ProductionSceneNumber(project_id=project_id, draft_id=draft_id,
                                            scene_id=scene_id)
            for k, v in fields.items():
                if hasattr(row, k):
                    setattr(row, k, v)
            row.updated_at = _now()
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_production_scene_numbers(self, draft_id: int) -> list[ProductionSceneNumber]:
        with Session(self._engine) as session:
            stmt = select(ProductionSceneNumber).where(
                ProductionSceneNumber.draft_id == draft_id,
            ).order_by(ProductionSceneNumber.sort_index)
            return list(session.exec(stmt).all())

    # Revision sets + changes.
    def create_revision_set(self, project_id: int, draft_id: int, **fields) -> RevisionSet:
        from logosforge.models.models import _now
        rs = RevisionSet(project_id=project_id, draft_id=draft_id, **fields)
        rs.updated_at = _now()
        with Session(self._engine) as session:
            session.add(rs)
            session.commit()
            session.refresh(rs)
            return rs

    def get_revision_sets(self, draft_id: int) -> list[RevisionSet]:
        with Session(self._engine) as session:
            stmt = select(RevisionSet).where(
                RevisionSet.draft_id == draft_id).order_by(RevisionSet.id)
            return list(session.exec(stmt).all())

    def update_revision_set(self, revision_set_id: int, **fields) -> "RevisionSet | None":
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            rs = session.get(RevisionSet, revision_set_id)
            if rs is None:
                return None
            for k, v in fields.items():
                if hasattr(rs, k):
                    setattr(rs, k, v)
            rs.updated_at = _now()
            session.add(rs)
            session.commit()
            session.refresh(rs)
            return rs

    def create_revision_change(self, project_id: int, draft_id: int,
                               revision_set_id: int, **fields) -> RevisionChange:
        rc = RevisionChange(project_id=project_id, draft_id=draft_id,
                            revision_set_id=revision_set_id, **fields)
        with Session(self._engine) as session:
            session.add(rc)
            session.commit()
            session.refresh(rc)
            return rc

    def get_revision_changes(self, draft_id: int) -> list[RevisionChange]:
        with Session(self._engine) as session:
            stmt = select(RevisionChange).where(
                RevisionChange.draft_id == draft_id).order_by(RevisionChange.id)
            return list(session.exec(stmt).all())

    # -- Revision impact reports (Phase 10K) ---------------------------------

    def create_revision_impact_report(self, project_id: int, *, items=None,
                                      diff=None, **fields) -> RevisionImpactReport:
        """Persist an impact report + its items (+ optional diff snapshot).

        *items* is a list of dicts (RevisionImpactItem fields); *diff* is an
        optional dict (RevisionDiffSnapshot fields). Explicit/user-confirmed.
        """
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        report = RevisionImpactReport(project_id=project_id, **fields)
        report.updated_at = _now()
        with Session(self._engine) as session:
            session.add(report)
            session.commit()
            session.refresh(report)
            for it in (items or []):
                it = dict(it)
                it.pop("project_id", None)
                it.pop("report_id", None)
                session.add(RevisionImpactItem(
                    project_id=project_id, report_id=report.id, **it))
            if diff is not None:
                d = dict(diff)
                d.pop("project_id", None)
                session.add(RevisionDiffSnapshot(project_id=project_id, **d))
            session.commit()
            session.refresh(report)
            return report

    def get_revision_impact_reports(self, project_id: int, *,
                                    scene_id: int | None = None,
                                    ) -> list[RevisionImpactReport]:
        with Session(self._engine) as session:
            stmt = select(RevisionImpactReport).where(
                RevisionImpactReport.project_id == project_id)
            if scene_id is not None:
                stmt = stmt.where(RevisionImpactReport.scene_id == scene_id)
            stmt = stmt.order_by(RevisionImpactReport.id)
            return list(session.exec(stmt).all())

    def get_latest_revision_impact_report(self, project_id: int,
                                          ) -> "RevisionImpactReport | None":
        reports = self.get_revision_impact_reports(project_id)
        return reports[-1] if reports else None

    def get_revision_impact_items(
        self,
        report_id: int,
        *,
        limit: int | None = None,
    ) -> list[RevisionImpactItem]:
        with Session(self._engine) as session:
            stmt = select(RevisionImpactItem).where(
                RevisionImpactItem.report_id == report_id).order_by(
                RevisionImpactItem.id)
            if limit is not None:
                if (
                    isinstance(limit, bool)
                    or not isinstance(limit, int)
                    or limit < 0
                ):
                    raise ValueError("revision impact item limit must be non-negative")
                stmt = stmt.limit(limit)
            return list(session.exec(stmt).all())

    # -- Rewrite sandbox (Phase 10L) -----------------------------------------

    def create_rewrite_session(self, project_id: int, **fields) -> RewriteSession:
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        s = RewriteSession(project_id=project_id, **fields)
        s.updated_at = _now()
        with Session(self._engine) as session:
            session.add(s)
            session.commit()
            session.refresh(s)
            return s

    def get_rewrite_sessions(self, project_id: int, *, status: str | None = None,
                             ) -> list[RewriteSession]:
        with Session(self._engine) as session:
            stmt = select(RewriteSession).where(RewriteSession.project_id == project_id)
            if status is not None:
                stmt = stmt.where(RewriteSession.status == status)
            return list(session.exec(stmt.order_by(RewriteSession.id)).all())

    def get_rewrite_session(self, session_id: int) -> "RewriteSession | None":
        with Session(self._engine) as session:
            return session.get(RewriteSession, session_id)

    def get_latest_rewrite_session(self, project_id: int, *, status: str | None = None,
                                   ) -> "RewriteSession | None":
        rows = self.get_rewrite_sessions(project_id, status=status)
        return rows[-1] if rows else None

    def update_rewrite_session(self, session_id: int, **fields) -> "RewriteSession | None":
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            s = session.get(RewriteSession, session_id)
            if s is None:
                return None
            for k, v in fields.items():
                if hasattr(s, k):
                    setattr(s, k, v)
            s.updated_at = _now()
            session.add(s)
            session.commit()
            session.refresh(s)
            return s

    def create_rewrite_variant(self, project_id: int, session_id: int,
                               **fields) -> RewriteVariant:
        from logosforge.models.models import _now
        v = RewriteVariant(project_id=project_id, session_id=session_id, **fields)
        v.updated_at = _now()
        with Session(self._engine) as session:
            session.add(v)
            session.commit()
            session.refresh(v)
            return v

    def get_rewrite_variants(self, session_id: int) -> list[RewriteVariant]:
        with Session(self._engine) as session:
            stmt = select(RewriteVariant).where(
                RewriteVariant.session_id == session_id).order_by(RewriteVariant.id)
            return list(session.exec(stmt).all())

    def get_rewrite_variant(self, variant_id: int) -> "RewriteVariant | None":
        with Session(self._engine) as session:
            return session.get(RewriteVariant, variant_id)

    def update_rewrite_variant(self, variant_id: int, **fields) -> "RewriteVariant | None":
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            v = session.get(RewriteVariant, variant_id)
            if v is None:
                return None
            for k, val in fields.items():
                if hasattr(v, k):
                    setattr(v, k, val)
            v.updated_at = _now()
            session.add(v)
            session.commit()
            session.refresh(v)
            return v

    def create_rewrite_apply_record(self, project_id: int, session_id: int,
                                    variant_id: int, **fields) -> RewriteApplyRecord:
        r = RewriteApplyRecord(project_id=project_id, session_id=session_id,
                              variant_id=variant_id, **fields)
        with Session(self._engine) as session:
            session.add(r)
            session.commit()
            session.refresh(r)
            return r

    # -- Controlled apply (Phase 10M) ----------------------------------------

    def create_apply_operation(self, project_id: int, *, conflicts=None,
                               **fields) -> ControlledApplyOperation:
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        op = ControlledApplyOperation(project_id=project_id, **fields)
        op.updated_at = _now()
        with Session(self._engine) as session:
            session.add(op)
            session.commit()
            session.refresh(op)
            for c in (conflicts or []):
                c = dict(c)
                c.pop("project_id", None)
                c.pop("operation_id", None)
                session.add(ControlledApplyConflict(
                    project_id=project_id, operation_id=op.id, **c))
            session.commit()
            session.refresh(op)
            return op

    def get_apply_operation(self, operation_id: int) -> "ControlledApplyOperation | None":
        with Session(self._engine) as session:
            return session.get(ControlledApplyOperation, operation_id)

    def get_apply_operations(self, project_id: int, *, status: str | None = None,
                             ) -> list[ControlledApplyOperation]:
        with Session(self._engine) as session:
            stmt = select(ControlledApplyOperation).where(
                ControlledApplyOperation.project_id == project_id)
            if status is not None:
                stmt = stmt.where(ControlledApplyOperation.status == status)
            return list(session.exec(stmt.order_by(ControlledApplyOperation.id)).all())

    def update_apply_operation(self, operation_id: int, **fields
                               ) -> "ControlledApplyOperation | None":
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            op = session.get(ControlledApplyOperation, operation_id)
            if op is None:
                return None
            for k, v in fields.items():
                if hasattr(op, k):
                    setattr(op, k, v)
            op.updated_at = _now()
            session.add(op)
            session.commit()
            session.refresh(op)
            return op

    def get_apply_conflicts(self, operation_id: int) -> list[ControlledApplyConflict]:
        with Session(self._engine) as session:
            stmt = select(ControlledApplyConflict).where(
                ControlledApplyConflict.operation_id == operation_id).order_by(
                ControlledApplyConflict.id)
            return list(session.exec(stmt).all())

    # -- Guided workflows (Phase 10O) ----------------------------------------

    def create_workflow_run(self, project_id: int, **fields) -> WorkflowRun:
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        run = WorkflowRun(project_id=project_id, **fields)
        run.updated_at = _now()
        with Session(self._engine) as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    def get_workflow_run(self, run_id: int) -> "WorkflowRun | None":
        with Session(self._engine) as session:
            return session.get(WorkflowRun, run_id)

    def get_workflow_runs(self, project_id: int, *, status: str | None = None,
                          ) -> list[WorkflowRun]:
        with Session(self._engine) as session:
            stmt = select(WorkflowRun).where(WorkflowRun.project_id == project_id)
            if status is not None:
                stmt = stmt.where(WorkflowRun.status == status)
            return list(session.exec(stmt.order_by(WorkflowRun.id)).all())

    def update_workflow_run(self, run_id: int, **fields) -> "WorkflowRun | None":
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            run = session.get(WorkflowRun, run_id)
            if run is None:
                return None
            for k, v in fields.items():
                if hasattr(run, k):
                    setattr(run, k, v)
            run.updated_at = _now()
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    def create_workflow_step_state(self, project_id: int, workflow_run_id: int,
                                   **fields) -> WorkflowStepState:
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        fields.pop("workflow_run_id", None)
        st = WorkflowStepState(project_id=project_id,
                               workflow_run_id=workflow_run_id, **fields)
        st.updated_at = _now()
        with Session(self._engine) as session:
            session.add(st)
            session.commit()
            session.refresh(st)
            return st

    def get_workflow_step_states(self, workflow_run_id: int) -> list[WorkflowStepState]:
        with Session(self._engine) as session:
            stmt = select(WorkflowStepState).where(
                WorkflowStepState.workflow_run_id == workflow_run_id).order_by(
                WorkflowStepState.sort_index, WorkflowStepState.id)
            return list(session.exec(stmt).all())

    def get_workflow_step_state(self, step_state_id: int) -> "WorkflowStepState | None":
        with Session(self._engine) as session:
            return session.get(WorkflowStepState, step_state_id)

    def update_workflow_step_state(self, step_state_id: int, **fields
                                   ) -> "WorkflowStepState | None":
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            st = session.get(WorkflowStepState, step_state_id)
            if st is None:
                return None
            for k, v in fields.items():
                if hasattr(st, k):
                    setattr(st, k, v)
            st.updated_at = _now()
            session.add(st)
            session.commit()
            session.refresh(st)
            return st

    def create_workflow_event(self, project_id: int, workflow_run_id: int,
                              **fields) -> WorkflowEvent:
        fields.pop("project_id", None)
        fields.pop("workflow_run_id", None)
        ev = WorkflowEvent(project_id=project_id,
                           workflow_run_id=workflow_run_id, **fields)
        with Session(self._engine) as session:
            session.add(ev)
            session.commit()
            session.refresh(ev)
            return ev

    def get_workflow_events(
        self,
        workflow_run_id: int,
        *,
        limit: int | None = None,
    ) -> list[WorkflowEvent]:
        with Session(self._engine) as session:
            stmt = select(WorkflowEvent).where(
                WorkflowEvent.workflow_run_id == workflow_run_id
            )
            if limit is None:
                return list(session.exec(stmt.order_by(WorkflowEvent.id)).all())
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
                raise WorkflowCommandError("event limit must be between 1 and 200")
            rows = list(session.exec(
                stmt.order_by(WorkflowEvent.id.desc()).limit(limit)
            ).all())
            rows.reverse()
            return rows

    def get_project_workflow_events(
        self,
        project_id: int,
        workflow_run_id: int,
        *,
        limit: int = 100,
    ) -> "list[WorkflowEvent] | None":
        """Return a bounded event tail, or ``None`` for missing/foreign runs."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise WorkflowCommandError("event limit must be between 1 and 200")
        with Session(self._engine) as session:
            run = session.get(WorkflowRun, workflow_run_id)
            if run is None or int(run.project_id) != int(project_id):
                return None
            rows = list(session.exec(
                select(WorkflowEvent)
                .where(
                    WorkflowEvent.project_id == project_id,
                    WorkflowEvent.workflow_run_id == workflow_run_id,
                )
                .order_by(WorkflowEvent.id.desc())
                .limit(limit)
            ).all())
            rows.reverse()
            return rows

    def _workflow_run_snapshot_in_session(
        self,
        session: Session,
        project_id: int,
        run_id: int,
    ) -> "WorkflowRunSnapshot | None":
        from logosforge.guided_workflows.revision import workflow_run_revision

        run = session.get(WorkflowRun, run_id)
        if run is None or int(run.project_id) != int(project_id):
            return None
        steps = tuple(session.exec(
            select(WorkflowStepState)
            .where(WorkflowStepState.workflow_run_id == run_id)
            .order_by(WorkflowStepState.sort_index, WorkflowStepState.id)
        ).all())
        if any(int(step.project_id) != int(run.project_id) for step in steps):
            raise RuntimeError(
                "Guided Workflow step project does not match its run"
            )
        if len({step.step_id for step in steps}) != len(steps):
            raise RuntimeError("Guided Workflow contains duplicate step identities")
        return WorkflowRunSnapshot(
            run=run,
            steps=steps,
            revision=workflow_run_revision(run, steps),
        )

    def read_workflow_run_snapshot(
        self,
        project_id: int,
        run_id: int,
    ) -> "WorkflowRunSnapshot | None":
        """Read one project-owned workflow run and its deterministic revision."""
        with Session(self._engine, expire_on_commit=False) as session:
            snapshot = self._workflow_run_snapshot_in_session(
                session, project_id, run_id,
            )
            session.expunge_all()
            return snapshot

    def read_workflow_run_snapshot_by_id(
        self,
        run_id: int,
    ) -> "WorkflowRunSnapshot | None":
        """Compatibility read for callers that already hold a trusted run id."""
        with Session(self._engine, expire_on_commit=False) as session:
            run = session.get(WorkflowRun, run_id)
            if run is None:
                return None
            snapshot = self._workflow_run_snapshot_in_session(
                session, int(run.project_id), run_id,
            )
            session.expunge_all()
            return snapshot

    def read_workflow_runs_snapshot(
        self,
        project_id: int,
    ) -> "tuple[WorkflowRunSnapshot, ...] | None":
        """Read every run and step from one coherent SQLite snapshot."""
        from logosforge.guided_workflows.revision import workflow_run_revision

        with Session(self._engine, expire_on_commit=False) as session:
            project = session.get(Project, project_id)
            if project is None:
                return None
            runs = tuple(session.exec(
                select(WorkflowRun)
                .where(WorkflowRun.project_id == project_id)
                .order_by(WorkflowRun.id)
            ).all())
            project_steps = tuple(session.exec(
                select(WorkflowStepState)
                .where(WorkflowStepState.project_id == project_id)
                .order_by(
                    WorkflowStepState.workflow_run_id,
                    WorkflowStepState.sort_index,
                    WorkflowStepState.id,
                )
            ).all())
            run_ids = {int(run.id) for run in runs}
            linked_steps = tuple(session.exec(
                select(WorkflowStepState)
                .where(WorkflowStepState.workflow_run_id.in_(run_ids))
                .order_by(
                    WorkflowStepState.workflow_run_id,
                    WorkflowStepState.sort_index,
                    WorkflowStepState.id,
                )
            ).all()) if run_ids else ()
            if any(
                int(step.workflow_run_id) not in run_ids
                for step in project_steps
            ):
                raise RuntimeError("Guided Workflow contains an orphaned step")
            if any(
                int(step.project_id) != int(project_id)
                for step in linked_steps
            ):
                raise RuntimeError(
                    "Guided Workflow step project does not match its run"
                )
            all_steps_by_id = {
                int(step.id): step for step in (*project_steps, *linked_steps)
            }
            all_steps = tuple(sorted(
                all_steps_by_id.values(),
                key=lambda step: (
                    int(step.workflow_run_id),
                    int(step.sort_index),
                    int(step.id),
                ),
            ))
            steps_by_run: dict[int, list[WorkflowStepState]] = {
                run_id: [] for run_id in run_ids
            }
            for step in all_steps:
                steps_by_run[int(step.workflow_run_id)].append(step)
            snapshots: list[WorkflowRunSnapshot] = []
            for run in runs:
                steps = tuple(steps_by_run[int(run.id)])
                if len({step.step_id for step in steps}) != len(steps):
                    raise RuntimeError(
                        "Guided Workflow contains duplicate step identities"
                    )
                snapshots.append(WorkflowRunSnapshot(
                    run=run,
                    steps=steps,
                    revision=workflow_run_revision(run, steps),
                ))
            session.expunge_all()
            return tuple(snapshots)

    def get_workflow_command_receipt(
        self,
        project_id: int,
        idempotency_key: str,
    ) -> "WorkflowCommandReceiptData | None":
        key_hash = _workflow_idempotency_key_hash(idempotency_key)
        with Session(self._engine) as session:
            row = session.get(
                WorkflowCommandReceipt,
                (int(project_id), key_hash),
            )
            return (
                _decode_workflow_command_receipt(row)
                if row is not None
                else None
            )

    def execute_workflow_command(
        self,
        project_id: int,
        *,
        kind: str,
        idempotency_key: str,
        expected_revision: str = "",
        _legacy_allow_noncurrent: bool = False,
        **fields,
    ) -> WorkflowCommandResult:
        """Apply one project-scoped Guided Workflow command atomically.

        The transaction mutates only ``Workflow*`` rows.  Every successful
        command, including an exact no-op refresh, commits a durable receipt in
        the same transaction.  Receipt replay is checked before optimistic
        concurrency and lifecycle guards, making ambiguous retries recoverable
        after a process restart without repeating an event or transition.
        """
        from logosforge.guided_workflows.models import KIND_CHECK
        from logosforge.guided_workflows.registry import get_template
        from logosforge.models.models import _now
        from logosforge.writing_modes import get_project_writing_mode

        expected_revision, normalized = _normalize_workflow_command(
            kind, expected_revision, fields,
        )
        key_hash = _workflow_idempotency_key_hash(idempotency_key)
        request_digest = _workflow_command_request_digest(
            project_id, kind, expected_revision, normalized,
        )

        with self.workflow_write_lock(project_id):
            with Session(self._engine, expire_on_commit=False) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    project = session.get(Project, project_id)
                    if project is None:
                        raise WorkflowProjectNotFound(project_id)

                    receipt_row = session.get(
                        WorkflowCommandReceipt,
                        (int(project_id), key_hash),
                    )
                    if receipt_row is not None:
                        receipt = _decode_workflow_command_receipt(receipt_row)
                        if not hmac.compare_digest(
                            receipt.request_digest, request_digest,
                        ):
                            raise WorkflowIdempotencyKeyConflict(
                                "Idempotency-Key was already used for a "
                                "different Guided Workflow command"
                            )
                        replay = self._workflow_run_snapshot_in_session(
                            session, project_id, receipt.run_id,
                        )
                        if replay is None:
                            raise RuntimeError(
                                "Guided Workflow receipt references a missing run"
                            )
                        session.expunge_all()
                        session.rollback()
                        return WorkflowCommandResult(
                            snapshot=replay,
                            changed=False,
                            replayed=True,
                            applied_revision=receipt.applied_revision,
                        )

                    if kind == "start_workflow":
                        template = get_template(normalized["template_id"])
                        if template is None:
                            raise WorkflowCommandError("Unknown workflow template")
                        mode = get_project_writing_mode(project)
                        if not template.applies_to(mode):
                            raise WorkflowCommandError(
                                "Workflow template is not available for this writing mode"
                            )
                        duplicate = session.exec(
                            select(WorkflowRun).where(
                                WorkflowRun.project_id == project_id,
                                WorkflowRun.template_id == template.id,
                                WorkflowRun.status.in_((
                                    "active", "paused", "blocked",
                                )),
                            )
                        ).first()
                        if duplicate is not None:
                            raise WorkflowStateConflict(
                                "An active run of this workflow already exists"
                            )
                        template_steps = template.steps_for_mode(mode)
                        run = WorkflowRun(
                            project_id=project_id,
                            template_id=template.id,
                            title=normalized.get("title", template.title),
                            writing_mode=mode,
                            status="active",
                            current_step_id=(
                                template_steps[0].id if template_steps else ""
                            ),
                        )
                        session.add(run)
                        session.flush()
                        for index, template_step in enumerate(template_steps):
                            session.add(WorkflowStepState(
                                project_id=project_id,
                                workflow_run_id=int(run.id),
                                step_id=template_step.id,
                                title=template_step.title,
                                status="active" if index == 0 else "pending",
                                section_name=template_step.section_name or None,
                                action_id=template_step.action_id or None,
                                sort_index=index,
                            ))
                        session.add(WorkflowEvent(
                            project_id=project_id,
                            workflow_run_id=int(run.id),
                            event_type="started",
                            message=f"Started workflow '{run.title}'.",
                        ))
                        session.flush()
                        updated = self._workflow_run_snapshot_in_session(
                            session, project_id, int(run.id),
                        )
                        assert updated is not None
                        session.add(WorkflowCommandReceipt(
                            project_id=project_id,
                            idempotency_key_hash=key_hash,
                            request_digest=request_digest,
                            result_json=_workflow_receipt_result_json(
                                kind=kind,
                                expected_revision="",
                                applied_revision=updated.revision,
                                original_changed=True,
                                run_id=int(run.id),
                            ),
                        ))
                        session.commit()
                        session.expunge_all()
                        return WorkflowCommandResult(
                            snapshot=updated,
                            changed=True,
                            applied_revision=updated.revision,
                        )

                    run_id = normalized["run_id"]
                    current = self._workflow_run_snapshot_in_session(
                        session, project_id, run_id,
                    )
                    if current is None:
                        raise WorkflowRunNotFound(run_id)
                    if not hmac.compare_digest(
                        expected_revision, current.revision,
                    ):
                        raise WorkflowRevisionConflict(
                            expected_revision, current.revision,
                        )

                    run = current.run
                    steps = list(current.steps)
                    template = get_template(run.template_id)

                    def event(
                        event_type: str,
                        message: str,
                        step_id: str | None = None,
                    ) -> None:
                        session.add(WorkflowEvent(
                            project_id=project_id,
                            workflow_run_id=run_id,
                            step_id=step_id,
                            event_type=event_type,
                            message=message,
                        ))

                    def require_status(*statuses: str) -> None:
                        if run.status not in statuses:
                            raise WorkflowStateConflict(
                                f"Command {kind} is unavailable while the "
                                f"workflow is {run.status}"
                            )

                    def requested_step() -> WorkflowStepState:
                        step_id = normalized["step_id"]
                        state = next((
                            item for item in steps if item.step_id == step_id
                        ), None)
                        if state is None:
                            raise WorkflowStepNotFound(step_id)
                        return state

                    def recompute_pointer() -> None:
                        open_steps = [
                            item for item in steps
                            if item.status in {"pending", "active"}
                        ]
                        if open_steps:
                            first = open_steps[0]
                            for item in open_steps:
                                desired = "active" if item is first else "pending"
                                if item.status != desired:
                                    item.status = desired
                                    item.updated_at = _now()
                                    session.add(item)
                            run.current_step_id = first.step_id
                        else:
                            blocked_steps = [
                                item for item in steps
                                if item.status == "blocked"
                            ]
                            if blocked_steps:
                                run.status = "blocked"
                                run.current_step_id = blocked_steps[0].step_id
                                run.completed_at = None
                                event(
                                    "blocked",
                                    f"Workflow blocked at step "
                                    f"'{blocked_steps[0].title}'.",
                                    blocked_steps[0].step_id,
                                )
                            else:
                                run.status = "completed"
                                run.current_step_id = ""
                                run.completed_at = _now()
                                event("completed", "Workflow completed.")

                    if kind in {"complete_step", "skip_step"}:
                        require_status("active")
                        state = requested_step()
                        if state.status not in {"pending", "active"} or (
                            not _legacy_allow_noncurrent
                            and (
                                state.status != "active"
                                or state.step_id != run.current_step_id
                            )
                        ):
                            raise WorkflowStateConflict(
                                "Only the current active step can be changed"
                            )
                        state.status = (
                            "completed" if kind == "complete_step" else "skipped"
                        )
                        if normalized.get("notes"):
                            state.notes = normalized["notes"]
                        state.updated_at = _now()
                        session.add(state)
                        event_type = (
                            "step_completed"
                            if kind == "complete_step"
                            else "step_skipped"
                        )
                        verb = "Completed" if kind == "complete_step" else "Skipped"
                        event(
                            event_type,
                            f"{verb} step '{state.title}'.",
                            state.step_id,
                        )
                        recompute_pointer()

                    elif kind == "advance":
                        require_status("active")
                        current_step = next((
                            item for item in steps
                            if item.step_id == run.current_step_id
                            and item.status == "active"
                        ), None)
                        if current_step is None:
                            raise WorkflowStateConflict(
                                "Workflow has no current active step"
                            )
                        open_steps = [
                            item for item in steps
                            if item.status in {"pending", "active"}
                        ]
                        current_index = open_steps.index(current_step)
                        next_step = open_steps[
                            (current_index + 1) % len(open_steps)
                        ]
                        if next_step is not current_step:
                            current_step.status = "pending"
                            current_step.updated_at = _now()
                            next_step.status = "active"
                            next_step.updated_at = _now()
                            run.current_step_id = next_step.step_id
                            session.add(current_step)
                            session.add(next_step)
                            event(
                                "advanced",
                                f"Advanced to step '{next_step.title}'.",
                                next_step.step_id,
                            )

                    elif kind == "refresh":
                        require_status("active")
                        refreshed = False
                        for state in steps:
                            template_step = next((
                                item for item in (
                                    template.steps if template else ()
                                )
                                if item.id == state.step_id
                            ), None)
                            if (
                                state.status in {"pending", "active"}
                                and template_step is not None
                                and template_step.kind == KIND_CHECK
                                and template_step.completion_check
                                and _workflow_completion_check_in_session(
                                    session,
                                    project,
                                    template_step.completion_check,
                                )
                            ):
                                state.status = "completed"
                                state.updated_at = _now()
                                session.add(state)
                                event(
                                    "step_auto_completed",
                                    "Auto-completed verifiable step "
                                    f"'{state.title}'.",
                                    state.step_id,
                                )
                                refreshed = True
                        if refreshed:
                            recompute_pointer()

                    elif kind == "pause":
                        require_status("active")
                        run.status = "paused"
                        event("paused", "Workflow paused.")

                    elif kind == "resume":
                        require_status("paused", "blocked")
                        if run.status == "blocked":
                            blocked_steps = [
                                item for item in steps if item.status == "blocked"
                            ]
                            current_blocked = next((
                                item for item in blocked_steps
                                if item.step_id == run.current_step_id
                            ), None)
                            if current_blocked is None and blocked_steps:
                                current_blocked = blocked_steps[0]
                                run.current_step_id = current_blocked.step_id
                            if current_blocked is None:
                                raise WorkflowStateConflict(
                                    "Blocked workflow has no blocked step to resume"
                                )
                            for item in blocked_steps:
                                item.status = (
                                    "active"
                                    if item is current_blocked
                                    else "pending"
                                )
                                item.updated_at = _now()
                                session.add(item)
                        run.status = "active"
                        event("resumed", "Workflow resumed.")

                    elif kind == "cancel":
                        require_status("active", "paused", "blocked")
                        run.status = "cancelled"
                        run.current_step_id = ""
                        run.completed_at = _now()
                        event("cancelled", "Workflow cancelled.")

                    session.add(run)
                    session.flush()
                    updated = self._workflow_run_snapshot_in_session(
                        session, project_id, run_id,
                    )
                    assert updated is not None
                    changed = not hmac.compare_digest(
                        current.revision, updated.revision,
                    )
                    if changed:
                        run.updated_at = _now()
                        session.add(run)
                        session.flush()
                        updated = self._workflow_run_snapshot_in_session(
                            session, project_id, run_id,
                        )
                        assert updated is not None

                    session.add(WorkflowCommandReceipt(
                        project_id=project_id,
                        idempotency_key_hash=key_hash,
                        request_digest=request_digest,
                        result_json=_workflow_receipt_result_json(
                            kind=kind,
                            expected_revision=expected_revision,
                            applied_revision=updated.revision,
                            original_changed=changed,
                            run_id=run_id,
                        ),
                    ))
                    session.commit()
                    session.expunge_all()
                    return WorkflowCommandResult(
                        snapshot=updated,
                        changed=changed,
                        applied_revision=updated.revision,
                    )
                except Exception:
                    session.rollback()
                    raise

    # -- Knowledge graph (Phase 10P) -----------------------------------------
    # Only user-confirmed / hidden edges (and their nodes) are persisted; the
    # live graph is computed in-memory each build and merges these back in.

    def _knowledge_graph_review_snapshot_in_session(
        self,
        session: Session,
        project_id: int,
        *,
        validate_unique: bool = True,
    ) -> KnowledgeGraphReviewSnapshot | None:
        """Read the complete persisted review layer in one transaction."""
        from logosforge.knowledge_graph.revision import (
            knowledge_graph_review_revision,
        )

        project = session.get(Project, project_id)
        if project is None:
            return None
        nodes = tuple(session.exec(
            select(KnowledgeGraphNode)
            .where(KnowledgeGraphNode.project_id == project_id)
            .order_by(KnowledgeGraphNode.id)
        ).all())
        edges = tuple(session.exec(
            select(KnowledgeGraphEdge)
            .where(KnowledgeGraphEdge.project_id == project_id)
            .order_by(KnowledgeGraphEdge.id)
        ).all())
        if validate_unique:
            node_keys = [row.node_key for row in nodes]
            edge_keys = [
                (row.source_node_key, row.target_node_key, row.edge_type)
                for row in edges
            ]
            if (
                len(node_keys) != len(set(node_keys))
                or len(edge_keys) != len(set(edge_keys))
            ):
                raise KnowledgeGraphReviewStateCorrupt(
                    "Knowledge Graph review state violates logical uniqueness"
                )
        return KnowledgeGraphReviewSnapshot(
            project=project,
            nodes=nodes,
            edges=edges,
            revision=knowledge_graph_review_revision(
                edges,
                nodes=nodes,
                project_id=project_id,
                project_created_at=project.created_at,
            ),
        )

    def read_knowledge_graph_review_snapshot(
        self,
        project_id: int,
    ) -> KnowledgeGraphReviewSnapshot | None:
        """Return one coherent, detached persisted graph-review snapshot."""
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                snapshot = self._knowledge_graph_review_snapshot_in_session(
                    session, project_id,
                )
                if snapshot is not None:
                    session.expunge_all()
            finally:
                session.rollback()
        return snapshot

    def get_knowledge_graph_command_receipt(
        self,
        project_id: int,
        idempotency_key: str,
    ) -> KnowledgeGraphCommandReceiptData | None:
        """Resolve a completed graph command only within its project scope."""
        key_hash = _knowledge_graph_idempotency_key_hash(idempotency_key)
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                if session.get(Project, project_id) is None:
                    return None
                row = session.get(
                    KnowledgeGraphCommandReceipt,
                    (int(project_id), key_hash),
                )
                if row is None:
                    return None
                receipt = _decode_knowledge_graph_command_receipt(row)
            finally:
                session.rollback()
        return receipt

    def replay_knowledge_graph_command(
        self,
        project_id: int,
        *,
        kind: str,
        expected_revision: str,
        source: str,
        target: str,
        edge_type: str,
        idempotency_key: str,
    ) -> KnowledgeGraphCommandResult | None:
        """Resolve an exact committed retry before rebuilding live graph data."""
        if kind not in _KNOWLEDGE_GRAPH_COMMAND_KINDS:
            raise KnowledgeGraphCommandError(
                f"Unsupported Knowledge Graph command: {kind!r}"
            )
        if (
            not isinstance(expected_revision, str)
            or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
        ):
            raise KnowledgeGraphCommandError(
                "expected_revision must be a lowercase SHA-256 digest"
            )
        identity = _knowledge_graph_edge_identity(source, target, edge_type)
        key_hash = _knowledge_graph_idempotency_key_hash(idempotency_key)
        request_digest = _knowledge_graph_command_request_digest(
            project_id, kind, expected_revision, identity,
        )
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                if session.get(Project, project_id) is None:
                    return None
                row = session.get(
                    KnowledgeGraphCommandReceipt,
                    (int(project_id), key_hash),
                )
                if row is None:
                    return None
                receipt = _decode_knowledge_graph_command_receipt(row)
                if not hmac.compare_digest(
                    receipt.request_digest,
                    request_digest,
                ):
                    raise KnowledgeGraphIdempotencyKeyConflict(
                        "Idempotency-Key was already used for a different "
                        "Knowledge Graph command"
                    )
                current = self._knowledge_graph_review_snapshot_in_session(
                    session,
                    project_id,
                    validate_unique=False,
                )
                assert current is not None
                return KnowledgeGraphCommandResult(
                    revision=current.revision,
                    changed=False,
                    affected_edge=receipt.original_affected_edge,
                    replayed=True,
                    applied_revision=receipt.applied_revision,
                )
            finally:
                session.rollback()

    def execute_knowledge_graph_command(
        self,
        project_id: int,
        *,
        kind: str,
        expected_revision: str,
        source: str,
        target: str,
        edge_type: str,
        idempotency_key: str,
        edge=None,
        source_node=None,
        target_node=None,
    ) -> KnowledgeGraphCommandResult:
        """Atomically review one directional graph edge and store its receipt.

        ``expected_revision`` guards only the coherent persisted review layer;
        the live derived graph is freshly built by the route to resolve ``edge``
        but is not misrepresented as one database snapshot.  Receipt lookup is
        deliberately first so an exact retry remains recoverable after the
        inferred basis disappears.
        """
        from logosforge.knowledge_graph import provenance as graph_provenance
        from logosforge.models.models import _now

        if kind not in _KNOWLEDGE_GRAPH_COMMAND_KINDS:
            raise KnowledgeGraphCommandError(
                f"Unsupported Knowledge Graph command: {kind!r}"
            )
        if (
            not isinstance(expected_revision, str)
            or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
        ):
            raise KnowledgeGraphCommandError(
                "expected_revision must be a lowercase SHA-256 digest"
            )
        identity = _knowledge_graph_edge_identity(source, target, edge_type)
        key_hash = _knowledge_graph_idempotency_key_hash(idempotency_key)
        request_digest = _knowledge_graph_command_request_digest(
            project_id,
            kind,
            expected_revision,
            identity,
        )

        with self.knowledge_graph_write_lock(project_id):
            with Session(self._engine, expire_on_commit=False) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    if session.get(Project, project_id) is None:
                        raise KnowledgeGraphProjectNotFound(project_id)
                    receipt_row = session.get(
                        KnowledgeGraphCommandReceipt,
                        (int(project_id), key_hash),
                    )
                    if receipt_row is not None:
                        receipt = _decode_knowledge_graph_command_receipt(
                            receipt_row,
                        )
                        if not hmac.compare_digest(
                            receipt.request_digest,
                            request_digest,
                        ):
                            raise KnowledgeGraphIdempotencyKeyConflict(
                                "Idempotency-Key was already used for a "
                                "different Knowledge Graph command"
                            )
                        current = self._knowledge_graph_review_snapshot_in_session(
                            session,
                            project_id,
                            validate_unique=False,
                        )
                        assert current is not None
                        session.expunge_all()
                        session.rollback()
                        return KnowledgeGraphCommandResult(
                            revision=current.revision,
                            changed=False,
                            affected_edge=receipt.original_affected_edge,
                            replayed=True,
                            applied_revision=receipt.applied_revision,
                        )

                    current = self._knowledge_graph_review_snapshot_in_session(
                        session, project_id,
                    )
                    assert current is not None

                    if expected_revision != current.revision:
                        raise KnowledgeGraphRevisionConflict(
                            expected_revision,
                            current.revision,
                        )

                    if edge is None or source_node is None or target_node is None:
                        raise KnowledgeGraphEdgeNotFound(identity)
                    internal_source = str(getattr(edge, "source", "") or "")
                    internal_target = str(getattr(edge, "target", "") or "")
                    internal_type = str(getattr(edge, "edge_type", "") or "")
                    if (
                        _knowledge_graph_wire_key(internal_source) != source
                        or _knowledge_graph_wire_key(internal_target) != target
                        or internal_type != edge_type
                        or str(getattr(source_node, "key", "")) != internal_source
                        or str(getattr(target_node, "key", "")) != internal_target
                    ):
                        raise KnowledgeGraphEdgeNotFound(identity)

                    try:
                        edge_metadata_json = json.dumps(
                            dict(getattr(edge, "metadata", {}) or {}),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                    except (TypeError, ValueError) as exc:
                        raise KnowledgeGraphCommandError(
                            "Edge metadata cannot be persisted"
                        ) from exc

                    command_savepoint = session.begin_nested()
                    changed = False
                    nodes = list(current.nodes)
                    edges = list(current.edges)

                    def persist_endpoint(node) -> None:
                        nonlocal changed
                        key = str(node.key)
                        matches = [row for row in nodes if row.node_key == key]
                        if len(matches) > 1:
                            raise KnowledgeGraphCommandError(
                                "Knowledge Graph review state contains duplicate endpoint rows"
                            )
                        persisted = matches[0] if matches else None
                        try:
                            metadata_json = json.dumps(
                                dict(getattr(node, "metadata", {}) or {}),
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                                allow_nan=False,
                            )
                        except (TypeError, ValueError) as exc:
                            raise KnowledgeGraphCommandError(
                                "Node metadata cannot be persisted"
                            ) from exc
                        values = {
                            "node_type": str(getattr(node, "node_type", "") or "")[:128],
                            "source_type": str(getattr(node, "source_type", "") or "")[:128],
                            "source_id": (
                                None
                                if getattr(node, "source_id", None) is None
                                else str(node.source_id)[:512]
                            ),
                            "label": str(getattr(node, "label", "") or "")[:512],
                            "summary": str(getattr(node, "summary", "") or "")[:1000],
                            "metadata_json": metadata_json,
                        }
                        if persisted is None:
                            persisted = KnowledgeGraphNode(
                                project_id=project_id,
                                node_key=key,
                                **values,
                            )
                            session.add(persisted)
                            nodes.append(persisted)
                            changed = True
                        else:
                            endpoint_changed = False
                            for field, value in values.items():
                                if getattr(persisted, field) != value:
                                    setattr(persisted, field, value)
                                    endpoint_changed = True
                                    changed = True
                            if endpoint_changed:
                                persisted.updated_at = _now()

                    matching = [
                        row for row in edges
                        if row.source_node_key == internal_source
                        and row.target_node_key == internal_target
                        and row.edge_type == internal_type
                    ]
                    if len(matching) > 1:
                        raise KnowledgeGraphCommandError(
                            "Knowledge Graph review state contains duplicate edge rows"
                        )
                    persisted_edge = matching[0] if matching else None

                    is_hidden = bool(getattr(edge, "is_hidden", False))
                    is_inferred = bool(getattr(edge, "is_inferred", False))
                    if kind in {"confirm_edge", "hide_edge"} and (
                        is_hidden or not is_inferred
                    ):
                        raise KnowledgeGraphCommandError(
                            f"{kind} requires a visible inferred edge"
                        )
                    if kind == "unhide_edge" and (
                        not is_hidden
                        or persisted_edge is None
                        or not persisted_edge.is_hidden
                    ):
                        raise KnowledgeGraphCommandError(
                            "unhide_edge requires a persisted hidden edge"
                        )

                    # Confirm/hide creates durable review intent; unhide never
                    # invents a default row when no hidden decision exists.
                    if (
                        kind != "unhide_edge"
                        or (
                            persisted_edge is not None
                            and persisted_edge.is_user_confirmed
                        )
                    ):
                        persist_endpoint(source_node)
                        persist_endpoint(target_node)

                    evidence = {
                        "provenance": str(getattr(edge, "provenance", "") or "")[:512],
                        "source_system": str(getattr(edge, "source_system", "") or "")[:128],
                        "explanation": str(getattr(edge, "explanation", "") or "")[:1000],
                        "metadata_json": edge_metadata_json,
                    }
                    if persisted_edge is None and kind in {
                        "confirm_edge", "hide_edge",
                    }:
                        persisted_edge = KnowledgeGraphEdge(
                            project_id=project_id,
                            source_node_key=internal_source,
                            target_node_key=internal_target,
                            edge_type=internal_type,
                            confidence=(
                                graph_provenance.CONF_CONFIRMED
                                if kind == "confirm_edge"
                                else str(getattr(edge, "confidence", "") or "unknown")[:32]
                            ),
                            is_user_confirmed=(
                                True
                                if kind == "confirm_edge"
                                else bool(getattr(edge, "is_user_confirmed", False))
                            ),
                            is_hidden=(kind == "hide_edge"),
                            **evidence,
                        )
                        session.add(persisted_edge)
                        edges.append(persisted_edge)
                        changed = True
                    elif persisted_edge is not None:
                        updates: dict[str, object] = {}
                        if kind == "confirm_edge":
                            updates = {
                                **evidence,
                                "confidence": graph_provenance.CONF_CONFIRMED,
                                "is_user_confirmed": True,
                                "is_hidden": False,
                            }
                        elif kind == "hide_edge":
                            updates = {"is_hidden": True}
                            # Preserve prior confirmation and its evidence.  An
                            # unconfirmed legacy row may fill missing evidence.
                            if not persisted_edge.is_user_confirmed:
                                updates.update({
                                    key: value for key, value in evidence.items()
                                    if not getattr(persisted_edge, key)
                                })
                        else:  # unhide_edge
                            if persisted_edge.is_user_confirmed:
                                updates = {"is_hidden": False}
                            else:
                                # Removing an inferred-edge hide restores the
                                # derived edge; no neutral override row remains.
                                session.delete(persisted_edge)
                                edges.remove(persisted_edge)
                                changed = True
                                for endpoint_key in {
                                    internal_source, internal_target,
                                }:
                                    if not any(
                                        row.source_node_key == endpoint_key
                                        or row.target_node_key == endpoint_key
                                        for row in edges
                                    ):
                                        endpoint = next((
                                            row for row in nodes
                                            if row.node_key == endpoint_key
                                        ), None)
                                        if endpoint is not None:
                                            session.delete(endpoint)
                                            nodes.remove(endpoint)
                                updates = {}
                        row_changed = False
                        for field, value in updates.items():
                            if getattr(persisted_edge, field) != value:
                                setattr(persisted_edge, field, value)
                                row_changed = True
                        if row_changed:
                            persisted_edge.updated_at = _now()
                            changed = True

                    if not changed:
                        command_savepoint.rollback()
                        raise RuntimeError(
                            "Eligible Knowledge Graph command produced no state change"
                        )

                    session.flush()
                    updated = self._knowledge_graph_review_snapshot_in_session(
                        session, project_id,
                    )
                    assert updated is not None
                    if updated.revision == current.revision:
                        raise RuntimeError(
                            "Knowledge Graph mutation did not advance its revision"
                        )
                    command_savepoint.commit()
                    session.add(KnowledgeGraphCommandReceipt(
                        project_id=project_id,
                        idempotency_key_hash=key_hash,
                        request_digest=request_digest,
                        result_json=_knowledge_graph_receipt_result_json(
                            kind=kind,
                            expected_revision=expected_revision,
                            applied_revision=updated.revision,
                            original_changed=True,
                            affected_edge=identity,
                        ),
                    ))
                    session.commit()
                    session.expunge_all()
                    return KnowledgeGraphCommandResult(
                        revision=updated.revision,
                        changed=True,
                        affected_edge=identity,
                        applied_revision=updated.revision,
                    )
                except Exception:
                    session.rollback()
                    raise

    def upsert_kg_node(self, project_id: int, node_key: str, **fields,
                       ) -> KnowledgeGraphNode:
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        fields.pop("node_key", None)
        with Session(self._engine) as session:
            stmt = select(KnowledgeGraphNode).where(
                KnowledgeGraphNode.project_id == project_id,
                KnowledgeGraphNode.node_key == node_key)
            node = session.exec(stmt).first()
            if node is None:
                node = KnowledgeGraphNode(project_id=project_id, node_key=node_key,
                                          **fields)
            else:
                for k, v in fields.items():
                    if hasattr(node, k):
                        setattr(node, k, v)
            node.updated_at = _now()
            session.add(node)
            session.commit()
            session.refresh(node)
            return node

    def get_kg_nodes(self, project_id: int) -> list[KnowledgeGraphNode]:
        with Session(self._engine) as session:
            stmt = select(KnowledgeGraphNode).where(
                KnowledgeGraphNode.project_id == project_id).order_by(
                KnowledgeGraphNode.id)
            return list(session.exec(stmt).all())

    def upsert_kg_edge(self, project_id: int, source_node_key: str,
                       target_node_key: str, edge_type: str, **fields,
                       ) -> KnowledgeGraphEdge:
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        with Session(self._engine) as session:
            stmt = select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.project_id == project_id,
                KnowledgeGraphEdge.source_node_key == source_node_key,
                KnowledgeGraphEdge.target_node_key == target_node_key,
                KnowledgeGraphEdge.edge_type == edge_type)
            edge = session.exec(stmt).first()
            if edge is None:
                edge = KnowledgeGraphEdge(
                    project_id=project_id, source_node_key=source_node_key,
                    target_node_key=target_node_key, edge_type=edge_type, **fields)
            else:
                for k, v in fields.items():
                    if hasattr(edge, k):
                        setattr(edge, k, v)
            edge.updated_at = _now()
            session.add(edge)
            session.commit()
            session.refresh(edge)
            return edge

    def get_kg_edges(self, project_id: int, *, include_hidden: bool = True,
                     ) -> list[KnowledgeGraphEdge]:
        with Session(self._engine) as session:
            stmt = select(KnowledgeGraphEdge).where(
                KnowledgeGraphEdge.project_id == project_id)
            if not include_hidden:
                stmt = stmt.where(KnowledgeGraphEdge.is_hidden == False)  # noqa: E712
            return list(session.exec(stmt.order_by(KnowledgeGraphEdge.id)).all())

    def get_kg_edge(self, edge_id: int) -> "KnowledgeGraphEdge | None":
        with Session(self._engine) as session:
            return session.get(KnowledgeGraphEdge, edge_id)

    def update_kg_edge(self, edge_id: int, **fields) -> "KnowledgeGraphEdge | None":
        from logosforge.models.models import _now
        with Session(self._engine) as session:
            edge = session.get(KnowledgeGraphEdge, edge_id)
            if edge is None:
                return None
            for k, v in fields.items():
                if hasattr(edge, k):
                    setattr(edge, k, v)
            edge.updated_at = _now()
            session.add(edge)
            session.commit()
            session.refresh(edge)
            return edge

    def create_kg_snapshot(self, project_id: int, **fields) -> KnowledgeGraphSnapshot:
        fields.pop("project_id", None)
        snap = KnowledgeGraphSnapshot(project_id=project_id, **fields)
        with Session(self._engine) as session:
            session.add(snap)
            session.commit()
            session.refresh(snap)
            return snap

    def get_latest_kg_snapshot(self, project_id: int) -> "KnowledgeGraphSnapshot | None":
        with Session(self._engine) as session:
            stmt = select(KnowledgeGraphSnapshot).where(
                KnowledgeGraphSnapshot.project_id == project_id).order_by(
                KnowledgeGraphSnapshot.id.desc())
            return session.exec(stmt).first()

    # -- Semantic continuity (Phase 10Q) -------------------------------------
    # Only user issue *status* (dismiss/resolve/defer) + check runs persist; the
    # issues themselves are recomputed each run and merged with these by key.

    def _continuity_review_snapshot_in_session(
        self,
        session: Session,
        project_id: int,
        *,
        validate_unique: bool = True,
    ) -> ContinuityReviewSnapshot | None:
        """Read the complete persisted Continuity review layer atomically."""
        from logosforge.continuity.revision import continuity_review_revision

        project = session.get(Project, project_id)
        if project is None:
            return None
        issues = tuple(session.exec(
            select(ContinuityIssue)
            .where(ContinuityIssue.project_id == project_id)
            .order_by(ContinuityIssue.id)
        ).all())
        if validate_unique:
            issue_keys = [row.issue_key for row in issues]
            if len(issue_keys) != len(set(issue_keys)):
                raise ContinuityReviewStateCorrupt(
                    "Continuity review state violates logical uniqueness"
                )
        return ContinuityReviewSnapshot(
            project=project,
            issues=issues,
            revision=continuity_review_revision(
                issues,
                project_id=project_id,
                project_created_at=project.created_at,
            ),
        )

    def read_continuity_review_snapshot(
        self,
        project_id: int,
    ) -> ContinuityReviewSnapshot | None:
        """Return one coherent, detached persisted Continuity review snapshot."""
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                snapshot = self._continuity_review_snapshot_in_session(
                    session, project_id,
                )
                if snapshot is not None:
                    session.expunge_all()
            finally:
                session.rollback()
        return snapshot

    def get_continuity_command_receipt(
        self,
        project_id: int,
        idempotency_key: str,
    ) -> ContinuityCommandReceiptData | None:
        """Resolve a completed Continuity command within its project scope."""
        key_hash = _continuity_idempotency_key_hash(idempotency_key)
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                if session.get(Project, project_id) is None:
                    return None
                row = session.get(
                    ContinuityCommandReceipt,
                    (int(project_id), key_hash),
                )
                if row is None:
                    return None
                receipt = _decode_continuity_command_receipt(row)
            finally:
                session.rollback()
        return receipt

    def replay_continuity_command(
        self,
        project_id: int,
        *,
        kind: str,
        expected_revision: str,
        issue_key: str,
        expected_issue_fingerprint: str,
        idempotency_key: str,
    ) -> ContinuityCommandResult | None:
        """Resolve an exact committed retry before rebuilding live findings."""
        status = _CONTINUITY_COMMAND_STATUSES.get(kind)
        if status is None:
            raise ContinuityCommandError(
                f"Unsupported Continuity command: {kind!r}"
            )
        if (
            not isinstance(expected_revision, str)
            or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
        ):
            raise ContinuityCommandError(
                "expected_revision must be a lowercase SHA-256 digest"
            )
        if (
            not isinstance(issue_key, str)
            or _CONTINUITY_ISSUE_KEY_RE.fullmatch(issue_key) is None
        ):
            raise ContinuityCommandError(
                "issue_key must be a 16-character lowercase hexadecimal key"
            )
        if (
            not isinstance(expected_issue_fingerprint, str)
            or _LOWER_SHA256_RE.fullmatch(expected_issue_fingerprint) is None
        ):
            raise ContinuityCommandError(
                "expected_issue_fingerprint must be a lowercase SHA-256 digest"
            )
        key_hash = _continuity_idempotency_key_hash(idempotency_key)
        request_digest = _continuity_command_request_digest(
            project_id, kind, expected_revision, issue_key,
            expected_issue_fingerprint,
        )
        with Session(self._engine, expire_on_commit=False) as session:
            session.connection().exec_driver_sql("BEGIN")
            try:
                if session.get(Project, project_id) is None:
                    return None
                row = session.get(
                    ContinuityCommandReceipt,
                    (int(project_id), key_hash),
                )
                if row is None:
                    return None
                receipt = _decode_continuity_command_receipt(row)
                if not hmac.compare_digest(receipt.request_digest, request_digest):
                    raise ContinuityIdempotencyKeyConflict(
                        "Idempotency-Key was already used for a different "
                        "Continuity command"
                    )
                current = self._continuity_review_snapshot_in_session(
                    session, project_id, validate_unique=False,
                )
                assert current is not None
                return ContinuityCommandResult(
                    revision=current.revision,
                    changed=False,
                    issue_key=receipt.issue_key,
                    previous_status=receipt.previous_status,
                    status=receipt.status,
                    replayed=True,
                    applied_revision=receipt.applied_revision,
                )
            finally:
                session.rollback()

    def execute_continuity_command(
        self,
        project_id: int,
        *,
        kind: str,
        expected_revision: str,
        issue_key: str,
        expected_issue_fingerprint: str,
        idempotency_key: str,
        issue=None,
    ) -> ContinuityCommandResult:
        """Atomically review one computed issue and store its durable receipt."""
        from logosforge.models.models import _now

        status = _CONTINUITY_COMMAND_STATUSES.get(kind)
        if status is None:
            raise ContinuityCommandError(
                f"Unsupported Continuity command: {kind!r}"
            )
        if (
            not isinstance(expected_revision, str)
            or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
        ):
            raise ContinuityCommandError(
                "expected_revision must be a lowercase SHA-256 digest"
            )
        if (
            not isinstance(issue_key, str)
            or _CONTINUITY_ISSUE_KEY_RE.fullmatch(issue_key) is None
        ):
            raise ContinuityCommandError(
                "issue_key must be a 16-character lowercase hexadecimal key"
            )
        if (
            not isinstance(expected_issue_fingerprint, str)
            or _LOWER_SHA256_RE.fullmatch(expected_issue_fingerprint) is None
        ):
            raise ContinuityCommandError(
                "expected_issue_fingerprint must be a lowercase SHA-256 digest"
            )
        key_hash = _continuity_idempotency_key_hash(idempotency_key)
        request_digest = _continuity_command_request_digest(
            project_id, kind, expected_revision, issue_key,
            expected_issue_fingerprint,
        )

        with self.continuity_write_lock(project_id):
            with Session(self._engine, expire_on_commit=False) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    if session.get(Project, project_id) is None:
                        raise ContinuityProjectNotFound(project_id)
                    receipt_row = session.get(
                        ContinuityCommandReceipt,
                        (int(project_id), key_hash),
                    )
                    if receipt_row is not None:
                        receipt = _decode_continuity_command_receipt(receipt_row)
                        if not hmac.compare_digest(
                            receipt.request_digest, request_digest,
                        ):
                            raise ContinuityIdempotencyKeyConflict(
                                "Idempotency-Key was already used for a "
                                "different Continuity command"
                            )
                        current = self._continuity_review_snapshot_in_session(
                            session, project_id, validate_unique=False,
                        )
                        assert current is not None
                        session.expunge_all()
                        session.rollback()
                        return ContinuityCommandResult(
                            revision=current.revision,
                            changed=False,
                            issue_key=receipt.issue_key,
                            previous_status=receipt.previous_status,
                            status=receipt.status,
                            replayed=True,
                            applied_revision=receipt.applied_revision,
                        )

                    current = self._continuity_review_snapshot_in_session(
                        session, project_id,
                    )
                    assert current is not None
                    if expected_revision != current.revision:
                        raise ContinuityRevisionConflict(
                            expected_revision, current.revision,
                        )
                    if (
                        issue is None
                        or str(getattr(issue, "issue_key", "")) != issue_key
                        or str(getattr(issue, "status", "open")) != "open"
                    ):
                        raise ContinuityIssueNotFound(issue_key)
                    if not hmac.compare_digest(
                        str(getattr(issue, "review_fingerprint", "")),
                        expected_issue_fingerprint,
                    ):
                        raise ContinuityRevisionConflict(
                            expected_issue_fingerprint,
                            str(getattr(issue, "review_fingerprint", "")),
                        )

                    try:
                        evidence_json = json.dumps(
                            list(getattr(issue, "evidence", []) or []),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                        related_node_ids_json = json.dumps(
                            list(getattr(issue, "related_node_ids", []) or []),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                        related_scene_ids_json = json.dumps(
                            list(getattr(issue, "related_scene_ids", []) or []),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                    except (TypeError, ValueError) as exc:
                        raise ContinuityCommandError(
                            "Continuity issue evidence cannot be persisted"
                        ) from exc

                    matches = [
                        row for row in current.issues
                        if row.issue_key == issue_key
                    ]
                    if len(matches) > 1:
                        raise ContinuityReviewStateCorrupt(
                            "Continuity review state violates logical uniqueness"
                        )
                    persisted = matches[0] if matches else None
                    if persisted is not None and persisted.status != "open":
                        raise ContinuityIssueNotFound(issue_key)
                    values = {
                        "issue_type": str(getattr(issue, "issue_type", "") or "")[:128],
                        "dimension": str(getattr(issue, "dimension", "") or "")[:128],
                        "severity": str(getattr(issue, "severity", "") or "")[:32],
                        "confidence": str(getattr(issue, "confidence", "") or "")[:32],
                        "title": str(getattr(issue, "title", "") or "")[:1000],
                        "explanation": str(getattr(issue, "explanation", "") or "")[:4000],
                        "evidence_json": evidence_json,
                        "related_node_ids_json": related_node_ids_json,
                        "related_scene_ids_json": related_scene_ids_json,
                        "suggested_action": str(
                            getattr(issue, "suggested_action", "") or ""
                        )[:4000],
                        "status": status,
                    }
                    if persisted is None:
                        persisted = ContinuityIssue(
                            project_id=project_id,
                            issue_key=issue_key,
                            **values,
                        )
                        session.add(persisted)
                    else:
                        for field, value in values.items():
                            setattr(persisted, field, value)
                        persisted.updated_at = _now()
                    session.flush()
                    updated = self._continuity_review_snapshot_in_session(
                        session, project_id,
                    )
                    assert updated is not None
                    if updated.revision == current.revision:
                        raise RuntimeError(
                            "Continuity mutation did not advance its revision"
                        )
                    session.add(ContinuityCommandReceipt(
                        project_id=project_id,
                        idempotency_key_hash=key_hash,
                        request_digest=request_digest,
                        result_json=_continuity_receipt_result_json(
                            kind=kind,
                            expected_revision=expected_revision,
                            applied_revision=updated.revision,
                            issue_key=issue_key,
                            expected_issue_fingerprint=expected_issue_fingerprint,
                            previous_status="open",
                            status=status,
                            original_changed=True,
                        ),
                    ))
                    session.commit()
                    session.expunge_all()
                    return ContinuityCommandResult(
                        revision=updated.revision,
                        changed=True,
                        issue_key=issue_key,
                        previous_status="open",
                        status=status,
                        applied_revision=updated.revision,
                    )
                except Exception:
                    session.rollback()
                    raise

    def upsert_continuity_issue(self, project_id: int, issue_key: str, **fields,
                                ) -> ContinuityIssue:
        from logosforge.models.models import _now
        fields.pop("project_id", None)
        fields.pop("issue_key", None)
        with self.continuity_write_lock(project_id):
            with Session(self._engine, expire_on_commit=False) as session:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    matches = list(session.exec(select(ContinuityIssue).where(
                        ContinuityIssue.project_id == project_id,
                        ContinuityIssue.issue_key == issue_key,
                    )).all())
                    if len(matches) > 1:
                        raise ContinuityReviewStateCorrupt(
                            "Continuity review state violates logical uniqueness"
                        )
                    issue = matches[0] if matches else None
                    if issue is None:
                        issue = ContinuityIssue(
                            project_id=project_id,
                            issue_key=issue_key,
                            **fields,
                        )
                    else:
                        for k, v in fields.items():
                            if hasattr(issue, k):
                                setattr(issue, k, v)
                    issue.updated_at = _now()
                    session.add(issue)
                    session.commit()
                    session.refresh(issue)
                    return issue
                except Exception:
                    session.rollback()
                    raise

    def get_continuity_issues(self, project_id: int, *, status: str | None = None,
                              ) -> list[ContinuityIssue]:
        with Session(self._engine) as session:
            stmt = select(ContinuityIssue).where(
                ContinuityIssue.project_id == project_id)
            if status is not None:
                stmt = stmt.where(ContinuityIssue.status == status)
            return list(session.exec(stmt.order_by(ContinuityIssue.id)).all())

    def get_continuity_issue_by_key(self, project_id: int, issue_key: str,
                                    ) -> "ContinuityIssue | None":
        with Session(self._engine) as session:
            stmt = select(ContinuityIssue).where(
                ContinuityIssue.project_id == project_id,
                ContinuityIssue.issue_key == issue_key)
            return session.exec(stmt).first()

    def set_continuity_issue_status(self, project_id: int, issue_key: str,
                                    status: str, **fields) -> ContinuityIssue:
        return self.upsert_continuity_issue(project_id, issue_key,
                                            status=status, **fields)

    def create_continuity_check_run(self, project_id: int, **fields,
                                    ) -> ContinuityCheckRun:
        fields.pop("project_id", None)
        run = ContinuityCheckRun(project_id=project_id, **fields)
        with Session(self._engine) as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    def get_continuity_check_runs(self, project_id: int) -> list[ContinuityCheckRun]:
        with Session(self._engine) as session:
            stmt = select(ContinuityCheckRun).where(
                ContinuityCheckRun.project_id == project_id).order_by(
                ContinuityCheckRun.id)
            return list(session.exec(stmt).all())

    def get_latest_continuity_check_run(self, project_id: int,
                                        ) -> "ContinuityCheckRun | None":
        with Session(self._engine) as session:
            stmt = select(ContinuityCheckRun).where(
                ContinuityCheckRun.project_id == project_id).order_by(
                ContinuityCheckRun.id.desc())
            return session.exec(stmt).first()

    @staticmethod
    def _matches(query_lower: str, *fields: str) -> bool:
        for field in fields:
            if field and query_lower in field.lower():
                return True
        return False
