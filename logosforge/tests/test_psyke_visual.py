"""Tests for the PSYKE visual-memory layer (Graphic Novel Engine)."""

import pytest

from logosforge.db import Database
from logosforge.psyke_visual import (
    CHARACTER_VISUAL_FIELDS,
    LOCATION_VISUAL_FIELDS,
    MOTIF_KINDS,
    build_visual_memory_context,
    get_motif_recurrences,
    get_object_reappearances,
    get_visual_callbacks,
    get_visual_memory,
    set_visual_memory,
    visual_fields_for_type,
)


def _gn(db):
    return db.create_project(
        "GN", narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )


# =========================================================================
# 1. Field schemas (§1, §2, §3)
# =========================================================================

def test_character_visual_fields():
    for f in (
        "silhouette", "shape_language", "color_identity", "costume_state",
        "pose_language", "gesture_vocabulary", "visual_symbolism",
    ):
        assert f in CHARACTER_VISUAL_FIELDS


def test_location_visual_fields():
    for f in ("architecture", "lighting_mood", "environmental_motifs",
              "recurring_objects"):
        assert f in LOCATION_VISUAL_FIELDS


def test_motif_kinds():
    for k in ("symbol", "object", "color", "pose", "framing", "composition"):
        assert k in MOTIF_KINDS


def test_visual_fields_for_type():
    assert visual_fields_for_type("character") == CHARACTER_VISUAL_FIELDS
    assert visual_fields_for_type("place") == LOCATION_VISUAL_FIELDS
    # Slice 4 added object/theme/lore visual field sets.
    from logosforge.psyke_visual import (
        LORE_VISUAL_FIELDS,
        OBJECT_VISUAL_FIELDS,
        THEME_VISUAL_FIELDS,
    )
    assert visual_fields_for_type("object") == OBJECT_VISUAL_FIELDS
    assert visual_fields_for_type("theme") == THEME_VISUAL_FIELDS
    assert visual_fields_for_type("lore") == LORE_VISUAL_FIELDS
    assert visual_fields_for_type("other") == ()


# =========================================================================
# 2. Visual memory persists + merges (§1) and reloads (§6)
# =========================================================================

def test_set_and_get_visual_memory():
    db = Database()
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Alice", entry_type="character")
    set_visual_memory(db, e.id, silhouette="tall, angular",
                       color_identity="cold blue")
    vm = get_visual_memory(db, e.id)
    assert vm["silhouette"] == "tall, angular"
    assert vm["color_identity"] == "cold blue"


def test_visual_memory_merges_without_clobbering():
    db = Database()
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Alice", entry_type="character")
    set_visual_memory(db, e.id, silhouette="tall")
    set_visual_memory(db, e.id, color_identity="blue")
    vm = get_visual_memory(db, e.id)
    assert vm["silhouette"] == "tall"        # preserved
    assert vm["color_identity"] == "blue"    # added


def test_visual_memory_does_not_clobber_other_details():
    db = Database()
    p = _gn(db)
    e = db.create_psyke_entry(
        p.id, "Alice", entry_type="character", details={"role": "protagonist"},
    )
    set_visual_memory(db, e.id, silhouette="tall")
    details = db.get_psyke_entry_details(e.id)
    assert details["role"] == "protagonist"      # untouched
    assert details["visual"]["silhouette"] == "tall"


def test_empty_value_clears_visual_key():
    db = Database()
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Alice", entry_type="character")
    set_visual_memory(db, e.id, silhouette="tall")
    set_visual_memory(db, e.id, silhouette="")
    assert "silhouette" not in get_visual_memory(db, e.id)


def test_location_visual_memory():
    db = Database()
    p = _gn(db)
    loc = db.create_psyke_entry(p.id, "Precinct", entry_type="place")
    set_visual_memory(db, loc.id, architecture="brutalist",
                      lighting_mood="fluorescent dread")
    vm = get_visual_memory(db, loc.id)
    assert vm["architecture"] == "brutalist"
    assert vm["lighting_mood"] == "fluorescent dread"


def test_visual_memory_reloads_from_disk(tmp_path):
    path = str(tmp_path / "gn.db")
    db = Database(path)
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Alice", entry_type="character")
    set_visual_memory(db, e.id, color_identity="amber", costume_state="cloak")
    eid = e.id

    db2 = Database(path)
    vm = get_visual_memory(db2, eid)
    assert vm["color_identity"] == "amber"
    assert vm["costume_state"] == "cloak"


# =========================================================================
# 3. Motif tracking + panel context (§3, §4)
# =========================================================================

def _seq_page_with_motifs(db, project_id):
    seq = db.create_gn_sequence(project_id, title="S")
    page = db.create_gn_page(project_id, sequence_id=seq.id)
    db.create_gn_panel(page.id, visual_motifs=["rain", "locket"])
    db.create_gn_panel(page.id, visual_motifs=["rain"])
    db.create_gn_panel(page.id, visual_motifs=["mirror"])
    return page


def test_motif_recurrences():
    db = Database()
    p = _gn(db)
    _seq_page_with_motifs(db, p.id)
    rec = get_motif_recurrences(db, p.id)
    assert len(rec["rain"]) == 2     # appears in two panels
    assert len(rec["locket"]) == 1
    assert len(rec["mirror"]) == 1


def test_visual_callbacks_are_recurring_only():
    db = Database()
    p = _gn(db)
    _seq_page_with_motifs(db, p.id)
    callbacks = get_visual_callbacks(db, p.id)
    assert "rain" in callbacks       # 2+ panels
    assert "locket" not in callbacks  # only once
    assert "mirror" not in callbacks


def test_object_reappearances():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    pan = db.create_gn_panel(page.id)
    item = db.create_gn_continuity_item(p.id, "Locket", item_type="object")
    db.add_gn_continuity_appearance(item.id, panel_id=pan.id,
                                    state_description="whole")
    db.add_gn_continuity_appearance(item.id, page_id=page.id,
                                    state_description="cracked",
                                    continuity_status="changed")
    objs = get_object_reappearances(db, p.id)
    assert "Locket" in objs
    assert [a["status"] for a in objs["Locket"]] == ["consistent", "changed"]


# =========================================================================
# 4. Assistant-facing context (§5, §6)
# =========================================================================

def test_build_context_summary():
    db = Database()
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Alice", entry_type="character")
    set_visual_memory(db, e.id, silhouette="tall", color_identity="blue")
    _seq_page_with_motifs(db, p.id)
    ctx = build_visual_memory_context(db, p.id)
    assert ctx.startswith("[Visual Memory]")
    assert "Alice" in ctx
    assert "silhouette" in ctx
    assert "rain" in ctx  # recurring motif surfaced


def test_build_context_for_entry():
    db = Database()
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Alice", entry_type="character")
    set_visual_memory(db, e.id, shape_language="sharp triangles")
    ctx = build_visual_memory_context(db, p.id, e.id)
    assert "Alice" in ctx
    assert "shape language" in ctx
    assert "sharp triangles" in ctx


def test_build_context_empty_is_blank():
    db = Database()
    p = _gn(db)
    assert build_visual_memory_context(db, p.id) == ""


def test_empty_project_does_not_crash():
    db = Database()
    p = db.create_project("Empty")
    assert build_visual_memory_context(db, p.id) == ""
    assert get_motif_recurrences(db, p.id) == {}
    assert get_object_reappearances(db, p.id) == {}


# =========================================================================
# 5. Assistant sees the visual metadata (§6)
# =========================================================================

class _SettingsIsolation:
    pass


@pytest.fixture
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def test_assistant_context_includes_visual_memory(_isolated_settings):
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = _gn(db)
    e = db.create_psyke_entry(p.id, "Alice", entry_type="character")
    set_visual_memory(db, e.id, silhouette="tall, angular")
    db.create_scene(p.id, "PAGE ONE", content="x")

    panel = AssistantPanel(db, p.id)
    ctx = panel._build_context()
    structural = ctx[8]  # structural_ctx slot
    assert "[Visual Memory]" in structural
    assert "Alice" in structural
    assert "silhouette" in structural


def test_novel_project_has_no_visual_memory_context(_isolated_settings):
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = db.create_project("Novel")  # novel engine
    e = db.create_psyke_entry(p.id, "Alice", entry_type="character")
    set_visual_memory(db, e.id, silhouette="tall")
    db.create_scene(p.id, "Chapter 1", content="x")

    panel = AssistantPanel(db, p.id)
    ctx = panel._build_context()
    assert "[Visual Memory]" not in ctx[8]
