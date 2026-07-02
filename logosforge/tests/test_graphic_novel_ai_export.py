"""Tests for Slice 9 — Graphic Novel AI / ComfyUI prompt export hooks."""

import json

import pytest

from logosforge.db import Database
from logosforge.graphic_novel_ai_export import (
    GraphicNovelPromptPackage,
    assistant_missing_visual_data,
    assistant_page_prompts,
    assistant_panel_prompt,
    build_gn_page_prompt_packages,
    build_gn_panel_prompt_package,
    comfyui_available,
    get_gn_style_profile,
    package_to_json,
    package_to_markdown,
    send_to_comfyui,
    set_gn_style_profile,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _gn(db):
    return db.create_project(
        "GN", narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )


def _scene(db, project_id):
    page = db.create_gn_page(project_id, emotional_beat="dread",
                             density_level="dense", reveal_type="cliffhanger")
    z = db.create_psyke_entry(project_id, "Zampano", entry_type="character")
    db.set_psyke_visual_memory(z.id, {
        "silhouette": "small fluffy Maltese", "color_identity": "white, sepia",
        "costume_state": "crusader cloak",
    })
    loc = db.create_psyke_entry(project_id, "Ruined Gate", entry_type="place")
    db.set_psyke_visual_memory(loc.id, {"architecture": "broken stone arch"})
    panel = db.create_gn_panel(
        page.id, description="Zampano at the gate", action="sniffs the air",
        shot_type="wide", camera_angle="low_angle", emotional_tone="tense",
        characters_present=["Zampano"], visual_motifs=["Ruined Gate"],
    )
    return page, panel, z, loc


# =========================================================================
# 1. Panel prompt package — content (§3, §11.1)
# =========================================================================

def test_panel_package_includes_description_and_action():
    db = Database()
    p = _gn(db)
    _page, panel, _z, _loc = _scene(db, p.id)
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert isinstance(pkg, GraphicNovelPromptPackage)
    assert "Zampano at the gate" in pkg.prompt
    assert "sniffs the air" in pkg.prompt
    assert pkg.shot_type == "wide"
    assert pkg.camera_angle == "low_angle"
    assert pkg.emotional_tone == "tense"
    assert pkg.panel_id == panel.id


def test_package_includes_psyke_character_identity():
    db = Database()
    p = _gn(db)
    _page, panel, _z, _loc = _scene(db, p.id)
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    zampano = next(c for c in pkg.characters if c["name"] == "Zampano")
    assert "small fluffy Maltese" in zampano["visual_identity"]
    assert zampano["costume_state"] == "crusader cloak"


def test_package_includes_location_design():
    db = Database()
    p = _gn(db)
    _page, panel, _z, _loc = _scene(db, p.id)
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert any("broken stone arch" in loc["design"] for loc in pkg.locations)


def test_package_includes_visual_motifs():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id, description="x", shot_type="wide",
                               camera_angle="eye_level",
                               visual_motifs=["broken halo", "muddy cross"])
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert "broken halo" in pkg.visual_motifs
    assert "muddy cross" in pkg.visual_motifs


def test_package_includes_page_context_metadata():
    db = Database()
    p = _gn(db)
    _page, panel, _z, _loc = _scene(db, p.id)
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert pkg.metadata_json["page_emotional_beat"] == "dread"
    assert pkg.metadata_json["page_density"] == "dense"
    assert pkg.metadata_json["page_reveal"] == "cliffhanger"


def test_missing_panel_returns_none():
    db = Database()
    p = _gn(db)
    assert build_gn_panel_prompt_package(db, p.id, 999) is None


# =========================================================================
# 2. Consistency guardrails -> warnings (§8, §11.4)
# =========================================================================

def test_warning_missing_character_visual_identity():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_psyke_entry(p.id, "Bob", entry_type="character")  # no visual
    panel = db.create_gn_panel(page.id, description="x", shot_type="wide",
                               camera_angle="eye_level",
                               characters_present=["Bob"])
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert any("Bob" in w and "visual identity" in w for w in pkg.warnings)


def test_warning_undefined_character():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id, description="x", shot_type="wide",
                               camera_angle="eye_level",
                               characters_present=["Ghost"])
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert any("Ghost" in w and "not defined" in w for w in pkg.warnings)


def test_warning_missing_description_and_framing():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id)  # no desc/action/shot/camera
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    msgs = " ".join(pkg.warnings).lower()
    assert "no description or action" in msgs
    assert "no shot type" in msgs
    assert "no camera angle" in msgs
    assert pkg.metadata_json["warning_count"] == len(pkg.warnings)


def test_warning_undefined_motif():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id, description="x", shot_type="wide",
                               camera_angle="eye_level",
                               visual_motifs=["mystery glyph"])
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert any("mystery glyph" in w and "not defined" in w
               for w in pkg.warnings)


def test_warning_too_many_characters():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(
        page.id, description="crowd", shot_type="wide", camera_angle="wide",
        characters_present=["A", "B", "C", "D", "E"],
    )
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert any("characters in one panel" in w for w in pkg.warnings)


def test_warnings_do_not_block_export():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id)  # maximally incomplete
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert pkg is not None             # still produced
    assert package_to_json(pkg)        # still exportable


# =========================================================================
# 3. Page prompt pack (§4, §11.5)
# =========================================================================

def test_page_pack_panels_in_order():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    a = db.create_gn_panel(page.id, description="first")
    b = db.create_gn_panel(page.id, description="second")
    c = db.create_gn_panel(page.id, description="third")
    pkgs = build_gn_page_prompt_packages(db, p.id, page.id)
    assert [pk.panel_id for pk in pkgs] == [a.id, b.id, c.id]


def test_page_pack_not_merged():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="a")
    db.create_gn_panel(page.id, description="b")
    pkgs = build_gn_page_prompt_packages(db, p.id, page.id)
    assert len(pkgs) == 2   # one package per panel, not one merged


# =========================================================================
# 4. Export formats (§5, §11.6, §11.7)
# =========================================================================

def test_json_export_is_valid():
    db = Database()
    p = _gn(db)
    _page, panel, _z, _loc = _scene(db, p.id)
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    parsed = json.loads(package_to_json(pkg))
    assert parsed["panel_id"] == panel.id
    assert parsed["prompt"]


def test_json_export_list_is_valid():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="a")
    db.create_gn_panel(page.id, description="b")
    pkgs = build_gn_page_prompt_packages(db, p.id, page.id)
    parsed = json.loads(package_to_json(pkgs))
    assert isinstance(parsed, list) and len(parsed) == 2


def test_markdown_export_includes_all_panels():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="alpha scene")
    db.create_gn_panel(page.id, description="beta scene")
    pkgs = build_gn_page_prompt_packages(db, p.id, page.id)
    md = package_to_markdown(pkgs)
    assert "alpha scene" in md
    assert "beta scene" in md
    assert md.count("Prompt:") == 2


# =========================================================================
# 5. Style profile (§7)
# =========================================================================

def test_style_profile_default_empty():
    db = Database()
    p = _gn(db)
    prof = get_gn_style_profile(db, p.id)
    assert set(prof.keys()) >= {"art_style", "aspect_ratio",
                                "negative_prompt_defaults"}
    assert prof["art_style"] == ""


def test_style_profile_persists_and_applies():
    db = Database()
    p = _gn(db)
    set_gn_style_profile(db, p.id, {
        "art_style": "noir ink", "aspect_ratio": "2:3",
        "negative_prompt_defaults": "blurry, extra fingers",
    })
    assert get_gn_style_profile(db, p.id)["art_style"] == "noir ink"
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id, description="x", shot_type="wide",
                               camera_angle="eye_level")
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    assert "noir ink" in pkg.prompt          # style folded into prompt
    assert pkg.output_preset == "2:3"
    assert pkg.negative_prompt == "blurry, extra fingers"


# =========================================================================
# 6. ComfyUI hook is a disabled stub (§9, §12)
# =========================================================================

def test_comfyui_unavailable():
    assert comfyui_available() is False


def test_send_to_comfyui_raises():
    db = Database()
    p = _gn(db)
    _page, panel, _z, _loc = _scene(db, p.id)
    pkg = build_gn_panel_prompt_package(db, p.id, panel.id)
    with pytest.raises(NotImplementedError):
        send_to_comfyui(pkg)


# =========================================================================
# 7. Assistant hooks reuse the same builder (§10, §11.9)
# =========================================================================

def test_assistant_panel_prompt_uses_builder():
    db = Database()
    p = _gn(db)
    _page, panel, _z, _loc = _scene(db, p.id)
    out = assistant_panel_prompt(db, p.id, panel.id)
    assert "Prompt:" in out
    assert "Zampano at the gate" in out


def test_assistant_page_prompts_ordered():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="one")
    db.create_gn_panel(page.id, description="two")
    out = assistant_page_prompts(db, p.id, page.id)
    assert out.index("one") < out.index("two")


def test_assistant_missing_visual_data():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    panel = db.create_gn_panel(page.id, characters_present=["Ghost"])
    out = assistant_missing_visual_data(db, p.id, panel.id)
    assert "Ghost" in out


def test_assistant_missing_data_clean_panel():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    loc = db.create_psyke_entry(p.id, "Gate", entry_type="place")
    db.set_psyke_visual_memory(loc.id, {"architecture": "stone"})
    panel = db.create_gn_panel(page.id, description="lone gate", action="wind",
                               shot_type="wide", camera_angle="low_angle",
                               visual_motifs=["Gate"])
    out = assistant_missing_visual_data(db, p.id, panel.id)
    assert "needed" in out.lower()


# =========================================================================
# 8. UI actions + engine gating (§6, §11.8)
# =========================================================================

def test_pages_view_build_and_copy():
    from PySide6.QtWidgets import QApplication
    db = Database()
    p = _gn(db)
    page, panel, _z, _loc = _scene(db, p.id)
    from logosforge.ui.graphic_novel_pages_view import GraphicNovelPagesView
    view = GraphicNovelPagesView(db, p.id)
    view.select_page(page.id)
    view.select_panel(panel.id)
    pkg = view.build_panel_prompt_package()
    assert pkg is not None and pkg.panel_id == panel.id
    view.copy_panel_prompt()
    assert "Zampano at the gate" in QApplication.clipboard().text()


def test_pages_view_page_pack():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="a")
    db.create_gn_panel(page.id, description="b")
    from logosforge.ui.graphic_novel_pages_view import GraphicNovelPagesView
    view = GraphicNovelPagesView(db, p.id)
    view.select_page(page.id)
    assert len(view.build_page_prompt_packages()) == 2


def test_non_gn_view_no_prompt_actions():
    db = Database()
    p = db.create_project("Novel")
    from logosforge.ui.graphic_novel_pages_view import GraphicNovelPagesView
    view = GraphicNovelPagesView(db, p.id)
    assert view.build_panel_prompt_package() is None
    assert view.build_page_prompt_packages() == []
    assert not hasattr(view, "_prompt_btn")
