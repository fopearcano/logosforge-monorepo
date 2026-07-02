"""Conservative repair for manuscript bodies contaminated by old outline bugs.

Earlier versions could write a generated *outline* response into a scene's
manuscript ``content`` field (e.g. via the Assistant's Replace/Append while in
Outline Mode). That prose then renders in the Manuscript canvas as if the user
had written it. Prevention is now in place, but existing projects may still
carry the contamination.

This module DETECTS only *obvious* outline contamination and clears it — never
normal user prose. Anything uncertain is reported and left untouched. It is
dry-run by default and is never invoked automatically.

Detection signals (a scene's ``content`` is treated as contaminated only when a
signal fires):
  * starts with "a complete outline" (the classic generated preamble),
  * contains "a complete outline for your novel",
  * the body is *exactly equal* to the scene's own ``summary`` or ``synopsis``
    (outline planning text duplicated into the manuscript body), or
  * the body is *pure outline markup* (mostly headers / bullets / Act-Chapter-
    Scene-Beat labels, with no real prose sentences).

Pure-logic + a single project-scoped DB read/write — no UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Markup line: markdown header, bullet, or numbered list item.
_MARKUP_RE = re.compile(r"^\s*(#{1,6}\s|[-*•]\s|\d+[.)]\s)")
# Structural keyword line: "Act 1", "Chapter 2:", "Scene - …", "Beat …".
_KIND_RE = re.compile(r"^\s*(act|part|chapter|sequence|scene|beat)\b", re.IGNORECASE)

_PREAMBLE_PREFIXES = ("a complete outline",)
_PREAMBLE_CONTAINS = ("a complete outline for your novel",)


@dataclass
class ContaminationFinding:
    scene_id: int
    title: str
    reason: str
    preview: str           # first ~80 chars of the offending body


def _looks_like_pure_outline_markup(text: str) -> bool:
    """True if *text* is overwhelmingly outline markup, not prose.

    Requires several lines and a strong majority that are headers/bullets/
    structural-keyword lines, so a normal paragraph (even one mentioning an
    act/scene) is never flagged.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3:
        return False
    structural = sum(
        1 for ln in lines if _MARKUP_RE.match(ln) or _KIND_RE.match(ln)
    )
    # No long prose sentence should be present (a real paragraph line).
    has_prose_line = any(
        not _MARKUP_RE.match(ln) and not _KIND_RE.match(ln) and len(ln.split()) > 12
        for ln in lines
    )
    return (structural / len(lines)) >= 0.7 and not has_prose_line


def _contamination_reason(scene) -> str | None:
    """Return a reason string if *scene*'s content is obvious outline
    contamination, else None (uncertain / clean is left alone)."""
    content = (getattr(scene, "content", "") or "").strip()
    if not content:
        return None
    low = content.lower()
    if low.startswith(_PREAMBLE_PREFIXES):
        return "body starts with a generated outline preamble"
    if any(p in low for p in _PREAMBLE_CONTAINS):
        return "body contains a generated outline title"
    summary = (getattr(scene, "summary", "") or "").strip()
    if summary and content == summary:
        return "body is exactly the scene's outline summary"
    synopsis = (getattr(scene, "synopsis", "") or "").strip()
    if synopsis and content == synopsis:
        return "body is exactly the scene's synopsis"
    if _looks_like_pure_outline_markup(content):
        return "body is pure outline markup (headers/bullets), not prose"
    return None


def scan_manuscript_contamination(db, project_id: int) -> list[ContaminationFinding]:
    """Return obvious-contamination findings for *project_id* (no writes)."""
    findings: list[ContaminationFinding] = []
    for scene in db.get_all_scenes(project_id):
        reason = _contamination_reason(scene)
        if reason is not None:
            body = (scene.content or "").strip().replace("\n", " ")
            findings.append(ContaminationFinding(
                scene_id=scene.id,
                title=(scene.title or "(untitled)"),
                reason=reason,
                preview=body[:80] + ("…" if len(body) > 80 else ""),
            ))
    return findings


def repair_manuscript_contamination(
    db, project_id: int, *, apply: bool = False,
) -> dict:
    """Detect (and optionally clear) obvious outline contamination.

    Returns a report ``{"scanned", "cleared", "findings"}``. With ``apply`` left
    False (the default) nothing is written — it only reports what *would* be
    cleared. When ``apply=True`` the offending ``content`` is set to "" (the
    scene, its title, summary, and all structure are preserved). Conservative by
    design: only the signals above clear a body; anything else is untouched.
    """
    findings = scan_manuscript_contamination(db, project_id)
    cleared = 0
    if apply:
        for f in findings:
            db.update_scene_content(f.scene_id, "")
            cleared += 1
    return {
        "scanned": len(db.get_all_scenes(project_id)),
        "cleared": cleared,
        "findings": findings,
    }
