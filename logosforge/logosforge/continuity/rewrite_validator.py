"""Continuity validation for proposed changes (Phase 10Q).

Compares before/after text for a proposed rewrite / controlled-apply and reports
continuity risks. **Preview only** — never mutates; apply still requires the
existing Controlled Apply confirmation. Deterministic; reuses
``revision_intelligence.psyke_impact``.
"""

from __future__ import annotations

import re

from logosforge.continuity import models as M

_SLUG = re.compile(r"\b(INT|EXT|INT\.?/EXT)\b[.\- ]", re.I)
_TIME = re.compile(r"\b(DAY|NIGHT|DAWN|DUSK|MORNING|EVENING|AFTERNOON|CONTINUOUS|"
                   r"LATER|MOMENTS LATER)\b", re.I)


def _tokens(pat: re.Pattern, text: str) -> set[str]:
    return {m.group(0).upper().strip(". -") for m in pat.finditer(text or "")}


def validate_continuity_change(db, project_id: int, target_type: str,
                               target_id, before_text: str | None,
                               after_text: str | None, *,
                               writing_mode: str | None = None,
                               ) -> M.ContinuityChangeValidation:
    if writing_mode is None:
        try:
            from logosforge.writing_modes import get_project_writing_mode_by_id
            writing_mode = get_project_writing_mode_by_id(db, project_id)
        except Exception:
            writing_mode = "novel"

    v = M.ContinuityChangeValidation(target_type=target_type, target_id=target_id,
                                     writing_mode=writing_mode)

    # Removed PSYKE references (confirmed) → warning.
    try:
        from logosforge.revision_intelligence.psyke_impact import detect_psyke_impact
        for imp in detect_psyke_impact(db, project_id, before_text, after_text):
            if getattr(imp, "impact_kind", "") == "removed":
                name = getattr(imp, "name", "") or "A PSYKE entry"
                v.warnings.append(f"'{name}' is no longer mentioned after the change.")
                v.related_psyke.append(name)
    except Exception:
        pass

    before, after = before_text or "", after_text or ""

    # Screenplay heading / time continuity.
    if writing_mode == "screenplay":
        b_slug, a_slug = _tokens(_SLUG, before), _tokens(_SLUG, after)
        if b_slug and not a_slug:
            v.warnings.append("Scene heading (INT/EXT) removed by the change.")
        b_time, a_time = _tokens(_TIME, before), _tokens(_TIME, after)
        if b_time and a_time and b_time != a_time:
            v.warnings.append(
                f"Time-of-day marker changed ({'/'.join(b_time)} → "
                f"{'/'.join(a_time)}).")
        v.follow_up_checks.append("Re-validate Fountain/production export.")

    # Major length reduction can drop continuity content.
    if before and len(after) < 0.5 * len(before):
        v.warnings.append("The change removes more than half the text — verify no "
                          "continuity-bearing content was lost.")

    # Safe apply mode suggestion.
    if v.blocking:
        v.suggested_apply_mode = "manual_copy"
    elif v.warnings:
        v.suggested_apply_mode = "replace"
    v.follow_up_checks.append("Run a scene continuity check after applying.")

    return v
