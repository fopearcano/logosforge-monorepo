"""Narrative Structure view — the Act -> Chapter -> Scene hierarchy.

This shows the story's *structural* shape (canonical Act/Chapter/Scene tree and
numbering from :mod:`logosforge.story_structure`), distinct from the Beats
section (which groups scenes by Save-the-Cat beat). Each scene is numbered,
annotated with its beat, and clickable to open in the editor.
"""

from collections.abc import Callable
from typing import Optional

from PySide6.QtWidgets import (
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.story_structure import (
    BEAT_ORDER,
    UNASSIGNED_ACT,
    UNASSIGNED_CHAPTER,
    build_structure_tree,
    compute_structural_numbers,
    is_novel_project,
)
from logosforge.ui import theme

# BEAT_ORDER now lives in logosforge.story_structure (non-UI) and is re-exported
# here for back-compatibility — other modules historically imported it from this
# view. New non-UI callers should import it from story_structure directly.
__all__ = ["BEAT_ORDER", "StructureView"]


class StructureView(QWidget):
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
        layout.addWidget(QLabel("Narrative Structure"))
        subtitle = QLabel(
            "Your story's Act → Chapter → Scene hierarchy in canonical order. "
            "Each scene shows its number and beat — click a scene to open it. "
            "(For beat-by-beat analysis, see Beats.)"
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
        self._render()

    def _on_anchor(self, url) -> None:
        ref = url.toString()
        if ref.startswith("scene:") and self._on_open_scene is not None:
            try:
                self._on_open_scene(int(ref.split(":", 1)[1]))
            except (ValueError, TypeError):
                pass

    def _render(self) -> None:
        tree = build_structure_tree(self._db, self._project_id)
        numbers = compute_structural_numbers(
            tree, is_novel_project(self._db, self._project_id))
        self._browser.setHtml(self._build_html(tree, numbers))

    def _build_html(self, tree, numbers) -> str:
        parts: list[str] = []

        total_scenes = sum(len(scs) for _a, chs in tree for _c, scs in chs)
        if total_scenes == 0:
            parts.append("<p>No scenes yet.</p>")
            parts.append(
                f"<p style='color: {theme.TEXT_MUTED};'>Add scenes — and assign "
                "them to Acts and Chapters in the Outline or Scenes view — to "
                "see your story's structure take shape here.</p>")
            return "".join(parts)

        n_acts = sum(1 for a, _ in tree if a != UNASSIGNED_ACT)
        n_chapters = sum(
            1 for a, chs in tree for c, _ in chs
            if a != UNASSIGNED_ACT and c != UNASSIGNED_CHAPTER)
        parts.append(
            f"<p style='color: {theme.TEXT_MUTED};'>{n_acts} act(s), "
            f"{n_chapters} chapter(s), {total_scenes} scene(s).</p>")

        for act_name, ch_list in tree:
            act_no = numbers["acts"].get(act_name, "")
            act_label = "Unassigned" if act_name == UNASSIGNED_ACT else act_name
            prefix = f"Act {act_no} — " if act_no else ""
            parts.append(f"<h2>{prefix}{_esc(act_label)}</h2>")

            for ch_name, scenes in ch_list:
                show_chapter = ch_name != UNASSIGNED_CHAPTER
                if show_chapter:
                    ch_no = numbers["chapters"].get((act_name, ch_name), "")
                    cprefix = f"Chapter {ch_no} — " if ch_no else ""
                    parts.append(
                        f"<h3 style='margin: 6px 0 2px 12px;'>"
                        f"{cprefix}{_esc(ch_name)}</h3>")

                indent = 24 if show_chapter else 12
                for scene in scenes:
                    s_no = numbers["scenes"].get(scene.id, "")
                    label = f"[{s_no}] " if s_no else ""
                    title = _esc(scene.title or "Untitled")
                    if self._on_open_scene is not None:
                        title = f"<a href='scene:{scene.id}'>{title}</a>"
                    beat = ""
                    if scene.beat:
                        beat = (f" <span style='color: {theme.TEXT_MUTED};'>"
                                f"· {_esc(scene.beat)}</span>")
                    parts.append(
                        f"<p style='margin: 2px 0 2px {indent}px;'>"
                        f"<b>{label}</b>{title}{beat}</p>")

        return "".join(parts)


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
