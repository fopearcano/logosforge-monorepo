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

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from logosforge import writing_modes as wm


def _data_dir() -> Path:
    return Path(os.environ.get("LOGOSFORGE_DATA_DIR") or (Path.home() / ".logosforge"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # atomic: a crash mid-save can't corrupt the file


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
    title: str
    mode: str
    blocks: list[WhiteboardBlock] = Field(default_factory=list)
    updated_at: str


class WhiteboardDocumentSummary(BaseModel):
    """A document in the library list — no blocks, so the list stays light."""

    id: str
    title: str
    mode: str
    updated_at: str


class WhiteboardCreate(BaseModel):
    title: Optional[str] = None
    mode: Optional[str] = None
    blocks: Optional[list[WhiteboardBlock]] = None


class WhiteboardUpdate(BaseModel):
    title: Optional[str] = None
    mode: Optional[str] = None
    blocks: Optional[list[WhiteboardBlock]] = None


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

    def _default(self, doc_id: str) -> WhiteboardDocument:
        return WhiteboardDocument(
            id=doc_id, title="Untitled", mode=wm.DEFAULT_MODE, blocks=[], updated_at=_now())

    def _load(self, doc_id: str) -> WhiteboardDocument:
        path = self._path(doc_id)
        try:
            if path.exists():
                doc = WhiteboardDocument.model_validate_json(path.read_text(encoding="utf-8"))
                # The path is the source of truth for the id (tolerate a stale id).
                return doc if doc.id == doc_id else doc.model_copy(update={"id": doc_id})
        except Exception:
            pass  # corrupt/unreadable must never crash the backend — start blank
        return self._default(doc_id)

    def exists(self, doc_id: str) -> bool:
        return self._path(doc_id).exists()

    def get(self, doc_id: str) -> WhiteboardDocument:
        return self._load(doc_id)

    def create(self, doc_id: str, payload: WhiteboardCreate) -> WhiteboardDocument:
        doc = WhiteboardDocument(
            id=doc_id, title=payload.title or "Untitled",
            mode=wm.normalize_mode(payload.mode), blocks=payload.blocks or [],
            updated_at=_now())
        _atomic_write_text(self._path(doc_id), doc.model_dump_json(indent=2))
        return doc

    def update(self, doc_id: str, payload: WhiteboardUpdate) -> WhiteboardDocument:
        # PARTIAL-PATCH MERGE (invariant): a None field keeps the stored value, so a
        # blocks-only autosave never clobbers `mode` (and a mode change never drops
        # blocks). This is what makes doc-switching safe — a late autosave draining
        # for the previous doc can't corrupt its mode. Do NOT "simplify" to overwrite
        # fields unconditionally.
        cur = self._load(doc_id)
        doc = WhiteboardDocument(
            id=doc_id,
            title=cur.title if payload.title is None else payload.title,
            mode=cur.mode if payload.mode is None else wm.normalize_mode(payload.mode),
            blocks=cur.blocks if payload.blocks is None else payload.blocks,
            updated_at=_now())
        _atomic_write_text(self._path(doc_id), doc.model_dump_json(indent=2))
        return doc

    def delete(self, doc_id: str) -> None:
        self._path(doc_id).unlink(missing_ok=True)

    def list_summaries(self) -> list[WhiteboardDocumentSummary]:
        if not self._dir.exists():
            return []
        out: list[WhiteboardDocumentSummary] = []
        for p in self._dir.glob("*.json"):
            doc = self._load(p.stem)
            out.append(WhiteboardDocumentSummary(
                id=doc.id, title=doc.title, mode=doc.mode, updated_at=doc.updated_at))
        out.sort(key=lambda s: s.updated_at, reverse=True)  # most-recent first
        return out


# -- Manual outliner (opaque node list owned by the frontend) ----------------

class OutlineItemsDocument(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class OutlineItemsStore:
    """Per-document manual outliner — one file per document id under
    ``<data_dir>/outlines/{doc_id}.json``. Node shape is opaque (frontend-owned)."""

    def __init__(self, root: Path | None = None) -> None:
        self._dir = (root or _data_dir()) / _OL_DIRNAME

    def _path(self, doc_id: str) -> Path:
        return self._dir / f"{doc_id}.json"

    def get(self, doc_id: str) -> list[dict[str, Any]]:
        path = self._path(doc_id)
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    return data["items"]
        except Exception:
            pass  # a corrupt file must never crash the backend — start empty
        return []

    def replace(self, doc_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _atomic_write_text(self._path(doc_id), json.dumps({"items": list(items)}, indent=2))
        return list(items)

    def delete(self, doc_id: str) -> None:
        self._path(doc_id).unlink(missing_ok=True)


# -- Comments (per-document inline notes anchored to block spans) -------------

class CommentAnchor(BaseModel):
    """Where a comment attaches: a character span inside a block. Anchored by
    block INDEX (ProseMirror does not preserve block ids — see the renderer's
    docToBlocks) plus the quoted text and short prefix/suffix context, which the
    frontend uses to re-locate the span (and pick the right occurrence) after
    edits. prefix/suffix default to "" for comments created before context
    anchoring landed."""

    block_index: int
    from_offset: int
    to_offset: int
    end_block_index: Optional[int] = None  # last block of a multi-block selection
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
        path = self._path(doc_id)
        try:
            if path.exists():
                return CommentsDocument.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            pass  # corrupt/unreadable must never crash the backend — start empty
        return CommentsDocument()

    def _save(self, doc_id: str, doc: CommentsDocument) -> None:
        _atomic_write_text(self._path(doc_id), doc.model_dump_json(indent=2))

    def get(self, doc_id: str) -> CommentsDocument:
        return self._load(doc_id)

    def create(self, doc_id: str, comment_id: str, payload: CommentCreate) -> Comment:
        doc = self._load(doc_id)
        now = _now()
        comment = Comment(
            id=comment_id, anchor=payload.anchor, quote=payload.quote,
            body=payload.body, resolved=False, created_at=now, updated_at=now)
        doc.comments.append(comment)
        self._save(doc_id, doc)
        return comment

    def update(self, doc_id: str, comment_id: str, payload: CommentUpdate) -> Comment | None:
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
        doc = self._load(doc_id)
        before = len(doc.comments)
        doc.comments = [c for c in doc.comments if c.id != comment_id]
        if len(doc.comments) < before:
            self._save(doc_id, doc)
            return True
        return False

    def add_reply(self, doc_id: str, comment_id: str, reply_id: str,
                  payload: CommentReplyCreate) -> Comment | None:
        doc = self._load(doc_id)
        for i, c in enumerate(doc.comments):
            if c.id == comment_id:
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
        self._path(doc_id).unlink(missing_ok=True)


def migrate_legacy(default_doc_id: str) -> None:
    """One-time upgrade: fold the pre-multi-document singleton files
    (``whiteboard.json`` / ``outline.json``) into the default document so an
    upgrading user keeps their work. No-op once the per-document file exists."""
    root = _data_dir()
    legacy_wb = root / _LEGACY_WB
    new_wb = root / _WB_DIRNAME / f"{default_doc_id}.json"
    if legacy_wb.exists() and not new_wb.exists():
        try:
            doc = WhiteboardDocument.model_validate_json(legacy_wb.read_text(encoding="utf-8"))
            doc = doc.model_copy(update={"id": default_doc_id})
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
            _atomic_write_text(new_ol, json.dumps({"items": items}, indent=2))
            legacy_ol.rename(legacy_ol.with_suffix(".json.migrated"))
        except Exception:
            pass


whiteboard_store = WhiteboardStore()
outline_items_store = OutlineItemsStore()
comments_store = CommentsStore()
