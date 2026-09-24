"""Desktop-only board state — per-document Whiteboard blocks + manual outliner.

These are NOT core domain: the core has no whiteboard block-doc table, and the
manual outliner's node shape is owned by the frontend (stored opaquely). So they
live locally as atomic-JSON stores under the user data dir (``~/.logosforge``,
override ``LOGOSFORGE_DATA_DIR``). Each document is one file keyed by its id (the
core project id, stringified) — blocks under ``whiteboards/{id}.json`` and the
outliner under ``outlines/{id}.json``. PSYKE lives in the core, isolated by giving
each document its own core project. The one piece that IS core data — the
whiteboard's writing ``mode`` — is normalized against the core
``logosforge.writing_modes`` (single source of truth), never a duplicated catalog.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

from logosforge import writing_modes as wm


_LOG = logging.getLogger(__name__)
_STATE_LOCK = threading.RLock()
_T = TypeVar("_T")
_RECOVERY_NOTICES: list[dict[str, str]] = []


class LocalStateError(RuntimeError):
    """Base class for a protected local-state failure."""


class LocalStateIOError(LocalStateError):
    """The saved state could not be read or written at the filesystem level."""

    def __init__(self, path: Path, action: str, cause: BaseException) -> None:
        self.path = path
        self.action = action
        super().__init__(
            f"Could not {action} saved Whiteboard data at '{path}'. "
            "Whiteboard stopped the operation without substituting empty data. "
            "Check disk space and file permissions."
        )
        self.__cause__ = cause


class LocalStateCorruptionError(LocalStateError):
    """A state file and all available backups failed validation."""

    def __init__(self, path: Path, label: str) -> None:
        self.path = path
        self.label = label
        super().__init__(
            f"The saved {label} at '{path}' is unreadable and no valid backup was found. "
            "It was not replaced or cleared. Restore a backup before editing this project."
        )


class ResourceRevisionConflict(RuntimeError):
    """A conditional resource write was based on an older durable snapshot."""

    def __init__(self, expected_revision: str, current_revision: str) -> None:
        self.expected_revision = expected_revision
        self.current_revision = current_revision
        super().__init__("The saved resource changed after it was loaded.")


class MutationIdConflict(RuntimeError):
    """One mutation id was reused for a different conditional request."""

    def __init__(self, mutation_id: str) -> None:
        self.mutation_id = mutation_id
        super().__init__("The mutation id was already used for a different request.")


def consume_recovery_notices() -> list[dict[str, str]]:
    """Return and clear successful automatic-recovery notices for the UI."""
    with _STATE_LOCK:
        notices = [dict(item) for item in _RECOVERY_NOTICES]
        _RECOVERY_NOTICES.clear()
        return notices


def _data_dir() -> Path:
    return Path(os.environ.get("LOGOSFORGE_DATA_DIR") or (Path.home() / ".logosforge"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_revision() -> str:
    """Return an opaque durable resource validator.

    Revisions deliberately are not counters. Restoring an older rotating backup
    must not make a later numeric revision reusable (an ABA stale-write gap).
    """
    return uuid4().hex


def _valid_revision(value: str) -> bool:
    return len(value) == 32 and all(character in "0123456789abcdef" for character in value)


def _mutation_fingerprint(
    kind: str,
    payload: BaseModel,
    expected_revision: str | None,
) -> str:
    """Hash the complete conditional request represented by a mutation id."""
    canonical = json.dumps(
        {
            "kind": kind,
            "expected_revision": expected_revision,
            "payload": payload.model_dump(exclude_none=True, mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _backup_paths(path: Path) -> tuple[Path, Path]:
    """Return newest and older backup paths for one state file."""
    return (
        path.with_name(path.name + ".bak"),
        path.with_name(path.name + ".bak.1"),
    )


def _fsync_directory(path: Path) -> None:
    """Persist a directory entry where the platform supports directory fsync."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return  # Windows commonly refuses opening a directory as a file handle.
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _replace_bytes(path: Path, data: bytes) -> None:
    """Atomically replace *path* with already-encoded bytes, including fsync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _atomic_write_text(path: Path, text: str) -> None:
    """Atomically save text while retaining two previous generations.

    The current file remains in place until the replacement has been flushed.
    Existing bytes are rotated to ``.bak`` / ``.bak.1`` first, so a crash,
    interrupted write, or later JSON corruption has a known recovery source.
    """
    encoded = text.encode("utf-8")
    with _STATE_LOCK:
        try:
            newest, older = _backup_paths(path)
            if path.exists():
                current = path.read_bytes()
                if newest.exists():
                    os.replace(newest, older)
                    _fsync_directory(path.parent)
                _replace_bytes(newest, current)
            _replace_bytes(path, encoded)
        except OSError as exc:
            raise LocalStateIOError(path, "save", exc) from exc


def _parse_file(path: Path, parser: Callable[[str], _T]) -> tuple[_T, bytes]:
    raw = path.read_bytes()
    return parser(raw.decode("utf-8")), raw


def _quarantine_path(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    # Do not end with .json: document discovery intentionally scans only
    # canonical ``*.json`` files and must never treat quarantined bytes as a doc.
    return path.with_name(f"{path.name}.corrupt-{stamp}")


def _delete_state_files(path: Path) -> None:
    """Remove a canonical state file and its rotating backups."""
    with _STATE_LOCK:
        try:
            for candidate in (path, *_backup_paths(path)):
                candidate.unlink(missing_ok=True)
            _fsync_directory(path.parent)
        except OSError as exc:
            raise LocalStateIOError(path, "delete", exc) from exc


def _read_with_recovery(
    path: Path,
    parser: Callable[[str], _T],
    *,
    label: str,
    prepare_recovery: Callable[[_T], tuple[_T, bytes]] | None = None,
) -> tuple[_T | None, bool]:
    """Read validated state, restoring the newest valid backup when necessary.

    Missing state is represented by ``(None, False)``. The boolean reports that
    a backup was restored, allowing revisioned stores to mint a fresh validator
    before returning recovered content. Invalid state is never represented by an
    empty document/list: if no backup validates, a protected error aborts the
    request so a subsequent autosave cannot overwrite the damaged file.
    """
    with _STATE_LOCK:
        if not path.exists():
            return None, False
        try:
            return _parse_file(path, parser)[0], False
        except OSError as exc:
            raise LocalStateIOError(path, "read", exc) from exc
        except Exception as current_error:
            invalid_backups: list[Path] = []
            for backup in _backup_paths(path):
                if not backup.exists():
                    continue
                try:
                    recovered, raw = _parse_file(backup, parser)
                except (OSError, UnicodeError, ValueError, TypeError):
                    invalid_backups.append(backup)
                    continue

                # Revisioned resources replace the backup's old validator and
                # retry metadata before its bytes become canonical. This must be
                # part of the recovery write itself: if persistence fails, a
                # later read must not mistake the unrotated backup for current.
                if prepare_recovery is not None:
                    recovered, raw = prepare_recovery(recovered)

                quarantine = _quarantine_path(path)
                try:
                    os.replace(path, quarantine)
                    _fsync_directory(path.parent)
                    _replace_bytes(path, raw)
                except OSError as exc:
                    # Best effort rollback: never leave the canonical path absent
                    # merely because automatic recovery could not be completed.
                    if not path.exists() and quarantine.exists():
                        try:
                            os.replace(quarantine, path)
                        except OSError:
                            pass
                    raise LocalStateIOError(path, "recover", exc) from exc

                # Do not let a known-bad newest backup overwrite the valid older
                # generation during the next rotation. Preserve it separately.
                for invalid in invalid_backups:
                    try:
                        os.replace(invalid, _quarantine_path(invalid))
                    except OSError:
                        _LOG.warning("Could not quarantine invalid backup %s", invalid)

                _LOG.warning(
                    "Recovered %s from %s; quarantined unreadable state as %s",
                    label,
                    backup,
                    quarantine,
                )
                _RECOVERY_NOTICES.append({
                    "id": uuid4().hex,
                    "label": label,
                    "message": (
                        f"Recovered {label} from an automatic backup. "
                        f"The unreadable copy was preserved as '{quarantine.name}'."
                    ),
                    "recovered_from": str(backup),
                    "quarantined_path": str(quarantine),
                    "recovered_at": _now(),
                })
                # A single-user desktop session cannot usefully display an
                # unbounded history; the quarantined files themselves remain.
                del _RECOVERY_NOTICES[:-50]
                return recovered, True

            raise LocalStateCorruptionError(path, label) from current_error


# -- Whiteboard document -----------------------------------------------------

class WhiteboardBlock(BaseModel):
    id: str
    type: str = "paragraph"
    text: str = ""
    level: Optional[int] = None
    sp: Optional[str] = None  # optional screenplay element type
    marks: Optional[list[dict[str, Any]]] = None  # inline bold/italic runs (prose)


class WhiteboardDocument(BaseModel):
    id: str
    # Stable for one core-project incarnation, and rotated whenever SQLite
    # reuses a deleted numeric project id.  Clients echo this token on every
    # mutation so a delayed request cannot target the replacement project.
    incarnation: str = ""
    title: str
    mode: str
    blocks: list[WhiteboardBlock] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    updated_at: str
    # Opaque per-resource validator. It rotates on every committed manuscript
    # change and is intentionally unrelated to renderer-local save counters.
    revision: str = ""


class _StoredWhiteboardDocument(WhiteboardDocument):
    """On-disk manuscript envelope; retry metadata is never an API field."""

    last_mutation_id: str = ""
    last_mutation_fingerprint: str = ""


class WhiteboardDocumentSummary(BaseModel):
    """A document in the library list — no blocks, so the list stays light."""

    id: str
    incarnation: str = ""
    title: str
    mode: str
    updated_at: str
    revision: str = ""


class WhiteboardCreate(BaseModel):
    title: Optional[str] = None
    mode: Optional[str] = None
    blocks: Optional[list[WhiteboardBlock]] = None
    settings: Optional[dict[str, Any]] = None


class WhiteboardUpdate(BaseModel):
    title: Optional[str] = None
    mode: Optional[str] = None
    blocks: Optional[list[WhiteboardBlock]] = None
    settings: Optional[dict[str, Any]] = None


_WB_DIRNAME = "whiteboards"
_OL_DIRNAME = "outlines"
_COMMENTS_DIRNAME = "comments"
_LEGACY_WB = "whiteboard.json"
_LEGACY_OL = "outline.json"


class WhiteboardStore:
    """Per-document Whiteboard block store — one atomic-JSON file per document id
    under ``<data_dir>/whiteboards/{doc_id}.json``. There is no single 'current'
    document; every method is keyed by id."""

    def __init__(self, root: Path | None = None) -> None:
        self._dir = (root or _data_dir()) / _WB_DIRNAME

    def _path(self, doc_id: str) -> Path:
        return self._dir / f"{doc_id}.json"

    @staticmethod
    def _public(doc: _StoredWhiteboardDocument) -> WhiteboardDocument:
        return WhiteboardDocument.model_validate(doc.model_dump())

    def _default(self, doc_id: str) -> _StoredWhiteboardDocument:
        return _StoredWhiteboardDocument(
            id=doc_id, incarnation="", title="Untitled", mode=wm.DEFAULT_MODE, blocks=[],
            settings={}, updated_at=_now(), revision=_new_revision())

    def _load(self, doc_id: str) -> _StoredWhiteboardDocument:
        path = self._path(doc_id)

        def prepare_recovery(
            recovered: _StoredWhiteboardDocument,
        ) -> tuple[_StoredWhiteboardDocument, bytes]:
            rotated = recovered.model_copy(update={
                "id": doc_id,
                "revision": _new_revision(),
                "last_mutation_id": "",
                "last_mutation_fingerprint": "",
            })
            return rotated, rotated.model_dump_json(indent=2).encode("utf-8")

        doc, recovered = _read_with_recovery(
            path,
            _StoredWhiteboardDocument.model_validate_json,
            label=f"manuscript for document {doc_id}",
            prepare_recovery=prepare_recovery,
        )
        if doc is None:
            return self._default(doc_id)
        # The path is the source of truth for the id (tolerate a stale id).
        migrated = doc if doc.id == doc_id else doc.model_copy(update={"id": doc_id})
        if recovered:
            # A backup contains an older state incarnation. Never reuse its
            # validator or retry metadata: either would let a request prepared
            # before recovery masquerade as current. ``updated_at`` deliberately
            # remains unchanged because recovery is not a user edit.
            assert _valid_revision(migrated.revision)
        elif not _valid_revision(migrated.revision):
            # Persist the legacy migration once, but preserve updated_at: adding
            # a transport validator is not a user edit and must not reorder docs.
            migrated = migrated.model_copy(update={"revision": _new_revision()})
            _atomic_write_text(path, migrated.model_dump_json(indent=2))
        return migrated

    def exists(self, doc_id: str) -> bool:
        return self._path(doc_id).exists()

    def get(self, doc_id: str) -> WhiteboardDocument:
        with _STATE_LOCK:
            return self._public(self._load(doc_id))

    def ensure_incarnation(self, doc_id: str) -> str:
        """Return a durable identity token, migrating legacy/missing state once."""
        with _STATE_LOCK:
            doc = self._load(doc_id)
            if len(doc.incarnation) == 32 and all(c in "0123456789abcdef" for c in doc.incarnation):
                return doc.incarnation
            incarnation = uuid4().hex
            migrated = doc.model_copy(update={"incarnation": incarnation})
            # Preserve ``updated_at``: adding transport identity must not make a
            # document look user-edited or perturb recent-document ordering.
            _atomic_write_text(self._path(doc_id), migrated.model_dump_json(indent=2))
            return incarnation

    def create(self, doc_id: str, payload: WhiteboardCreate) -> WhiteboardDocument:
        # A legacy create call may target an existing id. Validate/recover it
        # before replacement so this path cannot bypass corruption protection.
        with _STATE_LOCK:
            incarnation = ""
            if self._path(doc_id).exists():
                incarnation = self._load(doc_id).incarnation
            doc = _StoredWhiteboardDocument(
                id=doc_id, incarnation=incarnation or uuid4().hex,
                title=payload.title or "Untitled",
                mode=wm.normalize_mode(payload.mode), blocks=payload.blocks or [],
                settings=dict(payload.settings or {}), updated_at=_now(),
                revision=_new_revision())
            _atomic_write_text(self._path(doc_id), doc.model_dump_json(indent=2))
            return self._public(doc)

    def update(
        self,
        doc_id: str,
        payload: WhiteboardUpdate,
        *,
        expected_revision: str | None = None,
        mutation_id: str | None = None,
    ) -> WhiteboardDocument:
        # PARTIAL-PATCH MERGE (invariant): a None field keeps the stored value, so a
        # blocks-only autosave never clobbers `mode` (and a mode change never drops
        # blocks). This is what makes doc-switching safe — a late autosave draining
        # for the previous doc can't corrupt its mode. Do NOT "simplify" to overwrite
        # fields unconditionally.
        with _STATE_LOCK:
            cur = self._load(doc_id)
            fingerprint = _mutation_fingerprint("whiteboard", payload, expected_revision)
            if mutation_id and cur.last_mutation_id == mutation_id:
                if cur.last_mutation_fingerprint != fingerprint:
                    raise MutationIdConflict(mutation_id)
                return self._public(cur)
            if expected_revision is not None and not hmac.compare_digest(
                expected_revision, cur.revision
            ):
                raise ResourceRevisionConflict(expected_revision, cur.revision)
            doc = _StoredWhiteboardDocument(
                id=doc_id,
                incarnation=cur.incarnation,
                title=cur.title if payload.title is None else payload.title,
                mode=cur.mode if payload.mode is None else wm.normalize_mode(payload.mode),
                blocks=cur.blocks if payload.blocks is None else payload.blocks,
                settings=cur.settings if payload.settings is None else dict(payload.settings),
                updated_at=_now(),
                revision=_new_revision(),
                last_mutation_id=mutation_id or "",
                last_mutation_fingerprint=fingerprint if mutation_id else "",
            )
            _atomic_write_text(self._path(doc_id), doc.model_dump_json(indent=2))
            return self._public(doc)

    def delete(self, doc_id: str) -> None:
        _delete_state_files(self._path(doc_id))

    def list_document_ids(self) -> set[str]:
        if not self._dir.exists():
            return set()
        return {path.stem for path in self._dir.glob("*.json")}

    def list_summaries(
        self, include_ids: set[str] | None = None,
    ) -> list[WhiteboardDocumentSummary]:
        if not self._dir.exists():
            return []
        out: list[WhiteboardDocumentSummary] = []
        for p in self._dir.glob("*.json"):
            if include_ids is not None and p.stem not in include_ids:
                continue
            doc = self._load(p.stem)
            out.append(WhiteboardDocumentSummary(
                id=doc.id, incarnation=doc.incarnation, title=doc.title,
                mode=doc.mode, updated_at=doc.updated_at, revision=doc.revision))
        out.sort(key=lambda s: s.updated_at, reverse=True)  # most-recent first
        return out


# -- Manual outliner (opaque node list owned by the frontend) ----------------

class OutlineItemsDocument(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    revision: str = ""


class _StoredOutlineItemsDocument(OutlineItemsDocument):
    """On-disk outline envelope; retry metadata is not exposed by the API."""

    last_mutation_id: str = ""
    last_mutation_fingerprint: str = ""


class OutlineItemsStore:
    """Per-document manual outliner — one file per document id under
    ``<data_dir>/outlines/{doc_id}.json``. Node shape is opaque (frontend-owned)."""

    def __init__(self, root: Path | None = None) -> None:
        self._dir = (root or _data_dir()) / _OL_DIRNAME

    def _path(self, doc_id: str) -> Path:
        return self._dir / f"{doc_id}.json"

    @staticmethod
    def _parse(text: str) -> _StoredOutlineItemsDocument:
        data = json.loads(text)
        if isinstance(data, list):
            return _StoredOutlineItemsDocument(items=data)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return _StoredOutlineItemsDocument.model_validate(data)
        raise ValueError("outline state must be a list or an object containing an items list")

    @staticmethod
    def _public(doc: _StoredOutlineItemsDocument) -> OutlineItemsDocument:
        return OutlineItemsDocument.model_validate(doc.model_dump())

    def _load(
        self,
        doc_id: str,
        *,
        persist_missing: bool = True,
    ) -> _StoredOutlineItemsDocument:
        path = self._path(doc_id)

        def prepare_recovery(
            recovered: _StoredOutlineItemsDocument,
        ) -> tuple[_StoredOutlineItemsDocument, bytes]:
            rotated = recovered.model_copy(update={
                "revision": _new_revision(),
                "last_mutation_id": "",
                "last_mutation_fingerprint": "",
            })
            return rotated, rotated.model_dump_json(indent=2).encode("utf-8")

        doc, recovered = _read_with_recovery(
            path,
            self._parse,
            label=f"outline for document {doc_id}",
            prepare_recovery=prepare_recovery,
        )
        if doc is None:
            doc = _StoredOutlineItemsDocument(items=[], revision=_new_revision())
            if persist_missing:
                _atomic_write_text(path, doc.model_dump_json(indent=2))
            return doc
        if recovered:
            assert _valid_revision(doc.revision)
        elif not _valid_revision(doc.revision):
            doc = doc.model_copy(update={"revision": _new_revision()})
            _atomic_write_text(path, doc.model_dump_json(indent=2))
        return doc

    def get_document(self, doc_id: str) -> OutlineItemsDocument:
        with _STATE_LOCK:
            return self._public(self._load(doc_id))

    def get(self, doc_id: str) -> list[dict[str, Any]]:
        return self.get_document(doc_id).items

    def replace(self, doc_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.replace_document(doc_id, items).items

    def replace_document(
        self,
        doc_id: str,
        items: list[dict[str, Any]],
        *,
        expected_revision: str | None = None,
        mutation_id: str | None = None,
    ) -> OutlineItemsDocument:
        with _STATE_LOCK:
            # PUT is a full-list replacement and otherwise has no read/merge step.
            # Validate/recover the stored copy explicitly so a queued autosave cannot
            # overwrite an unrecoverable outline with an apparently valid empty list.
            # A conditional conflict must advertise a durable validator. Persist
            # the initial empty outline before comparing so repeated stale PUTs
            # and the following GET all observe the same current revision.
            cur = self._load(doc_id, persist_missing=expected_revision is not None)
            payload = OutlineItemsDocument(items=list(items), revision="")
            fingerprint = _mutation_fingerprint("outline", payload, expected_revision)
            if mutation_id and cur.last_mutation_id == mutation_id:
                if cur.last_mutation_fingerprint != fingerprint:
                    raise MutationIdConflict(mutation_id)
                return self._public(cur)
            if expected_revision is not None and not hmac.compare_digest(
                expected_revision, cur.revision
            ):
                raise ResourceRevisionConflict(expected_revision, cur.revision)
            doc = _StoredOutlineItemsDocument(
                items=list(items),
                revision=_new_revision(),
                last_mutation_id=mutation_id or "",
                last_mutation_fingerprint=fingerprint if mutation_id else "",
            )
            _atomic_write_text(self._path(doc_id), doc.model_dump_json(indent=2))
            return self._public(doc)

    def delete(self, doc_id: str) -> None:
        _delete_state_files(self._path(doc_id))

    def list_document_ids(self) -> set[str]:
        if not self._dir.exists():
            return set()
        return {path.stem for path in self._dir.glob("*.json")}


# -- Comments (per-document inline notes anchored to block spans) -------------

class CommentAnchor(BaseModel):
    """Where a comment attaches: a character span inside a block. Anchored by
    a stable block id when available, with block INDEX as a legacy/navigation
    fallback, plus quoted text and short prefix/suffix context. Older comments
    have no ids and continue to re-locate through the text selectors."""

    block_index: int
    block_id: Optional[str] = None
    from_offset: int
    to_offset: int
    end_block_index: Optional[int] = None  # last block of a multi-block selection
    end_block_id: Optional[str] = None
    prefix: str = ""
    suffix: str = ""


class CommentReply(BaseModel):
    id: str
    body: str = ""
    author: str = "you"  # "you" = the writer; an assistant name for future AI replies
    created_at: str


class Comment(BaseModel):
    id: str
    anchor: CommentAnchor
    quote: str = ""   # snapshot of the highlighted text (used to re-anchor)
    body: str = ""    # the note itself (the thread root)
    resolved: bool = False
    replies: list[CommentReply] = Field(default_factory=list)
    created_at: str
    updated_at: str


class CommentCreate(BaseModel):
    anchor: CommentAnchor
    quote: str = ""
    body: str = ""


class CommentUpdate(BaseModel):
    body: Optional[str] = None
    resolved: Optional[bool] = None
    anchor: Optional[CommentAnchor] = None  # re-anchor after the frontend reconciles


class CommentReplyCreate(BaseModel):
    body: str = ""
    author: str = "you"
    # A renderer retry reuses this id so a response lost after the atomic write
    # cannot append the same reply (or trigger its assistant response) twice.
    client_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class CommentsDocument(BaseModel):
    comments: list[Comment] = Field(default_factory=list)


class CommentsStore:
    """Per-document comments — one atomic-JSON file per document id under
    ``<data_dir>/comments/{doc_id}.json``. Mirrors WhiteboardStore."""

    def __init__(self, root: Path | None = None) -> None:
        self._dir = (root or _data_dir()) / _COMMENTS_DIRNAME

    def _path(self, doc_id: str) -> Path:
        return self._dir / f"{doc_id}.json"

    def _load(self, doc_id: str) -> CommentsDocument:
        doc, _recovered = _read_with_recovery(
            self._path(doc_id),
            CommentsDocument.model_validate_json,
            label=f"comments for document {doc_id}",
        )
        return CommentsDocument() if doc is None else doc

    def _save(self, doc_id: str, doc: CommentsDocument) -> None:
        _atomic_write_text(self._path(doc_id), doc.model_dump_json(indent=2))

    def get(self, doc_id: str) -> CommentsDocument:
        return self._load(doc_id)

    def create(self, doc_id: str, comment_id: str, payload: CommentCreate) -> Comment:
        with _STATE_LOCK:
            doc = self._load(doc_id)
            now = _now()
            comment = Comment(
                id=comment_id, anchor=payload.anchor, quote=payload.quote,
                body=payload.body, resolved=False, created_at=now, updated_at=now)
            doc.comments.append(comment)
            self._save(doc_id, doc)
            return comment

    def update(self, doc_id: str, comment_id: str, payload: CommentUpdate) -> Comment | None:
        with _STATE_LOCK:
            doc = self._load(doc_id)
            for i, c in enumerate(doc.comments):
                if c.id == comment_id:
                    updated = Comment(
                        id=c.id,
                        anchor=payload.anchor if payload.anchor is not None else c.anchor,
                        quote=c.quote,
                        body=c.body if payload.body is None else payload.body,
                        resolved=c.resolved if payload.resolved is None else payload.resolved,
                        replies=c.replies,
                        created_at=c.created_at, updated_at=_now())
                    doc.comments[i] = updated
                    self._save(doc_id, doc)
                    return updated
            return None

    def delete_comment(self, doc_id: str, comment_id: str) -> bool:
        with _STATE_LOCK:
            doc = self._load(doc_id)
            before = len(doc.comments)
            doc.comments = [c for c in doc.comments if c.id != comment_id]
            if len(doc.comments) < before:
                self._save(doc_id, doc)
                return True
            return False

    def add_reply(self, doc_id: str, comment_id: str, reply_id: str,
                  payload: CommentReplyCreate) -> Comment | None:
        with _STATE_LOCK:
            doc = self._load(doc_id)
            for i, c in enumerate(doc.comments):
                if c.id == comment_id:
                    if any(reply.id == reply_id for reply in c.replies):
                        return c
                    reply = CommentReply(
                        id=reply_id, body=payload.body,
                        author=payload.author or "you", created_at=_now())
                    updated = c.model_copy(update={
                        "replies": [*c.replies, reply], "updated_at": _now()})
                    doc.comments[i] = updated
                    self._save(doc_id, doc)
                    return updated
            return None

    def delete_reply(self, doc_id: str, comment_id: str, reply_id: str) -> Comment | None:
        with _STATE_LOCK:
            doc = self._load(doc_id)
            for i, c in enumerate(doc.comments):
                if c.id == comment_id:
                    kept = [r for r in c.replies if r.id != reply_id]
                    if len(kept) == len(c.replies):
                        return None  # no such reply
                    updated = c.model_copy(update={"replies": kept, "updated_at": _now()})
                    doc.comments[i] = updated
                    self._save(doc_id, doc)
                    return updated
            return None

    def delete(self, doc_id: str) -> None:
        _delete_state_files(self._path(doc_id))

    def list_document_ids(self) -> set[str]:
        if not self._dir.exists():
            return set()
        return {path.stem for path in self._dir.glob("*.json")}


def migrate_legacy(default_doc_id: str) -> None:
    """One-time upgrade: fold the pre-multi-document singleton files
    (``whiteboard.json`` / ``outline.json``) into the default document so an
    upgrading user keeps their work. No-op once the per-document file exists."""
    root = _data_dir()
    legacy_wb = root / _LEGACY_WB
    new_wb = root / _WB_DIRNAME / f"{default_doc_id}.json"
    if legacy_wb.exists() and not new_wb.exists():
        try:
            doc = _StoredWhiteboardDocument.model_validate_json(
                legacy_wb.read_text(encoding="utf-8")
            )
            doc = doc.model_copy(update={
                "id": default_doc_id,
                "revision": doc.revision if _valid_revision(doc.revision) else _new_revision(),
            })
            _atomic_write_text(new_wb, doc.model_dump_json(indent=2))
            legacy_wb.rename(legacy_wb.with_suffix(".json.migrated"))
        except Exception:
            pass
    legacy_ol = root / _LEGACY_OL
    new_ol = root / _OL_DIRNAME / f"{default_doc_id}.json"
    if legacy_ol.exists() and not new_ol.exists():
        try:
            data = json.loads(legacy_ol.read_text(encoding="utf-8"))
            items = (
                data["items"] if isinstance(data, dict) and isinstance(data.get("items"), list)
                else data if isinstance(data, list) else []
            )
            _atomic_write_text(
                new_ol,
                _StoredOutlineItemsDocument(
                    items=items,
                    revision=_new_revision(),
                ).model_dump_json(indent=2),
            )
            legacy_ol.rename(legacy_ol.with_suffix(".json.migrated"))
        except Exception:
            pass


whiteboard_store = WhiteboardStore()
outline_items_store = OutlineItemsStore()
comments_store = CommentsStore()
