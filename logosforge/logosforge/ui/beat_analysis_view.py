"""Beat Analysis view — summary, phase coverage, and positioning of beats."""

from collections.abc import Callable
from typing import Optional

from PySide6.QtWidgets import (
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.quantum_outliner.scoring import BEAT_PHASE_MAP
from logosforge.ui import theme

# The seven narrative phases in story order (the Save the Cat-style model the
# beat → phase mapping uses). Coverage tells the writer which phases have a beat.
_PHASE_ORDER = ["setup", "catalyst", "development", "midpoint",
                "crisis", "climax", "resolution"]
_PHASE_LABEL = {
    "setup": "Setup", "catalyst": "Catalyst", "development": "Development",
    "midpoint": "Midpoint", "crisis": "Crisis", "climax": "Climax",
    "resolution": "Resolution",
}


class BeatAnalysisView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_open_scene: Optional[Callable[[int], None]] = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_open_scene = on_open_scene

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Beat Analysis"))
        subtitle = QLabel(
            "Story beats — Save the Cat-style moments (Catalyst, Midpoint, "
            "All Is Lost…) grouped into seven narrative phases. Set a scene's "
            "beat from its dropdown in the Scenes editor."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(subtitle)

        self._browser = QTextBrowser()
        self._browser.setOpenLinks(False)
        self._browser.anchorClicked.connect(self._on_anchor)
        layout.addWidget(self._browser)

        self._render()

    def refresh(self) -> None:
        """Re-render from current data so edits appear without a section switch."""
        self._render()

    def _on_anchor(self, url) -> None:
        ref = url.toString()
        if ref.startswith("scene:") and self._on_open_scene is not None:
            try:
                self._on_open_scene(int(ref.split(":", 1)[1]))
            except (ValueError, TypeError):
                pass

    def _render(self) -> None:
        scenes = self._db.get_all_scenes(self._project_id)

        beat_counts: dict[str, int] = {}
        beat_words: dict[str, int] = {}
        # (position, title, beat, scene_id)
        beat_positions: list[tuple[int, str, str, int]] = []
        phases_present: set[str] = set()

        for i, scene in enumerate(scenes):
            if scene.beat:
                beat_counts[scene.beat] = beat_counts.get(scene.beat, 0) + 1
                beat_words[scene.beat] = beat_words.get(scene.beat, 0) + len(
                    (scene.content or "").split())
                beat_positions.append((i + 1, scene.title, scene.beat, scene.id))
                phase = BEAT_PHASE_MAP.get(scene.beat.strip().lower())
                if phase:
                    phases_present.add(phase)

        self._browser.setHtml(self._build_html(
            beat_counts, beat_words, beat_positions, len(scenes), phases_present))

    def _build_html(
        self,
        beat_counts: dict[str, int],
        beat_words: dict[str, int],
        beat_positions: list[tuple[int, str, str, int]],
        total_scenes: int,
        phases_present: set[str],
    ) -> str:
        parts: list[str] = []

        if not beat_positions:
            parts.append("<p>No beats assigned yet.</p>")
            parts.append(
                f"<p style='color: {theme.TEXT_MUTED};'>Open the <b>Scenes</b> "
                "view and pick a beat (e.g. Catalyst, Midpoint) from a scene's "
                "beat dropdown to map your story's structure here.</p>")
            return "".join(parts)

        # -- Phase coverage --
        covered = [p for p in _PHASE_ORDER if p in phases_present]
        missing = [p for p in _PHASE_ORDER if p not in phases_present]
        parts.append("<h2>Phase coverage</h2>")
        parts.append(
            f"<p>{len(covered)} of {len(_PHASE_ORDER)} narrative phases have at "
            f"least one beat.</p>")
        if missing:
            parts.append(
                f"<p style='color: {theme.TEXT_MUTED};'>Phases with no beat yet: "
                + ", ".join(_PHASE_LABEL[p] for p in missing) + ".</p>")

        # -- Summary table (Beat / Scenes / Words) --
        parts.append("<h2>Beat Summary</h2>")
        parts.append(
            "<table cellpadding='4' cellspacing='0'"
            " style='border-collapse: collapse;'>")
        parts.append(
            f"<tr style='border-bottom: 2px solid {theme.BORDER};'>"
            "<th align='left'>Beat</th>"
            "<th align='right'>Scenes</th>"
            "<th align='right'>Words</th>"
            "</tr>")
        for beat, count in sorted(beat_counts.items()):
            parts.append(
                f"<tr style='border-bottom: 1px solid {theme.BORDER};'>"
                f"<td>{_esc(beat)}</td>"
                f"<td align='right'>{count}</td>"
                f"<td align='right'>{beat_words.get(beat, 0):,}</td>"
                f"</tr>")
        assigned = len(beat_positions)
        unassigned = total_scenes - assigned
        parts.append(
            f"<tr style='border-top: 2px solid {theme.BORDER};'>"
            f"<td><b>Total assigned</b></td>"
            f"<td align='right'><b>{assigned} / {total_scenes}</b></td>"
            f"<td></td>"
            f"</tr>")
        parts.append("</table>")

        if unassigned > 0:
            parts.append(
                f"<p style='color: {theme.TEXT_MUTED};'>"
                f"{unassigned} scene(s) without a beat.</p>")

        # -- Positions list (scene titles link to the editor when wired) --
        parts.append("<h2>Beat Positions</h2>")
        parts.append(
            "<table cellpadding='4' cellspacing='0'"
            " style='border-collapse: collapse;'>")
        parts.append(
            f"<tr style='border-bottom: 2px solid {theme.BORDER};'>"
            "<th align='left'>#</th>"
            "<th align='left'>Scene</th>"
            "<th align='left'>Beat</th>"
            "</tr>")
        for index, title, beat, scene_id in beat_positions:
            if self._on_open_scene is not None:
                scene_cell = f"<a href='scene:{scene_id}'>{_esc(title)}</a>"
            else:
                scene_cell = _esc(title)
            parts.append(
                f"<tr style='border-bottom: 1px solid {theme.BORDER};'>"
                f"<td>{index}</td>"
                f"<td>{scene_cell}</td>"
                f"<td>{_esc(beat)}</td>"
                f"</tr>")
        parts.append("</table>")

        return "".join(parts)


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
