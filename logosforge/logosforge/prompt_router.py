"""Keyword-based prompt routing for the writing assistant."""

from logosforge.assistant import PRESET_ACTIONS

# Ordered by specificity: narrow keywords first, broad ones last.
# First match wins — order matters.
ROUTING_TABLE: list[tuple[str, list[str]]] = [
    ("Dialogue", [
        "dialogue", "dialog", "conversation", "speech", "talking",
    ]),
    ("Tension", [
        "tension", "intense", "intensity", "suspense", "stakes",
        "urgent", "urgency",
    ]),
    ("Pacing", [
        "pacing", "pace", "too slow", "too fast", "rhythm",
    ]),
    ("Summarize", [
        "summarize", "summary", "sum up", "recap",
    ]),
    ("Expand", [
        "expand", "more detail", "flesh out", "elaborate", "longer",
        "add detail",
    ]),
    ("Next Beat", [
        "what happens", "what's next", "next beat", "continue",
        "brainstorm",
    ]),
    ("Rewrite", [
        "rewrite", "rephrase", "polish", "refine", "improve",
    ]),
]

_GENERIC_TEMPLATE = (
    "Assist the author with the following request about this scene."
)


def route_prompt(user_input: str) -> tuple[str, str]:
    """Return (template_name, action_prompt) for the given user input.

    Checks each routing entry in order. First keyword substring match
    wins. Falls back to a generic wrapper if nothing matches.
    """
    lower = user_input.lower()
    for template_key, keywords in ROUTING_TABLE:
        for kw in keywords:
            if kw in lower:
                base = PRESET_ACTIONS[template_key]
                return template_key, f"{base}\n\nUser request: {user_input}"

    return "Generic", f"{_GENERIC_TEMPLATE}\n\nUser request: {user_input}"
