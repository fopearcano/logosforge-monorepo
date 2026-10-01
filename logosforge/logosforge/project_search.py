"""Project-scoped, read-only search shared by HTTP and external clients.

The search deliberately derives its index from authoritative project rows on
each request.  That keeps writes simple and avoids a second persisted index
that could drift from SQLite.  Result ranking is internal; the public wire
format remains the compact ``kind/id/title/excerpt`` envelope.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from logosforge.comment_revision import comment_revision
from logosforge.db import Database

ProjectSearchKind = Literal["scene", "note", "psyke", "comment"]
PROJECT_SEARCH_KINDS: frozenset[ProjectSearchKind] = frozenset(
    {"scene", "note", "psyke", "comment"}
)
MAX_EXCERPT_LENGTH = 280


@dataclass(frozen=True)
class ProjectSearchMatch:
    kind: ProjectSearchKind
    id: int
    title: str
    excerpt: str
    revision: str | None = None
    resolved: bool | None = None


@dataclass(frozen=True)
class _FieldMatch:
    score: int
    field_order: int
    offset: int
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class _Candidate:
    match: ProjectSearchMatch
    field: _FieldMatch


_KIND_ORDER = {"scene": 0, "note": 1, "psyke": 2, "comment": 3}


def _single_line(value: object) -> str:
    # Normalize canonically equivalent input (notably decomposed text from
    # macOS input methods) before matching.  Excerpts intentionally use the
    # same NFC representation so their offsets remain exact.
    return unicodedata.normalize("NFC", " ".join(str(value or "").split()))


def _fold_with_offsets(value: str) -> tuple[str, list[int]]:
    """Case-fold *value* while retaining indexes into the original string.

    Unicode case folding can expand one character (``ß`` -> ``ss``), so an
    index into ``value.casefold()`` cannot safely slice ``value`` directly.
    """
    folded: list[str] = []
    offsets: list[int] = []
    for index, character in enumerate(value):
        chunk = character.casefold()
        folded.append(chunk)
        offsets.extend([index] * len(chunk))
    return "".join(folded), offsets


def _field_match(
    needle: str,
    value: object,
    *,
    weight: int,
    field_order: int,
) -> _FieldMatch | None:
    text = _single_line(value)
    if not text:
        return None
    folded, offsets = _fold_with_offsets(text)
    offset = folded.find(needle)
    if offset < 0:
        return None

    if folded == needle:
        match_class = 3
    elif offset == 0:
        match_class = 2
    else:
        match_class = 1
    score = match_class * 10_000 + weight - min(offset, 1_000)

    start = offsets[offset]
    folded_end = min(len(offsets) - 1, offset + len(needle) - 1)
    end = offsets[folded_end] + 1
    return _FieldMatch(score, field_order, offset, text, start, end)


def _best_field(
    needle: str,
    fields: Sequence[tuple[object, int]],
) -> _FieldMatch | None:
    matches = [
        match
        for field_order, (value, weight) in enumerate(fields)
        if (match := _field_match(
            needle,
            value,
            weight=weight,
            field_order=field_order,
        )) is not None
    ]
    if not matches:
        return None
    return min(
        matches,
        key=lambda match: (-match.score, match.field_order, match.offset),
    )


def _excerpt(match: _FieldMatch) -> str:
    text = match.text
    if len(text) <= MAX_EXCERPT_LENGTH:
        return text

    # Keep useful lead-in context while guaranteeing the result, including
    # ellipsis markers, never exceeds the public bound.
    window_start = max(0, match.start - 90)
    has_prefix = window_start > 0
    reserve = 1 if has_prefix else 0
    provisional_end = window_start + MAX_EXCERPT_LENGTH - reserve
    has_suffix = provisional_end < len(text)
    reserve += 1 if has_suffix else 0
    core_length = MAX_EXCERPT_LENGTH - reserve

    if match.end > window_start + core_length:
        window_start = max(0, match.end - core_length)
        has_prefix = window_start > 0
        reserve = 1 if has_prefix else 0
        has_suffix = window_start + MAX_EXCERPT_LENGTH - reserve < len(text)
        reserve += 1 if has_suffix else 0
        core_length = MAX_EXCERPT_LENGTH - reserve

    window_end = min(len(text), window_start + core_length)
    return (
        ("…" if window_start else "")
        + text[window_start:window_end]
        + ("…" if window_end < len(text) else "")
    )


def _candidate(
    *,
    kind: ProjectSearchKind,
    item_id: int | None,
    title: str,
    needle: str,
    fields: Sequence[tuple[object, int]],
    revision: str | None = None,
    resolved: bool | None = None,
) -> _Candidate | None:
    if item_id is None:
        return None
    field = _best_field(needle, fields)
    if field is None:
        return None
    return _Candidate(
        match=ProjectSearchMatch(
            kind=kind,
            id=int(item_id),
            title=title,
            excerpt=_excerpt(field),
            revision=revision,
            resolved=resolved,
        ),
        field=field,
    )


def _psyke_details_text(raw: str | None) -> str:
    try:
        value = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        value = {}
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def search_project(
    db: Database,
    project_id: int,
    query: str,
    *,
    kinds: set[ProjectSearchKind] | frozenset[ProjectSearchKind] | None = None,
    limit: int = 100,
) -> list[ProjectSearchMatch]:
    """Return deterministic, project-local matches for *query*.

    The API layer validates bounds and kind vocabulary.  Defensive clamping
    here keeps direct core callers bounded as well.
    """
    normalized_query = _single_line(query)
    if not normalized_query:
        return []
    needle = normalized_query.casefold()
    selected = PROJECT_SEARCH_KINDS if kinds is None else PROJECT_SEARCH_KINDS & kinds
    candidates: list[_Candidate] = []

    if "scene" in selected:
        for scene in db.get_all_scenes(project_id):
            title = scene.title or f"Scene {scene.id}"
            candidate = _candidate(
                kind="scene",
                item_id=scene.id,
                title=title,
                needle=needle,
                fields=[
                    (title, 900),
                    (str(scene.id), 850),
                    (scene.summary, 720),
                    (scene.synopsis, 700),
                    (scene.goal, 650),
                    (scene.conflict, 640),
                    (scene.outcome, 630),
                    (scene.beat, 610),
                    (scene.act, 560),
                    (scene.chapter, 550),
                    (scene.plotline, 540),
                    (scene.tags, 520),
                    (getattr(scene, "slugline", ""), 500),
                    (getattr(scene, "location", ""), 490),
                    (getattr(scene, "interior_exterior", ""), 480),
                    (getattr(scene, "time_of_day", ""), 470),
                    (getattr(scene, "visual_objective", ""), 450),
                    (getattr(scene, "dramatic_turn", ""), 440),
                    (getattr(scene, "blocking_notes", ""), 420),
                    (getattr(scene, "subtext_notes", ""), 410),
                    (getattr(scene, "setup_payoff_links", ""), 400),
                    (getattr(scene, "montage_group", ""), 390),
                    (getattr(scene, "cinematic_pacing", ""), 380),
                    (getattr(scene, "continuity_notes", ""), 370),
                    (getattr(scene, "visible_conflict", ""), 360),
                    (getattr(scene, "hidden_conflict", ""), 350),
                    (getattr(scene, "emotional_turn", ""), 340),
                    (getattr(scene, "who_knows_what", ""), 330),
                    (getattr(scene, "physical_action", ""), 320),
                    (getattr(scene, "visual_symbolism", ""), 310),
                    (getattr(scene, "stage_location", ""), 300),
                    (getattr(scene, "set_description", ""), 290),
                    (getattr(scene, "scene_objective", ""), 280),
                    (getattr(scene, "entrance_exit_notes", ""), 270),
                    (getattr(scene, "prop_notes", ""), 260),
                    (getattr(scene, "cue_notes", ""), 250),
                    (getattr(scene, "offstage_events", ""), 240),
                    (getattr(scene, "audience_visibility_notes", ""), 230),
                    (scene.content, 200),
                ],
            )
            if candidate is not None:
                candidates.append(candidate)

    if "note" in selected:
        for note in db.get_all_notes(project_id):
            title = note.title or f"Note {note.id}"
            candidate = _candidate(
                kind="note",
                item_id=note.id,
                title=title,
                needle=needle,
                fields=[
                    (title, 900),
                    (str(note.id), 850),
                    (note.tags, 520),
                    (note.content, 200),
                ],
            )
            if candidate is not None:
                candidates.append(candidate)

    if "psyke" in selected:
        for entry in db.get_all_psyke_entries(project_id):
            title = entry.name or f"PSYKE entry {entry.id}"
            candidate = _candidate(
                kind="psyke",
                item_id=entry.id,
                title=title,
                needle=needle,
                fields=[
                    (title, 900),
                    (str(entry.id), 850),
                    (entry.aliases, 760),
                    (entry.entry_type, 560),
                    (entry.notes, 220),
                    (_psyke_details_text(entry.details_json), 180),
                ],
            )
            if candidate is not None:
                candidates.append(candidate)

    if "comment" in selected:
        for comment in db.get_all_comments(project_id):
            replies = [
                reply
                for reply in db.get_comment_replies(comment.id)
                if reply.project_id == project_id
            ]
            quote_preview = _single_line(comment.quote)
            if len(quote_preview) > 80:
                quote_preview = quote_preview[:80] + "…"
            title = f"Comment {comment.id}: {quote_preview}"
            fields: list[tuple[object, int]] = [
                (title, 900),
                (str(comment.id), 850),
                (comment.quote, 820),
                (comment.body, 600),
            ]
            fields.extend(
                (f"{reply.author}: {reply.body}", 400)
                for reply in replies
            )
            candidate = _candidate(
                kind="comment",
                item_id=comment.id,
                title=title,
                needle=needle,
                fields=fields,
                resolved=bool(comment.resolved),
            )
            if candidate is not None:
                candidates.append(_Candidate(
                    match=replace(
                        candidate.match,
                        revision=comment_revision(comment, replies),
                    ),
                    field=candidate.field,
                ))

    candidates.sort(key=lambda candidate: (
        -candidate.field.score,
        candidate.field.field_order,
        candidate.field.offset,
        _KIND_ORDER[candidate.match.kind],
        candidate.match.title.casefold(),
        candidate.match.title,
        candidate.match.id,
    ))
    bounded_limit = max(1, min(int(limit), 100))
    return [candidate.match for candidate in candidates[:bounded_limit]]


__all__ = [
    "MAX_EXCERPT_LENGTH",
    "PROJECT_SEARCH_KINDS",
    "ProjectSearchKind",
    "ProjectSearchMatch",
    "search_project",
]
