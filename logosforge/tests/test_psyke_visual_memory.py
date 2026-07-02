"""Tests for Slice 4 — PSYKE Visual Memory (fields, appearances, UI, review)."""

import pytest

from logosforge.db import Database
from logosforge.models.psyke_details import get_visual_schema
from logosforge.psyke_visual import (
    CHARACTER_VISUAL_FIELDS,
    LOCATION_VISUAL_FIELDS,
    LORE_VISUAL_FIELDS,
    OBJECT_VISUAL_FIELDS,
    THEME_VISUAL_FIELDS,
    build_visual_memory_context,
    get_visual_appearances_for_psyke_entry,
    review_visual_memory,
    set_visual_memory,
    visual_fields_for_type,
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


# =========================================================================
# 1. Expanded visual field schemas (§2)
# =========================================================================

def test_character_has_facial_expression_range():
    assert "facial_expression_range" in CHARACTER_VISUAL_FIELDS


def test_location_has_new_fields():
    for f in ("color_palette", "recurring_camera_angles",
              "spatial_continuity_notes"):
        assert f in LOCATION_VISUAL_FIELDS


def test_object_visual_fields():
    for f in ("appearance", "scale", "owner", "continuity_state",
              "symbolic_meaning", "first_appearance", "recurring_use"):
        assert f in OBJECT_VISUAL_FIELDS


def test_theme_and_lore_visual_fields():
    for f in ("visual_manifestations", "symbolic_colors", "recurring_shapes",
              "motif_family"):
        assert f in THEME_VISUAL_FIELDS
    for f in ("visual_rules", "design_constraints", "world_style_notes"):
        assert f in LORE_VISUAL_FIELDS


def test_visual_fields_for_type_covers_all():
    assert visual_fields_for_type("object") == OBJECT_VISUAL_FIELDS
    assert visual_fields_for_type("theme") == THEME_VISUAL_FIELDS
    assert visual_fields_for_type("lore") == LORE_VISUAL_FIELDS
    assert visual_fields_for_type("other") == ()


# =========================================================================
# 2. Visual schema -> UI FieldSpecs (§3)
# =========================================================================

def test_visual_schema_for_character():
    schema = get_visual_schema("character")
    keys = [f.key for f in schema]
    assert keys == list(CHARACTER_VISUAL_FIELDS)
    assert all(f.section == "Visual Memory" for f in schema)


def test_visual_schema_empty_for_other():
    assert get_visual_schema("other") == []


# =========================================================================
# 3. Persistence through details_json (§2, §8)
# =========================================================================

def test_visual_details_save_load_roundtrip(tmp_path):
    path = str(tmp_path / "gn.db")
    db = Database(path)
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    set_visual_memory(db, e.id, silhouette="small fluffy Maltese",
                      facial_expression_range="anxious to heroic")
    eid = e.id
    db2 = Database(path)
    vm = db2.get_psyke_visual_memory(eid)
    assert vm["silhouette"] == "small fluffy Maltese"
    assert vm["facial_expression_range"] == "anxious to heroic"


def test_old_entry_without_details_json_loads():
    db = Database()
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Old", entry_type="character")
    # No visual memory ever set.
    assert db.get_psyke_visual_memory(e.id) == {}


def test_invalid_details_json_degrades_gracefully():
    db = Database()
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Broken", entry_type="character")
    # Corrupt the stored JSON directly.
    from sqlalchemy import text
    with db._engine.connect() as conn:
        conn.execute(
            text("UPDATE psykeentry SET details_json = '{not json' WHERE id = :i"),
            {"i": e.id},
        )
        conn.commit()
    assert db.get_psyke_visual_memory(e.id) == {}     # no crash
    # Setting still works (rebuilds a clean section).
    set_visual_memory(db, e.id, silhouette="ok")
    assert db.get_psyke_visual_memory(e.id)["silhouette"] == "ok"


# =========================================================================
# 4. Appearance matching (§4)
# =========================================================================

def _two_pages(db, project_id):
    page1 = db.create_gn_page(project_id)
    db.create_gn_panel(page1.id, characters_present=["Zampano"],
                       visual_motifs=["broken halo"])
    page2 = db.create_gn_page(project_id)
    db.create_gn_panel(page2.id, characters_present=["Zampano", "Villain"])
    return page1, page2


def test_character_appearances_by_name():
    db = Database()
    p = _gn(db)
    _two_pages(db, p.id)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    apps = get_visual_appearances_for_psyke_entry(db, p.id, z.id)
    assert [(a["page_number"], a["panel_number"]) for a in apps] == [(1, 1), (2, 1)]


def test_motif_appearances_by_name():
    db = Database()
    p = _gn(db)
    _two_pages(db, p.id)
    halo = db.create_psyke_entry(p.id, "Broken Halo", entry_type="theme")
    apps = get_visual_appearances_for_psyke_entry(db, p.id, halo.id)
    assert [(a["page_number"], a["panel_number"]) for a in apps] == [(1, 1)]


def test_appearance_matches_alias():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, characters_present=["Z"])
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character",
                              aliases="Z, The Dog")
    apps = get_visual_appearances_for_psyke_entry(db, p.id, z.id)
    assert len(apps) == 1


def test_no_appearances_when_unmatched():
    db = Database()
    p = _gn(db)
    _two_pages(db, p.id)
    ghost = db.create_psyke_entry(p.id, "Nobody", entry_type="character")
    assert get_visual_appearances_for_psyke_entry(db, p.id, ghost.id) == []


# =========================================================================
# 5. Assistant context includes visual memory + appearances (§5)
# =========================================================================

def test_context_includes_appearances():
    db = Database()
    p = _gn(db)
    _two_pages(db, p.id)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    set_visual_memory(db, z.id, silhouette="small fluffy Maltese",
                      color_identity="white, sepia")
    ctx = build_visual_memory_context(db, p.id)
    assert ctx.startswith("[Visual Memory]")
    assert "Zampano" in ctx
    assert "silhouette" in ctx
    assert "appears in:" in ctx
    assert "Page 1 Panel 1" in ctx


def test_focused_context_includes_appearances():
    db = Database()
    p = _gn(db)
    _two_pages(db, p.id)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    set_visual_memory(db, z.id, pose_language="anxious but heroic")
    ctx = build_visual_memory_context(db, p.id, z.id)
    assert "pose language: anxious but heroic" in ctx
    assert "appears in: Page 1 Panel 1, Page 2 Panel 1" in ctx


# =========================================================================
# 6. Review / validation helpers (§7)
# =========================================================================

def test_review_flags_missing_character_identity():
    db = Database()
    p = _gn(db)
    _two_pages(db, p.id)
    db.create_psyke_entry(p.id, "Zampano", entry_type="character")  # no visual
    types = {c.check_type for c in review_visual_memory(db, p.id)}
    assert "character_visual_missing" in types


def test_review_no_flag_when_identity_present():
    db = Database()
    p = _gn(db)
    _two_pages(db, p.id)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    set_visual_memory(db, z.id, silhouette="x")
    types = {c.check_type for c in review_visual_memory(db, p.id)}
    assert "character_visual_missing" not in types


def test_review_flags_single_use_motif():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, visual_motifs=["lonely symbol"])
    types = {c.check_type for c in review_visual_memory(db, p.id)}
    assert "motif_single_use" in types


def test_review_flags_object_without_continuity_state():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    item = db.create_gn_continuity_item(p.id, "Locket", item_type="object")
    db.add_gn_continuity_appearance(item.id, page_id=page.id,
                                    state_description="")  # blank state
    types = {c.check_type for c in review_visual_memory(db, p.id)}
    assert "object_missing_continuity_state" in types


def test_review_empty_project_safe():
    db = Database()
    p = _gn(db)
    assert review_visual_memory(db, p.id) == []


# =========================================================================
# 7. PSYKE UI integration — gated by engine (§3, §10)
# =========================================================================

def test_psyke_view_shows_visual_fields_for_gn():
    from logosforge.ui.psyke_view import PsykeView
    db = Database()
    p = _gn(db)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    view = PsykeView(db, p.id)
    assert view._gn_mode is True
    view.select_entry(z.id)
    assert "silhouette" in view._visual_widgets
    assert "facial_expression_range" in view._visual_widgets


def test_psyke_view_visual_roundtrip_through_ui():
    from logosforge.ui.psyke_view import PsykeView
    db = Database()
    p = _gn(db)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    view = PsykeView(db, p.id)
    view.select_entry(z.id)
    view._visual_widgets["silhouette"].setPlainText("small fluffy Maltese")
    view._visual_widgets["color_identity"].setPlainText("white, sepia")
    view._on_save()
    vm = db.get_psyke_visual_memory(z.id)
    assert vm["silhouette"] == "small fluffy Maltese"
    assert vm["color_identity"] == "white, sepia"
    # Standard (flat) details are untouched / coexist.
    assert "visual" in db.get_psyke_entry_details(z.id)


def test_psyke_view_clears_visual_field():
    from logosforge.ui.psyke_view import PsykeView
    db = Database()
    p = _gn(db)
    z = db.create_psyke_entry(p.id, "Zampano", entry_type="character")
    set_visual_memory(db, z.id, silhouette="temp")
    view = PsykeView(db, p.id)
    view.select_entry(z.id)
    assert view._visual_widgets["silhouette"].toPlainText() == "temp"
    view._visual_widgets["silhouette"].setPlainText("")
    view._on_save()
    assert "silhouette" not in db.get_psyke_visual_memory(z.id)


def test_psyke_view_non_gn_has_no_visual_fields():
    from logosforge.ui.psyke_view import PsykeView
    db = Database()
    p = db.create_project("Novel")
    z = db.create_psyke_entry(p.id, "Alice", entry_type="character")
    view = PsykeView(db, p.id)
    assert view._gn_mode is False
    view.select_entry(z.id)
    assert view._visual_widgets == {}
    # Saving a novel entry does not create a visual section.
    view._on_save()
    assert "visual" not in db.get_psyke_entry_details(z.id)
