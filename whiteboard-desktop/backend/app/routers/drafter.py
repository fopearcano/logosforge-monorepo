"""Project-owned Drafter scratch pages.

The collection API is used by Whiteboard's local editor. The bounded page,
index, and search APIs let MCP clients inspect or mutate one page without ever
round-tripping the potentially large project-wide collection.
"""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ValidationError

from app.document_lifecycle import locked_document_request
from app.local_state import (
    DrafterPage,
    DrafterPageAlreadyExists,
    DrafterPageMutationResult,
    DrafterPageNotFound,
    DrafterPagePatch,
    DrafterPageSummary,
    DrafterPagesDocument,
    MutationIdConflict,
    ResourceRevisionConflict,
    WhiteboardBlock,
    drafter_page_summary,
    drafter_pages_store,
)
from app.persistence_order import accept_persistence_write, request_persistence_order
from app.resource_revision import (
    ResourceProtocolError,
    mutation_id_conflict,
    request_mutation_id,
    request_revision_precondition,
    resource_etag,
    revision_conflict,
)

router = APIRouter()

_MAX_PAGE_READ_BLOCKS = 200
_MAX_PAGE_READ_CHARACTERS = 500_000
_MAX_SEARCH_QUERY_CHARACTERS = 500
_MAX_SEARCH_RESULTS = 100
_MAX_SEARCH_SNIPPET_CHARACTERS = 500


class DrafterPageIndex(BaseModel):
    pages: list[DrafterPageSummary]
    revision: str
    page_count: int


class DrafterBlockExcerpt(BaseModel):
    block_index: int
    text_offset: int
    total_text_characters: int
    complete: bool
    marks_omitted: bool
    block: WhiteboardBlock


class DrafterPagePagination(BaseModel):
    offset: int
    text_offset: int
    returned_blocks: int
    total_blocks: int
    next_offset: int | None
    next_text_offset: int | None
    max_characters: int
    truncated: bool


class DrafterPageRead(BaseModel):
    page: DrafterPageSummary
    blocks: list[DrafterBlockExcerpt]
    pagination: DrafterPagePagination
    revision: str
    page_count: int


class DrafterSearchResult(BaseModel):
    page_id: str
    page_title: str
    match_scope: Literal["title", "block"]
    block_id: str | None = None
    block_index: int | None = None
    snippet: str


class DrafterSearchResponse(BaseModel):
    results: list[DrafterSearchResult]
    total_matches: int
    truncated: bool
    revision: str
    page_count: int


def _publish_revision(response: Response, incarnation: str, revision: str) -> None:
    response.headers["ETag"] = resource_etag("drafter", incarnation, revision)


def _find_page(document: DrafterPagesDocument, page_id: str) -> DrafterPage:
    page = next((candidate for candidate in document.pages if candidate.id == page_id), None)
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "drafter_page_not_found",
                "message": f"Drafter page '{page_id}' was not found.",
                "page_id": page_id,
            },
        )
    return page


def _mutation_result_from_document(
    document: DrafterPagesDocument,
    page_id: str,
) -> DrafterPageMutationResult:
    page = _find_page(document, page_id)
    return DrafterPageMutationResult(
        page=drafter_page_summary(page),
        revision=document.revision,
        page_count=len(document.pages),
    )


def _page_already_exists(
    page_id: str,
    incarnation: str,
    revision: str,
) -> ResourceProtocolError:
    current_etag = resource_etag("drafter", incarnation, revision)
    return ResourceProtocolError(
        status_code=status.HTTP_409_CONFLICT,
        headers={"ETag": current_etag},
        detail={
            "code": "drafter_page_already_exists",
            "message": f"Drafter page '{page_id}' already exists.",
            "page_id": page_id,
            "current_revision": revision,
            "current_etag": current_etag,
        },
    )


def _stale_order(
    page_id: str,
    incarnation: str,
    revision: str,
) -> ResourceProtocolError:
    current_etag = resource_etag("drafter", incarnation, revision)
    return ResourceProtocolError(
        status_code=status.HTTP_409_CONFLICT,
        headers={"ETag": current_etag},
        detail={
            "code": "stale_persistence_order",
            "message": "A newer Drafter write already superseded this request.",
            "page_id": page_id,
            "current_revision": revision,
            "current_etag": current_etag,
        },
    )


def _drafter_limit_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "code": "drafter_limits_exceeded",
            "message": (
                "The Drafter page or collection exceeds a storage safety limit."
            ),
        },
    )


def _snippet(text: str, match: re.Match[str], max_characters: int) -> str:
    if len(text) <= max_characters:
        return text
    match_length = match.end() - match.start()
    before = max(0, (max_characters - min(match_length, max_characters)) // 2)
    start = max(0, match.start() - before)
    end = min(len(text), start + max_characters)
    start = max(0, end - max_characters)
    prefix = start > 0
    suffix = end < len(text)
    body_start = start + (1 if prefix else 0)
    body_end = max(body_start, end - (1 if suffix else 0))
    return ("…" if prefix else "") + text[body_start:body_end] + ("…" if suffix else "")


@router.get("/api/drafter/page-index", response_model=DrafterPageIndex)
async def get_drafter_page_index(
    request: Request,
    response: Response,
    doc: int | None = Query(None),
) -> DrafterPageIndex:
    async with locked_document_request(request, doc) as locked:
        document = drafter_pages_store.get_document(locked.document_id)
        _publish_revision(response, locked.incarnation, document.revision)
        return DrafterPageIndex(
            pages=[drafter_page_summary(page) for page in document.pages],
            revision=document.revision,
            page_count=len(document.pages),
        )


@router.get("/api/drafter/search", response_model=DrafterSearchResponse)
async def search_drafter_pages(
    request: Request,
    response: Response,
    doc: int | None = Query(None),
    q: str = Query(..., min_length=1, max_length=_MAX_SEARCH_QUERY_CHARACTERS),
    limit: int = Query(20, ge=1, le=_MAX_SEARCH_RESULTS),
    snippet_characters: int = Query(240, ge=40, le=_MAX_SEARCH_SNIPPET_CHARACTERS),
) -> DrafterSearchResponse:
    if not q.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Drafter search query must not be blank.",
        )
    pattern = re.compile(re.escape(q.strip()), re.IGNORECASE)
    async with locked_document_request(request, doc) as locked:
        document = drafter_pages_store.get_document(locked.document_id)
        results: list[DrafterSearchResult] = []
        total_matches = 0
        for page in document.pages:
            title_match = pattern.search(page.title)
            if title_match is not None:
                total_matches += 1
                if len(results) < limit:
                    results.append(DrafterSearchResult(
                        page_id=page.id,
                        page_title=page.title,
                        match_scope="title",
                        snippet=_snippet(page.title, title_match, snippet_characters),
                    ))
            for block_index, block in enumerate(page.blocks):
                block_match = pattern.search(block.text)
                if block_match is None:
                    continue
                total_matches += 1
                if len(results) < limit:
                    results.append(DrafterSearchResult(
                        page_id=page.id,
                        page_title=page.title,
                        match_scope="block",
                        block_id=block.id,
                        block_index=block_index,
                        snippet=_snippet(block.text, block_match, snippet_characters),
                    ))
        _publish_revision(response, locked.incarnation, document.revision)
        return DrafterSearchResponse(
            results=results,
            total_matches=total_matches,
            truncated=total_matches > len(results),
            revision=document.revision,
            page_count=len(document.pages),
        )


@router.get("/api/drafter/pages", response_model=DrafterPagesDocument)
async def get_drafter_pages(
    request: Request,
    response: Response,
    doc: int | None = Query(None),
) -> DrafterPagesDocument:
    async with locked_document_request(request, doc) as locked:
        drafter = drafter_pages_store.get_document(locked.document_id)
        _publish_revision(response, locked.incarnation, drafter.revision)
        return drafter


@router.get("/api/drafter/pages/{page_id}", response_model=DrafterPageRead)
async def get_drafter_page(
    request: Request,
    response: Response,
    page_id: str,
    doc: int | None = Query(None),
    offset: int = Query(0, ge=0, le=20_000),
    limit: int = Query(100, ge=1, le=_MAX_PAGE_READ_BLOCKS),
    max_characters: int = Query(100_000, ge=1, le=_MAX_PAGE_READ_CHARACTERS),
    text_offset: int = Query(0, ge=0, le=32_000_000),
) -> DrafterPageRead:
    async with locked_document_request(request, doc) as locked:
        document = drafter_pages_store.get_document(locked.document_id)
        page = _find_page(document, page_id)
        total_blocks = len(page.blocks)
        if offset > total_blocks or (offset == total_blocks and text_offset != 0):
            raise HTTPException(
                status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
                detail={
                    "code": "invalid_drafter_page_range",
                    "message": "The requested block or text offset is outside the page.",
                },
            )
        if offset < total_blocks and text_offset > len(page.blocks[offset].text):
            raise HTTPException(
                status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
                detail={
                    "code": "invalid_drafter_page_range",
                    "message": "The requested text offset is outside the first block.",
                },
            )

        excerpts: list[DrafterBlockExcerpt] = []
        block_index = offset
        first_text_offset = text_offset
        remaining = max_characters
        next_offset: int | None = None
        next_text_offset: int | None = None
        while block_index < total_blocks and len(excerpts) < limit and remaining > 0:
            source = page.blocks[block_index]
            start = first_text_offset if block_index == offset else 0
            take = min(len(source.text) - start, remaining)
            end = start + take
            whole_block = start == 0 and end == len(source.text)
            marks_omitted = bool(source.marks) and not whole_block
            excerpt = source.model_copy(update={
                "text": source.text[start:end],
                "marks": source.marks if whole_block else None,
            })
            excerpts.append(DrafterBlockExcerpt(
                block_index=block_index,
                text_offset=start,
                total_text_characters=len(source.text),
                complete=whole_block,
                marks_omitted=marks_omitted,
                block=excerpt,
            ))
            remaining -= take
            if end < len(source.text):
                next_offset = block_index
                next_text_offset = end
                break
            block_index += 1
            first_text_offset = 0

        if next_offset is None and block_index < total_blocks:
            next_offset = block_index
            next_text_offset = 0
        _publish_revision(response, locked.incarnation, document.revision)
        return DrafterPageRead(
            page=drafter_page_summary(page),
            blocks=excerpts,
            pagination=DrafterPagePagination(
                offset=offset,
                text_offset=text_offset,
                returned_blocks=len(excerpts),
                total_blocks=total_blocks,
                next_offset=next_offset,
                next_text_offset=next_text_offset,
                max_characters=max_characters,
                truncated=next_offset is not None,
            ),
            revision=document.revision,
            page_count=len(document.pages),
        )


@router.put("/api/drafter/pages", response_model=DrafterPagesDocument)
async def put_drafter_pages(
    request: Request,
    response: Response,
    payload: DrafterPagesDocument,
    doc: int | None = Query(None),
) -> DrafterPagesDocument:
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition = request_revision_precondition(
            request, "drafter", locked.incarnation, required=doc is not None
        )
        mutation_id = request_mutation_id(request)
        if precondition is not None and not precondition.matches_resource:
            current = drafter_pages_store.get_document(locked.document_id)
            raise revision_conflict(
                "drafter", locked.incarnation, precondition.revision, current.revision
            )
        order = request_persistence_order(request)
        with accept_persistence_write(
            "drafter",
            locked.document_id,
            order,
            current_revision=lambda: drafter_pages_store.get_document(
                locked.document_id
            ).revision,
        ) as accepted:
            if not accepted:
                drafter = drafter_pages_store.get_document(locked.document_id)
            else:
                try:
                    drafter = drafter_pages_store.replace_document(
                        locked.document_id,
                        payload.pages,
                        expected_revision=(
                            precondition.revision if precondition is not None else None
                        ),
                        mutation_id=mutation_id,
                    )
                except ResourceRevisionConflict as exc:
                    raise revision_conflict(
                        "drafter", locked.incarnation,
                        exc.expected_revision, exc.current_revision,
                    ) from exc
                except MutationIdConflict as exc:
                    raise mutation_id_conflict(exc.mutation_id) from exc
                accepted.commit(drafter.revision)
            _publish_revision(response, locked.incarnation, drafter.revision)
            return drafter


@router.post(
    "/api/drafter/pages",
    response_model=DrafterPageMutationResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_drafter_page(
    request: Request,
    response: Response,
    payload: DrafterPage,
    doc: int | None = Query(None),
) -> DrafterPageMutationResult:
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition = request_revision_precondition(
            request, "drafter", locked.incarnation, required=True
        )
        mutation_id = request_mutation_id(request, required=True)
        assert precondition is not None and mutation_id is not None
        current = drafter_pages_store.get_document(locked.document_id)
        if not precondition.matches_resource:
            raise revision_conflict(
                "drafter", locked.incarnation, precondition.revision, current.revision
            )
        order = request_persistence_order(request)
        with accept_persistence_write(
            "drafter",
            locked.document_id,
            order,
            current_revision=lambda: drafter_pages_store.get_document(
                locked.document_id
            ).revision,
        ) as accepted:
            if not accepted:
                current = drafter_pages_store.get_document(locked.document_id)
                try:
                    result = _mutation_result_from_document(current, payload.id)
                except HTTPException as exc:
                    if exc.status_code != status.HTTP_404_NOT_FOUND:
                        raise
                    raise _stale_order(
                        payload.id, locked.incarnation, current.revision
                    ) from exc
            else:
                try:
                    result = drafter_pages_store.create_page(
                        locked.document_id,
                        payload,
                        expected_revision=precondition.revision,
                        mutation_id=mutation_id,
                    )
                except ResourceRevisionConflict as exc:
                    raise revision_conflict(
                        "drafter", locked.incarnation,
                        exc.expected_revision, exc.current_revision,
                    ) from exc
                except MutationIdConflict as exc:
                    raise mutation_id_conflict(exc.mutation_id) from exc
                except DrafterPageAlreadyExists as exc:
                    current = drafter_pages_store.get_document(locked.document_id)
                    raise _page_already_exists(
                        str(exc), locked.incarnation, current.revision
                    ) from exc
                except ValidationError as exc:
                    raise _drafter_limit_error() from exc
                accepted.commit(result.revision)
            _publish_revision(response, locked.incarnation, result.revision)
            return result


@router.patch(
    "/api/drafter/pages/{page_id}",
    response_model=DrafterPageMutationResult,
)
async def patch_drafter_page(
    request: Request,
    response: Response,
    page_id: str,
    payload: DrafterPagePatch,
    doc: int | None = Query(None),
) -> DrafterPageMutationResult:
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition = request_revision_precondition(
            request, "drafter", locked.incarnation, required=True
        )
        mutation_id = request_mutation_id(request, required=True)
        assert precondition is not None and mutation_id is not None
        current = drafter_pages_store.get_document(locked.document_id)
        if not precondition.matches_resource:
            raise revision_conflict(
                "drafter", locked.incarnation, precondition.revision, current.revision
            )
        order = request_persistence_order(request)
        with accept_persistence_write(
            "drafter",
            locked.document_id,
            order,
            current_revision=lambda: drafter_pages_store.get_document(
                locked.document_id
            ).revision,
        ) as accepted:
            if not accepted:
                current = drafter_pages_store.get_document(locked.document_id)
                try:
                    result = _mutation_result_from_document(current, page_id)
                except HTTPException as exc:
                    if exc.status_code != status.HTTP_404_NOT_FOUND:
                        raise
                    raise _stale_order(
                        page_id, locked.incarnation, current.revision
                    ) from exc
            else:
                try:
                    result = drafter_pages_store.patch_page(
                        locked.document_id,
                        page_id,
                        payload,
                        expected_revision=precondition.revision,
                        mutation_id=mutation_id,
                    )
                except ResourceRevisionConflict as exc:
                    raise revision_conflict(
                        "drafter", locked.incarnation,
                        exc.expected_revision, exc.current_revision,
                    ) from exc
                except MutationIdConflict as exc:
                    raise mutation_id_conflict(exc.mutation_id) from exc
                except DrafterPageNotFound as exc:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={
                            "code": "drafter_page_not_found",
                            "message": f"Drafter page '{page_id}' was not found.",
                            "page_id": page_id,
                        },
                    ) from exc
                except ValidationError as exc:
                    raise _drafter_limit_error() from exc
                accepted.commit(result.revision)
            _publish_revision(response, locked.incarnation, result.revision)
            return result
