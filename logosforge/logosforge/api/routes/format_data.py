"""Format-specific structured-data writers (the dormant tables the audit flagged
as having no production caller): graphic-novel pages/panels, stage entrances/cues/
business, series seasons/episodes/arcs. Thin CRUD wrappers over the existing
``db.create_*``/``db.get_*`` methods so the data the format graph-enrichers consume
can finally be created through the API (not just test fixtures).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["format-data"])


def _entry_or_404(db: Database, project_id: int, entry_id: int):
    entry = db.get_psyke_entry_by_id(entry_id)
    if entry is None or entry.project_id != project_id:
        raise not_found(f"PSYKE entry {entry_id} not found")
    return entry


def _g(o, name, default=""):
    return getattr(o, name, default) or default


def _motifs(v) -> list[str]:
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return list(v or [])


# --------------------------------------------------------------------------- #
# Graphic novel — pages + panels (pages clear the enricher's no-pages gate)
# --------------------------------------------------------------------------- #
def _gn_page_dto(p) -> schemas.GnPageDTO:
    return schemas.GnPageDTO(
        id=p.id, page_number=_g(p, "page_number", 0) or 0, summary=_g(p, "summary"),
        emotional_beat=_g(p, "emotional_beat"), density_level=_g(p, "density_level"),
        reveal_type=_g(p, "reveal_type"), splash_page=bool(getattr(p, "splash_page", False)),
        notes=_g(p, "notes"),
    )


def _gn_panel_dto(p) -> schemas.GnPanelDTO:
    return schemas.GnPanelDTO(
        id=p.id, page_id=getattr(p, "page_id", 0) or 0, panel_number=_g(p, "panel_number", 0) or 0,
        description=_g(p, "description"), shot_type=_g(p, "shot_type"), camera_angle=_g(p, "camera_angle"),
        emotional_tone=_g(p, "emotional_tone"), action=_g(p, "action"),
        visual_motifs=_motifs(getattr(p, "visual_motifs", None)), transition_type=_g(p, "transition_type"),
    )


@router.post("/projects/{project_id}/gn/pages", response_model=schemas.GnPageDTO)
def gn_page_create(body: schemas.GnPageDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    page = db.create_gn_page(
        project.id, page_number=body.page_number or None, summary=body.summary,
        emotional_beat=body.emotional_beat, density_level=body.density_level,
        reveal_type=body.reveal_type, splash_page=body.splash_page, notes=body.notes,
    )
    broker.publish("project_data_changed", project_id=project.id)
    return _gn_page_dto(page)


@router.get("/projects/{project_id}/gn/pages", response_model=list[schemas.GnPageDTO])
def gn_pages_list(project=Depends(get_project), db: Database = Depends(get_db)):
    return [_gn_page_dto(p) for p in db.get_gn_pages(project.id)]


@router.post("/projects/{project_id}/gn/pages/{page_id}/panels", response_model=schemas.GnPanelDTO)
def gn_panel_create(page_id: int, body: schemas.GnPanelDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    panel = db.create_gn_panel(
        page_id, project_id=project.id, panel_number=body.panel_number or None,
        description=body.description, camera_angle=body.camera_angle, shot_type=body.shot_type,
        emotional_tone=body.emotional_tone, action=body.action,
        visual_motifs=body.visual_motifs, transition_type=body.transition_type,
    )
    broker.publish("project_data_changed", project_id=project.id)
    return _gn_panel_dto(panel)


@router.get("/projects/{project_id}/gn/pages/{page_id}/panels", response_model=list[schemas.GnPanelDTO])
def gn_panels_list(page_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    return [_gn_panel_dto(p) for p in db.get_gn_panels_for_page(page_id)]


def _gn_item_dto(r) -> schemas.GnContinuityItemDTO:
    return schemas.GnContinuityItemDTO(id=r.id, name=_g(r, "name"), item_type=_g(r, "item_type", "other"),
        description=_g(r, "description"), linked_psyke_entry_id=getattr(r, "linked_psyke_entry_id", None), notes=_g(r, "notes"))


def _gn_appearance_dto(r) -> schemas.GnContinuityAppearanceDTO:
    return schemas.GnContinuityAppearanceDTO(id=r.id, continuity_item_id=getattr(r, "continuity_item_id", 0) or 0,
        page_id=getattr(r, "page_id", None), panel_id=getattr(r, "panel_id", None),
        state_description=_g(r, "state_description"), continuity_status=_g(r, "continuity_status", "consistent"))


@router.post("/projects/{project_id}/gn/continuity-items", response_model=schemas.GnContinuityItemDTO)
def gn_continuity_item_create(body: schemas.GnContinuityItemDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    row = db.create_gn_continuity_item(project.id, body.name, item_type=body.item_type,
        description=body.description, linked_psyke_entry_id=body.linked_psyke_entry_id, notes=body.notes)
    broker.publish("project_data_changed", project_id=project.id)
    return _gn_item_dto(row)


@router.get("/projects/{project_id}/gn/continuity-items", response_model=list[schemas.GnContinuityItemDTO])
def gn_continuity_items_list(project=Depends(get_project), db: Database = Depends(get_db)):
    return [_gn_item_dto(r) for r in db.get_gn_continuity_items(project.id)]


@router.post("/projects/{project_id}/gn/continuity-items/{item_id}/appearances", response_model=schemas.GnContinuityAppearanceDTO)
def gn_continuity_appearance_create(item_id: int, body: schemas.GnContinuityAppearanceDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    row = db.add_gn_continuity_appearance(item_id, page_id=body.page_id, panel_id=body.panel_id,
        state_description=body.state_description, continuity_status=body.continuity_status)
    broker.publish("project_data_changed", project_id=project.id)
    return _gn_appearance_dto(row)


@router.get("/projects/{project_id}/gn/continuity-items/{item_id}/appearances", response_model=list[schemas.GnContinuityAppearanceDTO])
def gn_continuity_appearances_list(item_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    return [_gn_appearance_dto(r) for r in db.get_gn_continuity_appearances(item_id)]


@router.post("/projects/{project_id}/gn/sync-from-scenes", response_model=schemas.GnSyncResultDTO)
def gn_sync_from_scenes(project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker), replace: bool = False):
    """Persist each scene's GN-script body (PAGE/PANEL text) into structured page/panel
    rows so the GN graph enricher has input. Skips if pages already exist (unless
    ``replace``). This is the bridge from authored prose to the format graph."""
    from logosforge import gn_structure_sync
    result = gn_structure_sync.sync_gn_pages_from_scenes(db, project.id, replace=replace)
    broker.publish("project_data_changed", project_id=project.id)
    return schemas.GnSyncResultDTO(**result)


# --------------------------------------------------------------------------- #
# Stage — entrances/exits, cues, business (per scene)
# --------------------------------------------------------------------------- #
def _ee_dto(r) -> schemas.StageEntranceExitDTO:
    return schemas.StageEntranceExitDTO(id=r.id, scene_id=getattr(r, "scene_id", 0) or 0,
        character_id=getattr(r, "character_id", None), type=_g(r, "type", "entrance"),
        moment_order=getattr(r, "moment_order", None), cue_text=_g(r, "cue_text"), notes=_g(r, "notes"))


def _cue_dto(r) -> schemas.StageCueDTO:
    return schemas.StageCueDTO(id=r.id, scene_id=getattr(r, "scene_id", 0) or 0,
        cue_type=_g(r, "cue_type", "other"), moment_order=getattr(r, "moment_order", None),
        cue_text=_g(r, "cue_text"), notes=_g(r, "notes"))


def _biz_dto(r) -> schemas.StageBusinessDTO:
    return schemas.StageBusinessDTO(id=r.id, scene_id=getattr(r, "scene_id", 0) or 0,
        prop_psyke_entry_id=getattr(r, "prop_psyke_entry_id", None), character_id=getattr(r, "character_id", None),
        stage_action=_g(r, "stage_action"), continuity_note=_g(r, "continuity_note"),
        moment_order=getattr(r, "moment_order", None))


@router.post("/projects/{project_id}/stage/scenes/{scene_id}/entrances", response_model=schemas.StageEntranceExitDTO)
def stage_entrance_create(scene_id: int, body: schemas.StageEntranceExitDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    row = db.create_stage_entrance_exit(scene_id, character_id=body.character_id, type=body.type,
        moment_order=body.moment_order, cue_text=body.cue_text, notes=body.notes)
    broker.publish("scenes_changed", project_id=project.id)
    return _ee_dto(row)


@router.get("/projects/{project_id}/stage/scenes/{scene_id}/entrances", response_model=list[schemas.StageEntranceExitDTO])
def stage_entrances_list(scene_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    return [_ee_dto(r) for r in db.get_stage_entrances_exits(scene_id)]


@router.post("/projects/{project_id}/stage/scenes/{scene_id}/cues", response_model=schemas.StageCueDTO)
def stage_cue_create(scene_id: int, body: schemas.StageCueDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    row = db.create_stage_cue(scene_id, cue_type=body.cue_type, moment_order=body.moment_order,
        cue_text=body.cue_text, notes=body.notes)
    broker.publish("scenes_changed", project_id=project.id)
    return _cue_dto(row)


@router.get("/projects/{project_id}/stage/scenes/{scene_id}/cues", response_model=list[schemas.StageCueDTO])
def stage_cues_list(scene_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    return [_cue_dto(r) for r in db.get_stage_cues(scene_id)]


@router.post("/projects/{project_id}/stage/scenes/{scene_id}/business", response_model=schemas.StageBusinessDTO)
def stage_business_create(scene_id: int, body: schemas.StageBusinessDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    row = db.create_stage_business(scene_id, prop_psyke_entry_id=body.prop_psyke_entry_id,
        character_id=body.character_id, stage_action=body.stage_action,
        continuity_note=body.continuity_note, moment_order=body.moment_order)
    broker.publish("scenes_changed", project_id=project.id)
    return _biz_dto(row)


@router.get("/projects/{project_id}/stage/scenes/{scene_id}/business", response_model=list[schemas.StageBusinessDTO])
def stage_business_list(scene_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    return [_biz_dto(r) for r in db.get_stage_business(scene_id)]


@router.post("/projects/{project_id}/stage/sync-from-scenes", response_model=schemas.StageSyncResultDTO)
def stage_sync_from_scenes(project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker), replace: bool = False):
    """Parse each scene's stage directions (enter/exit, cues, offstage) into structured
    rows the stage graph enricher reads — the deterministic bridge from prose to graph."""
    from logosforge import stage_structure_sync
    result = stage_structure_sync.sync_stage_structure_from_scenes(db, project.id, replace=replace)
    broker.publish("scenes_changed", project_id=project.id)
    return schemas.StageSyncResultDTO(**result)


# --------------------------------------------------------------------------- #
# Series — seasons, episodes (episodes clear the enricher gate), arcs
# --------------------------------------------------------------------------- #
def _season_dto(s) -> schemas.SeasonDTO:
    return schemas.SeasonDTO(id=s.id, season_number=_g(s, "season_number", 0) or 0, title=_g(s, "title"),
        summary=_g(s, "summary"), central_question=_g(s, "central_question"),
        finale_payoff=_g(s, "finale_payoff"), status=_g(s, "status"))


def _episode_dto(e) -> schemas.EpisodeDTO:
    return schemas.EpisodeDTO(id=e.id, season_id=getattr(e, "season_id", 0) or 0,
        episode_number=_g(e, "episode_number", 0) or 0, title=_g(e, "title"), logline=_g(e, "logline"),
        summary=_g(e, "summary"), cliffhanger=_g(e, "cliffhanger"), status=_g(e, "status"))


def _arc_dto(a) -> schemas.SeriesArcDTO:
    return schemas.SeriesArcDTO(id=a.id, scope=_g(a, "scope", "series"), title=_g(a, "title"),
        summary=_g(a, "summary"), setup_episode_id=getattr(a, "setup_episode_id", None),
        payoff_episode_id=getattr(a, "payoff_episode_id", None), status=_g(a, "status", "active"),
        notes=_g(a, "notes"))


@router.post("/projects/{project_id}/series/seasons", response_model=schemas.SeasonDTO)
def season_create(body: schemas.SeasonDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    s = db.create_season(project.id, season_number=body.season_number or None, title=body.title,
        summary=body.summary, central_question=body.central_question, finale_payoff=body.finale_payoff, status=body.status)
    broker.publish("project_data_changed", project_id=project.id)
    return _season_dto(s)


@router.get("/projects/{project_id}/series/seasons", response_model=list[schemas.SeasonDTO])
def seasons_list(project=Depends(get_project), db: Database = Depends(get_db)):
    return [_season_dto(s) for s in db.get_seasons(project.id)]


@router.post("/projects/{project_id}/series/seasons/{season_id}/episodes", response_model=schemas.EpisodeDTO)
def episode_create(season_id: int, body: schemas.EpisodeDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    e = db.create_episode(season_id, project_id=project.id, episode_number=body.episode_number or None,
        title=body.title, logline=body.logline, summary=body.summary, cliffhanger=body.cliffhanger, status=body.status)
    broker.publish("project_data_changed", project_id=project.id)
    return _episode_dto(e)


@router.get("/projects/{project_id}/series/episodes", response_model=list[schemas.EpisodeDTO])
def episodes_list(project=Depends(get_project), db: Database = Depends(get_db)):
    return [_episode_dto(e) for e in db.get_episodes(project.id)]


@router.post("/projects/{project_id}/series/arcs", response_model=schemas.SeriesArcDTO)
def arc_create(body: schemas.SeriesArcDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    a = db.create_series_arc(project.id, scope=body.scope, title=body.title, summary=body.summary,
        setup_episode_id=body.setup_episode_id, payoff_episode_id=body.payoff_episode_id,
        status=body.status, notes=body.notes)
    broker.publish("project_data_changed", project_id=project.id)
    return _arc_dto(a)


@router.get("/projects/{project_id}/series/arcs", response_model=list[schemas.SeriesArcDTO])
def arcs_list(project=Depends(get_project), db: Database = Depends(get_db)):
    return [_arc_dto(a) for a in db.get_series_arcs(project.id)]


def _plotline_dto(p) -> schemas.EpisodePlotlineDTO:
    return schemas.EpisodePlotlineDTO(id=p.id, episode_id=getattr(p, "episode_id", 0) or 0,
        type=_g(p, "type", "A"), title=_g(p, "title"), summary=_g(p, "summary"),
        resolution_state=_g(p, "resolution_state"))


@router.post("/projects/{project_id}/series/episodes/{episode_id}/plotlines", response_model=schemas.EpisodePlotlineDTO)
def episode_plotline_create(episode_id: int, body: schemas.EpisodePlotlineDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    row = db.create_episode_plotline(episode_id, type=body.type or "A", title=body.title,
        summary=body.summary, resolution_state=body.resolution_state)
    broker.publish("project_data_changed", project_id=project.id)
    return _plotline_dto(row)


@router.get("/projects/{project_id}/series/episodes/{episode_id}/plotlines", response_model=list[schemas.EpisodePlotlineDTO])
def episode_plotlines_list(episode_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    return [_plotline_dto(p) for p in db.get_episode_plotlines(episode_id)]


@router.get("/projects/{project_id}/psyke/{entry_id}/series-memory", response_model=schemas.SeriesMemoryDTO)
def psyke_series_memory_get(entry_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    _entry_or_404(db, project.id, entry_id)
    mem = db.get_psyke_series_memory(entry_id) or {}
    csbe = mem.get("current_status_by_episode")
    if not isinstance(csbe, dict):  # the series section is a shared bag — tolerate junk
        csbe = {}
    return schemas.SeriesMemoryDTO(entry_id=entry_id, continuity_flags=str(mem.get("continuity_flags") or ""),
        current_status_by_episode={str(k): str(v) for k, v in csbe.items()})


@router.put("/projects/{project_id}/psyke/{entry_id}/series-memory", response_model=schemas.SeriesMemoryDTO)
def psyke_series_memory_set(entry_id: int, body: schemas.SeriesMemoryDTO, project=Depends(get_project), db: Database = Depends(get_db), broker: ApiEventBroker = Depends(get_broker)):
    """Merge a PSYKE character's series memory (per-episode status + continuity flags) —
    the writer for the series graph's character->episode echo / contradict edges."""
    _entry_or_404(db, project.id, entry_id)
    from logosforge import psyke_series
    psyke_series.set_series_memory(db, entry_id,
        continuity_flags=body.continuity_flags,
        current_status_by_episode=dict(body.current_status_by_episode or {}))
    broker.publish("psyke_changed", project_id=project.id)
    return psyke_series_memory_get(entry_id, project=project, db=db)
