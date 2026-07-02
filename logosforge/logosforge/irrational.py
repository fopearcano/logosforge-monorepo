"""IRRATIONAL — PSYKE rule-disruption engine.

Breaks temporal causality, blends unrelated entities, displaces progressions,
and generates surreal narrative prompts from the story bible.  Activated
explicitly via "Go Irrational" — never runs unless the writer opts in.

All computation is read-only; nothing is written to the database.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any

from logosforge.db import Database
from logosforge.temporal_psyke import TemporalGraph


# -- Data types ---------------------------------------------------------------

@dataclass(frozen=True)
class IrrationalFragment:
    """One surreal narrative fragment produced by the engine."""

    kind: str  # "displacement" | "blend" | "inversion" | "echo" | "rupture"
    text: str
    source_entries: list[int] = field(default_factory=list)


@dataclass
class IrrationalContext:
    """Full irrational output for a scene."""

    fragments: list[IrrationalFragment]
    seed: int
    scene_id: int


# -- Surreal verb/phrase pools ------------------------------------------------

_DISPLACEMENT_VERBS = [
    "remembers what hasn't happened yet",
    "carries the weight of a future they cannot see",
    "speaks in a voice borrowed from tomorrow",
    "moves through a memory that belongs to someone else",
    "exists simultaneously at the beginning and the end",
    "hears an echo of their own last words",
    "is already mourning something that hasn't been lost",
    "feels the gravity of an event still forming",
]

_BLEND_TEMPLATES = [
    "{a} wears the face of {b}",
    "{a} and {b} share one shadow",
    "Where {a} ends, {b} begins — there is no seam",
    "{a} speaks, but {b}'s words come out",
    "The boundary between {a} and {b} dissolves like salt in rain",
    "{a}'s hands move with {b}'s purpose",
    "{a} dreams of being {b}; {b} dreams of forgetting",
    "In the mirror, {a} sees only {b}",
]

_INVERSION_TEMPLATES = [
    "What if {entry} wanted the opposite of everything they've pursued?",
    "{entry} has been lying — not to others, but to the narrative itself",
    "The truth about {entry} is the exact reverse of what's been shown",
    "Remove {entry} from the story. What collapses? What finally makes sense?",
    "{entry}'s arc was never about growth — it was about beautiful unraveling",
    "What if {entry}'s conflict was the only honest thing in the story?",
]

_ECHO_TEMPLATES = [
    "This scene has already happened. The characters just don't know it yet.",
    "The first line of the story is the last thing said here.",
    "Everything in this scene is a distorted reflection of {scene}.",
    "The setting remembers a different version of these events.",
    "Time stutters: a moment from {scene} replays inside this one.",
    "Someone left a message here before the story began.",
]

_RUPTURE_TEMPLATES = [
    "A door appears that wasn't there before. It opens onto {place}.",
    "The rules of {lore} stop working. Just here. Just now.",
    "{theme} stops being metaphorical and becomes literal.",
    "The narrator loses track of who is speaking.",
    "A character who died is standing in the background, unconcerned.",
    "The scene's weather is emotionally wrong — joy under storm, grief in sunshine.",
    "An object from a completely different story appears on the table.",
    "The dialogue continues, but the setting has silently changed to {place}.",
]


# -- Engine -------------------------------------------------------------------

_MAX_FRAGMENTS = 5
_MIN_ENTRIES = 1


def generate_irrational(
    db: Database,
    project_id: int,
    scene_id: int,
    temporal_graph: TemporalGraph | None = None,
    seed: int | None = None,
) -> IrrationalContext:
    """Generate surreal narrative fragments for a scene.

    Uses a deterministic seed derived from scene_id so the same scene
    produces the same irrational output until the writer re-rolls.
    """
    if seed is None:
        seed = _scene_seed(scene_id)

    rng = random.Random(seed)

    entries = db.get_all_psyke_entries(project_id)
    scenes = db.get_all_scenes(project_id)
    scene = db.get_scene_by_id(scene_id)

    if temporal_graph is None and entries:
        temporal_graph = TemporalGraph(db, project_id)

    fragments: list[IrrationalFragment] = []

    if entries and temporal_graph:
        fragments.extend(_temporal_displacement(entries, scenes, scene, temporal_graph, rng))
    if len(entries) >= 2:
        fragments.extend(_entity_blend(entries, rng))
    if entries:
        fragments.extend(_arc_inversion(entries, rng))
    if scenes and scene:
        fragments.extend(_temporal_echo(scenes, scene, rng))
    fragments.extend(_reality_rupture(entries, rng))

    rng.shuffle(fragments)
    fragments = fragments[:_MAX_FRAGMENTS]

    return IrrationalContext(
        fragments=fragments,
        seed=seed,
        scene_id=scene_id,
    )


def _scene_seed(scene_id: int) -> int:
    h = hashlib.md5(f"irrational:{scene_id}".encode()).hexdigest()
    return int(h[:8], 16)


# -- Fragment generators ------------------------------------------------------

def _temporal_displacement(
    entries: list, scenes: list, scene: Any,
    tg: TemporalGraph, rng: random.Random,
) -> list[IrrationalFragment]:
    fragments: list[IrrationalFragment] = []
    if not scene:
        return fragments

    current_order = getattr(scene, "sort_order", 0)
    char_entries = [e for e in entries if e.entry_type == "character" and not e.is_global]
    if not char_entries:
        return fragments

    entry = rng.choice(char_entries)

    all_progs = tg._progressions.get(entry.id, [])
    future_progs = [
        p for p in all_progs
        if p.scene_sort_order is not None and p.scene_sort_order > current_order
    ]
    past_progs = [
        p for p in all_progs
        if p.scene_sort_order is not None and p.scene_sort_order < current_order
    ]

    if future_progs:
        prog = rng.choice(future_progs)
        verb = rng.choice(_DISPLACEMENT_VERBS)
        fragments.append(IrrationalFragment(
            kind="displacement",
            text=f"{entry.name} {verb}: \"{prog.text}\"",
            source_entries=[entry.id],
        ))
    elif past_progs and len(past_progs) >= 2:
        p = rng.choice(past_progs)
        fragments.append(IrrationalFragment(
            kind="displacement",
            text=f"{entry.name} re-lives a discarded state: \"{p.text}\" — but in the wrong body, the wrong room.",
            source_entries=[entry.id],
        ))

    return fragments


def _entity_blend(entries: list, rng: random.Random) -> list[IrrationalFragment]:
    fragments: list[IrrationalFragment] = []
    non_global = [e for e in entries if not e.is_global]
    if len(non_global) < 2:
        return fragments

    pair = rng.sample(non_global, 2)
    template = rng.choice(_BLEND_TEMPLATES)
    text = template.format(a=pair[0].name, b=pair[1].name)
    fragments.append(IrrationalFragment(
        kind="blend",
        text=text,
        source_entries=[pair[0].id, pair[1].id],
    ))

    return fragments


def _arc_inversion(entries: list, rng: random.Random) -> list[IrrationalFragment]:
    fragments: list[IrrationalFragment] = []
    candidates = [e for e in entries if not e.is_global and e.entry_type in ("character", "theme")]
    if not candidates:
        return fragments

    entry = rng.choice(candidates)
    template = rng.choice(_INVERSION_TEMPLATES)
    text = template.format(entry=entry.name)
    fragments.append(IrrationalFragment(
        kind="inversion",
        text=text,
        source_entries=[entry.id],
    ))

    return fragments


def _temporal_echo(
    scenes: list, current_scene: Any, rng: random.Random,
) -> list[IrrationalFragment]:
    fragments: list[IrrationalFragment] = []
    other_scenes = [s for s in scenes if s.id != current_scene.id and (s.content or "").strip()]
    if not other_scenes:
        return fragments

    ref_scene = rng.choice(other_scenes)
    template = rng.choice(_ECHO_TEMPLATES)
    text = template.format(scene=f"\"{ref_scene.title}\"")
    fragments.append(IrrationalFragment(
        kind="echo",
        text=text,
    ))

    return fragments


def _reality_rupture(entries: list, rng: random.Random) -> list[IrrationalFragment]:
    fragments: list[IrrationalFragment] = []
    places = [e for e in entries if e.entry_type == "place"]
    lore = [e for e in entries if e.entry_type == "lore"]
    themes = [e for e in entries if e.entry_type == "theme"]

    template = rng.choice(_RUPTURE_TEMPLATES)
    subs: dict[str, str] = {}
    if "{place}" in template:
        if places:
            subs["place"] = rng.choice(places).name
        else:
            subs["place"] = "somewhere that shouldn't exist"
    if "{lore}" in template:
        if lore:
            subs["lore"] = rng.choice(lore).name
        else:
            subs["lore"] = "the world's rules"
    if "{theme}" in template:
        if themes:
            subs["theme"] = rng.choice(themes).name
        else:
            subs["theme"] = "the story's deepest truth"

    text = template.format(**subs)
    source = []
    for e in (places + lore + themes):
        if e.name in text:
            source.append(e.id)

    fragments.append(IrrationalFragment(
        kind="rupture",
        text=text,
        source_entries=source,
    ))

    return fragments


# -- Context builder for assistant integration --------------------------------

def build_irrational_context(
    db: Database,
    project_id: int,
    scene_id: int,
    temporal_graph: TemporalGraph | None = None,
    seed: int | None = None,
) -> str:
    """Build an [IRRATIONAL] context block for the AI assistant."""
    result = generate_irrational(
        db, project_id, scene_id,
        temporal_graph=temporal_graph,
        seed=seed,
    )
    if not result.fragments:
        return ""

    lines = [
        "[IRRATIONAL MODE]",
        "The writer has activated irrational mode. Break narrative rules.",
        "Use the fragments below as surreal provocations — weave them into",
        "your response. Disrupt causality, blend identities, fracture time.",
        "",
    ]
    for frag in result.fragments:
        lines.append(f"- ({frag.kind}) {frag.text}")

    return "\n".join(lines)


# -- Re-roll support ----------------------------------------------------------

def reroll_seed(scene_id: int, iteration: int) -> int:
    h = hashlib.md5(f"irrational:{scene_id}:v{iteration}".encode()).hexdigest()
    return int(h[:8], 16)
