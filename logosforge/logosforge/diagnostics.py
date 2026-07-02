"""Runtime diagnostics — prove exactly which source files / widget classes the
launched app is using.

Two ways to use it:

* ``python -m logosforge.diagnostics`` — prints the report with NO GUI. This is
  the fastest way to prove which ``logosforge`` package Python actually resolves
  (e.g. local repo vs. an old installed package or an old app bundle).
* On real launch (``python run.py``) the same report is printed to stderr.

Optional visible markers: set ``LOGOSFORGE_DEV_MARKERS=1`` and each of the new
Manuscript / Outline / Timeline views floats a tiny labelled badge so you can
*see* at a glance that the running app mounts the new widgets.
"""

from __future__ import annotations

import os
import sys

_DEV_MARKERS_ENV = "LOGOSFORGE_DEV_MARKERS"


def git_commit() -> str:
    """Best-effort short commit of the *source tree this module loads from*."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        import subprocess
        out = subprocess.check_output(
            ["git", "-C", root, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if out:
            return out
    except Exception:
        pass
    try:
        head = open(os.path.join(root, ".git", "HEAD")).read().strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1].strip()
            return open(os.path.join(root, ".git", ref)).read().strip()[:7]
        return head[:7]
    except Exception:
        return "unknown"


def runtime_report() -> dict:
    """Collect the paths/classes that actually back the running app."""
    import logosforge
    from logosforge.ui import main_window as _mw
    from logosforge.ui.plan_view import PlanView
    from logosforge.ui.plot_timeline_view import PlotTimelineView
    from logosforge.ui.writing_core_view import WritingCoreView

    def _cls(c):
        return f"{c.__module__}.{c.__name__} <- {sys.modules[c.__module__].__file__}"

    return {
        "commit": git_commit(),
        "python": sys.executable,
        "sys_path_head": sys.path[:3],
        "logosforge_pkg": logosforge.__file__,
        "main_window": _mw.__file__,
        "manuscript_view": _cls(WritingCoreView),
        "outline_view": _cls(PlanView),
        "timeline_view": _cls(PlotTimelineView),
    }


def print_runtime_report(file=None) -> None:
    """Print the runtime report (defaults to stderr) as a compact banner."""
    file = file or sys.stderr
    try:
        r = runtime_report()
    except Exception as exc:  # never let diagnostics break a launch
        print(f"[logosforge.diagnostics] report failed: {exc}", file=file)
        return
    lines = [
        "==== logosforge runtime ====",
        f"  commit          : {r['commit']}",
        f"  python          : {r['python']}",
        f"  sys.path[:3]    : {r['sys_path_head']}",
        f"  package         : {r['logosforge_pkg']}",
        f"  main_window     : {r['main_window']}",
        f"  manuscript view : {r['manuscript_view']}",
        f"  outline view    : {r['outline_view']}",
        f"  timeline view   : {r['timeline_view']}",
        "==============================",
    ]
    print("\n".join(lines), file=file, flush=True)


def dev_markers_enabled() -> bool:
    return bool(os.environ.get(_DEV_MARKERS_ENV))


def attach_dev_marker(widget, text: str) -> None:
    """Float a tiny developer-only badge on *widget* when LOGOSFORGE_DEV_MARKERS
    is set. No-op otherwise — it is never part of the normal UX."""
    if not dev_markers_enabled():
        return
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel
        lbl = QLabel(f"{text} — {git_commit()}", widget)
        lbl.setObjectName("devRuntimeMarker")
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lbl.setStyleSheet(
            "QLabel#devRuntimeMarker { background: #b91c1c; color: white;"
            " font-size: 9px; font-weight: bold; padding: 1px 5px;"
            " border-radius: 3px; }"
        )
        lbl.move(6, 6)
        lbl.adjustSize()
        lbl.raise_()
        lbl.show()
    except Exception:
        pass


if __name__ == "__main__":
    print_runtime_report(sys.stdout)
