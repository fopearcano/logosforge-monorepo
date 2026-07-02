"""Logosforge — centralized theme with Dark, Light (Green), Light (Warm) palettes."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Palette definitions
# ---------------------------------------------------------------------------

_PALETTES: dict[str, dict[str, str]] = {
    "Dark": {
        "BG_DARK":       "#0f1219",
        "BG_PANEL":      "#161b26",
        "BG_INPUT":      "#1a2030",
        "BG_SIDEBAR":    "#0b0e14",
        "BG_HOVER":      "#222938",
        "BG_PRESSED":    "#1e2533",

        "TEXT_PRIMARY":  "#e5e7eb",
        "TEXT_SECONDARY": "#9ca3af",
        "TEXT_MUTED":    "#6b7280",

        "ACCENT":        "#4ade80",
        "ACCENT_DIM":    "#22c55e",
        "ACCENT_TEXT":   "#ffffff",

        "BORDER":        "#232b3a",
        "BORDER_FOCUS":  "#4ade80",

        "SELECTION_BG":  "#1e3a2a",
        "SELECTION_TEXT": "#ffffff",

        "TABLE_ALT_ROW": "#111620",

        "STATUS_OK":     "#4ade80",
        "STATUS_ERR":    "#f87171",

        "DIFF_ORIGINAL_BG":     "#1a1215",
        "DIFF_ORIGINAL_TEXT":   "#d4a0a0",
        "DIFF_ORIGINAL_BORDER": "#3a2020",
        "DIFF_PROPOSED_BG":     "#121a15",
        "DIFF_PROPOSED_TEXT":   "#a0d4a0",
        "DIFF_PROPOSED_BORDER": "#203a20",

        "LINK_COLOR":    "#4ade80",

        "CARD_BG":       "#181e2a",
        "CARD_BORDER":   "#232b3a",
        "CARD_HERO_BG":  "#162216",
        "CARD_HERO_BORDER": "#22543d",
        "CARD_BEAT_BG":  "#161b26",
        "CARD_KEY_BEAT_BG": "#1f1d14",
        "CARD_BEAT_BORDER": "#607d8b",
        "CARD_KEY_BEAT_BORDER": "#ff9800",

        "SIDEBAR_ACTIVE_BG": "#1e3a2a",
        "SIDEBAR_ACTIVE_TEXT": "#4ade80",
        "SIDEBAR_ICON":  "#6b7280",

        "BTN_PRIMARY_BG": "#22c55e",
        "BTN_PRIMARY_TEXT": "#0f1219",
        "BTN_PRIMARY_HOVER": "#16a34a",
        "BTN_PRIMARY_BORDER": "#22c55e",

        "SCROLLBAR_BG":  "#0f1219",
        "SCROLLBAR_HANDLE": "#2a3344",
        "SCROLLBAR_HOVER": "#3b4a60",

        "PSYKE_TEXT":        "#5ee8b4",
        "PSYKE_BRIGHT":     "#8df5d2",
        "PSYKE_MATCH":      "#a0fae0",
        "PSYKE_SELECTED_BG": "#0f2b24",

        "PSYKE_CHARACTER":  "#7cc4e8",
        "PSYKE_PLACE":      "#d4a876",
        "PSYKE_OBJECT":     "#a0aab4",

        "GRAMMAR_SPELLING": "#ef4444",
        "GRAMMAR_GRAMMAR":  "#60a5fa",
        "GRAMMAR_STYLE":    "#78716c",
        "STYLE_HINT":       "#8b8589",
        "VOICE_HINT":       "#c084fc",
    },

    "Light (Green)": {
        "BG_DARK":       "#edf2ee",
        "BG_PANEL":      "#f9fbf9",
        "BG_INPUT":      "#e8efe9",
        "BG_SIDEBAR":    "#dce8df",
        "BG_HOVER":      "#c8dccb",
        "BG_PRESSED":    "#b4cfb8",

        "TEXT_PRIMARY":  "#111a14",
        "TEXT_SECONDARY": "#3a5245",
        "TEXT_MUTED":    "#6b8574",

        "ACCENT":        "#16a34a",
        "ACCENT_DIM":    "#22c55e",
        "ACCENT_TEXT":   "#ffffff",

        "BORDER":        "#b8cfbe",
        "BORDER_FOCUS":  "#16a34a",

        "SELECTION_BG":  "#c6e7cc",
        "SELECTION_TEXT": "#111a14",

        "TABLE_ALT_ROW": "#e8efe9",

        "STATUS_OK":     "#16a34a",
        "STATUS_ERR":    "#dc2626",

        "DIFF_ORIGINAL_BG":     "#fef2f2",
        "DIFF_ORIGINAL_TEXT":   "#991b1b",
        "DIFF_ORIGINAL_BORDER": "#fecaca",
        "DIFF_PROPOSED_BG":     "#ecfdf5",
        "DIFF_PROPOSED_TEXT":   "#14532d",
        "DIFF_PROPOSED_BORDER": "#86efac",

        "LINK_COLOR":    "#0d7a32",

        "CARD_BG":       "#f9fbf9",
        "CARD_BORDER":   "#b8cfbe",
        "CARD_HERO_BG":  "#dcfce7",
        "CARD_HERO_BORDER": "#86efac",
        "CARD_BEAT_BG":  "#f0f7f1",
        "CARD_KEY_BEAT_BG": "#fef9c3",
        "CARD_BEAT_BORDER": "#6b9f78",
        "CARD_KEY_BEAT_BORDER": "#f59e0b",

        "SIDEBAR_ACTIVE_BG": "#c6e7cc",
        "SIDEBAR_ACTIVE_TEXT": "#0d7a32",
        "SIDEBAR_ICON":  "#5a7a64",

        "BTN_PRIMARY_BG": "#16a34a",
        "BTN_PRIMARY_TEXT": "#ffffff",
        "BTN_PRIMARY_HOVER": "#15803d",
        "BTN_PRIMARY_BORDER": "#16a34a",

        "SCROLLBAR_BG":  "#edf2ee",
        "SCROLLBAR_HANDLE": "#a3bca8",
        "SCROLLBAR_HOVER": "#7fa88a",

        "PSYKE_TEXT":        "#0d7a4a",
        "PSYKE_BRIGHT":     "#06613a",
        "PSYKE_MATCH":      "#047040",
        "PSYKE_SELECTED_BG": "#d0f0e0",

        "PSYKE_CHARACTER":  "#1a6b8a",
        "PSYKE_PLACE":      "#8a5a2a",
        "PSYKE_OBJECT":     "#5a6570",

        "GRAMMAR_SPELLING": "#dc2626",
        "GRAMMAR_GRAMMAR":  "#2563eb",
        "GRAMMAR_STYLE":    "#a8a29e",
        "STYLE_HINT":       "#9ca3af",
        "VOICE_HINT":       "#9333ea",
    },

    "Light (Warm)": {
        "BG_DARK":       "#1c1612",
        "BG_PANEL":      "#2a211b",
        "BG_INPUT":      "#221b16",
        "BG_SIDEBAR":    "#1a1410",
        "BG_HOVER":      "#3a2e26",
        "BG_PRESSED":    "#4a3c32",

        "TEXT_PRIMARY":  "#f2e6d8",
        "TEXT_SECONDARY": "#cbb8a6",
        "TEXT_MUTED":    "#8a7766",

        "ACCENT":        "#b07a3a",
        "ACCENT_DIM":    "#c48a45",
        "ACCENT_TEXT":   "#f2e6d8",

        "BORDER":        "#3a2f27",
        "BORDER_FOCUS":  "#b07a3a",

        "SELECTION_BG":  "#4a3828",
        "SELECTION_TEXT": "#f2e6d8",

        "TABLE_ALT_ROW": "#241d17",

        "STATUS_OK":     "#8aad5a",
        "STATUS_ERR":    "#c04030",

        "DIFF_ORIGINAL_BG":     "#2a1a18",
        "DIFF_ORIGINAL_TEXT":   "#d4a0a0",
        "DIFF_ORIGINAL_BORDER": "#3a2220",
        "DIFF_PROPOSED_BG":     "#1e2a1a",
        "DIFF_PROPOSED_TEXT":   "#a0c4a0",
        "DIFF_PROPOSED_BORDER": "#2a3a22",

        "LINK_COLOR":    "#c48a45",

        "CARD_BG":       "#2a211b",
        "CARD_BORDER":   "#3a2f27",
        "CARD_HERO_BG":  "#33281e",
        "CARD_HERO_BORDER": "#4a3828",
        "CARD_BEAT_BG":  "#2a211b",
        "CARD_KEY_BEAT_BG": "#33281a",
        "CARD_BEAT_BORDER": "#5a4a3a",
        "CARD_KEY_BEAT_BORDER": "#b07a3a",

        "SIDEBAR_ACTIVE_BG": "#3a2e22",
        "SIDEBAR_ACTIVE_TEXT": "#c48a45",
        "SIDEBAR_ICON":  "#8a7766",

        "BTN_PRIMARY_BG": "#b07a3a",
        "BTN_PRIMARY_TEXT": "#f2e6d8",
        "BTN_PRIMARY_HOVER": "#8f5e2a",
        "BTN_PRIMARY_BORDER": "#b07a3a",

        "SCROLLBAR_BG":  "#1c1612",
        "SCROLLBAR_HANDLE": "#3a2f27",
        "SCROLLBAR_HOVER": "#4a3c32",

        "PSYKE_TEXT":        "#6aad8a",
        "PSYKE_BRIGHT":     "#8ac4a0",
        "PSYKE_MATCH":      "#a0d4b0",
        "PSYKE_SELECTED_BG": "#1e2e24",

        "PSYKE_CHARACTER":  "#7aa0b0",
        "PSYKE_PLACE":      "#c4956a",
        "PSYKE_OBJECT":     "#8a9098",

        "GRAMMAR_SPELLING": "#ef4444",
        "GRAMMAR_GRAMMAR":  "#60a5fa",
        "GRAMMAR_STYLE":    "#78716c",
        "STYLE_HINT":       "#8b8589",
        "VOICE_HINT":       "#c084fc",
    },
}

# ---------------------------------------------------------------------------
# Active palette — module-level attributes updated by set_palette()
# ---------------------------------------------------------------------------

_current_palette: str = "Dark"


def _apply(palette: dict[str, str]) -> None:
    g = globals()
    for key, value in palette.items():
        g[key] = value


# Initialize with Dark
_apply(_PALETTES["Dark"])

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

PALETTE_NAMES: list[str] = list(_PALETTES.keys())


def current_palette() -> str:
    return _current_palette


def set_palette(name: str) -> None:
    global _current_palette
    if name not in _PALETTES:
        return
    _current_palette = name
    _apply(_PALETTES[name])


def get(key: str) -> str:
    """Get a color value by key name from the active palette."""
    return globals().get(key, "#ff00ff")


# ---------------------------------------------------------------------------
# build_stylesheet — reads current module-level values at call time
# ---------------------------------------------------------------------------

def _is_light() -> bool:
    return _current_palette != "Dark"


def build_stylesheet() -> str:
    light = _is_light()
    disabled_opacity = "0.5" if light else "0.4"

    return f"""
    /* -- Base -- */
    QWidget {{
        background-color: {BG_DARK};
        color: {TEXT_PRIMARY};
        font-size: 13px;
    }}

    QMainWindow {{
        background-color: {BG_DARK};
    }}

    /* -- Labels -- */
    QLabel {{
        background-color: transparent;
        padding: 2px 0px;
    }}

    /* -- Buttons (secondary = default) -- */
    QPushButton {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 4px 10px;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {BG_HOVER};
        border-color: {ACCENT_DIM};
    }}
    QPushButton:pressed {{
        background-color: {BG_PRESSED};
        border-color: {ACCENT};
    }}
    QPushButton:disabled {{
        color: {TEXT_MUTED};
        border-color: {BG_INPUT};
        opacity: {disabled_opacity};
    }}
    /* -- Tertiary (flat) buttons -- */
    QPushButton:flat {{
        border: none;
        background-color: transparent;
        padding: 4px 8px;
    }}
    QPushButton:flat:hover {{
        background-color: {BG_HOVER};
        border-radius: 6px;
    }}

    /* -- Sidebar -- */
    #sidebar {{
        background-color: {BG_SIDEBAR};
        border-right: 1px solid {BORDER};
    }}
    #sidebar QPushButton, #sidebarBtn {{
        border: none;
        border-radius: 6px;
        text-align: left;
        padding: 6px 8px;
        margin: 0px 4px;
        background-color: transparent;
        color: {TEXT_SECONDARY};
        font-size: 13px;
    }}
    #sidebar QPushButton:hover, #sidebarBtn:hover {{
        background-color: {BG_HOVER};
        color: {TEXT_PRIMARY};
    }}
    #sidebar QPushButton:pressed, #sidebarBtn:pressed {{
        background-color: {SIDEBAR_ACTIVE_BG};
        color: {SIDEBAR_ACTIVE_TEXT};
    }}
    #sidebar QPushButton:checked, #sidebarBtn:checked {{
        background-color: {SIDEBAR_ACTIVE_BG};
        color: {SIDEBAR_ACTIVE_TEXT};
        font-weight: bold;
    }}

    /* -- Line edits -- */
    QLineEdit {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 4px 8px;
        selection-background-color: {SELECTION_BG};
        selection-color: {SELECTION_TEXT};
    }}
    QLineEdit:focus {{
        border-color: {BORDER_FOCUS};
    }}
    QLineEdit:disabled {{
        color: {TEXT_MUTED};
        opacity: {disabled_opacity};
    }}

    /* -- Plain text edits -- */
    QPlainTextEdit {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px;
        selection-background-color: {SELECTION_BG};
        selection-color: {SELECTION_TEXT};
    }}
    QPlainTextEdit:focus {{
        border-color: {BORDER_FOCUS};
    }}

    /* -- Content editor (scene writing area) -- */
    #contentEditor {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: none;
        border-radius: 8px;
        padding: 32px 32px;
        selection-background-color: {SELECTION_BG};
        selection-color: {SELECTION_TEXT};
    }}

    /* -- Text browser -- */
    QTextBrowser {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 8px;
    }}

    /* -- Combo boxes -- */
    QComboBox {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 4px 8px;
        min-height: 20px;
    }}
    QComboBox:focus {{
        border-color: {BORDER_FOCUS};
    }}
    QComboBox:disabled {{
        color: {TEXT_MUTED};
        opacity: {disabled_opacity};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {TEXT_SECONDARY};
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        selection-background-color: {SELECTION_BG};
        selection-color: {SELECTION_TEXT};
        outline: none;
    }}

    /* -- Checkboxes -- */
    QCheckBox {{
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {BORDER};
        border-radius: 4px;
        background-color: {BG_INPUT};
    }}
    QCheckBox::indicator:hover {{
        border-color: {ACCENT_DIM};
    }}
    QCheckBox::indicator:checked {{
        background-color: {ACCENT};
        border-color: {ACCENT};
    }}

    /* -- List widgets -- */
    QListWidget {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        outline: none;
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 4px 8px;
        border-radius: 6px;
        margin: 1px 2px;
    }}
    QListWidget::item:selected {{
        background-color: {SELECTION_BG};
        color: {SELECTION_TEXT};
    }}
    QListWidget::item:hover {{
        background-color: {BG_HOVER};
    }}

    /* -- Table widgets -- */
    QTableWidget {{
        background-color: {BG_DARK};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        gridline-color: {BORDER};
        outline: none;
    }}
    QTableWidget::item {{
        padding: 4px 6px;
    }}
    QTableWidget::item:selected {{
        background-color: {SELECTION_BG};
        color: {SELECTION_TEXT};
    }}
    QHeaderView::section {{
        background-color: {BG_PANEL};
        color: {TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {BORDER};
        border-right: 1px solid {BORDER};
        padding: 6px 8px;
        font-weight: bold;
    }}

    /* -- Scroll area -- */
    QScrollArea {{
        border: none;
    }}

    /* -- Scroll bars -- */
    QScrollBar:vertical {{
        background-color: transparent;
        width: 8px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background-color: {SCROLLBAR_HANDLE};
        border-radius: 4px;
        min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {SCROLLBAR_HOVER};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background-color: transparent;
        height: 8px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {SCROLLBAR_HANDLE};
        border-radius: 4px;
        min-width: 32px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {SCROLLBAR_HOVER};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}

    /* -- Menu bar -- */
    QMenuBar {{
        background-color: {BG_SIDEBAR};
        color: {TEXT_PRIMARY};
        border-bottom: 1px solid {BORDER};
        padding: 2px 4px;
    }}
    QMenuBar::item {{
        padding: 4px 10px;
        border-radius: 6px;
        background-color: transparent;
    }}
    QMenuBar::item:selected {{
        background-color: {BG_HOVER};
    }}

    /* -- Menus -- */
    QMenu {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 20px 6px 12px;
        border-radius: 6px;
        margin: 1px 4px;
    }}
    QMenu::item:selected {{
        background-color: {SELECTION_BG};
        color: {SELECTION_TEXT};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {BORDER};
        margin: 4px 8px;
    }}

    /* -- Message boxes and dialogs -- */
    QMessageBox {{
        background-color: {BG_PANEL};
    }}
    QDialog {{
        background-color: {BG_DARK};
    }}

    /* -- Graphics view -- */
    QGraphicsView {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 6px;
    }}

    /* -- Splitter -- */
    QSplitter::handle {{
        background-color: {BORDER};
    }}

    /* -- Tool tips -- */
    QToolTip {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 10px;
    }}

    /* -- Frame cards -- */
    QFrame#dashCard, QFrame#projCard {{
        background-color: {CARD_BG};
        border: 1px solid {CARD_BORDER};
        border-radius: 8px;
    }}
    QFrame#heroCard {{
        background-color: {CARD_HERO_BG};
        border: 1px solid {CARD_HERO_BORDER};
        border-radius: 10px;
    }}

    /* -- Appearance selector -- */
    #appearanceBar {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: 6px;
    }}
    #appearanceBar QPushButton {{
        border: none;
        border-radius: 6px;
        padding: 4px 8px;
        margin: 2px;
        font-size: 11px;
        min-height: 18px;
        background-color: transparent;
        color: {TEXT_MUTED};
    }}
    #appearanceBar QPushButton:hover {{
        background-color: {BG_HOVER};
        color: {TEXT_PRIMARY};
    }}
    #appearanceBar QPushButton:checked {{
        background-color: {SIDEBAR_ACTIVE_BG};
        color: {SIDEBAR_ACTIVE_TEXT};
        font-weight: bold;
    }}

    /* -- Assistant panel -- */
    #assistantPanel {{
        border-left: 1px solid {BORDER};
        background-color: {BG_PANEL};
    }}

    /* -- Writing Core -- */
    #writingCanvas {{
        background-color: {BG_DARK};
    }}
    #writingScroll {{
        background-color: {BG_DARK};
        border: none;
    }}
    #writingTopBar {{
        background-color: {BG_PANEL};
        border-bottom: 1px solid {BORDER};
    }}
    #writingCoreEditor {{
        background-color: transparent;
        color: {TEXT_PRIMARY};
        border: none;
        padding: 0;
        font-size: 18px;
        selection-background-color: {SELECTION_BG};
        selection-color: {SELECTION_TEXT};
    }}
    #writingActHeader {{
        color: {TEXT_MUTED};
        font-size: 11px;
        font-weight: bold;
        background: transparent;
    }}
    #writingChapterHeader {{
        color: {TEXT_PRIMARY};
        font-size: 22px;
        font-weight: bold;
        background: transparent;
    }}
    #writingSceneTitle {{
        color: {TEXT_MUTED};
        font-size: 13px;
        font-weight: normal;
        background: transparent;
    }}
    #writingEndAction {{
        color: {TEXT_MUTED};
        font-size: 13px;
        background: transparent;
        border: none;
    }}
    #writingEndAction:hover {{
        color: {ACCENT};
    }}
    #writingEmptyState {{
        color: {TEXT_MUTED};
        font-size: 15px;
        background: transparent;
    }}

    #reviewOverlay {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
        color: {TEXT_SECONDARY};
        font-size: 11px;
    }}
    #reviewOverlayTitle {{
        color: {TEXT_PRIMARY};
        font-size: 12px;
        font-weight: bold;
        background: transparent;
    }}

    /* -- Story Grid -- */
    #gridToolbar {{
        background-color: {BG_PANEL};
        border-bottom: 1px solid {BORDER};
    }}
    #gridScrollArea {{
        background-color: {BG_DARK};
        border: none;
    }}
    #gridContainer {{
        background-color: {BG_DARK};
    }}
    #gridColumn {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
    #gridActSection {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 8px;
    }}
    #gridColumnHeader {{
        color: {TEXT_PRIMARY};
        font-size: 13px;
        font-weight: bold;
        background: transparent;
        padding: 4px 0;
    }}
    #gridSceneCard {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: 6px;
    }}
    #gridSceneCard:hover {{
        border-color: {ACCENT_DIM};
    }}
    #gridCardTitle {{
        color: {TEXT_PRIMARY};
        font-size: 12px;
        font-weight: 600;
        background: transparent;
        padding: 0;
    }}
    #gridCardSummary {{
        color: {TEXT_SECONDARY};
        font-size: 11px;
        background: transparent;
        padding: 0;
    }}
    #gridCardMeta {{
        color: {TEXT_MUTED};
        font-size: 10px;
        background: transparent;
        padding: 0;
    }}
    #gridEmptyColumn {{
        color: {TEXT_MUTED};
        font-size: 11px;
        background: transparent;
        padding: 12px 4px;
    }}
    #gridEmptyState {{
        background: transparent;
    }}
    #gridEmptyLabel {{
        color: {TEXT_MUTED};
        font-size: 14px;
        background: transparent;
    }}
    #gridZoomLabel {{
        color: {TEXT_SECONDARY};
        font-size: 11px;
        background: transparent;
    }}

    /* -- Story Flow indicators -- */
    #gridCardType {{
        color: {TEXT_MUTED};
        font-size: 11px;
        background: transparent;
        padding: 0;
    }}
    #gridCharRow {{
        background: transparent;
    }}
    #gridTensionBar {{
        background: transparent;
        border-radius: 1px;
    }}
    #gridSceneCardWarning {{
        background-color: {BG_HOVER};
        border: 1px solid {BORDER};
        border-radius: 6px;
    }}

    /* -- Multi-Plot views -- */
    #multiPlotToolbar {{
        background-color: {BG_PANEL};
        border-bottom: 1px solid {BORDER};
    }}
    #multiPlotModeBtn {{
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 12px;
    }}
    #multiPlotModeBtn:checked {{
        background-color: {SIDEBAR_ACTIVE_BG};
        color: {SIDEBAR_ACTIVE_TEXT};
        font-weight: bold;
    }}

    /* Timeline strip */
    #timelineScroll {{
        background-color: {BG_DARK};
        border: none;
    }}
    #timelineContainer {{
        background-color: {BG_DARK};
    }}
    #timelineGroupHeader {{
        color: {TEXT_MUTED};
        font-size: 11px;
        font-weight: bold;
        background: transparent;
        padding: 4px 8px;
    }}
    #timelineCard {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: 6px;
    }}
    #timelineCard:hover {{
        border-color: {ACCENT_DIM};
    }}
    #timelineCardTitle {{
        color: {TEXT_PRIMARY};
        font-size: 11px;
        font-weight: 600;
        background: transparent;
    }}
    #timelineCardSummary {{
        color: {TEXT_SECONDARY};
        font-size: 10px;
        background: transparent;
    }}
    #timelineEmpty {{
        color: {TEXT_MUTED};
        font-size: 13px;
        background: transparent;
    }}

    /* Arc lanes */
    #arcScroll {{
        background-color: {BG_DARK};
        border: none;
    }}
    #arcContainer {{
        background-color: {BG_DARK};
    }}
    #arcLane {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
    #arcLaneHeader {{
        color: {TEXT_PRIMARY};
        font-size: 13px;
        font-weight: bold;
        background: transparent;
    }}
    #arcCard {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: 5px;
    }}
    #arcCardTitle {{
        color: {TEXT_PRIMARY};
        font-size: 11px;
        background: transparent;
    }}
    #arcCardBeat {{
        color: {TEXT_MUTED};
        font-size: 10px;
        background: transparent;
    }}
    #arcEmpty {{
        color: {TEXT_MUTED};
        font-size: 13px;
        background: transparent;
    }}

    /* Character lanes */
    #charScroll {{
        background-color: {BG_DARK};
        border: none;
    }}
    #charContainer {{
        background-color: {BG_DARK};
    }}
    #charLane {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
    #charLaneHeader {{
        color: {TEXT_PRIMARY};
        font-size: 13px;
        font-weight: bold;
        background: transparent;
    }}
    #charLaneCount {{
        color: {TEXT_MUTED};
        font-size: 10px;
        background: transparent;
    }}
    #charCard {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: 5px;
    }}
    #charCardTitle {{
        color: {TEXT_PRIMARY};
        font-size: 11px;
        background: transparent;
    }}
    #charCardChapter {{
        color: {TEXT_MUTED};
        font-size: 10px;
        background: transparent;
    }}
    #charEmpty {{
        color: {TEXT_MUTED};
        font-size: 13px;
        background: transparent;
    }}

    /* -- Graph Focus System -- */
    #graphToolbar {{
        background-color: {BG_PANEL};
        border-bottom: 1px solid {BORDER};
    }}
    #graphToolbar QLabel {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
    }}
    #graphToolbar QLineEdit {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 3px 6px;
        color: {TEXT_PRIMARY};
        font-size: 12px;
    }}
    #graphToolbar QLineEdit:focus {{
        border-color: {ACCENT};
    }}
    #graphToolbar QCheckBox {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        spacing: 4px;
    }}
    #graphToolbar QComboBox {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 3px 6px;
        color: {TEXT_PRIMARY};
        font-size: 12px;
        min-width: 80px;
    }}
    #focusGraphView {{
        background-color: {BG_DARK};
        border: none;
    }}

    /* -- Suggestion panel -- */
    #suggestPanel {{
        background-color: {BG_PANEL};
        border-left: 1px solid {BORDER};
    }}
    #suggestHeader {{
        color: {TEXT_PRIMARY};
        font-size: 12px;
        font-weight: bold;
        padding: 4px 0;
        background: transparent;
    }}
    #suggestBtn {{
        color: {ACCENT};
        font-size: 12px;
        font-weight: bold;
        text-align: left;
        padding: 4px 6px;
        background: transparent;
        border: none;
    }}
    #suggestBtn:hover {{
        background-color: {BG_HOVER};
        border-radius: 4px;
    }}
    #suggestDesc {{
        color: {TEXT_SECONDARY};
        font-size: 11px;
        padding: 0 6px 6px 6px;
        background: transparent;
    }}
    #suggestHint {{
        color: {TEXT_MUTED};
        font-size: 12px;
        background: transparent;
    }}

    /* -- Story Health Panel -- */
    #storyHealthView {{
        background-color: {BG_DARK};
    }}
    #healthTitle {{
        color: {TEXT_PRIMARY};
        font-size: 16px;
        font-weight: bold;
        padding-bottom: 12px;
        background: transparent;
    }}
    #healthBar {{
        background: transparent;
    }}
    #healthBarTitle {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        background: transparent;
    }}
    #healthBarStatus {{
        font-size: 11px;
        font-weight: bold;
        background: transparent;
    }}
    #healthProgressBar {{
        background-color: {BG_INPUT};
        border: none;
        border-radius: 3px;
    }}

    /* -- Character & Arc Balance -- */
    #characterBalanceView {{
        background-color: {BG_DARK};
    }}
    #balanceTitle {{
        color: {TEXT_PRIMARY};
        font-size: 16px;
        font-weight: bold;
        padding-bottom: 8px;
        background: transparent;
    }}
    #balanceSectionHeader {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        font-weight: bold;
        padding: 8px 0 4px 0;
        background: transparent;
    }}
    #balanceScroll {{
        background-color: {BG_DARK};
        border: none;
    }}
    #balanceRow {{
        background: transparent;
        border-radius: 4px;
    }}
    #balanceRow:hover {{
        background-color: {BG_HOVER};
    }}
    #balanceRowName {{
        color: {TEXT_PRIMARY};
        font-size: 12px;
        background: transparent;
    }}
    #balanceRowCount {{
        color: {TEXT_MUTED};
        font-size: 11px;
        background: transparent;
    }}
    #balanceBar {{
        background-color: {BG_INPUT};
        border: none;
        border-radius: 4px;
    }}
    #balanceBar::chunk {{
        background-color: {ACCENT_DIM};
        border-radius: 4px;
    }}
    #balanceFlag {{
        font-size: 10px;
        font-weight: bold;
        background: transparent;
    }}
    #balanceEmpty {{
        color: {TEXT_MUTED};
        font-size: 13px;
        background: transparent;
    }}

    /* -- Pacing Insights -- */
    #pacingInsightsView {{
        background-color: {BG_DARK};
    }}
    #insightsTitle {{
        color: {TEXT_PRIMARY};
        font-size: 16px;
        font-weight: bold;
        padding-bottom: 8px;
        background: transparent;
    }}
    #insightRow {{
        background: transparent;
        border-radius: 4px;
    }}
    #insightRow:hover {{
        background-color: {BG_HOVER};
    }}
    #insightText {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        background: transparent;
    }}
    #insightsEmpty {{
        color: {TEXT_MUTED};
        font-size: 13px;
        background: transparent;
    }}

    /* -- Mode Suggestions -- */
    #modeSuggestionsView {{
        background-color: {BG_DARK};
    }}
    #modeSuggestionsTitle {{
        color: {TEXT_PRIMARY};
        font-size: 16px;
        font-weight: bold;
        padding-bottom: 4px;
        background: transparent;
    }}
    #modeBadge {{
        font-size: 18px;
        font-weight: bold;
        background: transparent;
    }}
    #modeDescription {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        background: transparent;
    }}
    #modeStageLabel {{
        color: {TEXT_MUTED};
        font-size: 11px;
        background: transparent;
    }}
    #modeSeparator {{
        background-color: {BORDER};
        max-height: 1px;
    }}
    #modeSuggestionsHeader {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        font-weight: bold;
        padding: 4px 0;
        background: transparent;
    }}
    #modeSuggestionRow {{
        background: transparent;
        border-radius: 4px;
    }}
    #modeSuggestionRow:hover {{
        background-color: {BG_HOVER};
    }}
    #modeSuggestionText {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        background: transparent;
    }}
    #modeSuggestionsEmpty {{
        color: {TEXT_MUTED};
        font-size: 13px;
        background: transparent;
    }}

    /* -- Mode Strip (Assistant panel) -- */
    #modeStrip {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: 4px;
    }}
    #modeStripHint {{
        color: {TEXT_MUTED};
        font-size: 10px;
        background: transparent;
        padding: 0 0 0 12px;
    }}
    #modeStripReset {{
        color: {TEXT_MUTED};
        font-size: 10px;
        border: none;
        padding: 0 4px;
        background: transparent;
    }}
    #modeStripReset:hover {{
        color: {ACCENT};
    }}

    /* -- Quantum Timeline Superposition -- */
    #qtlScroll {{
        background-color: {BG_DARK};
        border: none;
    }}
    #qtlContainer {{
        background-color: {BG_DARK};
    }}
    #qtlColumn {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 4px;
    }}
    #qtlSceneTitle {{
        color: {TEXT_PRIMARY};
        font-size: 10px;
        font-weight: bold;
        background: transparent;
        padding: 0;
    }}
    #qtlBranchTitle {{
        color: {TEXT_PRIMARY};
        font-size: 10px;
        font-weight: 600;
        background: transparent;
        padding: 0;
    }}
    #qtlBranchMeta {{
        color: {TEXT_MUTED};
        font-size: 9px;
        background: transparent;
        padding: 0;
    }}
    #qtlBeatMarker {{
        color: {ACCENT_DIM};
        font-size: 9px;
        font-weight: 600;
        background: transparent;
        padding: 0;
    }}
    #qtlBranchBeat {{
        color: {ACCENT_DIM};
        font-size: 9px;
        background: transparent;
        padding: 0;
    }}
    #qtlBranchType {{
        font-size: 8px;
        font-weight: bold;
        background: transparent;
        padding: 0 2px;
        border-radius: 2px;
    }}
    #qtlModeStrip {{
        font-size: 9px;
        background: {BG_DARK};
        padding: 0 6px;
    }}
    #qtlUncertainty {{
        color: {ACCENT_DIM};
        font-size: 8px;
        font-weight: bold;
        background: transparent;
        padding: 1px 0;
    }}
    #qtlProbLabel {{
        color: {TEXT_MUTED};
        font-size: 9px;
        font-weight: bold;
        background: transparent;
        padding: 0;
    }}
    #qtlEmpty {{
        color: {TEXT_MUTED};
        font-size: 11px;
        background: transparent;
        padding: 8px 0;
    }}

    /* -- Scoring weights popover -- */
    #weightsPopover {{
        background-color: {BG_PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
    #weightsPopover QLabel {{
        color: {TEXT_SECONDARY};
        font-size: 11px;
        background: transparent;
    }}
    #weightsPopover QLabel#weightsTitle {{
        color: {TEXT_PRIMARY};
        font-size: 12px;
        font-weight: bold;
    }}
    #weightsPopover QLabel#weightsValue {{
        color: {ACCENT_DIM};
        font-size: 10px;
        font-weight: bold;
        min-width: 30px;
    }}
    #weightsPopover QSlider::groove:horizontal {{
        height: 4px;
        background: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: 2px;
    }}
    #weightsPopover QSlider::handle:horizontal {{
        width: 10px;
        height: 10px;
        margin: -4px 0;
        background: {ACCENT_DIM};
        border: 1px solid {ACCENT};
        border-radius: 5px;
    }}
    #weightsPopover QSlider::handle:horizontal:hover {{
        background: {ACCENT};
    }}
    #weightsPopover QSlider::sub-page:horizontal {{
        background: {ACCENT_DIM};
        border-radius: 2px;
    }}
    #weightsPresetCombo {{
        background-color: {BG_INPUT};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 2px 6px;
        font-size: 11px;
        min-height: 18px;
    }}
    #weightsPresetCombo:hover {{
        border-color: {BORDER_FOCUS};
    }}
    #weightsPresetCombo QAbstractItemView {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        selection-background-color: {SELECTION_BG};
        selection-color: {SELECTION_TEXT};
    }}
    #weightsBtn {{
        background: transparent;
        color: {TEXT_MUTED};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 1px 6px;
        font-size: 9px;
    }}
    #weightsBtn:hover {{
        color: {TEXT_PRIMARY};
        border-color: {BORDER_FOCUS};
    }}
    """


# ---------------------------------------------------------------------------
# HTML helpers — re-generated each time to respect current palette
# ---------------------------------------------------------------------------

HTML_TABLE_BORDER = ""
HTML_TABLE_ALT = ""
HTML_MUTED_TEXT = ""
HTML_STYLES = ""


def _rebuild_html() -> None:
    global HTML_TABLE_BORDER, HTML_TABLE_ALT, HTML_MUTED_TEXT, HTML_STYLES
    HTML_TABLE_BORDER = BORDER
    HTML_TABLE_ALT = TABLE_ALT_ROW
    HTML_MUTED_TEXT = TEXT_MUTED
    HTML_STYLES = f"""
<style>
    body {{ color: {TEXT_PRIMARY}; }}
    table {{ border-collapse: collapse; }}
    th {{ text-align: left; padding: 5px 10px; }}
    td {{ padding: 5px 10px; }}
    tr {{ border-bottom: 1px solid {BORDER}; }}
    h1, h2, h3 {{ color: {TEXT_PRIMARY}; }}
    a {{ color: {LINK_COLOR}; }}
    .muted {{ color: {TEXT_MUTED}; }}
</style>
"""


_rebuild_html()


# ---------------------------------------------------------------------------
# Style helper functions — called at widget construction time
# ---------------------------------------------------------------------------

def primary_btn() -> str:
    return (
        f"QPushButton {{"
        f"  background-color: {BTN_PRIMARY_BG};"
        f"  color: {BTN_PRIMARY_TEXT};"
        f"  border: 1px solid {BTN_PRIMARY_BORDER};"
        f"  border-radius: 6px; padding: 5px 16px;"
        f"  font-weight: bold; font-size: 13px;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background-color: {BTN_PRIMARY_HOVER};"
        f"}}"
        f"QPushButton:disabled {{"
        f"  opacity: 0.5;"
        f"}}"
    )


def card_style(object_name: str = "dashCard") -> str:
    return (
        f"QFrame#{object_name} {{ background: {CARD_BG};"
        f" border: 1px solid {CARD_BORDER}; border-radius: 8px; }}"
    )


def hero_card_style() -> str:
    return (
        f"QFrame#heroCard {{ background: {CARD_HERO_BG};"
        f" border: 1px solid {CARD_HERO_BORDER}; border-radius: 10px; }}"
    )


def eyebrow() -> str:
    return (
        f"color: {TEXT_MUTED}; font-size: 10px;"
        f" font-weight: bold;"
    )


def small_btn() -> str:
    return (
        f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY};"
        f" border: 1px solid {BORDER}; border-radius: 6px;"
        f" padding: 4px 12px; font-size: 11px; }}"
        f"QPushButton:hover {{ background: {BG_HOVER};"
        f" color: {TEXT_PRIMARY}; }}"
    )


def apply_card_shadow(widget) -> None:
    """Apply a subtle drop shadow to a card widget (skipped for Warm theme)."""
    if _current_palette == "Light (Warm)":
        return
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    from PySide6.QtGui import QColor
    effect = QGraphicsDropShadowEffect(widget)
    if _is_light():
        effect.setColor(QColor(0, 0, 0, 18))
        effect.setBlurRadius(16)
        effect.setOffset(0, 2)
    else:
        effect.setColor(QColor(0, 0, 0, 50))
        effect.setBlurRadius(12)
        effect.setOffset(0, 2)
    widget.setGraphicsEffect(effect)
