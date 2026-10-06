"""Map internal ORM objects onto the stable DTOs.

Keeping the ORM→DTO mapping in one place means routes never leak SQLModel
objects, and the wire contract stays decoupled from the database schema.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from logosforge.api import schemas
from logosforge.comment_revision import comment_revision
from logosforge.db import (
    CanvasPlotReadSnapshot,
    Database,
    ManuscriptReadSnapshot,
    StoryStructureReadSnapshot,
    TimelineReadSnapshot,
)


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


def _local_scene_id(
    db: Database, project_id: int, scene_id: int | None,
) -> int | None:
    if scene_id is None:
        return None
    scene = db.get_scene_by_id(scene_id)
    return scene_id if scene is not None and scene.project_id == project_id else None


# -- Projects ----------------------------------------------------------------


def project_to_dto(project) -> schemas.ProjectDTO:
    from logosforge.project_compat import (
        get_project_narrative_engine,
        get_project_writing_format,
    )

    return schemas.ProjectDTO(
        id=project.id,
        title=project.title,
        description=project.description or "",
        narrative_engine=get_project_narrative_engine(project),
        default_writing_format=get_project_writing_format(project),
        format_mode=(project.format_mode or "novel"),
    )


# -- Scenes ------------------------------------------------------------------


def scene_revision(
    db: Database,
    scene,
    *,
    character_ids: list[int] | tuple[int, ...] | None = None,
    place_ids: list[int] | tuple[int, ...] | None = None,
    character_states: list[tuple[int, str]] | tuple[tuple[int, str], ...] | None = None,
) -> str:
    """Content-addressed revision for optimistic Scene updates.

    It is deliberately derived rather than stored, so existing databases need
    no migration. All scalar Scene columns and the associations replaced by
    ``update_scene`` participate in the token.
    """
    if character_ids is None:
        character_ids = db.get_scene_character_ids(scene.id)
    if place_ids is None:
        place_ids = db.get_scene_place_ids(scene.id)
    if character_states is None:
        character_states = db.get_scene_character_states(scene.id)
    payload = {
        "scene": scene.model_dump(),
        "character_ids": sorted(int(value) for value in character_ids),
        "place_ids": sorted(int(value) for value in place_ids),
        "character_states": sorted(
            (int(character_id), str(state))
            for character_id, state in character_states
        ),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scene_to_dto(
    db: Database,
    scene,
    order_index: int = 0,
    *,
    valid_character_ids: set[int] | frozenset[int] | None = None,
    valid_place_ids: set[int] | frozenset[int] | None = None,
    character_ids: list[int] | tuple[int, ...] | None = None,
    place_ids: list[int] | tuple[int, ...] | None = None,
    character_states: list[tuple[int, str]] | tuple[tuple[int, str], ...] | None = None,
) -> schemas.SceneDTO:
    if valid_character_ids is None:
        valid_character_ids = {
            character.id for character in db.get_all_characters(scene.project_id)
        }
    if valid_place_ids is None:
        valid_place_ids = {place.id for place in db.get_all_places(scene.project_id)}
    if character_ids is None:
        character_ids = db.get_scene_character_ids(scene.id)
    if place_ids is None:
        place_ids = db.get_scene_place_ids(scene.id)
    character_ids = [
        character_id
        for character_id in character_ids
        if character_id in valid_character_ids
    ]
    place_ids = [
        place_id
        for place_id in place_ids
        if place_id in valid_place_ids
    ]
    return schemas.SceneDTO(
        id=scene.id,
        title=scene.title,
        summary=scene.summary or "",
        synopsis=scene.synopsis or "",
        goal=scene.goal or "",
        conflict=scene.conflict or "",
        outcome=scene.outcome or "",
        beat=scene.beat or "",
        act=scene.act or "",
        chapter=scene.chapter or "",
        plotline=scene.plotline or "",
        color_label=scene.color_label or "",
        tags=_split_csv(scene.tags),
        content=scene.content or "",
        sort_order=scene.sort_order or 0,
        order_index=order_index,
        character_ids=character_ids,
        place_ids=place_ids,
        who_knows_what=getattr(scene, "who_knows_what", "") or "",
        revision=scene_revision(
            db,
            scene,
            character_ids=character_ids,
            place_ids=place_ids,
            character_states=character_states,
        ),
    )


def scenes_to_dtos(db: Database, scenes) -> list[schemas.SceneDTO]:
    scenes = list(scenes)
    if not scenes:
        return []
    project_id = scenes[0].project_id
    valid_character_ids = {
        character.id for character in db.get_all_characters(project_id)
    }
    valid_place_ids = {place.id for place in db.get_all_places(project_id)}
    return [
        scene_to_dto(
            db, scene, index + 1,
            valid_character_ids=valid_character_ids,
            valid_place_ids=valid_place_ids,
        )
        for index, scene in enumerate(scenes)
    ]


def manuscript_snapshot_to_dto(
    db: Database, snapshot: ManuscriptReadSnapshot,
) -> schemas.ManuscriptSnapshotDTO:
    """Serialize one transactional manuscript read without further queries."""
    from logosforge import story_structure
    from logosforge.project_compat import get_project_narrative_engine

    tree = story_structure.build_structure_tree_from_scenes(snapshot.scenes)
    ordered_scenes = [
        scene
        for _act_name, chapter_rows in tree
        for _chapter_name, scene_rows in chapter_rows
        for scene in scene_rows
    ]
    scene_dtos = [
        scene_to_dto(
            db,
            scene,
            index + 1,
            valid_character_ids=snapshot.valid_character_ids,
            valid_place_ids=snapshot.valid_place_ids,
            character_ids=snapshot.character_ids_by_scene.get(scene.id, ()),
            place_ids=snapshot.place_ids_by_scene.get(scene.id, ()),
            character_states=snapshot.character_states_by_scene.get(scene.id, ()),
        )
        for index, scene in enumerate(ordered_scenes)
    ]
    mode = get_project_narrative_engine(snapshot.project)
    chapter_level = mode == "novel"
    requires_chapter = mode in {"novel", "series"}
    return schemas.ManuscriptSnapshotDTO(
        project_id=snapshot.project.id,
        chapter_level=chapter_level,
        scene_count=len(scene_dtos),
        orphan_count=sum(
            1 for scene in ordered_scenes
            if story_structure.is_orphan_scene(scene, requires_chapter)
        ),
        scenes=scene_dtos,
    )


# -- Canonical story structure ----------------------------------------------


def story_structure_to_dto(
    db: Database, project_id: int,
) -> schemas.StoryStructureDTO:
    """Serialize the core-owned Act -> Chapter -> Scene projection.

    The nested array order and structural numbers come exclusively from
    :mod:`logosforge.story_structure`.  This intentionally returns compact
    scene references rather than ``SceneDTO`` records so navigation reads do
    not transfer manuscript prose or optimistic-concurrency revisions.
    """
    snapshot = db.read_story_structure_snapshot(project_id)
    if snapshot is None:
        raise ValueError(f"Project {project_id} not found")
    return story_structure_snapshot_to_dto(snapshot)


def story_structure_snapshot_to_dto(
    snapshot: StoryStructureReadSnapshot,
) -> schemas.StoryStructureDTO:
    """Serialize only values captured by one structure transaction."""
    from logosforge import story_structure
    from logosforge.project_compat import get_project_narrative_engine

    tree = story_structure.build_structure_tree_from_scenes(snapshot.scenes)
    mode = get_project_narrative_engine(snapshot.project)
    chapter_level = mode == "novel"
    requires_chapter = mode in {"novel", "series"}
    numbers = story_structure.compute_structural_numbers(tree, chapter_level)
    acts: list[schemas.StoryStructureActDTO] = []
    order_index = 0
    orphan_count = 0

    for act_name, chapter_rows in tree:
        chapters: list[schemas.StoryStructureChapterDTO] = []
        act_scene_count = 0
        for chapter_name, scene_rows in chapter_rows:
            scenes: list[schemas.StoryStructureSceneDTO] = []
            for scene in scene_rows:
                order_index += 1
                orphan = story_structure.is_orphan_scene(scene, requires_chapter)
                if orphan:
                    orphan_count += 1
                scenes.append(schemas.StoryStructureSceneDTO(
                    id=scene.id,
                    title=scene.title or "",
                    beat=scene.beat or "",
                    number=numbers["scenes"].get(scene.id, ""),
                    order_index=order_index,
                    is_orphan=orphan,
                    episode_id=getattr(scene, "episode_id", None),
                ))
            act_scene_count += len(scenes)
            chapters.append(schemas.StoryStructureChapterDTO(
                name=chapter_name,
                number=numbers["chapters"].get((act_name, chapter_name), ""),
                unassigned=(chapter_name == story_structure.UNASSIGNED_CHAPTER),
                scene_count=len(scenes),
                scenes=scenes,
            ))
        acts.append(schemas.StoryStructureActDTO(
            name=act_name,
            number=numbers["acts"].get(act_name, ""),
            unassigned=(act_name == story_structure.UNASSIGNED_ACT),
            scene_count=act_scene_count,
            chapters=chapters,
        ))

    return schemas.StoryStructureDTO(
        project_id=snapshot.project.id,
        revision=snapshot.revision,
        chapter_level=chapter_level,
        scene_count=order_index,
        orphan_count=orphan_count,
        acts=acts,
    )


# -- Outline -----------------------------------------------------------------


def outline_tree(db: Database, project_id: int) -> list[schemas.OutlineNodeDTO]:
    nodes = db.get_outline_nodes(project_id)
    node_ids = {node.id for node in nodes}
    scene_ids = {scene.id for scene in db.get_all_scenes(project_id)}
    children_map: dict[int | None, list] = {}
    for node in nodes:
        parent_id = node.parent_id if node.parent_id in node_ids and node.parent_id != node.id else None
        children_map.setdefault(parent_id, []).append(node)

    def build(parent_id: int | None) -> list[schemas.OutlineNodeDTO]:
        kids = children_map.get(parent_id, [])
        kids.sort(key=lambda n: (n.sort_order, n.id or 0))
        return [
            schemas.OutlineNodeDTO(
                id=n.id,
                parent_id=(n.parent_id if n.parent_id in node_ids and n.parent_id != n.id else None),
                title=n.title,
                description=n.description or "",
                sort_order=n.sort_order or 0,
                scene_id=(n.scene_id if n.scene_id in scene_ids else None),
                children=build(n.id),
            )
            for n in kids
        ]

    return build(None)


def outline_node_to_dto(db: Database, node) -> schemas.OutlineNodeDTO:
    parent = db.get_outline_node_by_id(node.parent_id) if node.parent_id is not None else None
    return schemas.OutlineNodeDTO(
        id=node.id,
        parent_id=(node.parent_id if parent is not None and parent.project_id == node.project_id else None),
        title=node.title,
        description=node.description or "",
        sort_order=node.sort_order or 0,
        scene_id=_local_scene_id(db, node.project_id, node.scene_id),
        children=[],
    )


# -- Plot --------------------------------------------------------------------


def plot_blocks(db: Database, project_id: int) -> list[schemas.PlotBlockDTO]:
    scenes = db.get_all_scenes(project_id)
    blocks: dict[str, list] = {}
    order: list[str] = []
    for scene in scenes:
        plotline = (scene.plotline or "").strip() or "Unassigned"
        if plotline not in blocks:
            blocks[plotline] = []
            order.append(plotline)
        blocks[plotline].append(
            schemas.PlotSceneDTO(
                scene_id=scene.id,
                title=scene.title,
                act=scene.act or "",
                summary=scene.summary or "",
                beat=scene.beat or "",
                color_label=scene.color_label or "",
                order_index=scene.sort_order or 0,
            )
        )
    return [
        schemas.PlotBlockDTO(id=name, plotline=name, scenes=blocks[name])
        for name in order
    ]


# -- Canvas Plot -------------------------------------------------------------


def canvas_plot_snapshot_to_dto(
    snapshot: CanvasPlotReadSnapshot,
) -> schemas.CanvasPlotSnapshotDTO:
    """Serialize the isolated board projection captured by one atomic read."""
    return schemas.CanvasPlotSnapshotDTO(
        project_id=int(snapshot.project.id),
        revision=snapshot.revision,
        nodes=[
            schemas.CanvasPlotNodeDTO(
                id=int(node.id),
                title=node.title or "",
                body=node.body or "",
                x=float(node.x),
                y=float(node.y),
                width=float(node.width),
                height=float(node.height),
                color_label=node.color_label or "",
                group_label=node.group_label or "",
                scene_id=(
                    int(node.scene_id)
                    if node.scene_id is not None
                    and int(node.scene_id) in snapshot.valid_scene_ids
                    else None
                ),
                sort_order=int(node.sort_order or 0),
                created_at=node.created_at,
            )
            for node in snapshot.nodes
        ],
        links=[
            schemas.CanvasPlotLinkDTO(
                id=int(link.id),
                source_node_id=int(link.source_node_id),
                target_node_id=int(link.target_node_id),
                label=link.label or "",
                color_label=link.color_label or "gray",
                link_type=link.link_type or "",
                created_at=link.created_at,
            )
            for link in snapshot.links
        ],
        frames=[
            schemas.CanvasPlotFrameDTO(
                id=int(frame.id),
                title=frame.title or "",
                color_label=frame.color_label or "",
                x=float(frame.x),
                y=float(frame.y),
                width=float(frame.width),
                height=float(frame.height),
                created_at=frame.created_at,
            )
            for frame in snapshot.frames
        ],
    )


# -- Timeline ----------------------------------------------------------------


def timeline_snapshot_to_dto(
    snapshot: TimelineReadSnapshot,
) -> schemas.TimelineSnapshotDTO:
    """Serialize only values captured by one atomic Timeline read."""
    from logosforge import story_structure
    from logosforge.project_compat import get_project_narrative_engine
    from logosforge.timeline import project_timeline

    projection = project_timeline(snapshot.scenes, snapshot.settings)
    scene_by_id = {int(scene.id): scene for scene in snapshot.scenes}
    tree = story_structure.build_structure_tree_from_scenes(snapshot.scenes)
    chapter_level = get_project_narrative_engine(snapshot.project) == "novel"
    numbers = story_structure.compute_structural_numbers(tree, chapter_level)["scenes"]

    lane_by_name: dict[str, object] = {}
    for lane in snapshot.lanes:
        lane_by_name.setdefault(lane.name or "", lane)
    event_set = set(projection.event_ids)
    event_count_by_lane: dict[int, int] = {}
    for scene_id in event_set:
        scene = scene_by_id[scene_id]
        lane = lane_by_name.get((scene.plotline or "").strip())
        if lane is not None:
            event_count_by_lane[int(lane.id)] = (
                event_count_by_lane.get(int(lane.id), 0) + 1
            )

    lanes = [
        schemas.TimelineLaneDTO(
            id=int(lane.id),
            name=lane.name or "",
            color_label=lane.color_label or "",
            order_index=index,
            collapsed=bool(lane.collapsed),
            event_count=event_count_by_lane.get(int(lane.id), 0),
        )
        for index, lane in enumerate(snapshot.lanes)
    ]

    events: list[schemas.TimelineEventDTO] = []
    for order_index, scene_id in enumerate(projection.effective_order, start=1):
        scene = scene_by_id[scene_id]
        lane = lane_by_name.get((scene.plotline or "").strip())
        duration = (
            scene.estimated_duration_minutes
            or getattr(scene, "performance_duration_minutes", 0)
            or 0
        )
        events.append(schemas.TimelineEventDTO(
            id=int(scene.id),
            order_index=order_index,
            title=scene.title or "",
            structural_number=numbers.get(int(scene.id), ""),
            act=scene.act or "",
            chapter=scene.chapter or "",
            plotline=scene.plotline or "",
            color_label=scene.color_label or "",
            lane_id=int(lane.id) if lane is not None else None,
            time_of_day=scene.time_of_day or "",
            location=scene.location or scene.slugline or "",
            duration_minutes=int(duration),
            character_states=[
                schemas.TimelineCharacterStateDTO(
                    character=snapshot.character_names_by_id.get(
                        character_id, str(character_id),
                    ),
                    state=state,
                )
                for character_id, state in snapshot.character_states_by_scene.get(
                    int(scene.id), (),
                )
            ],
        ))

    off_timeline = [
        schemas.TimelineOffTimelineSceneDTO(
            id=int(scene_id),
            title=scene_by_id[scene_id].title or "",
            structural_number=numbers.get(scene_id, ""),
            act=scene_by_id[scene_id].act or "",
            chapter=scene_by_id[scene_id].chapter or "",
        )
        for scene_id in projection.off_timeline_ids
    ]
    return schemas.TimelineSnapshotDTO(
        project_id=int(snapshot.project.id),
        revision=snapshot.revision,
        order_mode=projection.order_mode,
        lanes=lanes,
        events=events,
        off_timeline=off_timeline,
    )


# -- PSYKE -------------------------------------------------------------------


def psyke_entry_to_dto(db: Database, entry) -> schemas.PsykeEntryDTO:
    return schemas.PsykeEntryDTO(
        id=entry.id,
        name=entry.name,
        type=entry.entry_type,
        aliases=_split_csv(entry.aliases),
        notes=entry.notes or "",
        is_global=bool(entry.is_global),
        details=db.get_psyke_entry_details(entry.id),
    )


def logos_action_to_dto(action) -> schemas.LogosActionDTO:
    """Serialize a logosforge.logos.actions.LogosAction for the catalog."""
    from logosforge.logos.actions import CATEGORY_GENERATIVE

    return schemas.LogosActionDTO(
        name=action.name,
        label=action.label,
        description=action.description,
        category=action.category,
        sections=list(action.sections),
        needs_selection=action.needs_selection,
        deterministic=action.deterministic,
        generative=(action.category == CATEGORY_GENERATIVE),
    )


def logos_suggestion_to_dto(s) -> schemas.LogosSuggestionDTO:
    """Serialize a logosforge.logos.proactive.LogosSuggestion."""
    return schemas.LogosSuggestionDTO(
        id=s.id,
        type=s.type,
        title=s.title,
        message=s.message,
        section_name=s.section_name,
        evidence=s.evidence,
        confidence=s.confidence,
        severity=s.severity,
        target_type=s.target_type,
        target_id=s.target_id,
        suggested_actions=list(s.suggested_actions),
    )


def logos_result_to_dto(result, *, generative: bool = False) -> schemas.LogosResultDTO:
    """Serialize a logosforge.logos.result.LogosResult (+ a generative flag)."""
    d = result.to_dict()
    return schemas.LogosResultDTO(
        ok=d["ok"],
        action=d["action"],
        title=d["title"],
        message=d["message"],
        suggestions=list(d["suggestions"]),
        proposed_operations=list(d["proposed_operations"]),
        generative=generative,
        error=d["error"],
    )


def psyke_relations(db: Database, project_id: int) -> list[schemas.PsykeRelationDTO]:
    # The database stores every relation twice so traversal is cheap. Iterate
    # canonical endpoint order and emit one stable DTO for each unordered pair.
    # Directional types remain meaningful because the row from the lower id to
    # the higher id carries either the requested type or its stored inverse.
    entries = sorted(
        db.get_all_psyke_entries(project_id), key=lambda entry: entry.id
    )
    name_by_id = {e.id: e.name for e in entries}
    out: list[schemas.PsykeRelationDTO] = []
    seen: set[tuple[int, int]] = set()
    for e in entries:
        related_entries = sorted(
            db.get_typed_related_psyke_entries(e.id),
            key=lambda item: item[0].id,
        )
        for related, rtype in related_entries:
            if related.id not in name_by_id:
                continue
            key = (min(e.id, related.id), max(e.id, related.id))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                schemas.PsykeRelationDTO(
                    id=f"{key[0]}:{key[1]}",
                    source_id=e.id,
                    target_id=related.id,
                    source=name_by_id.get(e.id, ""),
                    target=name_by_id.get(related.id, ""),
                    relation_type=rtype,
                )
            )
    return out


def psyke_progressions(db: Database, project_id: int) -> list[schemas.PsykeProgressionDTO]:
    entries = db.get_all_psyke_entries(project_id)
    scene_title_by_id = {s.id: s.title for s in db.get_all_scenes(project_id)}
    out = []
    for e in entries:
        for prog in db.get_psyke_progressions(e.id):
            scene_id = prog.scene_id if prog.scene_id in scene_title_by_id else None
            out.append(
                schemas.PsykeProgressionDTO(
                    id=prog.id,
                    entry_id=e.id,
                    text=prog.text,
                    scene_id=scene_id,
                    scene_title=scene_title_by_id.get(scene_id, "")
                    if scene_id else "",
                    sort_order=prog.sort_order or 0,
                )
            )
    return out


def progression_to_dto(db: Database, project_id: int, prog, entry_id: int) -> schemas.PsykeProgressionDTO:
    scene_title = ""
    scene_id = _local_scene_id(db, project_id, prog.scene_id)
    if scene_id:
        scene = db.get_scene_by_id(scene_id)
        scene_title = scene.title if scene else ""
    return schemas.PsykeProgressionDTO(
        id=prog.id,
        entry_id=entry_id,
        text=prog.text,
        scene_id=scene_id,
        scene_title=scene_title,
        sort_order=prog.sort_order or 0,
    )


# -- Notes -------------------------------------------------------------------


def note_to_dto(db: Database, note) -> schemas.NoteDTO:
    psyke_links = [
        entry_id
        for entry_id in db.get_note_psyke_links(note.id)
        if (
            (entry := db.get_psyke_entry_by_id(entry_id)) is not None
            and entry.project_id == note.project_id
        )
    ]
    scene_links = [
        scene_id
        for scene_id in db.get_note_scene_links(note.id)
        if _local_scene_id(db, note.project_id, scene_id) is not None
    ]
    return schemas.NoteDTO(
        id=note.id,
        title=note.title,
        content=note.content or "",
        tags=_split_csv(note.tags),
        pinned=bool(note.pinned),
        psyke_links=psyke_links,
        scene_links=scene_links,
    )


def comment_to_dto(db: Database, comment) -> schemas.InlineCommentDTO:
    reply_rows = [
        reply
        for reply in db.get_comment_replies(comment.id)
        if reply.project_id == comment.project_id
    ]
    replies = [
        schemas.CommentReplyDTO(
            id=reply.id,
            source_id=reply.source_id or "",
            body=reply.body or "",
            author=reply.author or "you",
            sort_order=reply.sort_order or 0,
            created_at=reply.created_at,
        )
        for reply in reply_rows
    ]
    return schemas.InlineCommentDTO(
        id=comment.id,
        source_id=comment.source_id or "",
        anchor=schemas.InlineCommentAnchorDTO(
            start_scene_id=comment.start_scene_id,
            start_field=comment.start_field,
            from_offset=comment.from_offset,
            end_scene_id=comment.end_scene_id,
            end_field=comment.end_field,
            to_offset=comment.to_offset,
            prefix=comment.prefix or "",
            suffix=comment.suffix or "",
        ),
        quote=comment.quote or "",
        body=comment.body or "",
        resolved=bool(comment.resolved),
        replies=replies,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        revision=comment_revision(comment, reply_rows),
    )


def character_to_dto(db: Database, character) -> schemas.CharacterDTO:
    psyke_entry_id = character.psyke_entry_id
    if psyke_entry_id is not None:
        entry = db.get_psyke_entry_by_id(psyke_entry_id)
        if (
            entry is None
            or entry.project_id != character.project_id
            or (entry.entry_type or "").lower() != "character"
        ):
            psyke_entry_id = None
    return schemas.CharacterDTO(
        id=character.id,
        name=character.name,
        description=character.description or "",
        color=character.color or "#3498db",
        psyke_entry_id=psyke_entry_id,
    )


# -- Narrative dashboard -----------------------------------------------------


def dashboard_to_dto(data) -> schemas.NarrativeDashboardDTO:
    """Map ``narrative_dashboard.NarrativeDashboardData`` onto its DTO."""
    return schemas.NarrativeDashboardDTO(
        tension=schemas.TensionCurveDTO(
            points=[
                schemas.SceneTensionDTO(
                    scene_id=p.scene_id,
                    scene_order=p.scene_order,
                    scene_title=p.scene_title,
                    score=p.score,
                    char_count=p.char_count,
                    relation_pairs=p.relation_pairs,
                    keyword_hits=p.keyword_hits,
                    progression_count=p.progression_count,
                )
                for p in data.tension.points
            ],
            flags=list(data.tension.flags),
        ),
        characters=[
            schemas.CharacterPresenceDTO(
                entry_id=c.entry_id,
                name=c.name,
                present_scenes=list(c.present_scenes),
                total_scenes=c.total_scenes,
                flags=list(c.flags),
            )
            for c in data.characters
        ],
        structure=schemas.StructureDistributionDTO(
            segments=[
                schemas.ActSegmentDTO(
                    label=s.label,
                    scene_count=s.scene_count,
                    word_count=s.word_count,
                )
                for s in data.structure.segments
            ],
            total_scenes=data.structure.total_scenes,
            total_words=data.structure.total_words,
            flags=list(data.structure.flags),
            inferred=data.structure.inferred,
        ),
        themes=[
            schemas.ThemePresenceDTO(
                entry_id=t.entry_id,
                name=t.name,
                present_scenes=list(t.present_scenes),
                total_scenes=t.total_scenes,
                flags=list(t.flags),
                presence_source=getattr(t, "presence_source", "prose"),
            )
            for t in data.themes
        ],
    )


# -- Continuity / pacing / balance / health ----------------------------------


def continuity_report_to_dto(report) -> schemas.ContinuityReportDTO:
    """Map ``continuity.models.ContinuityReport`` onto its DTO (issues + counts)."""
    return schemas.ContinuityReportDTO(
        writing_mode=report.writing_mode,
        issues=[
            schemas.ContinuityIssueDTO(
                id=i.issue_key,
                issue_type=i.issue_type,
                dimension=i.dimension,
                severity=i.severity,
                confidence=i.confidence,
                title=i.title,
                explanation=i.explanation,
                suggested_action=i.suggested_action,
                related_scene_ids=[int(s) for s in i.related_scene_ids],
                status=i.status,
            )
            for i in report.issues
        ],
        blocking_count=report.blocking_count,
        warning_count=report.warning_count,
        unavailable=list(report.unavailable),
    )


def pacing_insights_to_dtos(insights) -> list[schemas.PacingInsightDTO]:
    return [
        schemas.PacingInsightDTO(text=i.text, severity=i.severity, category=i.category)
        for i in insights
    ]


def balance_to_dto(data) -> schemas.BalanceDataDTO:
    """Map ``character_balance.BalanceData`` onto its DTO."""
    return schemas.BalanceDataDTO(
        characters=[
            schemas.CharacterBalanceDTO(
                char_id=c.char_id,
                name=c.name,
                scene_count=c.scene_count,
                total_scenes=c.total_scenes,
                flag=c.flag,
            )
            for c in data.characters
        ],
        arcs=[
            schemas.ArcBalanceDTO(
                plotline=a.plotline,
                scene_count=a.scene_count,
                acts_spanned=a.acts_spanned,
                flag=a.flag,
            )
            for a in data.arcs
        ],
        total_scenes=data.total_scenes,
    )


def _health_signal_to_dto(s) -> schemas.HealthSignalDTO:
    return schemas.HealthSignalDTO(label=s.label, level=s.level, score=s.score)


def story_health_to_dto(health) -> schemas.StoryHealthDTO:
    """Map ``story_health.StoryHealth`` onto its DTO (four signals)."""
    return schemas.StoryHealthDTO(
        structure=_health_signal_to_dto(health.structure),
        characters=_health_signal_to_dto(health.characters),
        arcs=_health_signal_to_dto(health.arcs),
        density=_health_signal_to_dto(health.density),
    )


def structural_analysis_to_dto(analysis) -> schemas.StructuralAnalysisDTO:
    """Map ``structural_intelligence.StructuralAnalysis`` onto its DTO."""
    return schemas.StructuralAnalysisDTO(
        issues=[
            schemas.StructuralIssueDTO(
                issue_type=i.issue_type,
                category=i.category,
                severity=i.severity,
                message=i.message,
                suggestion=i.suggestion,
            )
            for i in analysis.issues
        ],
        suggestions=list(analysis.suggestions),
    )


def workflow_run_to_dto(view) -> schemas.WorkflowRunDTO:
    """Map a ``guided_workflows.engine.WorkflowRunView`` onto its DTO."""
    run = view.run
    return schemas.WorkflowRunDTO(
        id=getattr(run, "id", 0),
        title=getattr(run, "title", "") or "",
        status=getattr(run, "status", "") or "",
        writing_mode=getattr(run, "writing_mode", "") or "",
        template_id=getattr(run, "template_id", "") or "",
        current_step_id=getattr(run, "current_step_id", "") or "",
        total_steps=view.total_steps,
        completed_steps=view.completed_steps,
        steps=[
            schemas.WorkflowStepDTO(
                step_id=getattr(s, "step_id", "") or "",
                title=getattr(s, "title", "") or "",
                status=getattr(s, "status", "") or "",
                sort_index=getattr(s, "sort_index", 0) or 0,
                section_name=getattr(s, "section_name", "") or "",
                action_id=getattr(s, "action_id", "") or "",
            )
            for s in view.steps
        ],
    )


def workflows_to_dtos(views) -> list[schemas.WorkflowRunDTO]:
    return [workflow_run_to_dto(v) for v in views]


def decision_card_to_dto(card) -> schemas.DecisionCardDTO:
    return schemas.DecisionCardDTO(
        id=card.id,
        category=card.category,
        severity=card.severity,
        confidence=card.confidence,
        title=card.title,
        explanation=card.explanation,
        suggested_action=card.suggested_action,
        related_section=card.related_section,
        related_target_type=card.related_target_type,
        related_target_id=card.related_target_id,
        created_from=card.created_from,
    )


def decision_radar_to_dto(report) -> schemas.DecisionRadarDTO:
    """Map a ``project_intelligence.ProjectIntelligenceReport`` onto the radar DTO."""
    return schemas.DecisionRadarDTO(
        project_id=report.project_id,
        generated_light=bool(getattr(report, "light", False)),
        summary_line=report.summary_line(),
        radar=[decision_card_to_dto(c) for c in report.radar],
    )


def quantum_result_to_dto(result) -> schemas.QuantumResultDTO:
    """Map a ``quantum_outliner.QuantumResult`` onto its DTO (payload is JSON-ready)."""
    payload = result.payload if isinstance(result.payload, dict) else {}
    return schemas.QuantumResultDTO(
        kind=result.kind,
        title=result.title,
        body=result.body,
        payload=payload,
    )


_KNOWLEDGE_GRAPH_DIAGNOSTIC_CAP = 25
_KNOWLEDGE_GRAPH_WIRE_KEY_MAX = 512
_KNOWLEDGE_GRAPH_VIEW_MODES = frozenset({
    "project_map",
    "structure",
    "recorded_risk",
    "revision_impact",
})


def _knowledge_graph_view_projection(
    graph,
    *,
    view_mode: str,
    include_inferred: bool,
) -> tuple[set[str], list[Any]]:
    """Project the complete visible graph before any response bound is applied."""
    from logosforge.knowledge_graph import provenance as graph_provenance

    if view_mode not in _KNOWLEDGE_GRAPH_VIEW_MODES:
        raise ValueError(f"Unsupported Knowledge Graph view mode: {view_mode}")

    graph_node_keys = set(graph.nodes)
    visible_edges = [
        edge for edge in graph.visible_edges(include_inferred=include_inferred)
        if edge.source in graph_node_keys and edge.target in graph_node_keys
    ]
    visible_edges.sort(key=_knowledge_graph_edge_sort_key)

    if view_mode == "project_map":
        return graph_node_keys, visible_edges

    if view_mode == "structure":
        structural_types = {
            graph_provenance.NT_PROJECT,
            graph_provenance.NT_ACT,
            graph_provenance.NT_CHAPTER,
            graph_provenance.NT_SCENE,
            graph_provenance.NT_PLOT_BLOCK,
            graph_provenance.NT_TIMELINE_EVENT,
        }
        structural_edges = {
            graph_provenance.ET_CONTAINS,
            graph_provenance.ET_BELONGS_TO,
            graph_provenance.ET_PRECEDES,
            graph_provenance.ET_FOLLOWS,
        }
        selected_keys = {
            key for key, node in graph.nodes.items()
            if node.node_type in structural_types
        }
        return selected_keys, [
            edge for edge in visible_edges
            if edge.edge_type in structural_edges
            and edge.source in selected_keys
            and edge.target in selected_keys
        ]

    if view_mode == "recorded_risk":
        selected_edges = [
            edge for edge in visible_edges
            if edge.edge_type in {
                graph_provenance.ET_RISKS,
                graph_provenance.ET_CONTRADICTS,
            }
        ]
    else:
        selected_edges = [
            edge for edge in visible_edges
            if edge.source_system == graph_provenance.SS_REVISION
            and edge.edge_type in {
                graph_provenance.ET_REVISES,
                graph_provenance.ET_RISKS,
            }
        ]
    selected_keys = {
        key
        for edge in selected_edges
        for key in (edge.source, edge.target)
    }
    return selected_keys, selected_edges


def knowledge_graph_view_node_keys(
    graph,
    *,
    view_mode: str,
    include_inferred: bool,
) -> set[str]:
    """Return internal keys addressable by one canonical graph view."""
    keys, _ = _knowledge_graph_view_projection(
        graph,
        view_mode=view_mode,
        include_inferred=include_inferred,
    )
    return keys


def knowledge_graph_wire_key(internal_key: str) -> str:
    """Return a stable, focusable key that always fits the HTTP contract.

    A few legacy structural keys embed author-controlled act/chapter names.
    Preserve ordinary canonical keys verbatim and replace only overlong values
    with a deterministic SHA-256 token.  Edge endpoints and focus resolution use
    this same mapping, so no truncated/colliding identifier reaches clients.
    """
    value = str(internal_key)
    if len(value) <= _KNOWLEDGE_GRAPH_WIRE_KEY_MAX:
        return value
    return f"kg:sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def resolve_knowledge_graph_focus_key(graph, wire_key: str) -> str | None:
    """Resolve a public graph key inside *this* already-built project graph."""
    for internal_key in graph.nodes:
        if knowledge_graph_wire_key(internal_key) == wire_key:
            return internal_key
    return None


def _bounded_graph_value(value: Any, *, depth: int = 0) -> Any:
    """Return a small JSON-safe copy of graph metadata.

    The graph extractors currently emit shallow scalar metadata, but keeping the
    API boundary defensive prevents a future extractor from turning a bounded
    graph read into an unbounded nested payload.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:512]
    if depth >= 3:
        return str(value)[:512]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in sorted(value.items(), key=lambda item: str(item[0]))[:20]:
            result[str(key)[:128]] = _bounded_graph_value(child, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_bounded_graph_value(child, depth=depth + 1) for child in value[:20]]
    if isinstance(value, set):
        children = sorted(value, key=str)[:20]
        return [_bounded_graph_value(child, depth=depth + 1) for child in children]
    return str(value)[:512]


def _knowledge_graph_edge_sort_key(edge) -> tuple[str, str, str, str, str]:
    return (
        str(edge.source), str(edge.target), str(edge.edge_type),
        str(edge.confidence), str(edge.source_system),
    )


def _knowledge_graph_edge_to_dto(edge) -> schemas.KnowledgeGraphEdgeDTO:
    return schemas.KnowledgeGraphEdgeDTO(
        source=knowledge_graph_wire_key(edge.source),
        target=knowledge_graph_wire_key(edge.target),
        edge_type=str(edge.edge_type)[:128],
        confidence=str(edge.confidence)[:32],
        provenance=str(edge.provenance or "")[:512],
        source_system=str(edge.source_system or "")[:128],
        explanation=str(edge.explanation or "")[:1000],
        is_user_confirmed=bool(edge.is_user_confirmed),
        is_inferred=bool(edge.is_inferred),
        is_hidden=bool(edge.is_hidden),
        metadata=_bounded_graph_value(dict(edge.metadata or {})),
    )


def knowledge_graph_read_to_dto(
    graph,
    *,
    focus_key: str | None = None,
    depth: int = 1,
    limit: int = 100,
    include_inferred: bool = True,
    view_mode: str = "project_map",
    story_gravity_available: bool = False,
    story_gravity_totals: dict[str, float] | None = None,
) -> schemas.KnowledgeGraphReadDTO:
    """Serialize a bounded canonical view or node neighborhood.

    The builder's graph remains the source of truth.  This adapter drops
    dangling endpoints defensively, calculates degrees against the complete
    filtered view *before* slicing, and reserves Project Map capacity for
    edge-less orphan nodes and applicable diagnostics.
    """
    from logosforge.knowledge_graph import provenance as graph_provenance
    from logosforge.knowledge_graph import scoring as graph_scoring

    graph_node_keys = set(graph.nodes)
    gravity_totals = story_gravity_totals or {}
    full_hidden_edges = [
        edge for edge in graph.edges
        if edge.is_hidden
        and edge.source in graph_node_keys
        and edge.target in graph_node_keys
    ]
    full_hidden_edges.sort(key=_knowledge_graph_edge_sort_key)
    node_keys, full_edges = _knowledge_graph_view_projection(
        graph,
        view_mode=view_mode,
        include_inferred=include_inferred,
    )
    if focus_key is not None and focus_key not in node_keys:
        raise ValueError("Knowledge Graph focus is outside the selected view")

    degree_by_key = {key: 0 for key in node_keys}
    for edge in full_edges:
        degree_by_key[edge.source] += 1
        degree_by_key[edge.target] += 1

    if focus_key is not None:
        # Build adjacency once, then traverse the complete filtered graph before
        # applying the HTTP response cap.  The shared query helper scans every
        # edge once per frontier node; that becomes needlessly quadratic for a
        # dense depth-two neighborhood.
        adjacency: dict[str, list[Any]] = {key: [] for key in node_keys}
        for edge in full_edges:
            adjacency[edge.source].append(edge)
            if edge.target != edge.source:
                adjacency[edge.target].append(edge)
        candidate_keys = {focus_key}
        candidate_edges = []
        seen_edge_keys: set[tuple[str, str, str]] = set()
        frontier = {focus_key}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for key in sorted(frontier):
                for edge in adjacency.get(key, []):
                    if edge.dedupe_key not in seen_edge_keys:
                        seen_edge_keys.add(edge.dedupe_key)
                        candidate_edges.append(edge)
                    other = edge.target if edge.source == key else edge.source
                    if other not in candidate_keys:
                        candidate_keys.add(other)
                        next_frontier.add(other)
            frontier = next_frontier
            if not frontier:
                break
        candidate_edges.sort(key=_knowledge_graph_edge_sort_key)
    else:
        candidate_keys = set(node_keys)
        candidate_edges = list(full_edges)

    # Reuse the canonical story-orphan semantics (project membership alone does
    # not make a story node connected), but do not inherit its default UI cap.
    diagnostics_available = view_mode == "project_map"
    if diagnostics_available:
        canonical_orphans = graph_scoring.orphan_nodes(
            graph,
            cap=max(1, len(graph.nodes)),
            include_inferred=include_inferred,
        )
        candidate_orphan_keys = sorted(
            node.key for node in canonical_orphans if node.key in candidate_keys
        )

        canonical_weak_keys = {
            edge.dedupe_key for edge in graph_scoring.weak_link_edges(
                graph, cap=max(1, len(graph.edges)),
            )
        }
        candidate_weak_links = [
            edge for edge in candidate_edges
            if include_inferred and edge.dedupe_key in canonical_weak_keys
        ]
        candidate_weak_links.sort(
            key=lambda edge: (
                -graph_provenance.confidence_rank(edge.confidence),
                *_knowledge_graph_edge_sort_key(edge),
            )
        )
    else:
        candidate_orphan_keys = []
        candidate_weak_links = []

    def node_rank(key: str) -> tuple[int, int, str, str]:
        node = graph.nodes[key]
        return (
            0 if focus_key is not None and key == focus_key else 1,
            -degree_by_key.get(key, 0),
            str(node.node_type),
            key,
        )

    if focus_key is not None:
        selected_keys = sorted(candidate_keys, key=node_rank)[:limit]
    elif diagnostics_available:
        # Reserve a bounded portion of the Project Map for authoritative hidden
        # review state so a refresh does not strand the Restore action.  The
        # other half remains available for the useful central-node projection.
        hidden_key_budget = (
            min(limit, max(2, limit // 2))
            if full_hidden_edges and limit >= 2
            else 0
        )
        reserved_hidden_keys: list[str] = []
        reserved_hidden_set: set[str] = set()
        for edge in full_hidden_edges[:_KNOWLEDGE_GRAPH_DIAGNOSTIC_CAP]:
            additions = [
                key for key in (edge.source, edge.target)
                if key not in reserved_hidden_set
            ]
            if len(reserved_hidden_set) + len(additions) > hidden_key_budget:
                continue
            reserved_hidden_keys.extend(additions)
            reserved_hidden_set.update(additions)

        # Keep the map useful (central nodes first) while guaranteeing that an
        # edge-less story element survives truncation for the orphan rail.
        orphan_budget = 0
        if candidate_orphan_keys:
            orphan_budget = min(
                len(candidate_orphan_keys),
                _KNOWLEDGE_GRAPH_DIAGNOSTIC_CAP,
                max(1, limit // 4),
                max(0, limit - len(reserved_hidden_keys)),
            )
        reserved_orphans = [
            key for key in candidate_orphan_keys
            if key not in reserved_hidden_set
        ][:orphan_budget]
        reserved_set = {*reserved_hidden_set, *reserved_orphans}
        primary = sorted(candidate_keys - reserved_set, key=node_rank)
        selected_keys = (
            reserved_hidden_keys
            + primary[:max(0, limit - len(reserved_set))]
            + reserved_orphans
        )
    else:
        selected_keys = sorted(candidate_keys, key=node_rank)[:limit]

    selected_set = set(selected_keys)
    returned_edges = [
        edge for edge in candidate_edges
        if edge.source in selected_set and edge.target in selected_set
    ][:limit]
    returned_orphan_keys = [
        key for key in candidate_orphan_keys if key in selected_set
    ]
    weak_cap = min(limit, _KNOWLEDGE_GRAPH_DIAGNOSTIC_CAP)
    returned_weak_links = [
        edge for edge in candidate_weak_links
        if edge.source in selected_set and edge.target in selected_set
    ][:weak_cap]
    hidden_cap = min(limit, _KNOWLEDGE_GRAPH_DIAGNOSTIC_CAP)
    returned_hidden_edges = (
        [
            edge for edge in full_hidden_edges
            if edge.source in selected_set and edge.target in selected_set
        ][:hidden_cap]
        if diagnostics_available
        else []
    )
    hidden_edge_count = max(
        len(full_hidden_edges),
        int(getattr(graph, "persisted_hidden_edge_count", 0)),
    )

    nodes = []
    for key in selected_keys:
        node = graph.nodes[key]
        nodes.append(schemas.KnowledgeGraphNodeDTO(
            key=knowledge_graph_wire_key(node.key),
            node_type=str(node.node_type)[:128],
            source_type=str(node.source_type or "")[:128],
            source_id=(None if node.source_id is None else str(node.source_id)[:512]),
            label=str(node.label or "")[:512],
            summary=str(node.summary or "")[:1000],
            metadata=_bounded_graph_value(dict(node.metadata or {})),
            degree=degree_by_key.get(key, 0),
            story_gravity=gravity_totals.get(key),
        ))

    truncated = (
        len(selected_keys) < len(candidate_keys)
        or len(returned_edges) < len(candidate_edges)
        or (
            diagnostics_available
            and (
                len(returned_orphan_keys) < len(candidate_orphan_keys)
                or len(returned_weak_links) < len(candidate_weak_links)
                or len(returned_hidden_edges) < hidden_edge_count
            )
        )
    )
    return schemas.KnowledgeGraphReadDTO(
        project_id=int(graph.project_id),
        revision=str(graph.revision),
        writing_mode=str(graph.writing_mode or "")[:128],
        focus_key=(
            None if focus_key is None else knowledge_graph_wire_key(focus_key)
        ),
        depth=depth,
        include_inferred=include_inferred,
        view_mode=view_mode,
        story_gravity_available=story_gravity_available,
        nodes=nodes,
        edges=[_knowledge_graph_edge_to_dto(edge) for edge in returned_edges],
        node_count=len(candidate_keys),
        edge_count=len(candidate_edges),
        returned_node_count=len(nodes),
        returned_edge_count=len(returned_edges),
        truncated=truncated,
        story_diagnostics_available=diagnostics_available,
        orphan_keys=[knowledge_graph_wire_key(key) for key in returned_orphan_keys],
        orphan_count=len(candidate_orphan_keys),
        weak_links=[
            _knowledge_graph_edge_to_dto(edge) for edge in returned_weak_links
        ],
        weak_link_count=len(candidate_weak_links),
        hidden_edges=[
            _knowledge_graph_edge_to_dto(edge)
            for edge in returned_hidden_edges
        ],
        hidden_edge_count=hidden_edge_count,
        warnings=[str(warning)[:512] for warning in graph.warnings[:25]],
        unavailable=[str(source)[:128] for source in graph.unavailable[:25]],
    )


def knowledge_graph_hidden_edges_to_dto(
    graph,
    *,
    offset: int,
    limit: int,
) -> schemas.KnowledgeGraphHiddenEdgePageDTO:
    """Serialize a deterministic page of every durable hidden edge decision."""
    node_keys = set(graph.nodes)
    hidden = [
        edge for edge in graph.edges
        if edge.is_hidden
        and edge.source in node_keys
        and edge.target in node_keys
    ]
    hidden.sort(key=_knowledge_graph_edge_sort_key)
    persisted_count = int(
        getattr(graph, "persisted_hidden_edge_count", len(hidden))
    )
    if persisted_count != len(hidden):
        # Duplicate/corrupt legacy rows cannot be paginated into unambiguous
        # directional commands.  Fail closed rather than hiding a decision.
        raise RuntimeError("Knowledge Graph hidden review state is inconsistent")
    page = hidden[offset:offset + limit]
    endpoint_keys = sorted({
        key for edge in page for key in (edge.source, edge.target)
    })
    nodes = []
    for key in endpoint_keys:
        node = graph.nodes[key]
        nodes.append(schemas.KnowledgeGraphNodeDTO(
            key=knowledge_graph_wire_key(node.key),
            node_type=str(node.node_type)[:128],
            source_type=str(node.source_type or "")[:128],
            source_id=(
                None if node.source_id is None else str(node.source_id)[:512]
            ),
            label=str(node.label or "")[:512],
            summary=str(node.summary or "")[:1000],
            metadata=_bounded_graph_value(dict(node.metadata or {})),
            degree=graph.degree(key),
            story_gravity=None,
        ))
    return schemas.KnowledgeGraphHiddenEdgePageDTO(
        project_id=int(graph.project_id),
        revision=str(graph.revision),
        offset=offset,
        limit=limit,
        hidden_edge_count=persisted_count,
        returned_edge_count=len(page),
        nodes=nodes,
        edges=[_knowledge_graph_edge_to_dto(edge) for edge in page],
    )


def gravity_to_dto(gravity_map, data) -> schemas.GraphGravityDTO:
    """Map ``graph_gravity.compute_gravity`` output (+ GraphData) onto the DTO."""
    nodes = []
    for node_id, g in gravity_map.items():
        node = data.nodes.get(node_id) if data is not None else None
        nodes.append(schemas.StoryGravityNodeDTO(
            node_id=node_id,
            etype=getattr(node, "etype", "") if node is not None else "",
            name=getattr(node, "name", "") if node is not None else "",
            narrative=g.narrative,
            thematic=g.thematic,
            structural=g.structural,
            total=g.total,
        ))
    nodes.sort(key=lambda n: n.total, reverse=True)
    return schemas.GraphGravityDTO(available=True, nodes=nodes)
