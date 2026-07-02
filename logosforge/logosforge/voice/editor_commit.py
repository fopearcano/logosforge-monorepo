"""Safe transcript → editor commit (Alpha MVP: plain text only).

Inserts a transcript as **plain text at the current cursor** of the active text
editor, mode-agnostically: it tracks the last focused editable widget
(``QTextEdit`` / ``QPlainTextEdit`` / ``QLineEdit``) so a click on the voice
panel's *Commit* button still targets the editor the user was writing in. If no
editable widget is available it does nothing (returns ``False``) — it never
auto-creates scenes/pages/panels, never auto-formats, and never auto-commits.

Future, intentionally-unimplemented hooks (classification / mode-aware insertion)
are stubbed so later work has a clear shape; only ``insert_as_plain_text`` is live.
"""

from __future__ import annotations


def _is_editable(widget) -> bool:
    if widget is None:
        return False
    try:
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit
    except Exception:
        return False
    if not isinstance(widget, (QTextEdit, QPlainTextEdit, QLineEdit)):
        return False
    try:
        return not widget.isReadOnly()
    except Exception:
        return False


def _insert(widget, text: str) -> bool:
    try:
        from PySide6.QtWidgets import QLineEdit
        if isinstance(widget, QLineEdit):
            widget.insert(text)
        else:                                   # QTextEdit / QPlainTextEdit
            widget.textCursor().insertText(text)
        return True
    except (RuntimeError, Exception):           # stale/destroyed widget, etc.
        return False


class EditorCommitTarget:
    """Tracks the last focused editor and commits plain text into it."""

    def __init__(self) -> None:
        self._last = None

    def note_focus(self, widget) -> None:
        """Record *widget* if it is an editable text field (call from focusChanged)."""
        if _is_editable(widget):
            self._last = widget

    def clear(self) -> None:
        """Forget the tracked editor (e.g. on project switch / view teardown)."""
        self._last = None

    def active_editor(self):
        """The editor to commit into: the focused editable widget, else the last
        one tracked (if still valid). ``None`` if neither is available."""
        try:
            from PySide6.QtWidgets import QApplication
            focus = QApplication.focusWidget()
        except Exception:
            focus = None
        if _is_editable(focus):
            self._last = focus
            return focus
        if _is_editable(self._last):
            return self._last
        return None

    def has_target(self) -> bool:
        return self.active_editor() is not None

    def insert_as_plain_text(self, transcript: str) -> bool:
        """Commit *transcript* as plain text at the active editor's cursor."""
        text = transcript or ""
        if not text.strip():
            return False
        editor = self.active_editor()
        if editor is None:
            return False
        return _insert(editor, text)

    # Back-compat / convenience alias.
    def commit_plain_text(self, transcript: str) -> bool:
        return self.insert_as_plain_text(transcript)

    # -- Future hooks (NOT implemented for Alpha) ---------------------------
    # These define the intended shape for later classification-aware insertion.
    # They deliberately raise so nothing silently mis-routes a transcript.
    def insert_as_screenplay_dialogue(self, character_name, transcript):
        raise NotImplementedError("voice classification is deferred (Alpha)")

    def insert_as_action(self, transcript):
        raise NotImplementedError("voice classification is deferred (Alpha)")

    def insert_as_note(self, transcript):
        raise NotImplementedError("voice classification is deferred (Alpha)")

    def send_to_outline(self, transcript):
        raise NotImplementedError("voice classification is deferred (Alpha)")

    def send_to_psyke(self, transcript):
        raise NotImplementedError("voice classification is deferred (Alpha)")

    def send_to_graphic_novel_panel(self, panel_id, field, transcript):
        raise NotImplementedError("voice classification is deferred (Alpha)")

    def send_to_stage_direction(self, transcript):
        raise NotImplementedError("voice classification is deferred (Alpha)")

    def send_to_series_outline(self, transcript):
        raise NotImplementedError("voice classification is deferred (Alpha)")
