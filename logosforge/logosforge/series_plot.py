"""Plot and Timeline behavior for the Series Engine.

Deterministic, pure helpers that make Plot and Timeline season/episode-
aware: episodes grouped by seasons as plot blocks, an episode-order
timeline with arc evolution and setup/payoff chains, an episode detail
view, and a stable color/label system for A/B/C plots and arc scopes.

No UI / Tauri / filesystem / provider imports — the views consume these.
"""

from __future__ import annotations

from typing import Any


# Stable color/label system (§4). Keys: plotline types + arc scopes.
SERIES_COLORS: dict[str, str] = {
    "A": "#ef4444",          # A plot — red
    "B": "#3b82f6",          # B plot — blue
    "C": "#22c55e",          # C plot — green
    "runner": "#a78bfa",     # runner — violet
    "mystery": "#eab308",    # mystery arc — amber
    "relationship": "#ec4899",  # relationship arc — pink
    "season": "#06b6d4",     # season arc — cyan
    "series": "#f59e0b",     # series arc — orange
    "character": "#8b5cf6",  # character arc — purple
    "episode": "#94a3b8",    # episode arc — slate
}


def series_color_label(kind: str) -> str:
    """Stable hex color for a plotline type or arc scope ("" if unknown)."""
    return SERIES_COLORS.get(kind, "")


# ---------------------------------------------------------------------------
# Arc spanning
# ---------------------------------------------------------------------------

def _ordered_episodes(db: Any, project_id: int) -> list:
    """Episodes in true reading order: by season order, then episode order.

    (get_episodes sorts by a per-season order_index, so flattening the
    season → episode hierarchy gives the correct cross-season order.)
    """
    ordered: list = []
    seen: set[int] = set()
    for season in db.get_seasons(project_id):
        for ep in db.get_episodes_for_season(season.id):
            ordered.append(ep)
            seen.add(ep.id)
    # Episodes whose season is missing/None fall back to project order.
    for ep in db.get_episodes(project_id):
        if ep.id not in seen:
            ordered.append(ep)
    return ordered


def _episode_order(db: Any, project_id: int) -> dict[int, int]:
    return {ep.id: i for i, ep in enumerate(_ordered_episodes(db, project_id))}


def _arc_is_active_at(arc: Any, ep_order: int, order_map: dict[int, int]) -> bool:
    """True if *arc* spans the episode at *ep_order* and is still open."""
    if arc.status not in ("active", "delayed"):
        return False
    start = order_map.get(arc.setup_episode_id, None)
    end = order_map.get(arc.payoff_episode_id, None)
    if start is not None and ep_order < start:
        return False
    if end is not None and ep_order > end:
        return False
    return True


def _active_arcs_for(db, arcs, ep, order_map) -> list[dict]:
    ep_ord = order_map.get(ep.id, 0)
    return [
        {
            "id": a.id,
            "title": a.title,
            "scope": a.scope,
            "status": a.status,
            "color": series_color_label(a.scope),
        }
        for a in arcs if _arc_is_active_at(a, ep_ord, order_map)
    ]


# ---------------------------------------------------------------------------
# Plot grid (§1):  Episodes grouped by Seasons
# ---------------------------------------------------------------------------

def _episode_block(db, ep, arcs, order_map) -> dict:
    plotlines = db.get_episode_plotlines(ep.id)
    return {
        "id": ep.id,
        "season_id": ep.season_id,
        "episode_number": ep.episode_number,
        "title": ep.title or f"Episode {ep.episode_number}",
        "logline": ep.logline or "",
        "plot_indicators": [
            {"type": pl.type, "title": pl.title,
             "color": series_color_label(pl.type)}
            for pl in plotlines
        ],
        "active_arcs": _active_arcs_for(db, arcs, ep, order_map),
        "cliffhanger": (ep.cliffhanger or "").strip(),
        "setup_markers": [a.title for a in arcs if a.setup_episode_id == ep.id],
        "payoff_markers": [a.title for a in arcs if a.payoff_episode_id == ep.id],
        "runtime": ep.estimated_runtime_minutes or 0,
    }


def get_series_plot_blocks(db: Any, project_id: int) -> list[dict]:
    """One block per episode (reading order)."""
    arcs = db.get_series_arcs(project_id)
    order_map = _episode_order(db, project_id)
    return [
        _episode_block(db, ep, arcs, order_map)
        for ep in _ordered_episodes(db, project_id)
    ]


def get_series_plot_seasons(db: Any, project_id: int) -> list[dict]:
    """Episodes grouped by season → [{season, title, episodes:[block,...]}]."""
    arcs = db.get_series_arcs(project_id)
    order_map = _episode_order(db, project_id)
    groups: list[dict] = []
    for season in db.get_seasons(project_id):
        eps = db.get_episodes_for_season(season.id)
        groups.append({
            "season_id": season.id,
            "season_number": season.season_number,
            "title": season.title or f"Season {season.season_number}",
            "episodes": [_episode_block(db, ep, arcs, order_map) for ep in eps],
        })
    return groups


# ---------------------------------------------------------------------------
# Episode detail (§2) — first pass: plotlines + acts + active arcs.
# ---------------------------------------------------------------------------

def get_episode_detail(db: Any, project_id: int, episode_id: int) -> dict:
    ep = db.get_episode_by_id(episode_id)
    if ep is None:
        return {}
    arcs = db.get_series_arcs(project_id)
    order_map = _episode_order(db, project_id)
    return {
        "id": ep.id,
        "title": ep.title or f"Episode {ep.episode_number}",
        "logline": ep.logline or "",
        "acts": [a.strip() for a in (ep.act_breaks or "").split("\n") if a.strip()],
        "plotlines": [
            {"type": pl.type, "title": pl.title,
             "resolution_state": pl.resolution_state,
             "color": series_color_label(pl.type)}
            for pl in db.get_episode_plotlines(ep.id)
        ],
        "active_arcs": _active_arcs_for(db, arcs, ep, order_map),
        # Scenes are not yet linked to episodes in the data model — left
        # empty for this first pass rather than inventing a link.
        "scenes": [],
    }


# ---------------------------------------------------------------------------
# Timeline (§3):  season progression, episode order, arc evolution
# ---------------------------------------------------------------------------

def get_series_timeline(db: Any, project_id: int) -> list[dict]:
    """Ordered episode rows across seasons."""
    arcs = db.get_series_arcs(project_id)
    order_map = _episode_order(db, project_id)
    season_title = {
        s.id: (s.title or f"Season {s.season_number}")
        for s in db.get_seasons(project_id)
    }
    rows: list[dict] = []
    for idx, ep in enumerate(_ordered_episodes(db, project_id), start=1):
        rows.append({
            "episode_id": ep.id,
            "order": idx,
            "season_id": ep.season_id,
            "season": season_title.get(ep.season_id, ""),
            "title": ep.title or f"Episode {ep.episode_number}",
            "active_arcs": _active_arcs_for(db, arcs, ep, order_map),
            "setup": [a.title for a in arcs if a.setup_episode_id == ep.id],
            "payoff": [a.title for a in arcs if a.payoff_episode_id == ep.id],
            "cliffhanger": (ep.cliffhanger or "").strip(),
        })
    return rows


def get_season_progression(db: Any, project_id: int) -> list[str]:
    """Season titles in order."""
    return [
        s.title or f"Season {s.season_number}"
        for s in db.get_seasons(project_id)
    ]


def get_setup_payoff_chains(db: Any, project_id: int) -> list[dict]:
    """Arcs with both a setup and a payoff episode (the chains §3 draws)."""
    order_map = _episode_order(db, project_id)
    chains: list[dict] = []
    for arc in db.get_series_arcs(project_id):
        if arc.setup_episode_id is not None and arc.payoff_episode_id is not None:
            chains.append({
                "arc_id": arc.id,
                "title": arc.title,
                "scope": arc.scope,
                "color": series_color_label(arc.scope),
                "setup_episode_id": arc.setup_episode_id,
                "payoff_episode_id": arc.payoff_episode_id,
                "setup_order": order_map.get(arc.setup_episode_id),
                "payoff_order": order_map.get(arc.payoff_episode_id),
            })
    return chains
