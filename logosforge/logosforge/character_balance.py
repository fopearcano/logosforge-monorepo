"""Character & Arc Balance — distribution analysis.

Computes per-character and per-arc scene presence and flags imbalances.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logosforge.db import Database


@dataclass
class CharacterPresence:
    char_id: int
    name: str
    scene_count: int
    total_scenes: int
    flag: str = ""  # "dominant", "underused", ""

    @property
    def ratio(self) -> float:
        return self.scene_count / self.total_scenes if self.total_scenes > 0 else 0.0


@dataclass
class ArcPresence:
    plotline: str
    scene_count: int
    acts_spanned: int
    flag: str = ""  # "thin", ""

    @property
    def ratio(self) -> float:
        return self.scene_count / max(1, self.scene_count)


@dataclass
class BalanceData:
    characters: list[CharacterPresence] = field(default_factory=list)
    arcs: list[ArcPresence] = field(default_factory=list)
    total_scenes: int = 0


def compute_balance(db: Database, project_id: int) -> BalanceData:
    """Compute character and arc distribution data."""
    scenes = db.get_all_scenes(project_id)
    characters = db.get_all_characters(project_id)
    total = len(scenes)

    char_counts: dict[int, int] = {c.id: 0 for c in characters}
    for scene in scenes:
        char_ids = db.get_scene_character_ids(scene.id)
        for cid in char_ids:
            if cid in char_counts:
                char_counts[cid] += 1

    arc_data: dict[str, dict] = {}
    for scene in scenes:
        pl = scene.plotline or ""
        if not pl:
            continue
        if pl not in arc_data:
            arc_data[pl] = {"count": 0, "acts": set()}
        arc_data[pl]["count"] += 1
        if scene.act:
            arc_data[pl]["acts"].add(scene.act)

    avg_count = sum(char_counts.values()) / len(char_counts) if char_counts else 0
    max_count = max(char_counts.values()) if char_counts else 0

    char_presences: list[CharacterPresence] = []
    for c in characters:
        count = char_counts.get(c.id, 0)
        flag = ""
        if total > 0:
            ratio = count / total
            if ratio > 0.6 and avg_count > 0 and count > avg_count * 2:
                flag = "dominant"
            elif count <= 1 and total >= 3:
                flag = "underused"
            elif max_count > 0 and count < max_count * 0.2 and total >= 4:
                flag = "underused"
        char_presences.append(CharacterPresence(c.id, c.name, count, total, flag))

    char_presences.sort(key=lambda p: p.scene_count, reverse=True)

    arc_presences: list[ArcPresence] = []
    for pl, info in sorted(arc_data.items()):
        flag = ""
        if info["count"] <= 1:
            flag = "thin"
        elif len(info["acts"]) <= 1 and total >= 6:
            flag = "thin"
        arc_presences.append(ArcPresence(pl, info["count"], len(info["acts"]), flag))

    arc_presences.sort(key=lambda a: a.scene_count, reverse=True)

    return BalanceData(
        characters=char_presences,
        arcs=arc_presences,
        total_scenes=total,
    )


def flag_color(flag: str) -> str:
    """Map flag to indicator color."""
    if flag == "dominant":
        return "#f59e0b"
    elif flag == "underused":
        return "#ef4444"
    elif flag == "thin":
        return "#f59e0b"
    return ""


# Plain-language explanation of each imbalance flag (+ what to do about it).
FLAG_HELP: dict[str, str] = {
    "dominant":
        "Appears in over 60% of scenes (and more than twice the average) — "
        "consider giving other characters more presence.",
    "underused":
        "Appears in very few scenes relative to the rest — develop this "
        "character further or fold them into another.",
    "thin":
        "This plotline has only one scene, or stays within a single act — "
        "add scenes or let it span more of the story.",
}


def flag_help(flag: str) -> str:
    """Plain-language explanation for an imbalance flag, or '' if none."""
    return FLAG_HELP.get(flag, "")
