"""Central language registry — writing, Dexter, grammar and UI languages.

One stable taxonomy for every language-aware surface of LogosForge:

* **Project Writing Language** — the language of the book/script/comic/play/
  series. Stored per project (``settings_json``: ``writing_language_code`` +
  ``writing_language_source``), full OpenAI Whisper list + ``auto``.
* **Dexter Language** — transcription language for Dexter's Room. Defaults to
  the project writing language ("Use project language"), can be Auto detect
  or an explicit per-setup override (see :mod:`logosforge.voice.types`).
* **Grammar Language** — what the local rule-based checker runs as. Defaults
  to the project writing language **where supported**; unsupported languages
  degrade gracefully (no silent English-only checking on non-English text).
* **Software UI Language** — the application interface language
  (:mod:`logosforge.i18n`); global, separate from any project.

Languages are stored **by code** (Whisper codes as the base). The registry
adds script/direction metadata (RTL, CJK/no-word-space), grammar support
levels and UI-translation availability. Aliases are internal only.

Changing a project's writing language never reinterprets or rewrites text —
it only guides AI context, the grammar checker, Dexter defaults and future
glossary behavior. No network, no Qt, no provider access here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Base list — the full OpenAI Whisper language set ("auto" first, stored by
# code). This is the single source of truth; logosforge.voice.types
# re-exports it for the existing voice imports.
# ---------------------------------------------------------------------------

WHISPER_LANGUAGES: dict[str, str] = {
    "auto": "Auto detect",
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "as": "Assamese",
    "az": "Azerbaijani", "ba": "Bashkir", "be": "Belarusian",
    "bg": "Bulgarian", "bn": "Bengali", "bo": "Tibetan", "br": "Breton",
    "bs": "Bosnian", "ca": "Catalan", "cs": "Czech", "cy": "Welsh",
    "da": "Danish", "de": "German", "el": "Greek", "en": "English",
    "es": "Spanish", "et": "Estonian", "eu": "Basque", "fa": "Persian",
    "fi": "Finnish", "fo": "Faroese", "fr": "French", "gl": "Galician",
    "gu": "Gujarati", "ha": "Hausa", "haw": "Hawaiian", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "ht": "Haitian Creole",
    "hu": "Hungarian", "hy": "Armenian", "id": "Indonesian",
    "is": "Icelandic", "it": "Italian", "ja": "Japanese", "jw": "Javanese",
    "ka": "Georgian", "kk": "Kazakh", "km": "Khmer", "kn": "Kannada",
    "ko": "Korean", "la": "Latin", "lb": "Luxembourgish", "ln": "Lingala",
    "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian", "mg": "Malagasy",
    "mi": "Maori", "mk": "Macedonian", "ml": "Malayalam",
    "mn": "Mongolian", "mr": "Marathi", "ms": "Malay", "mt": "Maltese",
    "my": "Myanmar", "ne": "Nepali", "nl": "Dutch", "nn": "Nynorsk",
    "no": "Norwegian", "oc": "Occitan", "pa": "Punjabi", "pl": "Polish",
    "ps": "Pashto", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "sa": "Sanskrit", "sd": "Sindhi", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "sn": "Shona", "so": "Somali", "sq": "Albanian",
    "sr": "Serbian", "su": "Sundanese", "sv": "Swedish", "sw": "Swahili",
    "ta": "Tamil", "te": "Telugu", "tg": "Tajik", "th": "Thai",
    "tk": "Turkmen", "tl": "Tagalog", "tr": "Turkish", "tt": "Tatar",
    "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese",
    "yi": "Yiddish", "yo": "Yoruba", "yue": "Cantonese", "zh": "Chinese",
}

# Internal-only aliases (never shown in the UI): common alternate names map
# to their canonical Whisper code.
LANGUAGE_ALIASES: dict[str, str] = {
    "mandarin": "zh", "chinese mandarin": "zh", "cantonese": "yue",
    "castilian": "es", "valencian": "ca", "flemish": "nl",
    "haitian": "ht", "burmese": "my", "moldovan": "ro",
    "moldavian": "ro", "panjabi": "pa", "pushto": "ps",
    "sinhalese": "si", "letzeburgesch": "lb",
    "bahasa indonesia": "id", "bahasa melayu": "ms",
}


def normalize_language(value) -> str:
    """A valid language CODE for any stored value: codes pass through, known
    aliases and English names resolve, anything else falls back to auto."""
    raw = str(value or "").strip().lower()
    if not raw:
        return "auto"
    if raw in WHISPER_LANGUAGES:
        return raw
    if raw in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[raw]
    by_name = {name.lower(): code
               for code, name in WHISPER_LANGUAGES.items()}
    return by_name.get(raw, "auto")


# ---------------------------------------------------------------------------
# Script / direction metadata
# ---------------------------------------------------------------------------

# Right-to-left writing systems (Arabic and Hebrew scripts).
RTL_CODES: frozenset[str] = frozenset(
    {"ar", "he", "fa", "ur", "ps", "sd", "yi"})

# Scripts that do not separate words with spaces — word counts are
# approximate (characters) and space-based grammar rules do not apply.
NO_WORDSPACE_CODES: frozenset[str] = frozenset(
    {"zh", "yue", "ja", "th", "km", "lo", "my", "bo"})

# Script names for non-Latin writing systems ("latin" is the default).
_SCRIPTS: dict[str, str] = {
    "zh": "han", "yue": "han", "ja": "japanese", "ko": "hangul",
    "ar": "arabic", "fa": "arabic", "ur": "arabic", "ps": "arabic",
    "sd": "arabic", "he": "hebrew", "yi": "hebrew",
    "hi": "devanagari", "mr": "devanagari", "ne": "devanagari",
    "sa": "devanagari", "bn": "bengali", "as": "bengali",
    "pa": "gurmukhi", "gu": "gujarati", "ta": "tamil", "te": "telugu",
    "kn": "kannada", "ml": "malayalam", "si": "sinhala",
    "bo": "tibetan", "th": "thai", "km": "khmer", "lo": "lao",
    "my": "myanmar", "el": "greek", "hy": "armenian", "ka": "georgian",
    "am": "ethiopic",
    "ru": "cyrillic", "uk": "cyrillic", "be": "cyrillic", "bg": "cyrillic",
    "mk": "cyrillic", "sr": "cyrillic", "kk": "cyrillic", "mn": "cyrillic",
    "tg": "cyrillic", "tt": "cyrillic", "ba": "cyrillic",
    "auto": "",
}


def script_for(code: str) -> str:
    return _SCRIPTS.get(code, "latin")


def direction_for(code: str) -> str:
    return "rtl" if code in RTL_CODES else "ltr"


def uses_word_spaces(code: str) -> bool:
    return code not in NO_WORDSPACE_CODES


# ---------------------------------------------------------------------------
# Grammar support levels (the built-in checker is local + rule-based)
# ---------------------------------------------------------------------------

GRAMMAR_FULL = "full"        # English: spelling + grammar + style rules
GRAMMAR_BASIC = "basic"      # word-spaced scripts: generic rules only
GRAMMAR_NONE = "none"        # no-word-space or RTL: checks disabled


def grammar_support(code: str) -> str:
    """Honest support level of the built-in rule checker for *code*.
    Never pretends full support: only English has spelling rules; languages
    whose script breaks the rule assumptions (no word spaces, RTL) are
    excluded entirely instead of being silently checked as English."""
    code = normalize_language(code)
    if code in ("auto", ""):
        return GRAMMAR_BASIC          # per-paragraph detection (legacy path)
    if code == "en":
        return GRAMMAR_FULL
    if code in NO_WORDSPACE_CODES or code in RTL_CODES:
        return GRAMMAR_NONE
    return GRAMMAR_BASIC


def grammar_code_for(code: str) -> str:
    """Checker-side language code (the built-in backend uses the same codes;
    empty when grammar checking is unavailable for the language)."""
    code = normalize_language(code)
    return "" if grammar_support(code) == GRAMMAR_NONE else code


def grammar_status_message(code: str) -> str:
    code = normalize_language(code)
    name = language_name(code)
    level = grammar_support(code)
    if level == GRAMMAR_FULL:
        return f"Grammar and spelling checks run in {name}."
    if level == GRAMMAR_BASIC:
        return (f"Basic grammar checks run for {name} "
                f"(spelling rules are English-only in Alpha).")
    return (f"Grammar checking is not available for {name}. "
            f"You can still write and use AI review.")


# ---------------------------------------------------------------------------
# UI translation availability (see logosforge.i18n)
# ---------------------------------------------------------------------------

UI_LANGUAGE_CODES: tuple[str, ...] = ("en", "it")


# ---------------------------------------------------------------------------
# Registry records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LanguageDefinition:
    code: str
    name_en: str
    native_name: str = ""
    whisper_code: str = ""        # == code for every Whisper language
    grammar_code: str = ""        # "" when grammar checking is unavailable
    ui_locale: str = ""           # "" when no UI translation exists
    script: str = "latin"
    direction: str = "ltr"
    supports_whisper: bool = True
    supports_grammar: bool = False
    supports_ui: bool = False
    aliases: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


_REGISTRY: dict[str, LanguageDefinition] = {}


def get_language(code: str) -> LanguageDefinition:
    """The registry record for *code* (normalized; unknown values → auto)."""
    code = normalize_language(code)
    if code not in _REGISTRY:
        aliases = tuple(sorted(a for a, c in LANGUAGE_ALIASES.items()
                               if c == code))
        level = grammar_support(code)
        _REGISTRY[code] = LanguageDefinition(
            code=code,
            name_en=WHISPER_LANGUAGES.get(code, code),
            whisper_code=code,
            grammar_code=grammar_code_for(code),
            ui_locale=code if code in UI_LANGUAGE_CODES else "",
            script=script_for(code),
            direction=direction_for(code),
            supports_whisper=True,
            supports_grammar=level != GRAMMAR_NONE and code != "auto",
            supports_ui=code in UI_LANGUAGE_CODES,
            aliases=aliases,
            notes=("word counts are approximate (no word spaces)"
                   if code in NO_WORDSPACE_CODES else ""),
        )
    return _REGISTRY[code]


def all_languages() -> list[LanguageDefinition]:
    return [get_language(code) for code in WHISPER_LANGUAGES]


def language_name(code: str) -> str:
    return WHISPER_LANGUAGES.get(normalize_language(code), code)


def display_name(code: str) -> str:
    """Friendly selector label: ``Italian (it)`` / ``Auto detect``."""
    code = normalize_language(code)
    if code == "auto":
        return "Auto detect"
    return f"{language_name(code)} ({code})"


def selector_choices(*, include_auto: bool = True) -> list[tuple[str, str]]:
    """(code, label) pairs for language combos: Auto first (optional), then
    every language sorted by display name. No alias duplicates."""
    items = [(code, display_name(code)) for code in WHISPER_LANGUAGES
             if code != "auto"]
    items.sort(key=lambda pair: pair[1])
    return ([("auto", "Auto detect")] if include_auto else []) + items


# ---------------------------------------------------------------------------
# Project writing language (stored in the project's settings_json)
# ---------------------------------------------------------------------------

KEY_WRITING_LANGUAGE = "writing_language_code"
KEY_WRITING_SOURCE = "writing_language_source"
KEY_GRAMMAR_OVERRIDE = "grammar_language_override"
KEY_DEXTER_OVERRIDE = "dexter_language_override"

FALLBACK_WRITING_LANGUAGE = "en"


def default_writing_language() -> str:
    """The global default for NEW projects (Preferences → Language)."""
    try:
        from logosforge.settings import get_manager
        return normalize_language(get_manager().get("default_writing_language")
                                  or FALLBACK_WRITING_LANGUAGE)
    except Exception:
        return FALLBACK_WRITING_LANGUAGE


def get_project_writing_language(db, project_id: int) -> str:
    """The project's writing language CODE (normalized; invalid → default).
    Projects created before this feature read as the global default."""
    try:
        stored = (db.get_project_settings(project_id) or {}).get(
            KEY_WRITING_LANGUAGE)
    except Exception:
        stored = None
    if stored:
        return normalize_language(stored)
    return default_writing_language()


def get_project_writing_language_source(db, project_id: int) -> str:
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        return "default"
    if settings.get(KEY_WRITING_LANGUAGE):
        return str(settings.get(KEY_WRITING_SOURCE) or "user_selected")
    return "default"


def set_project_writing_language(db, project_id: int, code,
                                 *, source: str = "user_selected") -> str:
    """Persist the project's writing language (normalized). Touches ONLY the
    project settings JSON — never scene bodies, structure or other projects.
    Returns the stored code."""
    code = normalize_language(code)
    settings = db.get_project_settings(project_id) or {}
    settings[KEY_WRITING_LANGUAGE] = code
    settings[KEY_WRITING_SOURCE] = source
    db.save_project_settings(project_id, settings)
    return code


def _project_override(db, project_id: int, key: str) -> str:
    try:
        raw = (db.get_project_settings(project_id) or {}).get(key)
    except Exception:
        return ""
    return normalize_language(raw) if raw else ""


def set_project_override(db, project_id: int, key: str, code) -> None:
    """Set/clear (with falsy *code*) a per-project language override field
    (``grammar_language_override`` / ``dexter_language_override``)."""
    settings = db.get_project_settings(project_id) or {}
    if code:
        settings[key] = normalize_language(code)
    else:
        settings.pop(key, None)
    db.save_project_settings(project_id, settings)


def grammar_language_for_project(db, project_id: int) -> str:
    """The grammar checker's language for a project: the per-project grammar
    override if set, else the user-selected writing language. Returns ""
    when the project never chose a language (legacy per-paragraph
    auto-detection keeps working unchanged)."""
    override = _project_override(db, project_id, KEY_GRAMMAR_OVERRIDE)
    if override:
        return override
    if get_project_writing_language_source(db, project_id) in (
            "user_selected", "imported"):
        code = get_project_writing_language(db, project_id)
        return "" if code == "auto" else code
    return ""


def dexter_language_for_project(db, project_id: int) -> str:
    """Dexter's "Use project language" resolution: the per-project Dexter
    override if set, else the project writing language (may be "auto")."""
    override = _project_override(db, project_id, KEY_DEXTER_OVERRIDE)
    if override:
        return override
    return get_project_writing_language(db, project_id)


def project_language_for_ai(db, project_id: int) -> str:
    """The writing language the AI must preserve — only when the user (or an
    import) actually chose one. "" keeps the legacy detect-from-text
    behavior for untouched projects."""
    if get_project_writing_language_source(db, project_id) in (
            "user_selected", "imported"):
        code = get_project_writing_language(db, project_id)
        if code not in ("", "auto"):
            return code
    return ""


# ---------------------------------------------------------------------------
# AI coordination — the preserve-language instruction
# ---------------------------------------------------------------------------


def ai_language_instruction(code: str) -> str:
    """System-prompt suffix telling the AI to preserve the writing language.
    Empty for English/auto (English is the prompts' base assumption); never
    asks for translation and never converts script direction."""
    code = normalize_language(code)
    if code in ("", "auto", "en"):
        return ""
    name = language_name(code)
    text = (
        f"\n\nThe project writing language is: {name} ({code}). Preserve "
        f"this language unless the user explicitly asks to translate — all "
        f"prose, dialogue, feedback and suggestions must be in {name}. "
        f"Never translate the user's text on your own, and never translate "
        f"code, JSON keys, or structured output formats."
    )
    if code in RTL_CODES:
        text += (f" {name} is written right-to-left; keep the original "
                 f"text direction and punctuation.")
    if code in NO_WORDSPACE_CODES:
        text += (f" {name} does not separate words with spaces; never "
                 f"insert spaces between characters or assume word "
                 f"boundaries.")
    return text


def language_context_line(db, project_id: int) -> str:
    """One-line context block for assistant/Logos packaging ("" when the
    project never chose a language)."""
    code = project_language_for_ai(db, project_id)
    if not code:
        return ""
    return (f"[Writing Language] {display_name(code)} — preserve this "
            f"language unless asked to translate.")
