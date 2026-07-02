"""Idea di Controllo plugin for Logosforge.

Adds menu actions for showing, checking, and (where supported) creating the
PSYKE theme entry that mirrors the project's Controlling Idea. The Assistant
toggle and ``/idea`` slash command are wired in core code so this plugin only
needs to surface the user-facing actions.
"""

from __future__ import annotations


def register(api) -> None:  # noqa: ANN001 — PluginAPI duck-typed
    api.log("Idea di Controllo plugin loaded.")

    def _show_idea() -> None:
        db, pid = _get_db(api)
        if db is None:
            api.show_message(
                "Idea di Controllo",
                "No project loaded.",
            )
            return
        from logosforge.controlling_idea import (
            gather_controlling_idea_context,
            load,
        )
        idea = load(db, pid)
        if not idea.is_defined():
            api.show_message(
                "Idea di Controllo",
                "No Controlling Idea defined yet.\n\n"
                "Open the PSYKE console and run:\n"
                "  /idea set value=\"justice\" cause=\"when the hero "
                "sacrifices safety for truth\"",
            )
            return
        body = gather_controlling_idea_context(db, pid)
        api.show_message("Idea di Controllo", body or "No detail available.")

    def _check_idea() -> None:
        db, pid = _get_db(api)
        if db is None:
            api.show_message("Idea di Controllo", "No project loaded.")
            return
        from logosforge.controlling_idea import check
        report = check(db, pid)
        api.show_message("Idea di Controllo — Check", report.format())

    def _link_theme() -> None:
        db, pid = _get_db(api)
        if db is None:
            api.show_message("Idea di Controllo", "No project loaded.")
            return
        from logosforge.controlling_idea import ensure_theme_entry, load
        if not load(db, pid).is_defined():
            api.show_message(
                "Idea di Controllo",
                "Define a Controlling Idea first via '/idea set'.",
            )
            return
        entry_id = ensure_theme_entry(db, pid)
        api.show_message(
            "Idea di Controllo",
            f"PSYKE theme entry ready (id={entry_id}).",
        )

    api.register_menu_action(
        "Idea di Controllo: Show", _show_idea,
    )
    api.register_menu_action(
        "Idea di Controllo: Check", _check_idea,
    )
    api.register_menu_action(
        "Idea di Controllo: Create / Update PSYKE Theme", _link_theme,
    )


def _get_db(api):
    """Best-effort access to db + project_id from the read-only PluginAPI.

    We never mutate state directly here. The plugin instead delegates to
    :mod:`logosforge.controlling_idea`, which calls already-public db
    methods (``get_project_settings`` / ``save_project_settings`` /
    ``create_psyke_entry``).
    """
    manager = getattr(api, "_manager", None)
    if manager is None:
        return None, 0
    return getattr(manager, "_db", None), getattr(manager, "_project_id", 0)
