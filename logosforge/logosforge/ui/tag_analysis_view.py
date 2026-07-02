"""Tag Analysis view — summary and distribution of thematic tags across scenes."""

from collections.abc import Callable

from PySide6.QtWidgets import (
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui import theme


class TagAnalysisView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_open_scene: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        # Click a scene entry to jump to it (None → entries render as plain text).
        self._on_open_scene = on_open_scene

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tag Analysis"))

        self._browser = QTextBrowser()
        self._browser.setOpenLinks(False)          # we handle navigation ourselves
        self._browser.anchorClicked.connect(self._on_anchor)
        layout.addWidget(self._browser)

        self._render()

    def refresh(self) -> None:
        """Re-render from current data so edits appear without a section switch."""
        self._render()

    def _on_anchor(self, url) -> None:
        s = url.toString()
        if s.startswith("scene:") and self._on_open_scene is not None:
            try:
                self._on_open_scene(int(s.split(":", 1)[1]))
            except (ValueError, IndexError):
                pass

    def _render(self) -> None:
        scenes = self._db.get_all_scenes(self._project_id)

        # Group case-insensitively so "Magic"/"magic"/" magic " are one tag — the
        # same way the Scenes tag-filter matches — keeping the first-seen casing
        # as the display label.
        display: dict[str, str] = {}                              # lower -> label
        tag_scenes: dict[str, list[tuple[int, str, int]]] = {}    # lower -> rows
        tagged_count = 0

        for i, scene in enumerate(scenes):
            if not scene.tags:
                continue
            had_tag = False
            for raw_tag in scene.tags.split(","):
                tag = raw_tag.strip()
                if not tag:
                    continue
                had_tag = True
                key = tag.lower()
                display.setdefault(key, tag)
                tag_scenes.setdefault(key, []).append(
                    (i + 1, scene.title, scene.id))
            if had_tag:
                tagged_count += 1

        # Exposed for tests + the data-changed refresh path.
        self._tag_scenes = tag_scenes
        self._display = display
        html = self._build_html(tag_scenes, display, len(scenes), tagged_count)
        self._last_html = html
        self._browser.setHtml(html)

    def _build_html(
        self,
        tag_scenes: dict[str, list[tuple[int, str, int]]],
        display: dict[str, str],
        total_scenes: int,
        tagged_count: int,
    ) -> str:
        parts: list[str] = []

        if not tag_scenes:
            parts.append("<p>No tags assigned to any scenes.</p>")
            return "".join(parts)

        sorted_keys = sorted(tag_scenes.keys(), key=lambda k: display[k].lower())
        navigable = self._on_open_scene is not None

        # -- Summary table --
        parts.append("<h2>Tag Summary</h2>")
        pct = round(100 * tagged_count / total_scenes) if total_scenes else 0
        parts.append(
            f"<p style='color: {theme.TEXT_MUTED};'>"
            f"{tagged_count} of {total_scenes} scenes tagged ({pct}%).</p>"
        )
        parts.append(
            "<table cellpadding='4' cellspacing='0' style='border-collapse: collapse;'>"
        )
        parts.append(
            f"<tr style='border-bottom: 2px solid {theme.BORDER};'>"
            "<th align='left'>Tag</th>"
            "<th align='right'>Scenes</th>"
            "</tr>"
        )
        for key in sorted_keys:
            count = len(tag_scenes[key])
            parts.append(
                f"<tr style='border-bottom: 1px solid {theme.BORDER};'>"
                f"<td>{_esc(display[key])}</td>"
                f"<td align='right'>{count}</td>"
                f"</tr>"
            )
        parts.append(
            f"<tr style='border-top: 2px solid {theme.BORDER};'>"
            f"<td><b>Unique tags</b></td>"
            f"<td align='right'><b>{len(sorted_keys)}</b></td>"
            f"</tr>"
        )
        parts.append("</table>")

        untagged = total_scenes - tagged_count
        if untagged > 0:
            parts.append(
                f"<p style='color: {theme.TEXT_MUTED};'>"
                f"{untagged} scene(s) without tags.</p>"
            )

        # -- Details per tag --
        parts.append("<h2>Tag Details</h2>")
        for key in sorted_keys:
            parts.append(f"<h3>{_esc(display[key])}</h3>")
            parts.append("<ul style='margin-top: 2px;'>")
            for index, title, scene_id in tag_scenes[key]:
                label = f"#{index} — {_esc(title or 'Untitled')}"
                if navigable:
                    parts.append(
                        f"<li><a href='scene:{scene_id}' "
                        f"style='color: {theme.ACCENT}; text-decoration: none;'>"
                        f"{label}</a></li>"
                    )
                else:
                    parts.append(f"<li>{label}</li>")
            parts.append("</ul>")

        return "".join(parts)


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
