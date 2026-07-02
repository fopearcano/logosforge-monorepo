"""PSYKE long-form series-memory layer for the Series Engine.

Tracks continuity, arcs and unresolved threads across episodes/seasons.
Per-entry memory lives on PSYKE entries (details_json["series"]); mystery
threads and per-episode memory are derived from the Season/Episode/
SeriesArc/EpisodePlotline tables so PSYKE is reused, not duplicated.

Pure core/app logic: no UI / Tauri / filesystem / provider imports.
"""

from __future__ import annotations

from typing import Any


# Series fields for a character PSYKE entry (entry_type == "character").
CHARACTER_SERIES_FIELDS: tuple[str, ...] = (
    "season_arc",
    "episode_state",
    "long_term_goal",
    "unresolved_conflicts",
    "relationship_history",
    "continuity_flags",
    "current_status_by_episode",   # dict episode_id -> status
)

# Motif / callback fields for theme/object entries (§4).
MOTIF_CALLBACK_FIELDS: tuple[str, ...] = (
    "recurring_lines",
    "recurring_objects",
    "visual_motifs",
    "themes",
    "callbacks",
    "callback_episodes",
)

# A single relationship-evolution beat (§2).
RELATIONSHIP_EVOLUTION_FIELDS: tuple[str, ...] = (
    "episode_id", "state", "change", "cause", "unresolved_tension",
)


def series_fields_for_type(entry_type: str) -> tuple[str, ...]:
    et = (entry_type or "").lower()
    if et == "character":
        return CHARACTER_SERIES_FIELDS
    if et in ("theme", "object", "lore"):
        return MOTIF_CALLBACK_FIELDS
    return ()


def get_series_memory(db: Any, entry_id: int) -> dict:
    return db.get_psyke_series_memory(entry_id)


def set_series_memory(db: Any, entry_id: int, **fields: Any) -> None:
    """Merge series metadata onto a PSYKE entry. Empty values clear a key."""
    db.set_psyke_series_memory(entry_id, dict(fields))


# ---------------------------------------------------------------------------
# Relationship evolution (§2) — a list of beats stored on the entry.
# ---------------------------------------------------------------------------

def add_relationship_evolution(
    db: Any, entry_id: int, *, episode_id: int | None = None, state: str = "",
    change: str = "", cause: str = "", unresolved_tension: str = "",
) -> None:
    mem = db.get_psyke_series_memory(entry_id)
    beats = mem.get("relationship_evolution")
    if not isinstance(beats, list):
        beats = []
    beats.append({
        "episode_id": episode_id, "state": state, "change": change,
        "cause": cause, "unresolved_tension": unresolved_tension,
    })
    db.set_psyke_series_memory(entry_id, {"relationship_evolution": beats})


def get_relationship_evolution(db: Any, entry_id: int) -> list[dict]:
    beats = db.get_psyke_series_memory(entry_id).get("relationship_evolution")
    return beats if isinstance(beats, list) else []


# ---------------------------------------------------------------------------
# Mystery / thread tracking (§3) — derived from SeriesArc.
# ---------------------------------------------------------------------------

def get_mystery_threads(db: Any, project_id: int) -> list[dict]:
    """Mystery / long-thread arcs (setup → payoff, status)."""
    out: list[dict] = []
    for arc in db.get_series_arcs(project_id):
        out.append({
            "id": arc.id,
            "scope": arc.scope,
            "title": arc.title,
            "setup_episode_id": arc.setup_episode_id,
            "payoff_episode_id": arc.payoff_episode_id,
            "status": arc.status,
            "notes": arc.notes,
        })
    return out


def get_unresolved_threads(db: Any, project_id: int) -> list[dict]:
    """Arcs still open (active or delayed)."""
    return [
        t for t in get_mystery_threads(db, project_id)
        if t["status"] in ("active", "delayed")
    ]


# ---------------------------------------------------------------------------
# Episode memory (§5) — derived per episode from arcs + plotlines + PSYKE.
# ---------------------------------------------------------------------------

def get_episode_memory(db: Any, project_id: int, episode_id: int) -> dict:
    """What was set up / paid off / remains unresolved at an episode, plus
    per-character status recorded for it."""
    arcs = db.get_series_arcs(project_id)
    set_up = [a.title for a in arcs if a.setup_episode_id == episode_id]
    paid_off = [a.title for a in arcs if a.payoff_episode_id == episode_id]
    unresolved = [
        a.title for a in arcs if a.status in ("active", "delayed")
    ]

    # Plotlines that are not yet resolved in this episode.
    open_plotlines = [
        f"{pl.type}: {pl.title}"
        for pl in db.get_episode_plotlines(episode_id)
        if (pl.resolution_state or "").lower() not in ("resolved", "closed")
    ]

    # Per-character status recorded for this episode.
    who_changed: list[str] = []
    for e in db.get_all_psyke_entries(project_id):
        if (e.entry_type or "").lower() != "character":
            continue
        mem = db.get_psyke_series_memory(e.id)
        status_map = mem.get("current_status_by_episode")
        if isinstance(status_map, dict):
            val = status_map.get(str(episode_id)) or status_map.get(episode_id)
            if val:
                who_changed.append(f"{e.name}: {val}")

    return {
        "episode_id": episode_id,
        "set_up": set_up,
        "paid_off": paid_off,
        "unresolved": unresolved,
        "open_plotlines": open_plotlines,
        "character_status": who_changed,
    }


# ---------------------------------------------------------------------------
# Assistant context (§6)
# ---------------------------------------------------------------------------

_MAX = 8


def build_series_memory_context(
    db: Any, project_id: int, episode_id: int | None = None,
) -> str:
    """Compact ``[Series Memory]`` block for the Assistant (§6).

    Surfaces current season/episode, active arcs, unresolved threads,
    continuity risks, and character state history. Returns "" when there
    is nothing to report.
    """
    lines: list[str] = []

    # Current season / episode.
    seasons = db.get_seasons(project_id)
    episodes = db.get_episodes(project_id)
    if seasons:
        lines.append("Seasons: " + ", ".join(
            s.title or f"Season {s.season_number}" for s in seasons[:_MAX]
        ))
    cur_ep = db.get_episode_by_id(episode_id) if episode_id is not None else None
    if cur_ep is None and episodes:
        cur_ep = episodes[-1]
    if cur_ep is not None:
        lines.append(
            f"Current episode: {cur_ep.title or ('Episode ' + str(cur_ep.episode_number))}"
        )

    # Active arcs / unresolved threads.
    unresolved = get_unresolved_threads(db, project_id)
    if unresolved:
        bits = [f"{t['title']} [{t['scope']}/{t['status']}]" for t in unresolved]
        lines.append("Unresolved threads: " + "; ".join(bits[:_MAX]))

    # Character state history (continuity).
    states: list[str] = []
    risks: list[str] = []
    for e in db.get_all_psyke_entries(project_id):
        if (e.entry_type or "").lower() != "character":
            continue
        mem = db.get_psyke_series_memory(e.id)
        if not mem:
            continue
        if mem.get("episode_state"):
            states.append(f"{e.name}: {mem['episode_state']}")
        if mem.get("continuity_flags"):
            risks.append(f"{e.name}: {mem['continuity_flags']}")
    if states:
        lines.append("Character state: " + "; ".join(states[:_MAX]))
    if risks:
        lines.append("Continuity risks: " + "; ".join(risks[:_MAX]))

    # Episode memory for the focal episode (what was set up / paid off).
    if cur_ep is not None:
        em = get_episode_memory(db, project_id, cur_ep.id)
        if em["set_up"]:
            lines.append("Set up here: " + ", ".join(em["set_up"][:_MAX]))
        if em["paid_off"]:
            lines.append("Paid off here: " + ", ".join(em["paid_off"][:_MAX]))

    # Setup → payoff chains (which arcs already have both ends tracked).
    try:
        from logosforge.series_plot import get_setup_payoff_chains
        chains = get_setup_payoff_chains(db, project_id)
    except Exception:
        chains = []
    if chains:
        bits = [
            f"{c['title']} (ep#{(c['setup_order'] or 0) + 1}→"
            f"ep#{(c['payoff_order'] or 0) + 1})"
            for c in chains[:_MAX]
        ]
        lines.append("Setup→payoff chains: " + "; ".join(bits))

    if not lines:
        return ""
    return "[Series Memory]\n" + "\n".join(lines)
