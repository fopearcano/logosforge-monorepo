"""Fullscreen-safe modal dialogs.

On macOS a dialog that is **application-modal** (or parentless) and shown while
the main window is in a fullscreen Space pulls the window *out* of fullscreen /
onto another Space — the user sees the app flicker and "minimize", then has to
click the dock icon to bring it back. It is not a crash; it is a window-management
glitch.

The proven cure (first applied to ``NewProjectDialog``) is a **window-modal**
dialog — a *sheet* attached to the parent window on macOS — parented to the
top-level window. These helpers centralize that pattern so every confirm / prompt
behaves the same way and no section reintroduces the glitch.

Guarantees:

* The dialog is parented to the widget's **top-level window** (never parentless,
  never a bare child widget).
* ``Qt.WindowModality.WindowModal`` (a sheet on macOS; an ordinary modal child
  dialog elsewhere — cross-platform safe).
* **No window-state calls** — these helpers never minimize / hide / show / raise /
  activate the main window and set no fullscreen-hostile window flags.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox, QWidget


def _top_level(widget: QWidget | None) -> QWidget | None:
    """The top-level window for *widget* (so the dialog sheets to the real
    window, not a child widget). Returns *widget* if it is already top-level and
    ``None`` only when *widget* is ``None``."""
    if widget is None:
        return None
    return widget.window() or widget


def question(parent: QWidget | None, title: str, text: str, *,
             default_yes: bool = False) -> bool:
    """Window-modal Yes/No confirmation. Returns ``True`` for Yes.

    Default button is **No** unless ``default_yes`` — safe for destructive
    confirmations (Enter does not delete)."""
    box = QMessageBox(_top_level(parent))
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.Yes if default_yes
                         else QMessageBox.StandardButton.No)
    box.setWindowModality(Qt.WindowModality.WindowModal)
    return box.exec() == QMessageBox.StandardButton.Yes


def information(parent: QWidget | None, title: str, text: str) -> None:
    """Window-modal information box."""
    box = QMessageBox(_top_level(parent))
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.setWindowModality(Qt.WindowModality.WindowModal)
    box.exec()


def warning(parent: QWidget | None, title: str, text: str) -> None:
    """Window-modal warning box."""
    box = QMessageBox(_top_level(parent))
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.setWindowModality(Qt.WindowModality.WindowModal)
    box.exec()


def get_text(parent: QWidget | None, title: str, label: str, *,
             text: str = "") -> tuple[str, bool]:
    """Window-modal single-line text prompt. Returns ``(value, ok)``."""
    dlg = QInputDialog(_top_level(parent))
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    dlg.setTextValue(text)
    dlg.setInputMode(QInputDialog.InputMode.TextInput)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    ok = dlg.exec() == QDialog.DialogCode.Accepted
    return (dlg.textValue(), ok)
