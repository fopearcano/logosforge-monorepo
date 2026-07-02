"""Manuscript formatting highlighter — Markdown-like visual styling for the editor.

Extends PsykeHighlighter so PSYKE entity highlighting coexists with
bold, italic, heading, blockquote, list, and separator rendering.
"""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextDocument

from logosforge.ui import theme
from logosforge.ui.psyke_highlighter import PsykeHighlighter


class ManuscriptHighlighter(PsykeHighlighter):
    """Highlights Markdown-like formatting on top of PSYKE entity terms."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._build_manuscript_formats()

    def _build_manuscript_formats(self) -> None:
        muted = QColor(theme.get("TEXT_MUTED"))
        primary = QColor(theme.get("TEXT_PRIMARY"))
        secondary = QColor(theme.get("TEXT_SECONDARY"))
        accent = QColor(theme.get("ACCENT"))

        self._mk_fmt = QTextCharFormat()
        self._mk_fmt.setForeground(muted)

        self._b_fmt = QTextCharFormat()
        self._b_fmt.setFontWeight(QFont.Weight.Bold)

        self._i_fmt = QTextCharFormat()
        self._i_fmt.setFontItalic(True)

        self._bi_fmt = QTextCharFormat()
        self._bi_fmt.setFontWeight(QFont.Weight.Bold)
        self._bi_fmt.setFontItalic(True)

        self._h1_fmt = QTextCharFormat()
        self._h1_fmt.setFontWeight(QFont.Weight.Bold)
        self._h1_fmt.setForeground(primary)

        self._h2_fmt = QTextCharFormat()
        self._h2_fmt.setFontWeight(QFont.Weight.Bold)
        self._h2_fmt.setForeground(primary)

        self._h3_fmt = QTextCharFormat()
        self._h3_fmt.setFontWeight(QFont.Weight.DemiBold)
        self._h3_fmt.setForeground(secondary)

        self._q_fmt = QTextCharFormat()
        self._q_fmt.setFontItalic(True)
        self._q_fmt.setForeground(secondary)

        self._li_fmt = QTextCharFormat()
        self._li_fmt.setForeground(accent)

        self._sep_fmt = QTextCharFormat()
        self._sep_fmt.setForeground(muted)

    def refresh_theme(self) -> None:
        self._build_manuscript_formats()
        self.rehighlight()

    def refresh_patterns(self, terms: list[str], **kwargs) -> None:
        self._build_manuscript_formats()
        super().refresh_patterns(terms, **kwargs)

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        if not text:
            super().highlightBlock(text)
            return

        # Separator lines (---, ___, ***)
        if re.match(r"^(---+|___+|\*\*\*+)\s*$", text):
            self.setFormat(0, len(text), self._sep_fmt)
            super().highlightBlock(text)
            return

        # Headings — format entire line, then return
        for pat, fmt, prefix_len in (
            (r"^### .+", self._h3_fmt, 4),
            (r"^## .+", self._h2_fmt, 3),
            (r"^# .+", self._h1_fmt, 2),
        ):
            if re.match(pat, text):
                self.setFormat(0, prefix_len, self._mk_fmt)
                self.setFormat(prefix_len, len(text) - prefix_len, fmt)
                super().highlightBlock(text)
                return

        # Blockquote — format but continue for inline markup
        if text.startswith("> "):
            self.setFormat(0, 2, self._mk_fmt)
            self.setFormat(2, len(text) - 2, self._q_fmt)

        # List marker
        m = re.match(r"^(\s*[-*+]) ", text)
        if m:
            self.setFormat(m.start(1), m.end(1) - m.start(1), self._li_fmt)

        # Inline emphasis — track occupied positions to avoid overlaps
        occupied: set[int] = set()

        for m in re.finditer(r"\*\*\*(.+?)\*\*\*", text):
            if any(i in occupied for i in range(m.start(), m.end())):
                continue
            occupied.update(range(m.start(), m.end()))
            self.setFormat(m.start(), 3, self._mk_fmt)
            self.setFormat(m.start() + 3, len(m.group(1)), self._bi_fmt)
            self.setFormat(m.end() - 3, 3, self._mk_fmt)

        for m in re.finditer(r"\*\*(.+?)\*\*", text):
            if any(i in occupied for i in range(m.start(), m.end())):
                continue
            occupied.update(range(m.start(), m.end()))
            self.setFormat(m.start(), 2, self._mk_fmt)
            self.setFormat(m.start() + 2, len(m.group(1)), self._b_fmt)
            self.setFormat(m.end() - 2, 2, self._mk_fmt)

        for m in re.finditer(r"\*([^*]+?)\*", text):
            if any(i in occupied for i in range(m.start(), m.end())):
                continue
            self.setFormat(m.start(), 1, self._mk_fmt)
            self.setFormat(m.start() + 1, len(m.group(1)), self._i_fmt)
            self.setFormat(m.end() - 1, 1, self._mk_fmt)

        # PSYKE entity highlighting on top
        super().highlightBlock(text)
