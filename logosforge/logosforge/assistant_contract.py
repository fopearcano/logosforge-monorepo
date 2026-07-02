"""Context-aware assistant output contracts + response validation.

Encodes the LogosForge assistant behavior model: assistant output is determined
by the current **section**, **writing mode**, **action**, and the user's explicit
instruction. Direct manuscript-writing actions must produce real manuscript
content in the project's mode format — never planning structure, analysis, or
markdown templates (those belong to Outline/planning sections or explicit
analysis actions). Pure functions only: no model/provider/DB/UI calls.

This module is the single source of truth for the strict system "output
contract" given to the model, and for validating responses before they are
shown/applied. It does not change provider behavior.
"""

from __future__ import annotations

import re

# ---- normalization ----------------------------------------------------------
_MODES = ("novel", "screenplay", "graphic_novel", "stage_script", "series")


def norm_mode(mode: str | None) -> str:
    m = (mode or "").strip().lower().replace(" ", "_").replace("-", "_")
    if m in _MODES:
        return m
    if "screen" in m:
        return "screenplay"
    if "graphic" in m or m == "gn" or "comic" in m:
        return "graphic_novel"
    if "stage" in m or "theatre" in m or "theater" in m or "play" in m:
        return "stage_script"
    if "series" in m or "episode" in m or "tv" in m:
        return "series"
    return "novel"


def norm_section(section: str | None) -> str:
    return (section or "").strip().lower()


def norm_action(action: str | None) -> str:
    a = (action or "").strip().lower()
    return a or "generate"


# Actions that produce DIRECT manuscript content (mode-formatted text/edits).
WRITING_ACTIONS = {
    "generate", "write", "continue", "dialogue", "rewrite", "expand", "tension",
}
# Sections whose primary job is writing manuscript content.
_WRITING_SECTIONS = {"manuscript", "scenes"}
_STRUCTURE_SECTIONS = {"outline", "plot", "acts", "beats", "pacing"}


def is_direct_manuscript_writing(section: str | None, action: str | None) -> bool:
    """True when the user is in a writing section doing a direct-writing action
    (so output must be manuscript content, never structure/analysis)."""
    return (norm_section(section) in _WRITING_SECTIONS
            and norm_action(action) in WRITING_ACTIONS)


# ---- output contracts -------------------------------------------------------
_FORBIDDEN_TAIL = (
    "FORBIDDEN — never output any of: markdown headings (#, ##, ###); bullet or "
    "numbered lists; 'Suggested Scene Structure'; 'Production Notes'; 'Your "
    "Scene'; 'Expanded & Refined'; bracketed planning labels such as "
    "[INTRODUCING] / [MAIN ACTION] / [CULMINATING MOMENT]; 'Key Questions'; "
    "scene breakdowns; outlines; analysis; critique; commentary; explanations; "
    "or any meta-description of what you will do. Output the content and "
    "NOTHING else."
)

_SCREENPLAY_WRITE = (
    "ROLE: You are writing the SCREENPLAY MANUSCRIPT directly for the author.\n"
    "OUTPUT: screenplay-formatted text ONLY that continues or edits the current "
    "scene, honoring the user's request and the existing characters.\n"
    "FORMAT:\n"
    "- Scene heading (INT./EXT. LOCATION - TIME) only when a new scene starts.\n"
    "- Action lines in present tense, only when needed.\n"
    "- CHARACTER name in CAPITALS on its own line, with the dialogue beneath it.\n"
    "- Parentheticals used sparingly.\n"
    "Write in the project's writing language and continue naturally.\n"
    + _FORBIDDEN_TAIL
)

_NOVEL_WRITE = (
    "ROLE: You are writing the NOVEL MANUSCRIPT directly.\n"
    "OUTPUT: pure narrative PROSE — action, description, inner thought, and "
    "dialogue woven into paragraphs — that continues or edits the scene per the "
    "user's request, in the story's voice and the project's writing language.\n"
    "Do NOT use screenplay scene headings (INT./EXT.) or CHARACTER cue blocks "
    "unless the user explicitly asks.\n"
    + _FORBIDDEN_TAIL
)

_GRAPHIC_NOVEL_WRITE = (
    "ROLE: You are writing the GRAPHIC NOVEL MANUSCRIPT directly "
    "(Act → Page → Scene → Panel).\n"
    "OUTPUT: panel-level script content for the current scene/page per the "
    "user's request, using the panel fields — number panels where helpful:\n"
    "  Panel N\n  Visual: ...\n  Caption: ...\n  Dialogue: CHARACTER: ...\n"
    "  SFX: ...\n  Notes: ...\n"
    "Write in the project's writing language.\n"
    "Do NOT use old 'Comics Script'/page-manager language and do NOT produce "
    "image-generation / ComfyUI prompts.\n"
    + _FORBIDDEN_TAIL
)

_STAGE_WRITE = (
    "ROLE: You are writing the STAGE SCRIPT MANUSCRIPT directly.\n"
    "OUTPUT: stage-script text ONLY — CHARACTER cues with their dialogue, and "
    "(stage directions) only where needed — continuing or editing the scene per "
    "the user's request, in the project's writing language.\n"
    "Do NOT use screenplay INT./EXT. slugs unless requested, and do NOT write "
    "novel-style narration.\n"
    + _FORBIDDEN_TAIL
)

_SERIES_WRITE = (
    "ROLE: You are writing the SERIES MANUSCRIPT directly for the current "
    "episode/scene (Series → Season → Episode → Act → Chapter → Scene).\n"
    "OUTPUT: manuscript content for the current scene per the user's request, in "
    "the project's established prose/teleplay voice and writing language.\n"
    + _FORBIDDEN_TAIL
)

_WRITE_BY_MODE = {
    "screenplay": _SCREENPLAY_WRITE, "novel": _NOVEL_WRITE,
    "graphic_novel": _GRAPHIC_NOVEL_WRITE, "stage_script": _STAGE_WRITE,
    "series": _SERIES_WRITE,
}

_STRUCTURE_CONTRACT = (
    "ROLE: You are planning the story STRUCTURE. Produce a clear, structured "
    "outline (acts / chapters / scenes / beats as appropriate) per the user's "
    "request — concise descriptions; structure is expected here. Do not write "
    "full manuscript prose unless the user asks."
)
_PSYKE_CONTRACT = (
    "ROLE: You are developing the STORY BIBLE / codex (PSYKE). Produce "
    "structured entity content (character / place / object / lore / theme / "
    "relationship facts) per the user's request. Do not write manuscript scene "
    "prose unless the user asks."
)
_NOTES_CONTRACT = (
    "ROLE: You are working with the user's NOTES. Organize, brainstorm, "
    "summarize, extract tasks, or develop raw ideas per the user's request."
)


def output_contract(*, writing_mode: str | None, section: str | None,
                    action: str | None, user_instruction: str = "") -> str:
    """The strict system/output contract for this (section, mode, action).

    The user's explicit instruction always governs *what* to produce; this
    contract governs the *form* and forbids structure/analysis leakage in
    direct manuscript writing.
    """
    sec = norm_section(section)
    if is_direct_manuscript_writing(section, action):
        return _WRITE_BY_MODE.get(norm_mode(writing_mode), _NOVEL_WRITE)
    if sec in _STRUCTURE_SECTIONS:
        return _STRUCTURE_CONTRACT
    if sec == "psyke":
        return _PSYKE_CONTRACT
    if sec == "notes":
        return _NOTES_CONTRACT
    # Manuscript/Scenes with an ANALYSIS action (suggest/summarize/diagnose…).
    if sec in _WRITING_SECTIONS:
        return (
            f"ROLE: You are assisting the current scene (action: "
            f"{norm_action(action)}). Give concise, directly actionable output "
            f"for the scene per the user's request. Do not rewrite the whole "
            f"manuscript and do not invent unrelated structure.")
    return (
        "ROLE: You are a context-aware writing assistant. Produce output "
        "appropriate to the current section and writing mode per the user's "
        "request. Do not output planning structure unless asked.")


# ---- response validation ----------------------------------------------------
_LEAK_MARKERS = (
    "suggested scene structure", "production notes", "your scene",
    "expanded & refined", "expanded and refined", "[introducing]",
    "[main action]", "[culminating moment]", "key questions to explore",
    "key questions", "prose style & cadence", "the user is writing",
    "suggested structure", "scene breakdown", "as an ai",
    "here's how i will", "here is how i will",
)
_MD_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S")
_LIST_LINE = re.compile(r"(?m)^\s*(?:[-*]|\d+[.)])\s+\S")


def validate_response(text: str, *, writing_mode: str | None,
                      section: str | None, action: str | None) -> list[str]:
    """Detect structure/analysis/template leakage in a DIRECT manuscript-writing
    response. Returns a list of human-readable issues ([] when clean or when the
    action is not direct manuscript writing)."""
    if not is_direct_manuscript_writing(section, action):
        return []
    body = text or ""
    low = body.lower()
    issues: list[str] = []
    for marker in _LEAK_MARKERS:
        if marker in low:
            issues.append(f"contains '{marker}'")
    if _MD_HEADING.search(body):
        issues.append("contains markdown headings")
    if len(_LIST_LINE.findall(body)) >= 3:
        issues.append("contains a bullet/numbered list (planning structure)")
    return issues


# ===========================================================================
# Assistant routing matrix + validation profiles + cache key + strict retry.
# Output is determined by: SECTION × WRITING MODE × ACTION × TARGET × REQUEST.
# Pure functions only — no model/provider/DB/UI calls.
# ===========================================================================

import hashlib  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

OUTPUT_CONTRACT_VERSION = "2"
VALIDATOR_VERSION = "2"

# Output kinds (string constants for simple equality in callers/tests).
DIRECT_CONTENT = "direct_content"
STRUCTURE = "structure"
CODEX = "codex"
NOTES = "notes"
TIMELINE = "timeline"
ANALYSIS = "analysis"
SUGGESTIONS = "suggestions"
ANSWER = "answer"
TRANSCRIPT = "transcript"
CLARIFICATION = "clarification"

_PSYKE_SECTIONS = {"psyke"}
_NOTES_SECTIONS = {"notes"}
_TIMELINE_SECTIONS = {"timeline"}
_ANALYSIS_ACTIONS = {"summarize", "diagnose", "pacing"}
_SUGGEST_ACTIONS = {"suggest", "next beat", "alternatives", "brainstorm"}
_STRUCTURE_ACTIONS = {"structure"}


def infer_intent(action: str | None, user_instruction: str = "") -> str:
    """Infer the user's intent from the action and free-text instruction."""
    a = norm_action(action)
    t = (user_instruction or "").lower()
    if a in WRITING_ACTIONS:
        return "generate_dialogue" if a == "dialogue" else "write_content"
    if a in _SUGGEST_ACTIONS:
        return "give_suggestions"
    if a in _STRUCTURE_ACTIONS:
        return "generate_structure"
    if a in _ANALYSIS_ACTIONS:
        return "analyze"
    # Free-text (e.g. Chat / Ask): classify by keywords.
    if any(k in t for k in ("continue", "rewrite", "expand", "write ",
                            "draft", "dialogue")):
        return "write_content"
    if any(k in t for k in ("analyze", "analyse", "critique", "what's wrong",
                            "feedback", "review")):
        return "analyze"
    if any(k in t for k in ("structure", "outline", "beats", "act ", "chapter")):
        return "generate_structure"
    return "answer_question"


def _output_kind(section: str, action: str, intent: str) -> str:
    sec = norm_section(section)
    if sec in _WRITING_SECTIONS:
        if intent in ("write_content", "edit_content", "continue_content",
                      "generate_dialogue"):
            return DIRECT_CONTENT
        if intent == "give_suggestions":
            return SUGGESTIONS
        if intent == "generate_structure":
            return STRUCTURE
        return ANALYSIS
    if sec in _STRUCTURE_SECTIONS:
        return STRUCTURE
    if sec in _PSYKE_SECTIONS:
        return CODEX
    if sec in _NOTES_SECTIONS:
        return NOTES
    if sec in _TIMELINE_SECTIONS:
        return TIMELINE
    if sec in ("chat", "assistant", "logos"):
        return {"write_content": DIRECT_CONTENT, "generate_dialogue": DIRECT_CONTENT,
                "analyze": ANALYSIS, "generate_structure": STRUCTURE,
                "give_suggestions": SUGGESTIONS}.get(intent, ANSWER)
    if sec == "dexter":
        return TRANSCRIPT
    return ANSWER


_PROFILE_BY_KIND = {
    STRUCTURE: "outline_structure", CODEX: "psyke_entity",
    NOTES: "notes_operation", TIMELINE: "timeline_operation",
    ANALYSIS: "analysis_answer", SUGGESTIONS: "suggestions",
    ANSWER: "chat_answer", TRANSCRIPT: "dexter_transcript_format",
}
_DIRECT_PROFILES = {f"{m}_direct" for m in _MODES}


@dataclass
class AssistantTaskContract:
    entry_point: str
    section: str
    writing_mode: str
    action: str
    target: str
    intent: str
    output_kind: str
    output_format: str
    allowed_content: str
    forbidden_content: str
    apply_allowed: bool
    needs_clarification: bool
    clarification_question: str
    prompt_template_id: str
    output_contract_version: str
    validator_profile: str
    cache_profile: str


def route(*, entry_point: str = "assistant_panel", section: str | None = None,
          writing_mode: str | None = None, action: str | None = None,
          target: str = "", user_instruction: str = "",
          has_target: bool = True) -> AssistantTaskContract:
    """Classify a request into an AssistantTaskContract. No provider request
    should ever be built without one."""
    sec = norm_section(section)
    mode = norm_mode(writing_mode)
    act = norm_action(action)
    intent = infer_intent(action, user_instruction)
    kind = _output_kind(sec, act, intent)

    if kind == DIRECT_CONTENT:
        profile = f"{mode}_direct"
        fmt = mode
    else:
        profile = _PROFILE_BY_KIND.get(kind, "chat_answer")
        fmt = "free"

    needs_clar = (kind == DIRECT_CONTENT and not has_target
                  and sec in _WRITING_SECTIONS)
    apply_allowed = kind == DIRECT_CONTENT and not needs_clar

    return AssistantTaskContract(
        entry_point=entry_point or "assistant_panel", section=sec or "",
        writing_mode=mode, action=act, target=target or "no_target",
        intent=intent, output_kind=CLARIFICATION if needs_clar else kind,
        output_format=fmt,
        allowed_content=_ALLOWED_BY_KIND.get(kind, "appropriate output"),
        forbidden_content="planning/meta/markdown/context-dumps"
        if kind == DIRECT_CONTENT else "secrets, raw audio, hidden-context labels",
        apply_allowed=apply_allowed,
        needs_clarification=needs_clar,
        clarification_question=_clarification_text(mode) if needs_clar else "",
        prompt_template_id=f"{sec or 'generic'}.{mode}.{kind}",
        output_contract_version=OUTPUT_CONTRACT_VERSION,
        validator_profile=profile, cache_profile=f"{profile}.{act}")


_ALLOWED_BY_KIND = {
    DIRECT_CONTENT: "manuscript content in the project's mode format",
    STRUCTURE: "outline / acts / chapters / scenes / beats",
    CODEX: "codex / story-bible entity content",
    NOTES: "note organization / summary / extraction",
    TIMELINE: "timeline events / ordering / continuity",
    ANALYSIS: "concise analysis", SUGGESTIONS: "concise suggestions",
    ANSWER: "a direct answer", TRANSCRIPT: "cleaned/formatted transcript",
}


def _clarification_text(mode: str) -> str:
    if mode == "graphic_novel":
        return "Open a Panel or select text so I can write Graphic Novel content."
    return ("Select a passage or open a scene so I can write/continue it.")


def system_prompt_for(contract: AssistantTaskContract) -> str:
    """The strict system/output contract for a routed task (used as the model's
    system prompt). Reuses the mode output contracts for direct content."""
    if contract.output_kind == DIRECT_CONTENT:
        return output_contract(writing_mode=contract.writing_mode,
                               section=contract.section, action=contract.action)
    if contract.output_kind == CLARIFICATION:
        return ("Ask the user a single short clarifying question; do not produce "
                "content or planning.")
    return output_contract(writing_mode=contract.writing_mode,
                           section=contract.section, action=contract.action)


# ---- validation profiles + result ------------------------------------------
_HIDDEN_CONTEXT_MARKERS = (
    "[ai mode", "ai mode:", "psyke context", "[psyke", "global story memory",
    "[global story", "using the context above", "based on psyke",
    "i see from memory", "retrieval label", "[memory]", "hidden context",
)
_DIRECT_FORBIDDEN = _LEAK_MARKERS + (
    "key improvements", "scene heading options", "character notes",
    "formatting notes", "screenplay format", "dialogue flow",
    "dialogue development", "final thoughts", "i'll", "i will", "here's",
    "this creates", "this structured approach", "six-task line test",
    "stack technique", "review before applying", "suggestions focus",
    "structure growing", "let me",
)
_SECRET_RX = re.compile(r"\bsk-[A-Za-z0-9]{8,}\b|\.(wav|mp3|m4a|flac|ogg)\b"
                        r"|\b(api[_-]?key|password|bearer|token)\b\s*[:=]",
                        re.IGNORECASE)


@dataclass
class AssistantValidationResult:
    status: str                      # valid | invalid | uncertain
    reasons: list[str] = field(default_factory=list)
    apply_allowed: bool = False
    copy_allowed: bool = True
    cache_allowed: bool = True
    diagnostic_only: bool = False
    retry_recommended: bool = False
    retry_profile: str = ""


def validate(text: str, contract: AssistantTaskContract
             ) -> AssistantValidationResult:
    """Validate a response against its task contract's validator profile.
    Invalid direct output is never apply/cache-allowed and may trigger one
    strict retry. Secrets / raw-audio / hidden-context labels are invalid in
    ANY profile and are diagnostic-only (never shown/applied)."""
    body = text or ""
    low = body.lower()
    reasons: list[str] = []

    # Secrets / raw audio — never valid anywhere; never displayed/applied.
    if _SECRET_RX.search(body):
        return AssistantValidationResult(
            status="invalid", reasons=["contains a secret or raw-audio path"],
            apply_allowed=False, copy_allowed=False, cache_allowed=False,
            diagnostic_only=True, retry_recommended=False)
    # Hidden-context labels — must never leak into any user-facing output.
    for m in _HIDDEN_CONTEXT_MARKERS:
        if m in low:
            reasons.append(f"hidden-context label '{m}'")

    profile = contract.validator_profile
    if profile in _DIRECT_PROFILES:
        for m in _DIRECT_FORBIDDEN:
            if m in low:
                reasons.append(f"contains '{m}'")
        if _MD_HEADING.search(body):
            reasons.append("contains markdown headings")
        if len(_LIST_LINE.findall(body)) >= 3:
            reasons.append("contains a planning bullet/numbered list")

    if reasons:
        is_direct = profile in _DIRECT_PROFILES
        return AssistantValidationResult(
            status="invalid", reasons=reasons,
            apply_allowed=False, copy_allowed=False, cache_allowed=False,
            diagnostic_only=False,
            retry_recommended=is_direct,
            retry_profile=profile if is_direct else "")

    return AssistantValidationResult(
        status="valid", reasons=[], apply_allowed=contract.apply_allowed,
        copy_allowed=True, cache_allowed=True)


# ---- cache key + strict retry ----------------------------------------------
def _h(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


def cache_key(contract: AssistantTaskContract, *, project_id="",
              target_id="", user_instruction="", target_text="",
              assistant_mode="", personality="", provider_id="") -> str:
    """A cache key that is unique per action/section/mode/target/text/version —
    so a cached response is never replayed for a different request shape, and
    prompt/validator version bumps invalidate old entries."""
    parts = [
        contract.entry_point, contract.section, contract.writing_mode,
        contract.action, contract.target, contract.intent,
        contract.output_kind, contract.prompt_template_id,
        contract.output_contract_version, contract.validator_profile,
        VALIDATOR_VERSION, str(project_id), str(target_id),
        assistant_mode or "", personality or "", provider_id or "",
        _h(user_instruction), _h(target_text),
    ]
    return _h("|".join(parts))


def strict_retry_instruction(contract: AssistantTaskContract) -> str:
    """A strict retry directive after invalid direct-content output."""
    return (
        "You returned planning / meta commentary / structure / context, which "
        "is INVALID for this action. Return ONLY the final "
        f"{contract.writing_mode.replace('_', ' ')} content requested — no "
        "headings, no notes, no analysis, no bullet lists, no context dumps, no "
        "explanations, and no description of what you are doing. Output the "
        "content and nothing else.")
