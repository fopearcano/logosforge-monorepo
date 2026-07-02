"""Series review checks — data-driven, long-form serialized feedback.

When the SeriesEngine is active, these checks evaluate the actual
Season / Episode / SeriesArc / EpisodePlotline data and surface concrete
showrunner notes — episode function, A/B/C balance, cliffhanger presence,
season-arc movement, setups tracked to payoffs, and continuity. Never
novel/screenplay-style prose advice.

Also provides the formatter behind the optional ``/series …`` Assistant
commands (check / arcs / continuity / cliffhanger / payoff).

Pure core/app logic: no UI / Tauri / filesystem / provider imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from logosforge.series_plot import _ordered_episodes


@dataclass
class SeriesReviewCheck:
    """One review finding. episode_id is None for project-level checks."""

    check_type: str
    message: str
    severity: str = "info"      # "info" | "warning"
    episode_id: int | None = None


_OPEN = ("active", "delayed")


def _ep_title(ep: Any) -> str:
    return ep.title or f"Episode {ep.episode_number}"


def _ep_has_substance(db: Any, ep: Any) -> bool:
    """True if the episode carries enough to be reviewable (not a stub)."""
    if (ep.logline or "").strip() or (ep.summary or "").strip():
        return True
    return bool(db.get_episode_plotlines(ep.id))


# ---------------------------------------------------------------------------
# Review (§4)
# ---------------------------------------------------------------------------

def review_series(
    db: Any, project_id: int, episode_id: int | None = None,
) -> list[SeriesReviewCheck]:
    """Run series review checks (§4).

    With *episode_id*, runs episode-scoped checks only; otherwise runs
    episode checks for every episode plus project-level (arc) checks.
    """
    checks: list[SeriesReviewCheck] = []
    episodes = _ordered_episodes(db, project_id)
    if not episodes:
        return checks

    arcs = db.get_series_arcs(project_id)
    seasons = {s.id: s for s in db.get_seasons(project_id)}
    last_id = episodes[-1].id

    target = (
        [e for e in episodes if e.id == episode_id]
        if episode_id is not None else episodes
    )
    for ep in target:
        checks.extend(_episode_checks(db, ep, arcs, seasons, last_id))

    if episode_id is None:
        checks.extend(_arc_checks(db, project_id, arcs, episodes))
    return checks


def _episode_checks(
    db: Any, ep: Any, arcs: list, seasons: dict, last_id: int,
) -> list[SeriesReviewCheck]:
    out: list[SeriesReviewCheck] = []
    title = _ep_title(ep)
    if not _ep_has_substance(db, ep):
        return out

    # Does the episode have a clear engine?
    if not (ep.episode_engine or "").strip():
        out.append(SeriesReviewCheck(
            "episode_engine",
            f"“{title}” has no engine — its dramatic function is undefined.",
            "warning", ep.id,
        ))

    # Are A/B/C plots balanced? (a spine must exist; one plot mustn't swamp)
    plotlines = db.get_episode_plotlines(ep.id)
    types = [pl.type for pl in plotlines]
    if plotlines and "A" not in types:
        out.append(SeriesReviewCheck(
            "abc_balance",
            f"“{title}”: no A plot — the episode lacks a main spine.",
            "warning", ep.id,
        ))
    elif types.count("A") > 1 and not any(t in ("B", "C") for t in types):
        out.append(SeriesReviewCheck(
            "abc_balance",
            f"“{title}”: multiple A plots and no B/C — the plots don't "
            "balance or contrast.",
            "info", ep.id,
        ))

    # Is there a meaningful cliffhanger or hook? (non-final episodes)
    if ep.id != last_id and not (ep.cliffhanger or "").strip():
        out.append(SeriesReviewCheck(
            "cliffhanger",
            f"“{title}” ends without a cliffhanger or hook into the next "
            "episode.",
            "info", ep.id,
        ))

    # Does the episode advance the season arc? (only when one is defined)
    season = seasons.get(ep.season_id)
    if season is not None and (season.season_arc or "").strip():
        touches_arc = any(
            ep.id in (a.setup_episode_id, a.payoff_episode_id) for a in arcs
        )
        if not plotlines and not touches_arc:
            out.append(SeriesReviewCheck(
                "season_arc_movement",
                f"“{title}” does not visibly advance the season arc — it "
                "treads water.",
                "info", ep.id,
            ))

    return out


def _arc_checks(
    db: Any, project_id: int, arcs: list, episodes: list,
) -> list[SeriesReviewCheck]:
    out: list[SeriesReviewCheck] = []

    # Are setups tracked to payoffs?
    for a in arcs:
        if a.setup_episode_id is not None and a.payoff_episode_id is None \
                and a.status in _OPEN:
            out.append(SeriesReviewCheck(
                "unresolved_payoff",
                f"Setup “{a.title}” [{a.scope}] has no tracked payoff "
                "— a setup planted but never paid off.",
                "warning",
            ))

    # Are continuity states respected? (surface flags to verify)
    for e in db.get_all_psyke_entries(project_id):
        if (e.entry_type or "").lower() != "character":
            continue
        flags = (db.get_psyke_series_memory(e.id) or {}).get("continuity_flags")
        if flags:
            out.append(SeriesReviewCheck(
                "continuity",
                f"Continuity flag on {e.name}: {flags} — verify later "
                "episodes don't contradict it.",
                "info",
            ))

    # Are unresolved threads intentional?
    open_threads = [a for a in arcs if a.status in _OPEN]
    if open_threads:
        out.append(SeriesReviewCheck(
            "unresolved_threads",
            f"{len(open_threads)} unresolved thread(s) still open across the "
            "series — confirm each is intentional, not forgotten.",
            "info",
        ))

    return out


# ---------------------------------------------------------------------------
# Optional /series commands (§5) — pure formatter the chat view delegates to.
# ---------------------------------------------------------------------------

SERIES_COMMANDS = ("check", "arcs", "continuity", "cliffhanger", "payoff")


def format_series_command(db: Any, project_id: int, subcommand: str) -> str:
    """Render a ``/series <subcommand>`` response. Returns guidance text for
    unknown subcommands (the caller has already gated to series projects)."""
    sub = (subcommand or "").strip().lower()
    if sub in ("", "check"):
        return _fmt_check(db, project_id)
    if sub == "arcs":
        return _fmt_arcs(db, project_id)
    if sub == "continuity":
        return _fmt_continuity(db, project_id)
    if sub == "cliffhanger":
        return _fmt_cliffhanger(db, project_id)
    if sub == "payoff":
        return _fmt_payoff(db, project_id)
    return (
        "Unknown /series command. Try: "
        + ", ".join(f"/series {c}" for c in SERIES_COMMANDS)
    )


def _fmt_check(db: Any, project_id: int) -> str:
    checks = review_series(db, project_id)
    if not checks:
        return "Series review: no issues found."
    lines = ["Series review:"]
    for c in checks:
        mark = "⚠" if c.severity == "warning" else "•"
        lines.append(f"{mark} {c.message}")
    return "\n".join(lines)


def _fmt_arcs(db: Any, project_id: int) -> str:
    arcs = db.get_series_arcs(project_id)
    if not arcs:
        return "No series arcs defined."
    lines = ["Series arcs:"]
    for a in arcs:
        lines.append(f"• {a.title} [{a.scope}/{a.status}]")
    return "\n".join(lines)


def _fmt_continuity(db: Any, project_id: int) -> str:
    from logosforge.psyke_series import get_series_memory
    lines: list[str] = []
    for e in db.get_all_psyke_entries(project_id):
        if (e.entry_type or "").lower() != "character":
            continue
        mem = get_series_memory(db, e.id)
        if not mem:
            continue
        if mem.get("episode_state"):
            lines.append(f"• {e.name} — state: {mem['episode_state']}")
        if mem.get("continuity_flags"):
            lines.append(f"  ↳ flag: {mem['continuity_flags']}")
    if not lines:
        return "No continuity ledger recorded yet."
    return "Continuity ledger:\n" + "\n".join(lines)


def _fmt_cliffhanger(db: Any, project_id: int) -> str:
    episodes = _ordered_episodes(db, project_id)
    if not episodes:
        return "No episodes yet."
    lines = ["Cliffhangers:"]
    for ep in episodes:
        ch = (ep.cliffhanger or "").strip()
        lines.append(f"• {_ep_title(ep)}: {ch if ch else '(none)'}")
    return "\n".join(lines)


def _fmt_payoff(db: Any, project_id: int) -> str:
    from logosforge.series_plot import get_setup_payoff_chains
    chains = get_setup_payoff_chains(db, project_id)
    arcs = db.get_series_arcs(project_id)
    open_setups = [
        a for a in arcs
        if a.setup_episode_id is not None and a.payoff_episode_id is None
        and a.status in _OPEN
    ]
    lines: list[str] = []
    if chains:
        lines.append("Setup → payoff chains:")
        for c in chains:
            lines.append(
                f"• {c['title']} [{c['scope']}]: ep#{c['setup_order'] + 1} → "
                f"ep#{c['payoff_order'] + 1}"
            )
    if open_setups:
        lines.append("Setups awaiting payoff:")
        for a in open_setups:
            lines.append(f"⚠ {a.title} [{a.scope}]")
    if not lines:
        return "No setup/payoff chains tracked yet."
    return "\n".join(lines)
