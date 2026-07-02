"""Outline template presets for story structure planning.

Each template defines a hierarchical beat structure that can be applied
to a project's outline.  Add new templates by appending to OUTLINE_TEMPLATES.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TemplateBeat:
    title: str
    description: str = ""
    children: list[TemplateBeat] = field(default_factory=list)


@dataclass
class OutlineTemplate:
    name: str
    description: str
    beats: list[TemplateBeat] = field(default_factory=list)


OUTLINE_TEMPLATES: dict[str, OutlineTemplate] = {
    "heros_journey": OutlineTemplate(
        name="Hero's Journey",
        description=(
            "Joseph Campbell's monomyth, adapted by Christopher Vogler. "
            "12 stages across three acts."
        ),
        beats=[
            TemplateBeat(
                "Act I: Departure",
                "The setup — introduce the hero and their world before the adventure begins.",
                [
                    TemplateBeat(
                        "The Ordinary World",
                        "Show the hero's normal life, establishing their world, "
                        "relationships, and the status quo they'll eventually leave behind.",
                    ),
                    TemplateBeat(
                        "Call to Adventure",
                        "Something disrupts the hero's ordinary world — a challenge, "
                        "a discovery, a loss, or a message that demands action.",
                    ),
                    TemplateBeat(
                        "Refusal of the Call",
                        "The hero hesitates. Fear, duty, or comfort holds them back. "
                        "This moment reveals their vulnerability and the stakes.",
                    ),
                    TemplateBeat(
                        "Meeting the Mentor",
                        "The hero encounters a guide — someone who provides wisdom, "
                        "training, tools, or confidence to face the journey ahead.",
                    ),
                    TemplateBeat(
                        "Crossing the First Threshold",
                        "The hero commits to the adventure and leaves the ordinary world. "
                        "There is no turning back.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act II: Initiation",
                "The confrontation — the hero faces tests, grows, and confronts "
                "the central ordeal.",
                [
                    TemplateBeat(
                        "Tests, Allies, and Enemies",
                        "The hero navigates the new world, making allies, facing enemies, "
                        "and learning the rules of the unfamiliar terrain.",
                    ),
                    TemplateBeat(
                        "Approach to the Inmost Cave",
                        "The hero prepares for the major challenge. Tension builds as "
                        "they approach the source of greatest danger.",
                    ),
                    TemplateBeat(
                        "The Ordeal",
                        "The hero faces their greatest fear or most dangerous challenge. "
                        "A death-and-rebirth moment — literal or figurative.",
                    ),
                    TemplateBeat(
                        "Reward (Seizing the Sword)",
                        "Having survived the ordeal, the hero claims their reward — "
                        "knowledge, a treasure, reconciliation, or new power.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act III: Return",
                "The resolution — the hero returns transformed, bringing wisdom "
                "or change to their world.",
                [
                    TemplateBeat(
                        "The Road Back",
                        "The hero begins the journey home, but the adventure isn't over. "
                        "New complications or pursuit raise final stakes.",
                    ),
                    TemplateBeat(
                        "Resurrection",
                        "The hero faces a final, climactic test where everything is at "
                        "stake. They must use everything they've learned.",
                    ),
                    TemplateBeat(
                        "Return with the Elixir",
                        "The hero returns to the ordinary world, transformed. They bring "
                        "back something that benefits their community or themselves.",
                    ),
                ],
            ),
        ],
    ),
    "three_act": OutlineTemplate(
        name="Three-Act Structure",
        description="Classic dramatic structure: Setup, Confrontation, Resolution.",
        beats=[
            TemplateBeat(
                "Act I: Setup",
                "Establish the world, characters, and the central conflict.",
                [
                    TemplateBeat(
                        "Opening",
                        "Hook the reader. Establish tone, setting, and the "
                        "protagonist's starting state.",
                    ),
                    TemplateBeat(
                        "Inciting Incident",
                        "The event that disrupts the status quo and sets the main "
                        "conflict in motion.",
                    ),
                    TemplateBeat(
                        "First Act Turn",
                        "The protagonist commits to addressing the conflict. "
                        "The story's central question is established.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act II: Confrontation",
                "The protagonist pursues their goal, faces escalating obstacles, "
                "and undergoes change.",
                [
                    TemplateBeat(
                        "Rising Action",
                        "The protagonist takes action but meets resistance. "
                        "Stakes increase.",
                    ),
                    TemplateBeat(
                        "Midpoint",
                        "A major revelation or reversal that changes the protagonist's "
                        "understanding or approach.",
                    ),
                    TemplateBeat(
                        "Complications",
                        "Things get worse. Subplots converge, allies may fail, "
                        "and the protagonist's flaws are exposed.",
                    ),
                    TemplateBeat(
                        "Crisis",
                        "The darkest moment. The protagonist faces their biggest "
                        "setback and must find new resolve.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act III: Resolution",
                "The climax and aftermath. All threads converge.",
                [
                    TemplateBeat(
                        "Climax",
                        "The final confrontation. The protagonist faces the antagonist "
                        "or central conflict head-on.",
                    ),
                    TemplateBeat(
                        "Falling Action",
                        "The immediate aftermath of the climax. Consequences play out.",
                    ),
                    TemplateBeat(
                        "Denouement",
                        "The new normal. Show how the world and characters have changed.",
                    ),
                ],
            ),
        ],
    ),
    "save_the_cat": OutlineTemplate(
        name="Save the Cat",
        description="Blake Snyder's 15-beat screenplay structure.",
        beats=[
            TemplateBeat(
                "Act I — Thesis",
                "The world as it is.",
                [
                    TemplateBeat(
                        "Opening Image",
                        "A visual or scene that sets the tone and shows the "
                        "protagonist's starting state.",
                    ),
                    TemplateBeat(
                        "Theme Stated",
                        "Someone states the story's theme or lesson — often "
                        "unnoticed by the protagonist at first.",
                    ),
                    TemplateBeat(
                        "Setup",
                        "Introduce the protagonist's world, relationships, flaws, "
                        "and what needs to change.",
                    ),
                    TemplateBeat(
                        "Catalyst",
                        "The inciting incident — the event that disrupts the "
                        "protagonist's status quo.",
                    ),
                    TemplateBeat(
                        "Debate",
                        "The protagonist resists change. Should they act? "
                        "What's at stake? Internal conflict.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act II-A — Antithesis",
                "The upside-down world.",
                [
                    TemplateBeat(
                        "Break into Two",
                        "The protagonist makes a choice and enters a new world "
                        "or situation. Act II begins.",
                    ),
                    TemplateBeat(
                        "B Story",
                        "A secondary storyline begins — often a love interest or "
                        "mentor relationship that carries the theme.",
                    ),
                    TemplateBeat(
                        "Fun and Games",
                        "The promise of the premise. The protagonist explores the "
                        "new world — victories, humor, adventure.",
                    ),
                    TemplateBeat(
                        "Midpoint",
                        "A false victory or false defeat that raises the stakes "
                        "and shifts the story's direction.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act II-B — Synthesis Begins",
                "Combining old and new.",
                [
                    TemplateBeat(
                        "Bad Guys Close In",
                        "External pressures mount and internal flaws intensify. "
                        "The team fractures, plans fail.",
                    ),
                    TemplateBeat(
                        "All Is Lost",
                        "The lowest point. Something or someone is lost. "
                        "A 'whiff of death' — literal or metaphorical.",
                    ),
                    TemplateBeat(
                        "Dark Night of the Soul",
                        "The protagonist processes the loss. Despair before the "
                        "breakthrough.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act III — Synthesis",
                "Combining thesis and antithesis.",
                [
                    TemplateBeat(
                        "Break into Three",
                        "Inspired by the B Story and theme, the protagonist "
                        "finds a solution that combines old and new.",
                    ),
                    TemplateBeat(
                        "Finale",
                        "The protagonist confronts the conflict with a new approach. "
                        "All story threads converge and resolve.",
                    ),
                    TemplateBeat(
                        "Final Image",
                        "A mirror of the Opening Image, showing how much the "
                        "protagonist and world have changed.",
                    ),
                ],
            ),
        ],
    ),
    "story_circle": OutlineTemplate(
        name="Dan Harmon's Story Circle",
        description="An 8-step simplified Hero's Journey.",
        beats=[
            TemplateBeat(
                "1. You (Comfort Zone)",
                "Establish the character in their familiar world. "
                "Who are they? What do they want on the surface?",
            ),
            TemplateBeat(
                "2. Need (Desire)",
                "Something is missing. The character has a conscious or "
                "unconscious need that drives them forward.",
            ),
            TemplateBeat(
                "3. Go (Unfamiliar Situation)",
                "The character enters an unfamiliar situation — crosses a "
                "threshold into the unknown.",
            ),
            TemplateBeat(
                "4. Search (Adaptation)",
                "The character searches for what they need, adapting to "
                "the new world, facing trials along the way.",
            ),
            TemplateBeat(
                "5. Find (Getting What They Wanted)",
                "The character finds what they were looking for — but at "
                "a cost they didn't anticipate.",
            ),
            TemplateBeat(
                "6. Take (Paying the Price)",
                "The character pays a heavy price for what they've found. "
                "There are serious consequences.",
            ),
            TemplateBeat(
                "7. Return (Going Back)",
                "The character returns to their familiar world, but they "
                "are changed. The journey has transformed them.",
            ),
            TemplateBeat(
                "8. Change (Having Changed)",
                "The character has changed. They've grown, and their world "
                "reflects that transformation.",
            ),
        ],
    ),
    "five_act": OutlineTemplate(
        name="Five-Act Structure (Freytag)",
        description="Gustav Freytag's dramatic arc for plays and literary fiction.",
        beats=[
            TemplateBeat(
                "Act I: Exposition",
                "Introduce the setting, characters, and the initial situation.",
                [
                    TemplateBeat(
                        "Setting & Characters",
                        "Establish where and when the story takes place. "
                        "Introduce key characters and their relationships.",
                    ),
                    TemplateBeat(
                        "Status Quo",
                        "Show the normal state of the world that will soon "
                        "be disrupted.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act II: Rising Action",
                "Complications build. Conflicts deepen. Stakes rise.",
                [
                    TemplateBeat(
                        "Inciting Incident",
                        "The event that sets the main conflict in motion.",
                    ),
                    TemplateBeat(
                        "Escalation",
                        "Each new obstacle is greater than the last. "
                        "Alliances form and break.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act III: Climax",
                "The turning point — the moment of greatest tension.",
                [
                    TemplateBeat(
                        "Crisis Point",
                        "The protagonist faces the core conflict directly. "
                        "The outcome hangs in the balance.",
                    ),
                    TemplateBeat(
                        "Turning Point",
                        "A decisive moment that determines the direction "
                        "of the resolution.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act IV: Falling Action",
                "Consequences unfold. Loose ends begin to resolve.",
                [
                    TemplateBeat(
                        "Aftermath",
                        "The immediate consequences of the climax play out.",
                    ),
                    TemplateBeat(
                        "Resolution of Subplots",
                        "Secondary storylines reach their conclusions.",
                    ),
                ],
            ),
            TemplateBeat(
                "Act V: Denouement",
                "The final resolution. The new normal is established.",
                [
                    TemplateBeat(
                        "Final Resolution",
                        "The main conflict reaches its ultimate conclusion.",
                    ),
                    TemplateBeat(
                        "New Equilibrium",
                        "Show the changed world and transformed characters.",
                    ),
                ],
            ),
        ],
    ),
}


# Runtime-registered templates (e.g. contributed by a PSYKE Outline Templates
# plugin). Kept separate from the built-ins so plugins can extend the catalog
# without editing this module — the UI lists whatever is registered, never a
# hardcoded subset.
_PLUGIN_TEMPLATES: dict[str, OutlineTemplate] = {}


def register_outline_template(key: str, template: OutlineTemplate) -> None:
    """Register (or replace) a runtime outline template under *key*.

    Used by plugins to contribute templates. Built-ins are never overwritten:
    a key that collides with a built-in is ignored.
    """
    if not key or key in OUTLINE_TEMPLATES:
        return
    _PLUGIN_TEMPLATES[key] = template


def unregister_outline_template(key: str) -> None:
    _PLUGIN_TEMPLATES.pop(key, None)


def all_templates() -> dict[str, OutlineTemplate]:
    """Built-in templates plus any registered at runtime."""
    merged = dict(OUTLINE_TEMPLATES)
    merged.update(_PLUGIN_TEMPLATES)
    return merged


def get_template(key: str) -> OutlineTemplate | None:
    return all_templates().get(key)


def list_templates() -> list[tuple[str, str, str]]:
    """Return (key, display_name, description) for all templates.

    Includes built-ins and any plugin-registered templates — never a
    hardcoded subset, so unavailable templates are simply not listed.
    """
    return [(k, t.name, t.description) for k, t in all_templates().items()]
