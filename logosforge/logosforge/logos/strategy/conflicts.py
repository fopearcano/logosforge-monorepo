"""Deterministic conflict resolution between strategies.

Precedence (highest first):
    user manual override  >  project mode  >  selected template  >
    active plugin  >  general Assistant behavior

Each resolution emits an explainable note. Nothing here calls an LLM.
"""

from __future__ import annotations

# Whether a template treats dramatic conflict as the central organizing
# principle. Templates that work by contrast/turn (e.g. Story Circle) should NOT
# have McKee-style conflict forced on them. (No Kishotenketsu template ships
# yet; Story Circle is the contrast-leaning built-in — see remaining limits.)
_TEMPLATE_FORCES_CONFLICT = {
    "three_act": True,
    "save_the_cat": True,
    "heros_journey": True,
    "five_act": True,
    "story_circle": False,   # contrast/transformation cycle, not conflict-forced
    "kishotenketsu": False,  # future template — explicitly contrast-based
}


def template_forces_conflict(template_key: str) -> bool:
    """True if the template is conflict-centric. Unknown templates -> True
    (conservative: most Western structures are conflict-driven)."""
    if not template_key:
        return True
    return _TEMPLATE_FORCES_CONFLICT.get(template_key, True)


def resolve_conflict_principle(
    principle: str,
    *,
    project_stance: str,
    template_key: str = "",
    user_override: str = "",
) -> tuple[str, str]:
    """Resolve a single craft principle to a stance + an explanation note.

    *project_stance* is the medium profile's stance ("emphasize"/"allow"/
    "suppress"). Returns (stance, reasoning_note).
    """
    # 1. User manual override always wins.
    if user_override:
        return user_override, (
            f"'{principle}': user override -> {user_override}."
        )

    # 2. Template can veto conflict-forcing for the 'conflict' principle.
    if principle == "conflict" and template_key:
        if not template_forces_conflict(template_key):
            return "allow", (
                f"'conflict': template '{template_key}' is contrast-based, so "
                "conflict is not forced (project mode would emphasize it)."
            )

    # 3. Otherwise the project mode's stance holds.
    return project_stance, (
        f"'{principle}': project mode -> {project_stance}."
    )


def resolve_causality(*, lambda_on: bool, user_override: str = "") -> tuple[str, str]:
    """Lambda toggle decides linear-causality vs superposition."""
    if user_override:
        return user_override, f"causality: user override -> {user_override}."
    if lambda_on:
        return "allow", (
            "causality: Lambda mode is ON -> superposition / alternate "
            "timelines allowed."
        )
    return "emphasize", (
        "causality: Classical mode -> linear causality enforced."
    )
