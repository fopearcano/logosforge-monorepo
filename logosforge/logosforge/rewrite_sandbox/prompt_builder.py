"""Controlled rewrite prompt builder (Phase 10L).

Builds a capped system/user prompt for a rewrite variant. Uses the project's
writing mode + medium constraints, the chosen strategy, the user instruction,
and (optionally) PSYKE context. No full project dump; no stale leakage; source
language preserved unless the user asks otherwise. No provider/backend logic
here — the engine sends these messages through the shared Assistant backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_PSYKE_CAP = 12
_SRC_CAP = 6000


@dataclass
class RewritePrompt:
    system: str = ""
    user: str = ""
    context_blocks: list[str] = field(default_factory=list)
    constraints: str = ""

    def messages(self) -> list[dict]:
        return [{"role": "system", "content": self.system},
                {"role": "user", "content": self.user}]

    def to_dict(self) -> dict[str, Any]:
        return {"system": self.system, "user": self.user,
                "context_blocks": list(self.context_blocks),
                "constraints": self.constraints}

    def summary(self) -> str:
        return self.constraints[:200]


def _psyke_context(db, project_id: int, source_text: str) -> str:
    """Short list of PSYKE entries actually mentioned in the source (capped)."""
    try:
        entries = db.get_all_psyke_entries(project_id)
    except Exception:
        return ""
    low = (source_text or "").lower()
    names = []
    for e in entries:
        name = (getattr(e, "name", "") or "").strip()
        if name and len(name) >= 2 and name.lower() in low:
            names.append(f"{name} ({getattr(e, 'entry_type', '') or 'entry'})")
        if len(names) >= _PSYKE_CAP:
            break
    return ("Relevant PSYKE entries (preserve these unless instructed): "
            + "; ".join(names)) if names else ""


def build_rewrite_prompt(
    db, project_id: int, *, writing_mode: str, source_type: str,
    source_text: str, user_instruction: str = "", strategy_key: str = "",
    include_psyke: bool = True,
) -> RewritePrompt:
    from logosforge.writing_modes import mode_label, medium_constraints
    from logosforge.rewrite_sandbox.strategies import get_strategy

    src = (source_text or "")[:_SRC_CAP]
    strat = get_strategy(strategy_key)
    mode = (writing_mode or "novel")

    constraints = (
        f"Writing mode: {mode_label(mode)}. Medium priorities: "
        f"{medium_constraints(mode)}. "
        "Rewrite ONLY the provided text; do not invent new plot. Preserve the "
        "source language and proper nouns. Return only the rewritten text — no "
        "preamble, no commentary, no diagnostics."
    )
    system = (
        "You are a careful rewriting assistant inside an isolated sandbox. The "
        "user reviews and decides what becomes canonical — you never finalize a "
        "change. " + constraints
    )

    blocks: list[str] = []
    if strat is not None:
        blocks.append(f"[Strategy] {strat.label}: {strat.directive}")
    if include_psyke:
        pk = _psyke_context(db, project_id, src)
        if pk:
            blocks.append("[PSYKE] " + pk)
    instr = user_instruction.strip() or (
        strat.directive if strat else "Improve this passage.")

    user = "\n".join([
        *blocks,
        f"[Source type] {source_type}",
        f"[Instruction] {instr}",
        "[Source text]",
        src,
        "",
        "Return only the rewritten version of the source text.",
    ])
    return RewritePrompt(system=system, user=user, context_blocks=blocks,
                         constraints=constraints)
