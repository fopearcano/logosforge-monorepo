"""Software UI language — DORMANT translation scaffolding (deferred).

**Alpha UI is English-only. Multilingual interface localization is
deferred.** Project writing language and Dexter transcription language are
already separate from UI language and stay fully multilingual.

This module is the future localization infrastructure, kept intentionally
dormant for Alpha: ``UI_LOCALIZATION_ENABLED`` is ``False``, so
:func:`ui_language` always resolves to English and :func:`tr` is a
pass-through — no partial/mixed-language UI ever ships, and no UI-language
selector is exposed. The Italian catalog below remains as non-user-facing
scaffolding (the ``tr()`` call sites are the extraction points for the
future localization pass); the stored ``ui_language_code`` setting is kept
but ignored while localization is deferred. No machine translation, no Qt
``.qm`` toolchain.
"""

from __future__ import annotations

# Alpha scope decision: UI localization is DEFERRED. Flipping this on is the
# entry point for the future localization phase — nothing else exposes a
# non-English UI while it is False.
UI_LOCALIZATION_ENABLED = False

# Future selectable UI languages: code -> native display label. Only list
# languages that really have a catalog below (English is the reference).
UI_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("en", "English"),
    ("it", "Italiano"),
)

DEFAULT_UI_LANGUAGE = "en"

# Per-locale catalogs: exact English source string -> translation.
# Keep entries in sync with the tr() call sites; missing keys fall back to
# English (partial coverage is expected and documented for Alpha).
_CATALOG: dict[str, dict[str, str]] = {
    "it": {
        "Language": "Lingua",
        "Software UI Language:": "Lingua dell'interfaccia:",
        "Default writing language (new projects):":
            "Lingua di scrittura predefinita (nuovi progetti):",
        "Writing Language:": "Lingua di scrittura:",
        "UI translations are partial in Alpha; untranslated text stays "
        "in English. Applies to newly opened windows and dialogs.":
            "Le traduzioni dell'interfaccia sono parziali nella Alpha; il "
            "testo non tradotto resta in inglese. Si applica alle nuove "
            "finestre e finestre di dialogo.",
        "The writing language guides AI, grammar checking and Dexter's "
        "Room. Changing it never rewrites or translates your text.":
            "La lingua di scrittura guida l'AI, il controllo grammaticale "
            "e la Stanza di Dexter. Cambiarla non riscrive né traduce mai "
            "il tuo testo.",
        "Use project language": "Usa la lingua del progetto",
        "Transcription language:": "Lingua di trascrizione:",
    },
}


def ui_language() -> str:
    """The current UI language code. While localization is deferred this is
    always English — the stored setting is kept but ignored (invalid values
    fall back to English either way)."""
    if not UI_LOCALIZATION_ENABLED:
        return DEFAULT_UI_LANGUAGE
    try:
        from logosforge.settings import get_manager
        code = str(get_manager().get("ui_language_code") or "").strip().lower()
    except Exception:
        code = ""
    return code if code in _CATALOG or code == "en" else DEFAULT_UI_LANGUAGE


def tr(text: str) -> str:
    """Translate a user-facing label for the current UI language.

    English (default) returns *text* unchanged; other locales fall back to
    English for any string not in their catalog (partial coverage)."""
    locale = ui_language()
    if locale == "en":
        return text
    return _CATALOG.get(locale, {}).get(text, text)


def coverage(locale: str) -> int:
    """Number of translated strings for *locale* (0 = unsupported)."""
    return len(_CATALOG.get(locale, {}))
