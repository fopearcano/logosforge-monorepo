"""Possibility Generator — produces 3–5 plausible narrative branches.

Calls the LLM with a strict JSON-output prompt, parses, validates,
and returns Branch objects. Falls back to a stub list if the LLM is
unreachable so the UI never shows "blank".
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from logosforge.assistant import chat_completion
from logosforge.providers import ProviderConfig
from logosforge.quantum_outliner.psyke_adapter import gather_psyke_brief
from logosforge.quantum_outliner.state import Branch, StateDelta, Wavefunction
from logosforge.quantum_outliner.writing_methods_rag import (
    MethodResult,
    get_relevant_writing_methods,
)

if TYPE_CHECKING:
    from logosforge.db import Database

logger = logging.getLogger(__name__)

_MIN_BRANCHES = 3
_MAX_BRANCHES = 5
_TIMEOUT = 60

_BRANCH_SCHEMA = (
    "{\n"
    '  "branches": [\n'
    '    {\n'
    '      "title": "short label (3-6 words)",\n'
    '      "description": "what happens (1-3 sentences)",\n'
    '      "stakes": "what is at risk",\n'
    '      "consequence": "what changes if this path is taken",\n'
    '      "structure_method": "method name or null",\n'
    '      "structure_beat": "beat name or null",\n'
    '      "branch_type": "deviation|alternative|intensification|resolution or null",\n'
    '      "state_delta": {\n'
    '        "character_changes": [{"name": "...", "note": "..."}],\n'
    '        "new_relations": [{"from": "...", "to": "..."}],\n'
    '        "arc_updates": [{"name": "...", "note": "..."}]\n'
    "      }\n"
    "    }\n"
    "  ]\n"
    "}"
)

_QUANTUM_SYSTEM = (
    "You are QUANTUM, a story plotting agent. You see story moments as a "
    "superposition of possible directions, each with distinct stakes and "
    "consequences.\n\n"
    "Return ONLY JSON, no markdown, no explanation. Schema:\n"
    f"{_BRANCH_SCHEMA}\n\n"
    "Generate 3-5 branches. Each MUST be distinct in trajectory — not "
    "variations of the same outcome. Cover different emotional registers "
    "(conflict, alliance, deception, retreat, escalation)."
)

_CLASSICAL_SYSTEM = (
    "You are QUANTUM, a story plotting agent grounded in classical writing "
    "structure. You anchor every branch to an established story beat from a "
    "recognised writing method.\n\n"
    "Return ONLY JSON, no markdown, no explanation. Schema:\n"
    f"{_BRANCH_SCHEMA}\n\n"
    "Generate 3-5 branches. Each branch MUST reference the writing method "
    "and beat it fulfills via structure_method and structure_beat. Use "
    "branch_type to classify: deviation (breaks from expected beat), "
    "alternative (different execution of the same beat), intensification "
    "(amplifies the beat), resolution (closes the beat)."
)

_HYBRID_SYSTEM = (
    "You are QUANTUM, a story plotting agent that combines classical "
    "structure with creative possibility. Anchor the first branch to the "
    "expected structural beat, then generate alternatives that deviate, "
    "intensify, or resolve differently.\n\n"
    "Return ONLY JSON, no markdown, no explanation. Schema:\n"
    f"{_BRANCH_SCHEMA}\n\n"
    "Generate 3-5 branches. The first branch should follow the structural "
    "method closely (branch_type: null or 'intensification'). Remaining "
    "branches explore creative departures. Set structure_method, "
    "structure_beat, and branch_type where applicable; null when not."
)

_AUTO_STRUCTURAL_KEYWORDS = frozenset({
    "act", "midpoint", "catalyst", "climax", "inciting", "incident",
    "beat", "setup", "resolution", "turning", "point", "structure",
    "pinch", "ordeal", "threshold", "opening", "finale", "denouement",
    "hook", "twist", "fun", "games", "debate", "sequel",
})


def _build_provider() -> ProviderConfig:
    # Delegates to the single shared provider builder (Phase 8B).
    from logosforge.providers import build_active_provider
    return build_active_provider()


def _resolve_auto_mode(anchor: str) -> str:
    words = set(anchor.lower().split())
    if words & _AUTO_STRUCTURAL_KEYWORDS:
        return "hybrid"
    return "quantum"


def _select_system_prompt(mode: str) -> str:
    if mode == "classical":
        return _CLASSICAL_SYSTEM
    if mode == "hybrid":
        return _HYBRID_SYSTEM
    return _QUANTUM_SYSTEM


def build_rag_context(anchor: str, mode: str) -> tuple[str, list[MethodResult]]:
    """Retrieve writing-method context for classical/hybrid modes.

    Returns (context_block, raw_results) so tests can inspect both.
    """
    if mode == "quantum":
        return "", []

    methods = get_relevant_writing_methods(anchor, max_results=2)
    if not methods:
        return "", []

    lines = ["Relevant writing methods:"]
    for m in methods:
        lines.append(f"- {m.title}: {m.snippet}")
    return "\n".join(lines), methods


def generate_possibilities(
    anchor: str,
    db: "Database | None" = None,
    project_id: int | None = None,
    *,
    extra_context: str = "",
    n: int = 4,
    source_scene_id: int | None = None,
    source_scene_order: int | None = None,
    structure_mode: str = "hybrid",
) -> Wavefunction:
    """Generate a wavefunction of N branches for a narrative anchor.

    `anchor` is the situation prompt: "Hero meets enemy", "Scene 3 ends".
    PSYKE characters are folded in for grounding when db+project_id given.
    `source_scene_id` anchors the wavefunction to a timeline position.
    `structure_mode` controls how classical writing methods are integrated.
    """
    n = max(_MIN_BRANCHES, min(n, _MAX_BRANCHES))

    effective_mode = structure_mode
    if effective_mode == "auto":
        effective_mode = _resolve_auto_mode(anchor)

    psyke_brief = ""
    if db is not None and project_id is not None:
        psyke_brief = gather_psyke_brief(db, project_id)

    rag_context, rag_methods = build_rag_context(anchor, effective_mode)

    user_parts = []
    if psyke_brief:
        user_parts.append("Story bible:\n" + psyke_brief)
    if rag_context:
        user_parts.append(rag_context)
    if extra_context:
        user_parts.append("Context:\n" + extra_context)
    user_parts.append(f"Anchor situation: {anchor}")
    user_parts.append(f"Generate {n} distinct branches.")

    system_prompt = _select_system_prompt(effective_mode)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]

    try:
        response, _cached = chat_completion(
            messages, provider=_build_provider(), timeout=_TIMEOUT, use_cache=True,
        )
        branches = _parse_branches(response)
    except (ConnectionError, RuntimeError, OSError) as exc:
        logger.debug("Possibility LLM unavailable: %s", exc)
        branches = []

    if not branches:
        branches = _stub_branches(anchor, n, effective_mode, rag_methods)

    wf = Wavefunction.new(
        anchor=anchor,
        branches=branches,
        source_scene_id=source_scene_id,
        source_scene_order=source_scene_order,
    )
    wf.effective_mode = effective_mode
    if rag_methods and effective_mode in ("classical", "hybrid"):
        wf.structure_method = rag_methods[0].title
        beat = _infer_beat(rag_methods[0], anchor)
        if beat:
            wf.structure_beat = beat
    return wf


def _infer_beat(method: MethodResult, anchor: str) -> str | None:
    """Extract the most relevant beat name from the method snippet."""
    anchor_lower = anchor.lower()
    if "Beats:" in method.snippet or "Stages:" in method.snippet or "Steps:" in method.snippet or "Points:" in method.snippet:
        for label in ("Beats:", "Stages:", "Steps:", "Points:", "Parts:", "Template:"):
            if label in method.snippet:
                beat_line = method.snippet.split(label, 1)[1].split("\n")[0]
                beats = [b.strip().rstrip(".") for b in beat_line.split(",")]
                for beat in beats:
                    if beat.lower() in anchor_lower or any(
                        w in anchor_lower for w in beat.lower().split() if len(w) > 3
                    ):
                        return beat
                if beats:
                    return beats[0]
    return None


def _parse_branches(response: str) -> list[Branch]:
    """Extract Branch list from LLM JSON. Returns [] on any failure."""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.debug("Possibility LLM returned invalid JSON: %s", text[:200])
        return []

    raw_branches = data.get("branches") if isinstance(data, dict) else data
    if not isinstance(raw_branches, list):
        return []

    out: list[Branch] = []
    for raw in raw_branches:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title", "")).strip()
        description = str(raw.get("description", "")).strip()
        if not title or not description:
            continue
        delta_raw = raw.get("state_delta") or {}
        delta = StateDelta(
            character_changes=_clean_dict_list(delta_raw.get("character_changes")),
            new_relations=_clean_dict_list(delta_raw.get("new_relations")),
            arc_updates=_clean_dict_list(delta_raw.get("arc_updates")),
        )
        raw_type = (raw.get("branch_type") or "")
        if isinstance(raw_type, str):
            raw_type = raw_type.strip() or None
        else:
            raw_type = None
        if raw_type and raw_type not in (
            "deviation", "alternative", "intensification", "resolution",
        ):
            raw_type = None

        out.append(Branch.new(
            title=title,
            description=description,
            stakes=str(raw.get("stakes", "")).strip(),
            consequence=str(raw.get("consequence", "")).strip(),
            state_delta=delta,
            structure_method=(raw.get("structure_method") or None),
            structure_beat=(raw.get("structure_beat") or None),
            branch_type=raw_type,
        ))
    return out


def _clean_dict_list(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


_STUB_TEMPLATES = [
    ("Conflict", "Open hostility breaks out.", "Trust", "A relationship is severed."),
    ("Alliance", "An unexpected agreement forms.", "Independence", "Sides must compromise."),
    ("Deception", "One side conceals their real intent.", "Truth", "A future betrayal seeds itself."),
    ("Retreat", "The confrontation is postponed.", "Momentum", "Pressure builds elsewhere."),
    ("Escalation", "A small spark grows uncontrollably.", "Stability", "The story shifts gears."),
]

_STUB_BRANCH_TYPES = [None, "alternative", "deviation", "intensification", "resolution"]


def _stub_branches(
    anchor: str,
    n: int,
    mode: str = "quantum",
    rag_methods: list[MethodResult] | None = None,
) -> list[Branch]:
    """Offline fallback so the UI is never empty when LLM is down."""
    method_name = rag_methods[0].title if rag_methods else None
    use_structure = mode in ("classical", "hybrid") and method_name is not None

    branches: list[Branch] = []
    for i, (title, desc, stakes, cons) in enumerate(_STUB_TEMPLATES[:n]):
        branches.append(Branch.new(
            title=f"{title} — {anchor[:30]}",
            description=desc,
            stakes=stakes,
            consequence=cons,
            structure_method=method_name if use_structure else None,
            branch_type=_STUB_BRANCH_TYPES[i % len(_STUB_BRANCH_TYPES)] if use_structure else None,
        ))
    return branches
