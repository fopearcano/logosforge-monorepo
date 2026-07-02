"""Local PC Writer QA Agent Mode — OFF by default, opt-in via environment.

Makes LogosForge testable end-to-end by an external GUI / computer-use writer
agent running on the user's own machine, WITHOUT calling any real AI provider,
without real credentials, and without any network / cloud / GitHub access.
Everything here is inert unless ``LOGOSFORGE_QA_MODE`` is explicitly enabled.

LogosForge principle (unchanged): *the model generates; LogosForge remembers,
retrieves, structures, updates, and syncs.* QA mode swaps only the *generator*
for a deterministic fake one, so the real routing → validation → apply pipeline
can be exercised reproducibly from the real UI.

Safety guarantees:
  * Disabled by default. Only ``LOGOSFORGE_QA_MODE`` in {1, true, yes, on}
    enables it; nothing else changes runtime behavior.
  * The fake provider is reachable ONLY when QA mode is on — never in production
    (the ``chat_completion`` hook checks :func:`is_qa_mode` before short-circuit).
  * Structured QA logs REDACT secrets, API keys, tokens, bearer credentials,
    local / OS file paths, and raw audio + audio paths, and truncate long
    content. Raw user manuscripts are never written verbatim — only redacted,
    truncated excerpts.
  * Generated logs / reports are written under ``logs/writer_qa/`` and
    ``reports/writer_qa/local_*``; both are git-ignored.

This module is self-contained (standard library only) so it stays valid in an
installed / packaged app and never imports the headless harness in
``tools/writer_qa``.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment switches
# ---------------------------------------------------------------------------
QA_ENV = "LOGOSFORGE_QA_MODE"
PROFILE_ENV = "LOGOSFORGE_FAKE_PROVIDER_PROFILE"
LOG_DIR_ENV = "LOGOSFORGE_QA_LOG_DIR"
REPORT_DIR_ENV = "LOGOSFORGE_QA_REPORT_DIR"

_TRUE = {"1", "true", "yes", "on"}

DEFAULT_PROFILE = "valid_auto"


def is_qa_mode() -> bool:
    """True only when the local QA mode is explicitly enabled. Default OFF."""
    return os.environ.get(QA_ENV, "").strip().lower() in _TRUE


class FakeProviderError(Exception):
    """Simulated provider failure (timeout / connection error) for QA mode.

    Raised by the ``provider_error`` profile so a writer/QA agent can exercise
    the assistant's error path exactly like a real provider failure — without
    any network call.
    """


# ---------------------------------------------------------------------------
# Deterministic fake-provider profiles (self-contained; A–O)
# ---------------------------------------------------------------------------
# Mode-correct VALID outputs (one per writing mode) -------------------------
_VALID_NOVEL = (
    "Ada stepped into the archive, dust hanging in the dawn light. Milo did not "
    "look up from the cabinet. \"You're late,\" he said, and she heard the "
    "accusation folded under the words."
)
_VALID_SCREENPLAY = (
    "MILO VOSS\nIt was not open when I arrived.\n\n"
    "ADA NORTH\nThen someone wanted us to think it was.\n\n"
    "Milo glances at the velvet cushion, then away."
)
_VALID_GRAPHIC_NOVEL = (
    "Panel 1\nVisual: Ada in the doorway, notebook clutched to her chest.\n"
    "Caption: Dawn, and the lock already broken.\n"
    "Dialogue: MILO: You are late.\nSFX: creak"
)
_VALID_STAGE = (
    "MILO. You are late.\n(He does not turn from the window.)\n"
    "ADA. The door was not supposed to be open."
)
_VALID_SERIES = (
    "Ada crossed the bullpen. On the monitor, last night's footage looped. "
    "\"Run it back,\" she told Milo. \"The part everyone skipped.\""
)

# Non-manuscript VALID outputs ---------------------------------------------
_VALID_OUTLINE = (
    "Act I\n- Scene 1: Ada arrives at the archive before dawn\n"
    "- Scene 2: the missing ledger\n- Scene 3: the first lie"
)
_VALID_PSYKE = (
    "Ada North — methodical archivist; distrusts easy answers; haunted by a "
    "case she could not close. Wants the truth even when it costs her."
)
_VALID_NOTE_SUMMARY = (
    "Summary: the heist hinges on the archive's blind spot. Open questions: who "
    "tipped them off, and where the ledger went."
)

# INVALID outputs the Assistant contract must block / withhold --------------
_INVALID_PLANNING = (
    "### Suggested Scene Structure\n"
    "- [INTRODUCING] establish the archive at dawn\n"
    "- [MAIN ACTION] Milo confronts Ada\n"
    "- [CULMINATING MOMENT] the reveal\n\n"
    "## Production Notes\n"
    "Key Questions to Explore:\n"
    "1. What does Ada want?\n"
    "Let me craft a taut scene. This creates visual rhythm."
)
_INVALID_CONTEXT_DUMP = (
    "[AI Mode: Balance]\n"
    "Based on PSYKE Context and Global Story Memory, here is the scene.\n"
    "Using the context above, I will now write."
)
_INVALID_META = (
    "I'll help you with this. Here's how I will approach the scene. "
    "This structured approach uses the Stack Technique. Let me begin."
)
# Wrong-mode: prose returned where a non-prose mode is expected.
_INVALID_WRONG_MODE = _VALID_NOVEL
# Secret leak: must be WITHHELD by the validator (diagnostic_only), never shown.
_INVALID_SECRET_LEAK = (
    "Here is the scene. api_key: sk-ABCD1234EFGH5678IJKL and the source clip is "
    "/Users/jane/Recordings/take_01.wav for reference."
)

# Public, self-contained profile table (A–O) -------------------------------
# Order documents the A–O labelling used in docs / the agent script.
QA_PROFILES: dict[str, str] = {
    "valid_novel_prose": _VALID_NOVEL,             # A
    "valid_screenplay_dialogue": _VALID_SCREENPLAY,  # B
    "valid_graphic_novel_panel": _VALID_GRAPHIC_NOVEL,  # C
    "valid_stage_script_dialogue": _VALID_STAGE,   # D
    "valid_series_scene": _VALID_SERIES,           # E
    "valid_outline_structure": _VALID_OUTLINE,     # F
    "valid_psyke_entity": _VALID_PSYKE,            # G
    "valid_note_summary": _VALID_NOTE_SUMMARY,     # H
    "invalid_planning_markdown": _INVALID_PLANNING,  # I
    "invalid_context_dump": _INVALID_CONTEXT_DUMP,   # J
    "invalid_meta_reasoning": _INVALID_META,       # K
    "invalid_wrong_mode": _INVALID_WRONG_MODE,     # L
    "invalid_empty": "",                           # M
    "invalid_secret_leak": _INVALID_SECRET_LEAK,   # N
    # "provider_error" (O) is handled specially in fake_completion (it raises).
}

# Mode → its valid manuscript output, used by the "valid_auto" default so the
# real UI returns mode-correct content when no explicit profile is chosen.
_MODE_VALID = {
    "novel": _VALID_NOVEL,
    "screenplay": _VALID_SCREENPLAY,
    "graphic_novel": _VALID_GRAPHIC_NOVEL,
    "stage_script": _VALID_STAGE,
    "series": _VALID_SERIES,
}


def list_profiles() -> tuple[str, ...]:
    """All selectable fake-provider profiles (A–O) plus the meta defaults."""
    return tuple(QA_PROFILES) + ("provider_error", "valid_auto")


def fake_provider_profile() -> str:
    """Resolve the active fake-provider profile.

    Precedence: settings key ``qa_fake_provider_profile`` → environment
    ``LOGOSFORGE_FAKE_PROVIDER_PROFILE`` → :data:`DEFAULT_PROFILE`.
    """
    try:  # settings first (best-effort; never required)
        from logosforge.settings import get_manager
        val = str(get_manager().get("qa_fake_provider_profile") or "").strip()
        if val:
            return val
    except Exception:
        pass
    env = os.environ.get(PROFILE_ENV, "").strip()
    if env:
        return env
    return DEFAULT_PROFILE


# Unique ROLE phrases emitted by ``assistant_contract.output_contract`` per mode
# (the only reliable mode signal — several contracts mention "screenplay" in
# their forbidden clauses, so we key off the ROLE line, not loose tokens).
_ROLE_TO_MODE = (
    ("graphic novel manuscript", "graphic_novel"),
    ("screenplay manuscript", "screenplay"),
    ("stage script manuscript", "stage_script"),
    ("series manuscript", "series"),
    ("novel manuscript", "novel"),
)


def _infer_mode(messages) -> str:
    """Best-effort writing-mode inference from the prompt (for ``valid_auto``)."""
    text = ""
    if isinstance(messages, str):
        text = messages
    elif messages:
        try:
            text = " ".join(
                str(m.get("content", "")) for m in messages
                if isinstance(m, dict)
            )
        except Exception:
            text = str(messages)
    low = text.lower()
    for phrase, mode in _ROLE_TO_MODE:
        if phrase in low:
            return mode
    # Secondary hints for non-manuscript prompts.
    if "panel-level" in low or "panel n" in low:
        return "graphic_novel"
    return "novel"


def fake_completion(messages=None, *, profile: str | None = None) -> str:
    """Return a deterministic fake completion for the active QA profile.

    * ``provider_error`` raises :class:`FakeProviderError`.
    * ``invalid_empty`` (and any empty profile value) returns ``""``.
    * ``valid_auto`` (the default) infers the writing mode from the prompt and
      returns mode-correct valid content.
    * Any unknown profile falls back to the safe ``valid_auto`` behavior so the
      live UI never crashes on a typo.

    Never touches the network, a real provider, or any credential.
    """
    prof = (profile or fake_provider_profile() or DEFAULT_PROFILE).strip()
    if prof == "provider_error":
        raise FakeProviderError("simulated provider failure (QA mode)")
    if prof in ("valid_auto", "auto", ""):
        return _MODE_VALID.get(_infer_mode(messages), _VALID_NOVEL)
    spec = QA_PROFILES.get(prof)
    if spec is None:
        # Unknown profile → safe deterministic default; never raise in the UI.
        return _MODE_VALID.get(_infer_mode(messages), _VALID_NOVEL)
    return spec


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
# Field excerpts default to a short cap; full bodies are never logged verbatim.
DEFAULT_MAX_LEN = 280
_FIELD_MAX = 200

# Secrets / API keys / tokens — redacted whole (key + value where present).
_SECRET_RX = re.compile(
    r"\bsk-[A-Za-z0-9]{8,}\b"
    r"|\b(?:api[_-]?key|apikey|password|passwd|secret|bearer|token|"
    r"authorization|auth[_-]?token|access[_-]?token|client[_-]?secret)\b"
    r"\s*[:=]\s*\S+"
    r"|\bBearer\s+[A-Za-z0-9._\-]{10,}",
    re.IGNORECASE,
)
# Audio files / paths — redacted whole, BEFORE generic path redaction.
_AUDIO_RX = re.compile(
    r"[^\s'\"]*\.(?:wav|mp3|m4a|flac|ogg|aac|wma|aif|aiff)\b",
    re.IGNORECASE,
)
# Absolute local / OS paths (POSIX ≥2 segments, or Windows drive paths).
_PATH_RX = re.compile(
    r"[A-Za-z]:\\[^\s'\"]+"
    r"|(?:/[A-Za-z0-9._\-]+){2,}/?",
)


def redact(value, *, max_len: int = DEFAULT_MAX_LEN) -> str:
    """Redact secrets / tokens / audio / local paths, then truncate.

    Over-redaction is intentional and safe: a QA log must never carry a real
    secret, credential, raw-audio path, or private OS path, and never a full
    manuscript body.
    """
    s = "" if value is None else str(value)
    s = _SECRET_RX.sub("<redacted-secret>", s)
    s = _AUDIO_RX.sub("<audio>", s)
    s = _PATH_RX.sub("<path>", s)
    if len(s) > max_len:
        s = s[:max_len].rstrip() + f"… (+{len(s) - max_len} chars redacted)"
    return s


# ---------------------------------------------------------------------------
# Structured, redacted QA logging
# ---------------------------------------------------------------------------
_EVENTS: list[dict] = []
# Fields that carry user / model content → always heavily redacted + truncated.
_EXCERPT_FIELDS = {
    "response_excerpt", "instruction_excerpt", "instruction", "response",
    "target_text", "excerpt", "note",
}


def qa_log_dir() -> Path:
    """Directory for the rolling QA session log (git-ignored)."""
    override = os.environ.get(LOG_DIR_ENV, "").strip()
    return Path(override) if override else Path("logs") / "writer_qa"


def _session_log_path() -> Path:
    return qa_log_dir() / "qa_session.jsonl"


def _redact_field(key: str, value):
    if key in _EXCERPT_FIELDS:
        return redact(value, max_len=DEFAULT_MAX_LEN)
    if isinstance(value, str):
        return redact(value, max_len=_FIELD_MAX)
    if isinstance(value, (list, tuple)):
        return [redact(str(x), max_len=_FIELD_MAX) for x in value][:20]
    if isinstance(value, dict):
        return {str(k): _redact_field(str(k), v) for k, v in list(value.items())[:20]}
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return redact(value, max_len=_FIELD_MAX)


def log_event(event_type: str, **fields) -> dict:
    """Record one redacted structured QA event (buffered + appended to disk).

    Returns the redacted record. Callers gate on :func:`is_qa_mode`; this
    function redacts unconditionally so it is safe to unit-test directly.
    """
    rec: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": str(event_type),
    }
    for key, value in fields.items():
        rec[key] = _redact_field(key, value)
    _EVENTS.append(rec)
    try:
        path = _session_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging must never break the app
    return rec


def buffered_events() -> list[dict]:
    """A copy of the in-memory event buffer (already redacted)."""
    return list(_EVENTS)


def reset_log() -> None:
    """Clear the in-memory event buffer (used by tests / a fresh session)."""
    _EVENTS.clear()


# ---------------------------------------------------------------------------
# Report export
# ---------------------------------------------------------------------------
def default_report_base() -> Path:
    """Base path (no extension) for the exported local QA report (git-ignored)."""
    override = os.environ.get(REPORT_DIR_ENV, "").strip()
    base_dir = Path(override) if override else Path("reports") / "writer_qa"
    return base_dir / "local_latest"


def _summarize(events: list[dict]) -> dict:
    responses = [e for e in events if e.get("event") == "assistant_response"]
    by_status: dict[str, int] = {}
    by_section: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    withheld = 0
    applyable = 0
    for e in responses:
        st = str(e.get("validation_status", "none"))
        by_status[st] = by_status.get(st, 0) + 1
        sec = str(e.get("section", ""))
        by_section[sec] = by_section.get(sec, 0) + 1
        mode = str(e.get("writing_mode", ""))
        by_mode[mode] = by_mode.get(mode, 0) + 1
        if e.get("withheld"):
            withheld += 1
        if e.get("apply_allowed"):
            applyable += 1
    return {
        "events_total": len(events),
        "responses": len(responses),
        "by_validation_status": by_status,
        "by_section": by_section,
        "by_writing_mode": by_mode,
        "withheld_responses": withheld,
        "applyable_responses": applyable,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _render_markdown(summary: dict, events: list[dict]) -> str:
    lines = [
        "# LogosForge — Local Writer QA Report",
        "",
        "> Generated by the local QA agent mode (fake provider; no real "
        "provider / network / cloud). All content excerpts are redacted and "
        "truncated.",
        "",
        f"- Generated at: {summary.get('generated_at', '')}",
        f"- Events total: {summary.get('events_total', 0)}",
        f"- Assistant responses: {summary.get('responses', 0)}",
        f"- Withheld (secret/raw-audio): {summary.get('withheld_responses', 0)}",
        f"- Apply-eligible: {summary.get('applyable_responses', 0)}",
        "",
        "## Validation status",
        "",
    ]
    for st, n in sorted(summary.get("by_validation_status", {}).items()):
        lines.append(f"- {st}: {n}")
    lines += ["", "## By section", ""]
    for sec, n in sorted(summary.get("by_section", {}).items()):
        lines.append(f"- {sec or '(none)'}: {n}")
    lines += ["", "## Events", ""]
    for e in events:
        lines.append(
            f"- `{e.get('ts', '')}` **{e.get('event', '')}** "
            f"section={e.get('section', '')} mode={e.get('writing_mode', '')} "
            f"action={e.get('action', '')} kind={e.get('output_kind', '')} "
            f"status={e.get('validation_status', '')} "
            f"apply={e.get('apply_allowed', '')}"
        )
        excerpt = e.get("response_excerpt")
        if excerpt:
            lines.append(f"    - response: {excerpt}")
    lines.append("")
    return "\n".join(lines)


def export_report(path: str | Path | None = None) -> tuple[str, str]:
    """Write the buffered QA session to ``<base>.json`` + ``<base>.md``.

    Defaults to ``reports/writer_qa/local_latest.{json,md}`` (git-ignored).
    Returns the two written paths.
    """
    base = Path(path) if path is not None else default_report_base()
    events = buffered_events()
    summary = _summarize(events)
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"summary": summary, "events": events},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(summary, events), encoding="utf-8")
    return str(json_path), str(md_path)
