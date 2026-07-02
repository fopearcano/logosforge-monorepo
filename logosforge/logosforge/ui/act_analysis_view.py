"""Act Distribution view — overview of scene distribution across acts."""

from PySide6.QtWidgets import (
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui import theme

ACT_ORDER = ["Act I", "Act II", "Act III"]
UNASSIGNED = "Unassigned"


class ActAnalysisView(QWidget):
    def __init__(self, db: Database, project_id: int) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Act Distribution"))
        subtitle = QLabel(
            "Scene count per act, with the scene-position range each act "
            "spans (e.g. 3–7 = scenes 3 through 7)."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(subtitle)

        self._browser = QTextBrowser()
        self._browser.setOpenLinks(False)
        layout.addWidget(self._browser)

        self._render()

    def refresh(self) -> None:
        """Re-render from current data so edits appear without a section switch."""
        self._render()

    def _render(self) -> None:
        scenes = self._db.get_all_scenes(self._project_id)

        act_scenes: dict[str, list[tuple[int, str]]] = {}
        for i, scene in enumerate(scenes):
            act = scene.act if scene.act else UNASSIGNED
            act_scenes.setdefault(act, []).append((i + 1, scene.title))

        self._browser.setHtml(self._build_html(act_scenes, len(scenes)))

    def _build_html(
        self,
        act_scenes: dict[str, list[tuple[int, str]]],
        total: int,
    ) -> str:
        parts: list[str] = []

        if not act_scenes or total == 0:
            parts.append("<p>No scenes to display.</p>")
            return "".join(parts)

        # -- Summary table --
        parts.append("<h2>Summary</h2>")
        parts.append(
            "<table cellpadding='4' cellspacing='0'"
            " style='border-collapse: collapse;'>"
        )
        parts.append(
            f"<tr style='border-bottom: 2px solid {theme.BORDER};'>"
            "<th align='left'>Act</th>"
            "<th align='right'>Scenes</th>"
            "<th align='left'>Scene range</th>"
            "</tr>"
        )

        ordered_keys = [a for a in ACT_ORDER if a in act_scenes]
        if UNASSIGNED in act_scenes:
            ordered_keys.append(UNASSIGNED)

        for act in ordered_keys:
            entries = act_scenes[act]
            count = len(entries)
            indices = [idx for idx, _ in entries]
            range_str = f"{min(indices)}\u2013{max(indices)}" if count > 1 else str(indices[0])
            parts.append(
                f"<tr style='border-bottom: 1px solid {theme.BORDER};'>"
                f"<td>{_esc(act)}</td>"
                f"<td align='right'>{count}</td>"
                f"<td>{range_str}</td>"
                f"</tr>"
            )

        parts.append(
            f"<tr style='border-top: 2px solid {theme.BORDER};'>"
            f"<td><b>Total</b></td>"
            f"<td align='right'><b>{total}</b></td>"
            f"<td></td>"
            f"</tr>"
        )
        parts.append("</table>")

        unassigned_count = len(act_scenes.get(UNASSIGNED, []))
        if unassigned_count > 0:
            parts.append(
                f"<p style='color: {theme.TEXT_MUTED};'>"
                f"{unassigned_count} scene(s) without an act.</p>"
            )

        # -- Detailed listing per act --
        parts.append("<h2>Scenes by Act</h2>")
        for act in ordered_keys:
            entries = act_scenes[act]
            parts.append(f"<h3>{_esc(act)}</h3>")
            parts.append("<ul>")
            for idx, title in entries:
                parts.append(f"<li>[{idx}] {_esc(title)}</li>")
            parts.append("</ul>")

        return "".join(parts)


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
