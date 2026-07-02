"""Entry point for LogosForge."""

import sys

from PySide6.QtCore import QTimer

from logosforge.app import create_app


def main() -> int:
    # Runtime proof: print which source files / widget classes back this launch
    # (commit, package path, Manuscript/Outline/Timeline view modules) to stderr.
    from logosforge.diagnostics import print_runtime_report
    print_runtime_report()

    app, window = create_app()
    window.show()

    # On macOS, Python can spawn a stray blank NSWindow before Qt takes over.
    # Close any top-level widget that isn't the main window.
    if sys.platform == "darwin":
        def _close_stray_windows() -> None:
            for w in app.topLevelWidgets():
                if w is not window and w.isVisible() and not w.windowTitle():
                    w.close()
        QTimer.singleShot(0, _close_stray_windows)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
