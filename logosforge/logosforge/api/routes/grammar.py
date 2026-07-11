"""Grammar / spelling / style check — stateless, no external dependency.

Wraps :mod:`logosforge.grammar_checker` (the same rule-based checker the Qt
manuscript editor uses). ``language=""`` auto-detects via trigram comparison.
The endpoint is project-scoped for auth/route-map consistency, but it operates
purely on the supplied ``text`` (nothing is read from or written to the project).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas
from logosforge.api.deps import get_project

router = APIRouter(tags=["grammar"])


@router.post(
    "/projects/{project_id}/grammar/check",
    response_model=schemas.GrammarCheckResultDTO,
)
def grammar_check(body: schemas.GrammarCheckRequestDTO, project=Depends(get_project)):
    from logosforge.grammar_checker import check_text, detect_language

    language = body.language.strip() or detect_language(body.text)
    issues = check_text(body.text, language=language)
    return schemas.GrammarCheckResultDTO(
        language=language,
        issues=[
            schemas.GrammarIssueDTO(
                start=i.start,
                end=i.end,
                issue_type=i.issue_type,
                message=i.message,
                suggestions=list(i.suggestions),
            )
            for i in issues
        ],
    )
