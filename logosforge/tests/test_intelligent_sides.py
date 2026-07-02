"""Tests for Intelligent Sides — assistant and sidebar improvements."""

from logosforge.db import Database
from logosforge.ui.assistant_view import AssistantPanel
from logosforge.ui.main_window import MainWindow
from logosforge.ui import theme


def _make_panel():
    db = Database()
    proj = db.create_project("Test")
    panel = AssistantPanel(db, proj.id)
    return panel, db, proj


def _make_window():
    db = Database()
    proj = db.create_project("SidebarTest")
    win = MainWindow(db, proj.id)
    return win


# -- Assistant panel size constraints -----------------------------------------

def test_assistant_max_width():
    panel, *_ = _make_panel()
    assert panel.maximumWidth() <= 360


def test_assistant_min_width():
    panel, *_ = _make_panel()
    assert panel.minimumWidth() >= 200


def test_assistant_object_name():
    panel, *_ = _make_panel()
    assert panel.objectName() == "assistantPanel"


# -- Overlay mode --------------------------------------------------------------

def test_overlay_default_off():
    panel, *_ = _make_panel()
    assert panel.is_overlay() is False


def test_overlay_toggle():
    panel, *_ = _make_panel()
    signals = []
    panel.overlay_toggled.connect(lambda v: signals.append(v))
    panel._toggle_overlay()
    assert panel.is_overlay() is True
    assert signals == [True]
    panel._toggle_overlay()
    assert panel.is_overlay() is False
    assert signals == [True, False]


def test_overlay_style_differs_from_docked():
    panel, *_ = _make_panel()
    docked = panel._build_style()
    panel._overlay_mode = True
    overlay = panel._build_style()
    assert "border-left:" in docked
    assert "border-radius:" in overlay
    assert docked != overlay


# -- Contextual dimming --------------------------------------------------------

def test_dim_undim():
    panel, *_ = _make_panel()
    assert panel._typing_dimmed is False
    panel.dim_for_typing()
    assert panel._typing_dimmed is True
    panel.undim()
    assert panel._typing_dimmed is False


def test_dim_idempotent():
    panel, *_ = _make_panel()
    panel.dim_for_typing()
    panel.dim_for_typing()
    assert panel._typing_dimmed is True
    panel.undim()
    assert panel._typing_dimmed is False


def test_dimmed_style_includes_opacity():
    panel, *_ = _make_panel()
    style = panel._build_style(dimmed=True)
    assert "opacity" in style


def test_normal_style_no_opacity():
    panel, *_ = _make_panel()
    style = panel._build_style(dimmed=False)
    assert "opacity:" not in style or "opacity: 0" not in style


# -- Overlay button exists -----------------------------------------------------

def test_overlay_button_in_header():
    panel, *_ = _make_panel()
    assert hasattr(panel, "_overlay_btn")
    assert "overlay" in panel._overlay_btn.toolTip().lower()


# -- Style refresh -------------------------------------------------------------

def test_refresh_style():
    panel, *_ = _make_panel()
    panel.refresh_style()
    ss = panel.styleSheet()
    assert "assistantPanel" in ss


# -- Theme stylesheet includes assistant panel ---------------------------------

def test_theme_has_assistant_panel_rule():
    ss = theme.build_stylesheet()
    assert "#assistantPanel" in ss
    assert "border-left" in ss


# -- Suggest Beats button present ----------------------------------------------

def test_suggest_beats_button_in_panel():
    panel, *_ = _make_panel()
    assert hasattr(panel, "_suggest_btn")
    assert panel._suggest_btn.toolTip() == "Structured narrative direction suggestions"


# -- Sidebar alignment: deferred label update ---------------------------------

def test_sidebar_initial_expanded_has_labels():
    win = _make_window()
    label = list(win.sidebar_buttons.keys())[0]
    btn = win.sidebar_buttons[label]
    assert label in btn.text()
    assert win._sidebar.objectName() == "sidebar"


def test_sidebar_collapse_sets_icon_only():
    win = _make_window()
    win._set_sidebar_collapsed(True, animate=False)
    for label, btn in win.sidebar_buttons.items():
        assert label not in btn.text()


def test_sidebar_expand_restores_labels():
    win = _make_window()
    win._set_sidebar_collapsed(True, animate=False)
    win._set_sidebar_collapsed(False, animate=False)
    for label, btn in win.sidebar_buttons.items():
        assert label in btn.text()


def test_sidebar_appearance_hidden_when_collapsed():
    win = _make_window()
    win._set_sidebar_collapsed(True, animate=False)
    assert win._appearance_label.isHidden()
    assert win._appearance_bar.isHidden()


def test_sidebar_appearance_shown_when_expanded():
    win = _make_window()
    win._set_sidebar_collapsed(True, animate=False)
    win._set_sidebar_collapsed(False, animate=False)
    assert not win._appearance_label.isHidden()
    assert not win._appearance_bar.isHidden()


def test_sidebar_import_export_text_collapsed():
    win = _make_window()
    win._set_sidebar_collapsed(True, animate=False)
    assert "Import" not in win._import_btn.text()
    assert "Export" not in win._export_btn.text()


def test_sidebar_import_export_text_expanded():
    win = _make_window()
    win._set_sidebar_collapsed(True, animate=False)
    win._set_sidebar_collapsed(False, animate=False)
    assert "Import" in win._import_btn.text()
    assert "Export" in win._export_btn.text()


def test_sidebar_repeated_toggles():
    win = _make_window()
    label = list(win.sidebar_buttons.keys())[0]
    btn = win.sidebar_buttons[label]
    for _ in range(5):
        win._set_sidebar_collapsed(True, animate=False)
        assert label not in btn.text()
        win._set_sidebar_collapsed(False, animate=False)
        assert label in btn.text()
