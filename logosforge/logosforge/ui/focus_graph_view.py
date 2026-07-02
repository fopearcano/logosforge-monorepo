"""Graph Focus System — controlled graph exploration.

Replaces the full graph dump with focused navigation: click a node to see
only its neighborhood, expand/collapse, temporal filtering, type filters,
search, and hover highlighting.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QActionGroup, QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)
from PySide6.QtGui import QPolygonF
from PySide6.QtCore import QPointF

from logosforge.db import Database
from logosforge.graph_data import (
    NODE_KIND_CHARACTER,
    NODE_KIND_PLACE,
    NODE_KIND_OBJECT,
    NODE_KIND_THEME,
    NODE_KIND_LORE,
    NODE_KIND_SCENE,
    NODE_KIND_ACT,
    NODE_KIND_NOTE,
    NODE_KIND_OTHER,
    NODE_KIND_PAGE,
    NODE_KIND_PANEL,
    NODE_KIND_MOTIF,
    NODE_KIND_GN_OBJECT,
    NODE_KIND_CUE,
    NODE_KIND_OFFSTAGE,
    NODE_KIND_SEASON,
    NODE_KIND_EPISODE,
    NODE_KIND_ARC,
    NODE_KIND_MYSTERY,
    NODE_KIND_PLOTLINE,
    NODE_KIND_WAVEFUNCTION,
    NODE_KIND_BRANCH,
    EDGE_LINK,
    EDGE_MENTION,
    EDGE_PSYKE_RELATION,
    EDGE_PARTICIPATION,
    EDGE_CONTAINMENT,
    EDGE_QUANTUM,
    EDGE_CAUSALITY,
    EDGE_SETUP_PAYOFF,
    EDGE_KNOWLEDGE,
    EDGE_SUBTEXT,
    EDGE_VISUAL_MOTIF,
    EDGE_CONTINUITY,
    EDGE_GN_CONTAINS,
    EDGE_GN_PAGE_FLOW,
    EDGE_GN_PANEL_CAUSALITY,
    EDGE_GN_MOTIF,
    EDGE_GN_SYMBOL_ECHO,
    EDGE_GN_OBJECT_CONTINUITY,
    EDGE_GN_CHARACTER_PRESENT,
    EDGE_GN_PSYKE_MOTIF,
    EDGE_SS_PRESSURE,
    EDGE_SS_SUBTEXT,
    EDGE_SS_ENTRANCE_EXIT,
    EDGE_SS_USES_PROP,
    EDGE_SS_BLOCKING,
    EDGE_SS_CUE,
    EDGE_SS_OFFSTAGE,
    EDGE_SR_CONTAINS,
    EDGE_SR_CONTINUES,
    EDGE_SR_SETS_UP,
    EDGE_SR_PAYS_OFF,
    EDGE_SR_RESOLVES,
    EDGE_SR_DELAYS,
    EDGE_SR_ESCALATES,
    EDGE_SR_ECHOES,
    EDGE_SR_CONTRADICTS,
    GraphData,
    GraphEdge,
    GraphNode,
    build_graph_data,
)
from logosforge.graph_enrichers import (
    enrich_graphic_novel_graph,
    enrich_screenplay_edges,
    enrich_series_graph,
    enrich_stage_script_graph,
)
from logosforge.graph_analysis import (
    GraphInsight,
    NodeAnalysis,
    analyze_node,
    compose_assistant_context,
    explain_structure,
    find_disconnected_nodes,
    find_weak_thematic_clusters,
    suggest_missing_relations,
)
from logosforge.graph_flow import (
    FLOW_ACTS,
    FLOW_ARC,
    FLOW_CAUSAL,
    FLOW_TIMELINE,
    FLOW_TYPES,
    FlowSegment,
    band_color,
    compute_flow,
)
from logosforge.graph_gravity import (
    GRAVITY_GLOW_THRESHOLD,
    StoryGravity,
    compute_gravity,
    gravity_centrality_pull,
    gravity_glow_alpha,
    gravity_radius_multiplier,
)
from logosforge.graph_meaning import (
    MeaningData,
    NodeMeaning,
    compute_meaning,
    importance_radius_delta,
    state_color,
)
from logosforge.ui import theme


_TYPE_COLORS = {
    "Character": "#42a5f5",
    "Place": "#66bb6a",
    "Scene": "#ffa726",
    "Note": "#ab47bc",
    "PSYKE": "#4ade80",
}

# Semantic node/edge kind constants + the GraphNode/GraphEdge/GraphData model +
# build_graph_data now live in logosforge.graph_data (Qt-free) and are imported
# at the top of this module. Rendering (colors / shapes / styles below) and the
# screenplay/GN/stage/series edge enrichers + the Qt view stay here.

LAYER_KINDS: tuple[str, ...] = (
    NODE_KIND_CHARACTER, NODE_KIND_PLACE, NODE_KIND_OBJECT,
    NODE_KIND_THEME, NODE_KIND_LORE, NODE_KIND_SCENE,
    NODE_KIND_ACT, NODE_KIND_NOTE, NODE_KIND_OTHER,
)

SKELETON_LAYERS: frozenset[str] = frozenset({
    NODE_KIND_CHARACTER, NODE_KIND_THEME, NODE_KIND_ACT,
})

_KIND_COLORS: dict[str, str] = {
    NODE_KIND_CHARACTER: "#42a5f5",
    NODE_KIND_PLACE: "#66bb6a",
    NODE_KIND_OBJECT: "#f59e0b",
    NODE_KIND_THEME: "#c084fc",
    NODE_KIND_LORE: "#22d3ee",
    NODE_KIND_SCENE: "#ffa726",
    NODE_KIND_ACT: "#94a3b8",
    NODE_KIND_NOTE: "#ab47bc",
    NODE_KIND_OTHER: "#9e9e9e",
    "wavefunction": "#ec4899",
    "branch": "#f472b6",
    NODE_KIND_PAGE: "#ffa726",
    NODE_KIND_PANEL: "#fbbf24",
    NODE_KIND_MOTIF: "#06b6d4",
    NODE_KIND_GN_OBJECT: "#f59e0b",
    NODE_KIND_CUE: "#eab308",
    NODE_KIND_OFFSTAGE: "#a78bfa",
    NODE_KIND_SEASON: "#06b6d4",
    NODE_KIND_EPISODE: "#ffa726",
    NODE_KIND_ARC: "#f59e0b",
    NODE_KIND_MYSTERY: "#eab308",
    NODE_KIND_PLOTLINE: "#ef4444",
}

_KIND_SHAPES: dict[str, str] = {
    NODE_KIND_CHARACTER: "circle",
    NODE_KIND_PLACE: "square",
    NODE_KIND_OBJECT: "triangle",
    NODE_KIND_THEME: "diamond",
    NODE_KIND_LORE: "hexagon",
    NODE_KIND_SCENE: "rounded_rect",
    NODE_KIND_ACT: "act_band",
    NODE_KIND_NOTE: "small_circle",
    NODE_KIND_OTHER: "circle",
    "wavefunction": "hexagon",
    "branch": "small_circle",
    NODE_KIND_PAGE: "rounded_rect",
    NODE_KIND_PANEL: "square",
    NODE_KIND_MOTIF: "diamond",
    NODE_KIND_GN_OBJECT: "triangle",
    NODE_KIND_CUE: "small_circle",
    NODE_KIND_OFFSTAGE: "hexagon",
    NODE_KIND_SEASON: "act_band",
    NODE_KIND_EPISODE: "rounded_rect",
    NODE_KIND_ARC: "triangle",
    NODE_KIND_MYSTERY: "diamond",
    NODE_KIND_PLOTLINE: "small_circle",
}

EDGE_STYLE: dict[str, dict] = {
    EDGE_PARTICIPATION: {"color": "#4ade80", "width": 1.3, "dash": "solid"},
    EDGE_CONTAINMENT:   {"color": "#60a5fa", "width": 2.4, "dash": "solid"},
    EDGE_PSYKE_RELATION:{"color": "#c084fc", "width": 1.6, "dash": "solid"},
    EDGE_MENTION:       {"color": "#94a3b8", "width": 0.9, "dash": "dash"},
    EDGE_QUANTUM:       {"color": "#f472b6", "width": 1.5, "dash": "dot"},
    EDGE_LINK:          {"color": "#4a5568", "width": 1.2, "dash": "solid"},
    EDGE_CAUSALITY:     {"color": "#f59e0b", "width": 1.8, "dash": "solid"},
    EDGE_SETUP_PAYOFF:  {"color": "#10b981", "width": 2.0, "dash": "solid"},
    EDGE_KNOWLEDGE:     {"color": "#8b5cf6", "width": 1.5, "dash": "dash"},
    EDGE_SUBTEXT:       {"color": "#ec4899", "width": 1.4, "dash": "dot"},
    EDGE_VISUAL_MOTIF:  {"color": "#06b6d4", "width": 1.6, "dash": "dash"},
    EDGE_CONTINUITY:    {"color": "#4ade80", "width": 1.4, "dash": "solid"},
    EDGE_GN_CONTAINS:   {"color": "#60a5fa", "width": 1.6, "dash": "solid"},
    EDGE_GN_PAGE_FLOW:  {"color": "#ffa726", "width": 2.0, "dash": "solid"},
    EDGE_GN_PANEL_CAUSALITY: {"color": "#fbbf24", "width": 1.5, "dash": "solid"},
    EDGE_GN_MOTIF:      {"color": "#06b6d4", "width": 1.4, "dash": "dash"},
    EDGE_GN_SYMBOL_ECHO: {"color": "#22d3ee", "width": 1.6, "dash": "dot"},
    EDGE_GN_OBJECT_CONTINUITY: {"color": "#f59e0b", "width": 1.4, "dash": "solid"},
    EDGE_GN_CHARACTER_PRESENT: {"color": "#42a5f5", "width": 1.4, "dash": "solid"},
    EDGE_GN_PSYKE_MOTIF: {"color": "#c084fc", "width": 1.3, "dash": "dot"},
    EDGE_SS_PRESSURE:   {"color": "#ef4444", "width": 1.8, "dash": "solid"},
    EDGE_SS_SUBTEXT:    {"color": "#ec4899", "width": 1.4, "dash": "dot"},
    EDGE_SS_ENTRANCE_EXIT: {"color": "#4ade80", "width": 1.5, "dash": "solid"},
    EDGE_SS_USES_PROP:  {"color": "#f59e0b", "width": 1.4, "dash": "dash"},
    EDGE_SS_BLOCKING:   {"color": "#60a5fa", "width": 1.4, "dash": "solid"},
    EDGE_SS_CUE:        {"color": "#eab308", "width": 1.0, "dash": "dot"},
    EDGE_SS_OFFSTAGE:   {"color": "#a78bfa", "width": 1.3, "dash": "dash"},
    EDGE_SR_CONTAINS:   {"color": "#60a5fa", "width": 2.0, "dash": "solid"},
    EDGE_SR_CONTINUES:  {"color": "#ffa726", "width": 1.8, "dash": "solid"},
    EDGE_SR_SETS_UP:    {"color": "#10b981", "width": 1.8, "dash": "solid"},
    EDGE_SR_PAYS_OFF:   {"color": "#22c55e", "width": 2.0, "dash": "solid"},
    EDGE_SR_RESOLVES:   {"color": "#4ade80", "width": 2.0, "dash": "solid"},
    EDGE_SR_DELAYS:     {"color": "#eab308", "width": 1.6, "dash": "dash"},
    EDGE_SR_ESCALATES:  {"color": "#f97316", "width": 1.4, "dash": "dot"},
    EDGE_SR_ECHOES:     {"color": "#a78bfa", "width": 1.4, "dash": "dash"},
    EDGE_SR_CONTRADICTS:{"color": "#ef4444", "width": 1.8, "dash": "dot"},
}

# -- Narrative modes ---------------------------------------------------------
# A mode is a self-contained "view" of the graph: it dictates which kinds of
# nodes and edges appear, how they are laid out, and which kinds are visually
# prominent.  Modes are mutually exclusive (one at a time); MODE_ALL is the
# permissive default that lets the Layers panel decide everything.

MODE_ALL = "all"
MODE_RELATIONSHIP = "relationship"
MODE_THEME = "theme"
MODE_STRUCTURE = "structure"
MODE_QUANTUM = "quantum"
MODE_PSYKE = "psyke"
MODE_MEANING = "meaning"

# Screenplay-specific graph modes (only shown for screenplay projects).
MODE_CAUSALITY = "causality"
MODE_SETUP_PAYOFF = "setup_payoff"
MODE_KNOWLEDGE = "knowledge"
MODE_SUBTEXT = "subtext"
MODE_VISUAL_MOTIFS = "visual_motifs"
MODE_CONTINUITY_GRAPH = "continuity_graph"

# Graphic-novel-specific graph modes (only shown for graphic_novel projects).
MODE_GN_MOTIF = "gn_visual_motif"
MODE_GN_PANEL_CAUSALITY = "gn_panel_causality"
MODE_GN_SYMBOL_RECURRENCE = "gn_symbol_recurrence"
MODE_GN_PAGE_RHYTHM = "gn_page_rhythm"
MODE_GN_OBJECT_CONTINUITY = "gn_object_continuity"
MODE_GN_CHARACTER = "gn_character_appearance"

# Stage-script-specific graph modes (only shown for stage_script projects).
MODE_SS_PRESSURE = "ss_character_pressure"
MODE_SS_ENTRANCE_EXIT = "ss_entrance_exit"
MODE_SS_PROP = "ss_prop_continuity"
MODE_SS_BLOCKING = "ss_blocking_spatial"
MODE_SS_SUBTEXT = "ss_subtext_conflict"
MODE_SS_OFFSTAGE = "ss_offstage_knowledge"

# Series-specific graph modes (only shown for series projects).
MODE_SR_SEASON_ARC = "sr_season_arc"
MODE_SR_EPISODE_DEP = "sr_episode_dependency"
MODE_SR_ABC_PLOT = "sr_abc_plot"
MODE_SR_MYSTERY = "sr_mystery_payoff"
MODE_SR_CHARACTER = "sr_character_progression"
MODE_SR_RELATIONSHIP = "sr_relationship_evolution"
MODE_SR_CONTINUITY = "sr_continuity_risk"

@dataclass(frozen=True)
class ModeProfile:
    """Self-contained recipe for one narrative-mode view of the graph."""
    name: str
    visible_kinds: frozenset[str]
    visible_edge_types: frozenset[str]
    layout: str  # "circular" | "linear_timeline" | "theme_centered" | "quantum_tree"
    prominence: dict[str, float] = field(default_factory=dict)
    meaning_overlay: bool = False
    uses_quantum: bool = False
    description: str = ""


MODE_PROFILES: dict[str, ModeProfile] = {
    MODE_ALL: ModeProfile(
        name=MODE_ALL,
        visible_kinds=frozenset(LAYER_KINDS),
        visible_edge_types=frozenset({
            EDGE_PARTICIPATION, EDGE_CONTAINMENT, EDGE_PSYKE_RELATION,
            EDGE_MENTION, EDGE_LINK,
        }),
        layout="circular",
        description="Full graph — Layers panel controls visibility.",
    ),
    MODE_RELATIONSHIP: ModeProfile(
        name=MODE_RELATIONSHIP,
        visible_kinds=frozenset({NODE_KIND_CHARACTER}),
        visible_edge_types=frozenset({EDGE_PARTICIPATION, EDGE_PSYKE_RELATION, EDGE_MENTION}),
        layout="circular",
        prominence={NODE_KIND_CHARACTER: 1.15},
        description="Character relations only.",
    ),
    MODE_THEME: ModeProfile(
        name=MODE_THEME,
        visible_kinds=frozenset({NODE_KIND_THEME, NODE_KIND_CHARACTER, NODE_KIND_SCENE}),
        visible_edge_types=frozenset({EDGE_PSYKE_RELATION, EDGE_PARTICIPATION, EDGE_MENTION}),
        layout="theme_centered",
        prominence={NODE_KIND_THEME: 1.5},
        description="Themes and the entries they touch.",
    ),
    MODE_STRUCTURE: ModeProfile(
        name=MODE_STRUCTURE,
        visible_kinds=frozenset({NODE_KIND_ACT, NODE_KIND_SCENE}),
        visible_edge_types=frozenset({EDGE_CONTAINMENT}),
        layout="linear_timeline",
        prominence={NODE_KIND_ACT: 1.3},
        description="Acts and scenes laid out as a story timeline.",
    ),
    MODE_QUANTUM: ModeProfile(
        name=MODE_QUANTUM,
        visible_kinds=frozenset({NODE_KIND_WAVEFUNCTION, NODE_KIND_BRANCH}),
        visible_edge_types=frozenset({EDGE_QUANTUM}),
        layout="quantum_tree",
        prominence={NODE_KIND_WAVEFUNCTION: 1.4},
        uses_quantum=True,
        description="Active wavefunctions and their alternate branches.",
    ),
    MODE_PSYKE: ModeProfile(
        name=MODE_PSYKE,
        visible_kinds=frozenset({
            NODE_KIND_THEME, NODE_KIND_LORE, NODE_KIND_OBJECT, NODE_KIND_OTHER,
        }),
        visible_edge_types=frozenset({EDGE_PSYKE_RELATION}),
        layout="circular",
        description="PSYKE semantic network (themes, lore, objects, other).",
    ),
    MODE_MEANING: ModeProfile(
        name=MODE_MEANING,
        visible_kinds=frozenset({
            NODE_KIND_CHARACTER, NODE_KIND_SCENE, NODE_KIND_THEME, NODE_KIND_ACT,
        }),
        visible_edge_types=frozenset({
            EDGE_PARTICIPATION, EDGE_CONTAINMENT, EDGE_PSYKE_RELATION,
        }),
        layout="circular",
        meaning_overlay=True,
        description="Symbolic resonance — state colors, importance, arcs.",
    ),
    # -- Screenplay-specific modes -------------------------------------------
    MODE_CAUSALITY: ModeProfile(
        name=MODE_CAUSALITY,
        visible_kinds=frozenset({NODE_KIND_SCENE, NODE_KIND_CHARACTER}),
        visible_edge_types=frozenset({EDGE_CAUSALITY, EDGE_PARTICIPATION}),
        layout="linear_timeline",
        prominence={NODE_KIND_SCENE: 1.1},
        description="Scene causality — consecutive scenes linked by shared characters.",
    ),
    MODE_SETUP_PAYOFF: ModeProfile(
        name=MODE_SETUP_PAYOFF,
        visible_kinds=frozenset({
            NODE_KIND_SCENE, NODE_KIND_THEME, NODE_KIND_OBJECT,
        }),
        visible_edge_types=frozenset({EDGE_SETUP_PAYOFF, EDGE_PSYKE_RELATION}),
        layout="circular",
        description="Setup/payoff — narrative plants and their resolutions.",
    ),
    MODE_KNOWLEDGE: ModeProfile(
        name=MODE_KNOWLEDGE,
        visible_kinds=frozenset({NODE_KIND_SCENE, NODE_KIND_CHARACTER}),
        visible_edge_types=frozenset({EDGE_KNOWLEDGE, EDGE_PARTICIPATION}),
        layout="circular",
        prominence={NODE_KIND_CHARACTER: 1.15},
        description="Character knowledge — who knows what and when.",
    ),
    MODE_SUBTEXT: ModeProfile(
        name=MODE_SUBTEXT,
        visible_kinds=frozenset({
            NODE_KIND_SCENE, NODE_KIND_THEME, NODE_KIND_CHARACTER,
        }),
        visible_edge_types=frozenset({EDGE_SUBTEXT, EDGE_PSYKE_RELATION}),
        layout="circular",
        prominence={NODE_KIND_THEME: 1.3},
        description="Subtext — hidden tensions and oppositions.",
    ),
    MODE_VISUAL_MOTIFS: ModeProfile(
        name=MODE_VISUAL_MOTIFS,
        visible_kinds=frozenset({
            NODE_KIND_SCENE, NODE_KIND_OBJECT, NODE_KIND_THEME,
        }),
        visible_edge_types=frozenset({EDGE_VISUAL_MOTIF, EDGE_PSYKE_RELATION}),
        layout="circular",
        prominence={NODE_KIND_OBJECT: 1.2},
        description="Visual motifs — recurring images and symbols.",
    ),
    MODE_CONTINUITY_GRAPH: ModeProfile(
        name=MODE_CONTINUITY_GRAPH,
        visible_kinds=frozenset({
            NODE_KIND_SCENE, NODE_KIND_CHARACTER, NODE_KIND_PLACE,
        }),
        visible_edge_types=frozenset({EDGE_CONTINUITY, EDGE_PARTICIPATION}),
        layout="linear_timeline",
        prominence={NODE_KIND_SCENE: 1.1},
        description="Continuity — tracked props, wounds, and states across scenes.",
    ),
    # -- Graphic Novel modes -------------------------------------------------
    MODE_GN_MOTIF: ModeProfile(
        name=MODE_GN_MOTIF,
        visible_kinds=frozenset({NODE_KIND_MOTIF, NODE_KIND_PAGE}),
        visible_edge_types=frozenset({EDGE_GN_MOTIF}),
        layout="theme_centered",
        prominence={NODE_KIND_MOTIF: 1.5},
        description="Visual motifs and the pages they appear on.",
    ),
    MODE_GN_PANEL_CAUSALITY: ModeProfile(
        name=MODE_GN_PANEL_CAUSALITY,
        visible_kinds=frozenset({NODE_KIND_PAGE, NODE_KIND_PANEL}),
        visible_edge_types=frozenset({EDGE_GN_PANEL_CAUSALITY, EDGE_GN_CONTAINS}),
        layout="linear_timeline",
        prominence={NODE_KIND_PAGE: 1.2},
        description="Panel flow / causality across the reading order.",
    ),
    MODE_GN_SYMBOL_RECURRENCE: ModeProfile(
        name=MODE_GN_SYMBOL_RECURRENCE,
        visible_kinds=frozenset({NODE_KIND_MOTIF, NODE_KIND_PAGE}),
        visible_edge_types=frozenset({EDGE_GN_SYMBOL_ECHO, EDGE_GN_MOTIF}),
        layout="circular",
        prominence={NODE_KIND_MOTIF: 1.4},
        description="Symbol recurrence — pages echoing the same motif.",
    ),
    MODE_GN_PAGE_RHYTHM: ModeProfile(
        name=MODE_GN_PAGE_RHYTHM,
        visible_kinds=frozenset({NODE_KIND_PAGE}),
        visible_edge_types=frozenset({EDGE_GN_PAGE_FLOW}),
        layout="linear_timeline",
        prominence={NODE_KIND_PAGE: 1.2},
        description="Page rhythm — reading progression through the pages.",
    ),
    MODE_GN_OBJECT_CONTINUITY: ModeProfile(
        name=MODE_GN_OBJECT_CONTINUITY,
        visible_kinds=frozenset({NODE_KIND_GN_OBJECT, NODE_KIND_PAGE}),
        visible_edge_types=frozenset({EDGE_GN_OBJECT_CONTINUITY}),
        layout="circular",
        prominence={NODE_KIND_GN_OBJECT: 1.3},
        description="Object continuity — where tracked objects reappear.",
    ),
    MODE_GN_CHARACTER: ModeProfile(
        name=MODE_GN_CHARACTER,
        visible_kinds=frozenset({NODE_KIND_CHARACTER, NODE_KIND_PAGE}),
        visible_edge_types=frozenset({EDGE_GN_CHARACTER_PRESENT}),
        layout="theme_centered",
        prominence={NODE_KIND_CHARACTER: 1.4},
        description="Character appearances — who appears on which pages.",
    ),
    # -- Stage Script modes --------------------------------------------------
    MODE_SS_PRESSURE: ModeProfile(
        name=MODE_SS_PRESSURE,
        visible_kinds=frozenset({NODE_KIND_CHARACTER}),
        visible_edge_types=frozenset({EDGE_SS_PRESSURE}),
        layout="circular",
        prominence={NODE_KIND_CHARACTER: 1.2},
        description="Character pressure — who pressures/confronts whom.",
    ),
    MODE_SS_ENTRANCE_EXIT: ModeProfile(
        name=MODE_SS_ENTRANCE_EXIT,
        visible_kinds=frozenset({NODE_KIND_SCENE, NODE_KIND_CHARACTER}),
        visible_edge_types=frozenset({EDGE_SS_ENTRANCE_EXIT}),
        layout="linear_timeline",
        prominence={NODE_KIND_SCENE: 1.1},
        description="Entrances/exits — who enters and leaves each scene.",
    ),
    MODE_SS_PROP: ModeProfile(
        name=MODE_SS_PROP,
        visible_kinds=frozenset({
            NODE_KIND_OBJECT, NODE_KIND_SCENE, NODE_KIND_CHARACTER,
        }),
        visible_edge_types=frozenset({EDGE_SS_USES_PROP}),
        layout="circular",
        prominence={NODE_KIND_OBJECT: 1.3},
        description="Prop continuity — who uses which prop, and where.",
    ),
    MODE_SS_BLOCKING: ModeProfile(
        name=MODE_SS_BLOCKING,
        visible_kinds=frozenset({NODE_KIND_SCENE, NODE_KIND_PLACE}),
        visible_edge_types=frozenset({EDGE_SS_BLOCKING}),
        layout="theme_centered",
        prominence={NODE_KIND_PLACE: 1.3},
        description="Blocking / spatial — scenes staged in each set location.",
    ),
    MODE_SS_SUBTEXT: ModeProfile(
        name=MODE_SS_SUBTEXT,
        visible_kinds=frozenset({NODE_KIND_CHARACTER}),
        visible_edge_types=frozenset({EDGE_SS_SUBTEXT}),
        layout="circular",
        prominence={NODE_KIND_CHARACTER: 1.15},
        description="Subtext conflict — opposing/avoiding stances.",
    ),
    MODE_SS_OFFSTAGE: ModeProfile(
        name=MODE_SS_OFFSTAGE,
        visible_kinds=frozenset({
            NODE_KIND_CHARACTER, NODE_KIND_OFFSTAGE, NODE_KIND_SCENE,
        }),
        visible_edge_types=frozenset({EDGE_SS_OFFSTAGE}),
        layout="circular",
        prominence={NODE_KIND_OFFSTAGE: 1.2},
        description="Offstage knowledge — events offstage and who is present.",
    ),
    # -- Series modes --------------------------------------------------------
    MODE_SR_SEASON_ARC: ModeProfile(
        name=MODE_SR_SEASON_ARC,
        visible_kinds=frozenset({
            NODE_KIND_SEASON, NODE_KIND_EPISODE, NODE_KIND_ARC,
            NODE_KIND_MYSTERY,
        }),
        visible_edge_types=frozenset({
            EDGE_SR_CONTAINS, EDGE_SR_CONTINUES, EDGE_SR_ESCALATES,
            EDGE_SR_SETS_UP, EDGE_SR_PAYS_OFF, EDGE_SR_RESOLVES,
        }),
        layout="linear_timeline",
        prominence={NODE_KIND_SEASON: 1.4},
        description="Season arc — seasons, their episodes, and arcs escalating across them.",
    ),
    MODE_SR_EPISODE_DEP: ModeProfile(
        name=MODE_SR_EPISODE_DEP,
        visible_kinds=frozenset({NODE_KIND_EPISODE}),
        visible_edge_types=frozenset({EDGE_SR_CONTINUES}),
        layout="linear_timeline",
        prominence={NODE_KIND_EPISODE: 1.2},
        description="Episode dependency — reading order / what each episode depends on.",
    ),
    MODE_SR_ABC_PLOT: ModeProfile(
        name=MODE_SR_ABC_PLOT,
        visible_kinds=frozenset({NODE_KIND_EPISODE, NODE_KIND_PLOTLINE}),
        visible_edge_types=frozenset({EDGE_SR_CONTAINS}),
        layout="theme_centered",
        prominence={NODE_KIND_PLOTLINE: 1.3},
        description="A/B/C plot — episodes and the plotlines they carry.",
    ),
    MODE_SR_MYSTERY: ModeProfile(
        name=MODE_SR_MYSTERY,
        visible_kinds=frozenset({
            NODE_KIND_EPISODE, NODE_KIND_MYSTERY, NODE_KIND_ARC,
        }),
        visible_edge_types=frozenset({
            EDGE_SR_SETS_UP, EDGE_SR_PAYS_OFF, EDGE_SR_RESOLVES,
            EDGE_SR_DELAYS,
        }),
        layout="circular",
        prominence={NODE_KIND_MYSTERY: 1.4},
        description="Mystery / payoff — setups tracked to their payoffs.",
    ),
    MODE_SR_CHARACTER: ModeProfile(
        name=MODE_SR_CHARACTER,
        visible_kinds=frozenset({NODE_KIND_CHARACTER, NODE_KIND_EPISODE}),
        visible_edge_types=frozenset({EDGE_SR_ECHOES}),
        layout="circular",
        prominence={NODE_KIND_CHARACTER: 1.2},
        description="Character progression — character state recorded across episodes.",
    ),
    MODE_SR_RELATIONSHIP: ModeProfile(
        name=MODE_SR_RELATIONSHIP,
        visible_kinds=frozenset({
            NODE_KIND_CHARACTER, NODE_KIND_EPISODE, NODE_KIND_ARC,
        }),
        visible_edge_types=frozenset({
            EDGE_SR_SETS_UP, EDGE_SR_PAYS_OFF, EDGE_SR_ECHOES,
        }),
        layout="circular",
        prominence={NODE_KIND_CHARACTER: 1.15},
        description="Relationship evolution — relationship arcs across the cast.",
    ),
    MODE_SR_CONTINUITY: ModeProfile(
        name=MODE_SR_CONTINUITY,
        visible_kinds=frozenset({NODE_KIND_CHARACTER, NODE_KIND_EPISODE}),
        visible_edge_types=frozenset({EDGE_SR_CONTRADICTS}),
        layout="circular",
        prominence={NODE_KIND_CHARACTER: 1.2},
        description="Continuity risk — flagged states and the episodes they touch.",
    ),
}

MODE_ORDER: tuple[str, ...] = (
    MODE_ALL, MODE_RELATIONSHIP, MODE_THEME, MODE_STRUCTURE,
    MODE_QUANTUM, MODE_PSYKE, MODE_MEANING,
)

SCREENPLAY_MODE_ORDER: tuple[str, ...] = (
    MODE_CAUSALITY, MODE_SETUP_PAYOFF, MODE_KNOWLEDGE,
    MODE_SUBTEXT, MODE_VISUAL_MOTIFS, MODE_CONTINUITY_GRAPH,
)

GRAPHIC_NOVEL_MODE_ORDER: tuple[str, ...] = (
    MODE_GN_MOTIF, MODE_GN_PANEL_CAUSALITY, MODE_GN_SYMBOL_RECURRENCE,
    MODE_GN_PAGE_RHYTHM, MODE_GN_OBJECT_CONTINUITY, MODE_GN_CHARACTER,
)

STAGE_SCRIPT_MODE_ORDER: tuple[str, ...] = (
    MODE_SS_PRESSURE, MODE_SS_ENTRANCE_EXIT, MODE_SS_PROP,
    MODE_SS_BLOCKING, MODE_SS_SUBTEXT, MODE_SS_OFFSTAGE,
)

SERIES_MODE_ORDER: tuple[str, ...] = (
    MODE_SR_SEASON_ARC, MODE_SR_EPISODE_DEP, MODE_SR_ABC_PLOT,
    MODE_SR_MYSTERY, MODE_SR_CHARACTER, MODE_SR_RELATIONSHIP,
    MODE_SR_CONTINUITY,
)


def get_mode_profile(mode: str) -> ModeProfile:
    return MODE_PROFILES.get(mode, MODE_PROFILES[MODE_ALL])

def node_kind(node: "GraphNode") -> str:
    """Resolve the semantic kind of a node — uses subtype when available."""
    if node.subtype:
        return node.subtype
    etype = (node.etype or "").lower()
    if etype in {NODE_KIND_CHARACTER, NODE_KIND_PLACE, NODE_KIND_SCENE,
                 NODE_KIND_NOTE, NODE_KIND_ACT}:
        return etype
    if node.etype == "PSYKE":
        return NODE_KIND_OTHER
    return NODE_KIND_OTHER


_NODE_RADIUS = 22
_FOCUS_RADIUS = 28
_GRAPH_RADIUS = 200
_EDGE_COLOR = "#4a5568"
_EDGE_HIGHLIGHT = "#4ade80"
_DIM_OPACITY = 0.25

# Zoom thresholds — below these, parts of the graph are progressively hidden.
_ZOOM_HIDE_LABELS = 0.6
_ZOOM_HIDE_MENTIONS = 0.5
_ZOOM_HIDE_WEAK_EDGES = 0.3

_ARC_PALETTE = ["#42a5f5", "#ab47bc", "#ef5350", "#26a69a", "#ffa726", "#78909c"]


def _arc_color(plotline: str) -> str:
    idx = hash(plotline) % len(_ARC_PALETTE)
    return _ARC_PALETTE[idx]


# Filter presets (§2): name → predicate over node kinds / id prefixes.
def gn_filter_node_ids(data: GraphData, filter_name: str) -> set[str]:
    """Return node ids matching a graphic-novel filter preset.

    "motifs", "pages", "panel_continuity" (pages + panels),
    "symbolic_echoes" (motifs + pages).
    """
    kinds_by_filter = {
        "motifs": {NODE_KIND_MOTIF},
        "pages": {NODE_KIND_PAGE},
        "panels": {NODE_KIND_PANEL},
        "panel_continuity": {NODE_KIND_PAGE, NODE_KIND_PANEL},
        "symbolic_echoes": {NODE_KIND_MOTIF, NODE_KIND_PAGE},
        "objects": {NODE_KIND_GN_OBJECT, NODE_KIND_PAGE},
        "characters": {NODE_KIND_CHARACTER},
        "character_appearances": {NODE_KIND_CHARACTER, NODE_KIND_PAGE},
    }
    kinds = kinds_by_filter.get(filter_name, set())
    return {nid for nid, node in data.nodes.items() if node_kind(node) in kinds}


def ss_filter_node_ids(data: GraphData, filter_name: str) -> set[str]:
    """Return node ids matching a stage-script filter preset.

    "characters_on_stage", "props", "entrances_exits" (characters +
    scenes), "cue_relations" (cues + scenes), "conflict_pressure"
    (characters), "offstage_events" (offstage + scenes).
    """
    kinds_by_filter = {
        "characters_on_stage": {NODE_KIND_CHARACTER},
        "props": {NODE_KIND_OBJECT},
        "entrances_exits": {NODE_KIND_CHARACTER, NODE_KIND_SCENE},
        "cue_relations": {NODE_KIND_CUE, NODE_KIND_SCENE},
        "conflict_pressure": {NODE_KIND_CHARACTER},
        "offstage_events": {NODE_KIND_OFFSTAGE, NODE_KIND_SCENE},
    }
    kinds = kinds_by_filter.get(filter_name, set())
    return {nid for nid, node in data.nodes.items() if node_kind(node) in kinds}


def series_filter_node_ids(data: GraphData, filter_name: str) -> set[str]:
    """Return node ids matching a series filter preset (§2).

    "season" / "seasons" (seasons + episodes), "episode"/"episodes"
    (episodes), "arcs"/"active_arcs"/"unresolved" (arcs + mysteries),
    "character"/"characters", "mystery"/"mystery_thread" (mysteries +
    episodes).
    """
    kinds_by_filter = {
        "season": {NODE_KIND_SEASON, NODE_KIND_EPISODE},
        "seasons": {NODE_KIND_SEASON, NODE_KIND_EPISODE},
        "episode": {NODE_KIND_EPISODE},
        "episodes": {NODE_KIND_EPISODE},
        "arcs": {NODE_KIND_ARC, NODE_KIND_MYSTERY},
        "active_arcs": {NODE_KIND_ARC, NODE_KIND_MYSTERY},
        "unresolved": {NODE_KIND_ARC, NODE_KIND_MYSTERY},
        "character": {NODE_KIND_CHARACTER},
        "characters": {NODE_KIND_CHARACTER},
        "mystery": {NODE_KIND_MYSTERY, NODE_KIND_EPISODE},
        "mystery_thread": {NODE_KIND_MYSTERY, NODE_KIND_EPISODE},
    }
    kinds = kinds_by_filter.get(filter_name, set())
    return {nid for nid, node in data.nodes.items() if node_kind(node) in kinds}


def series_default_node_ids(
    db: Database, project_id: int, data: GraphData,
) -> set[str]:
    """The non-hairball default view (§4): current season overview + active
    arcs only — the current season node, its episodes, and arcs still open
    (active/delayed). Empty set means "no restriction" (no series data)."""
    seasons = db.get_seasons(project_id)
    if not seasons:
        return set()
    current = seasons[-1]  # highest order_index = the current season
    keep: set[str] = set()
    snode = f"Season:{current.id}"
    if snode in data.nodes:
        keep.add(snode)
    for ep in db.get_episodes_for_season(current.id):
        enode = f"Episode:{ep.id}"
        if enode in data.nodes:
            keep.add(enode)
    for arc in db.get_series_arcs(project_id):
        if arc.status in ("active", "delayed"):
            anode = f"SeriesArc:{arc.id}"
            if anode in data.nodes:
                keep.add(anode)
    return keep


def default_skeleton_layers() -> frozenset[str]:
    """The minimal narrative skeleton: characters, themes, acts."""
    return SKELETON_LAYERS


def filter_by_layers(data: GraphData, layers: set[str]) -> set[str]:
    """Return node IDs whose semantic kind is in *layers*.

    Empty set means 'no layers active' → returns empty.
    """
    if not layers:
        return set()
    return {nid for nid, node in data.nodes.items() if node_kind(node) in layers}


def get_neighborhood(data: GraphData, node_id: str, hops: int = 1) -> set[str]:
    """Get all nodes within N hops of the given node."""
    visited: set[str] = {node_id}
    frontier: set[str] = {node_id}

    for _ in range(hops):
        next_frontier: set[str] = set()
        for nid in frontier:
            for neighbor in data.adjacency.get(nid, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier

    return visited


def filter_by_type(data: GraphData, allowed_types: set[str]) -> set[str]:
    """Return node IDs matching the allowed types."""
    if not allowed_types:
        return set(data.nodes.keys())
    return {nid for nid, node in data.nodes.items() if node.etype in allowed_types}


def filter_by_scene_order(
    db: Database, project_id: int, data: GraphData, max_order: int,
) -> set[str]:
    """Return nodes active at or before the given scene order."""
    scenes = db.get_all_scenes(project_id)
    active_scene_ids = {s.id for s in scenes if s.sort_order <= max_order}
    active_scene_node_ids = {f"Scene:{sid}" for sid in active_scene_ids}

    active_char_ids: set[int] = set()
    active_place_ids: set[int] = set()
    for sid in active_scene_ids:
        active_char_ids.update(db.get_scene_character_ids(sid))
        active_place_ids.update(db.get_scene_place_ids(sid))

    active = set()
    for nid, node in data.nodes.items():
        if node.etype == "Scene" and nid in active_scene_node_ids:
            active.add(nid)
        elif node.etype == "Character" and node.entity_id in active_char_ids:
            active.add(nid)
        elif node.etype == "Place" and node.entity_id in active_place_ids:
            active.add(nid)
        elif node.etype == "PSYKE":
            active.add(nid)
        elif node.etype == "Note":
            active.add(nid)

    return active


# =============================================================================
# UI Widget
# =============================================================================

class _NodeInteractionMixin:
    """Click + hover behaviour shared across node shapes."""

    def _init_interaction(
        self, node_id: str,
        on_click: Callable[[str], None] | None,
        on_hover: Callable[[str, bool], None] | None,
    ) -> None:
        self.node_id = node_id
        self._on_click = on_click
        self._on_hover = on_hover
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if self._on_click and event.button() == Qt.MouseButton.LeftButton:
            # Defer: the handler rebuilds the scene (deleting THIS item), so run
            # it after the press/release cycle finishes. Calling it inline left a
            # dangling grab on a freed C++ item ("Internal C++ object already
            # deleted"). Capture the callback + id, never `self`, past the rebuild.
            cb, nid = self._on_click, self.node_id
            QTimer.singleShot(0, lambda: cb(nid))
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event) -> None:
        if self._on_hover:
            self._on_hover(self.node_id, True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        if self._on_hover:
            self._on_hover(self.node_id, False)
        super().hoverLeaveEvent(event)


class _FocusNode(_NodeInteractionMixin, QGraphicsEllipseItem):
    """Clickable, hoverable graph node — ellipse shape (back-compat)."""

    def __init__(
        self, x: float, y: float, radius: float,
        node_id: str,
        on_click: Callable[[str], None] | None = None,
        on_hover: Callable[[str, bool], None] | None = None,
    ) -> None:
        QGraphicsEllipseItem.__init__(
            self, x - radius, y - radius, radius * 2, radius * 2,
        )
        self._init_interaction(node_id, on_click, on_hover)


class _PolygonNode(_NodeInteractionMixin, QGraphicsPolygonItem):
    """Clickable, hoverable polygon node (triangle, diamond, hexagon)."""

    def __init__(
        self, polygon: "QPolygonF",
        node_id: str,
        on_click: Callable[[str], None] | None = None,
        on_hover: Callable[[str, bool], None] | None = None,
    ) -> None:
        QGraphicsPolygonItem.__init__(self, polygon)
        self._init_interaction(node_id, on_click, on_hover)


class _RectNode(_NodeInteractionMixin, QGraphicsRectItem):
    """Clickable, hoverable rect node (square, scene)."""

    def __init__(
        self, x: float, y: float, w: float, h: float,
        node_id: str,
        on_click: Callable[[str], None] | None = None,
        on_hover: Callable[[str, bool], None] | None = None,
    ) -> None:
        QGraphicsRectItem.__init__(self, x - w / 2, y - h / 2, w, h)
        self._init_interaction(node_id, on_click, on_hover)


def _make_shape_node(
    kind: str, x: float, y: float, radius: float, node_id: str,
    on_click: Callable[[str], None] | None,
    on_hover: Callable[[str, bool], None] | None,
):
    """Factory: return a node graphics-item matching the kind's shape."""
    shape = _KIND_SHAPES.get(kind, "circle")

    if shape == "small_circle":
        return _FocusNode(x, y, radius * 0.7, node_id, on_click, on_hover)
    if shape == "circle":
        return _FocusNode(x, y, radius, node_id, on_click, on_hover)
    if shape == "square":
        side = radius * 1.7
        return _RectNode(x, y, side, side, node_id, on_click, on_hover)
    if shape == "rounded_rect":
        return _RectNode(x, y, radius * 2.2, radius * 1.5, node_id, on_click, on_hover)
    if shape == "act_band":
        return _RectNode(x, y, radius * 3.0, radius * 1.4, node_id, on_click, on_hover)
    if shape == "triangle":
        h = radius * 1.7
        poly = QPolygonF([
            QPointF(x, y - h),
            QPointF(x - h * 0.9, y + h * 0.7),
            QPointF(x + h * 0.9, y + h * 0.7),
        ])
        return _PolygonNode(poly, node_id, on_click, on_hover)
    if shape == "diamond":
        r = radius * 1.2
        poly = QPolygonF([
            QPointF(x, y - r), QPointF(x + r, y),
            QPointF(x, y + r), QPointF(x - r, y),
        ])
        return _PolygonNode(poly, node_id, on_click, on_hover)
    if shape == "hexagon":
        r = radius
        pts = []
        for i in range(6):
            angle = math.pi / 3 * i - math.pi / 2
            pts.append(QPointF(x + r * math.cos(angle), y + r * math.sin(angle)))
        return _PolygonNode(QPolygonF(pts), node_id, on_click, on_hover)
    # Fallback
    return _FocusNode(x, y, radius, node_id, on_click, on_hover)


class _ZoomGraphicsView(QGraphicsView):
    """QGraphicsView with smooth zoom (wheel) + drag pan + antialiasing."""

    def __init__(self, scene, on_zoom: Callable[[float], None] | None = None) -> None:
        super().__init__(scene)
        from PySide6.QtGui import QPainter
        self._on_zoom = on_zoom
        self._zoom = 1.0
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform,
        )
        # Subtle visual cleanup — no border on the viewport.
        self.setFrameShape(self.Shape.NoFrame)

    def wheelEvent(self, event) -> None:
        if event.angleDelta().y() > 0:
            factor = 1.15
        else:
            factor = 1 / 1.15
        new_zoom = self._zoom * factor
        # Clamp to a sane range.
        new_zoom = max(0.1, min(5.0, new_zoom))
        actual = new_zoom / self._zoom
        self._zoom = new_zoom
        self.scale(actual, actual)
        if self._on_zoom:
            self._on_zoom(self._zoom)

    def current_zoom(self) -> float:
        return self._zoom

    def reset_zoom(self) -> None:
        if self._zoom == 1.0:
            return
        actual = 1.0 / self._zoom
        self._zoom = 1.0
        self.scale(actual, actual)
        if self._on_zoom:
            self._on_zoom(self._zoom)


class FocusGraphView(QWidget):
    """Graph with focus-based exploration, temporal filter, and search."""

    def __init__(
        self,
        db: Database,
        project_id: int,
        on_node_selected: Callable[[str, int], None] | None = None,
        on_send_to_assistant: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_node_selected = on_node_selected
        self._on_send_to_assistant = on_send_to_assistant

        try:
            project = db.get_project_by_id(project_id)
            from logosforge.project_compat import (
                get_project_narrative_engine,
                is_screenplay_project,
            )
            self._screenplay_mode = is_screenplay_project(project)
            _engine = get_project_narrative_engine(project)
            self._graphic_novel_mode = _engine == "graphic_novel"
            self._stage_script_mode = _engine == "stage_script"
            self._series_mode = _engine == "series"
        except Exception:
            self._screenplay_mode = False
            self._graphic_novel_mode = False
            self._stage_script_mode = False
            self._series_mode = False
        # Series default view (§4): restrict to current season + active arcs
        # until the user changes mode or focuses a node.
        self._series_default_active = self._series_mode

        self._graph_data: GraphData | None = None
        self._focus_node: str | None = None
        self._hops = 1
        self._type_filter: str = "All"
        self._temporal_enabled = False
        self._temporal_max_order: int = 9999
        self._show_future = False
        self._meaning_enabled = False
        self._meaning_data: MeaningData | None = None
        self._suggestions_visible = False
        self._suggestions = None  # GraphSuggestions | None
        self._trace_highlight: list[str] = []
        # Layers panel — which semantic kinds are visible.  Default: all.
        self._active_layers: set[str] = set(LAYER_KINDS)
        self._layer_checks: dict[str, QCheckBox] = {}
        self._zoom: float = 1.0
        # Narrative mode — controls layout, filters, and prominence.
        self._mode: str = MODE_ALL
        self._mode_buttons: dict[str, QPushButton] = {}
        # Quantum data only loaded when entering Quantum mode.
        self._quantum_nodes: dict[str, GraphNode] = {}
        self._quantum_edges: list[GraphEdge] = []
        # Story Gravity — narrative-importance weights per node.
        self._gravity_enabled: bool = True
        self._gravity_map: dict[str, StoryGravity] = {}
        # Temporal narrative flow — story-order overlay.
        self._flow_enabled: bool = False
        self._flow_type: str = FLOW_TIMELINE
        # Graph analysis panel — per-node digest + global insights.
        self._analysis_visible: bool = False
        self._last_node_analysis: NodeAnalysis | None = None
        self._last_insights: list[GraphInsight] = []
        # Edge-type visibility — Mention edges are noisy, default off so the
        # graph reads as semantic structure, not link spaghetti.
        self._edge_visibility: dict[str, bool] = {
            EDGE_MENTION: False,
            EDGE_PARTICIPATION: True,
            EDGE_CONTAINMENT: True,
            EDGE_PSYKE_RELATION: True,
            EDGE_QUANTUM: True,
            EDGE_LINK: True,
            EDGE_CAUSALITY: True,
            EDGE_SETUP_PAYOFF: True,
            EDGE_KNOWLEDGE: True,
            EDGE_SUBTEXT: True,
            EDGE_VISUAL_MOTIF: True,
            EDGE_CONTINUITY: True,
            EDGE_GN_CONTAINS: True,
            EDGE_GN_PAGE_FLOW: True,
            EDGE_GN_PANEL_CAUSALITY: True,
            EDGE_GN_MOTIF: True,
            EDGE_GN_SYMBOL_ECHO: True,
            EDGE_GN_OBJECT_CONTINUITY: True,
            EDGE_GN_CHARACTER_PRESENT: True,
            EDGE_GN_PSYKE_MOTIF: True,
            EDGE_SS_PRESSURE: True,
            EDGE_SS_SUBTEXT: True,
            EDGE_SS_ENTRANCE_EXIT: True,
            EDGE_SS_USES_PROP: True,
            EDGE_SS_BLOCKING: True,
            EDGE_SS_CUE: True,
            EDGE_SS_OFFSTAGE: True,
            EDGE_SR_CONTAINS: True,
            EDGE_SR_CONTINUES: True,
            EDGE_SR_SETS_UP: True,
            EDGE_SR_PAYS_OFF: True,
            EDGE_SR_RESOLVES: True,
            EDGE_SR_DELAYS: True,
            EDGE_SR_ESCALATES: True,
            EDGE_SR_ECHOES: True,
            EDGE_SR_CONTRADICTS: True,
        }

        self._node_items: dict[str, object] = {}
        self._label_items: dict[str, QGraphicsSimpleTextItem] = {}
        self._edge_items: list[QGraphicsLineItem] = []

        # Graph readability controls (Slice: structural viz + compact menus).
        self._label_mode = "important"      # none | focus | important | all
        self._layout_override = ""          # "" = use the mode's layout
        self._hide_isolated = False

        self._build_ui()
        if self._series_mode:
            # Default to the Season Arc view (current season + active arcs),
            # not a full-series hairball.
            self._on_mode_changed(MODE_SR_SEASON_ARC, user=False)
        elif self._graphic_novel_mode:
            # Default to a focused GN mode (motifs, else page rhythm) so the
            # graph never opens as a full all-node hairball.
            try:
                self._on_mode_changed(
                    gn_default_mode(self._db, self._project_id), user=False,
                )
            except Exception:
                pass
        else:
            # Default to Structure (Acts → Scenes), not a full hairball.
            self._on_mode_changed(MODE_STRUCTURE, user=False)
        self.refresh()

    # -- Persistence --------------------------------------------------------

    def _capture_state(self) -> dict:
        """Snapshot the user-visible filters & toggles."""
        return {
            "mode": self._mode,
            "layers": sorted(self._active_layers),
            "gravity": self._gravity_enabled,
            "flow_enabled": self._flow_enabled,
            "flow_type": self._flow_type,
            "edge_visibility": dict(self._edge_visibility),
            "skeleton": self._skeleton_btn.isChecked()
                if hasattr(self, "_skeleton_btn") else False,
        }

    def _apply_state(self, state: dict) -> None:
        """Restore a previously captured state (best-effort)."""
        if not isinstance(state, dict):
            return
        mode = state.get("mode")
        if mode in MODE_PROFILES:
            self._on_mode_changed(mode)
        layers = state.get("layers")
        if isinstance(layers, list):
            kept = {k for k in layers if k in LAYER_KINDS}
            if kept:
                self._active_layers = kept
                for kind, cb in self._layer_checks.items():
                    cb.blockSignals(True)
                    cb.setChecked(kind in kept)
                    cb.blockSignals(False)
        if isinstance(state.get("gravity"), bool):
            self._gravity_enabled = state["gravity"]
            self._gravity_check.blockSignals(True)
            self._gravity_check.setChecked(self._gravity_enabled)
            self._gravity_check.blockSignals(False)
        if isinstance(state.get("flow_enabled"), bool):
            self._flow_enabled = state["flow_enabled"]
            self._flow_check.blockSignals(True)
            self._flow_check.setChecked(self._flow_enabled)
            self._flow_check.blockSignals(False)
        ft = state.get("flow_type")
        if isinstance(ft, str) and ft in FLOW_TYPES:
            self._flow_type = ft
            idx = self._flow_combo.findData(ft)
            if idx >= 0:
                self._flow_combo.blockSignals(True)
                self._flow_combo.setCurrentIndex(idx)
                self._flow_combo.blockSignals(False)
        ev = state.get("edge_visibility")
        if isinstance(ev, dict):
            for k, v in ev.items():
                if isinstance(v, bool):
                    self._edge_visibility[k] = v
        self._flow_combo.setEnabled(self._flow_enabled)
        self._rebuild_view()

    def _graph_state_key(self) -> str:
        """Project-scoped settings key for the graph view state."""
        return f"graph_state:{self._project_id}"

    def _graph_presets_key(self) -> str:
        return f"graph_presets:{self._project_id}"

    def restore_persisted_state(self) -> None:
        """Restore last-saved filter/mode/flow state for THIS project.

        Not called automatically — the host (MainWindow) calls this after
        construction so that headless tests stay isolated from the user's
        ~/.logosforge/settings.json file.
        """
        try:
            from logosforge.settings import get_manager
            state = get_manager().get(self._graph_state_key())
        except Exception:
            return
        if isinstance(state, dict) and state:
            self._apply_state(state)

    def _persist_state(self) -> None:
        try:
            from logosforge.settings import get_manager
            get_manager().set(self._graph_state_key(), self._capture_state())
        except Exception:
            pass

    def get_saved_presets(self) -> dict[str, dict]:
        try:
            from logosforge.settings import get_manager
            raw = get_manager().get(self._graph_presets_key()) or {}
        except Exception:
            return {}
        return raw if isinstance(raw, dict) else {}

    def save_preset(self, name: str) -> None:
        """Persist the current filter / mode state under *name*."""
        if not name:
            return
        try:
            from logosforge.settings import get_manager
            mgr = get_manager()
            presets = mgr.get(self._graph_presets_key()) or {}
            if not isinstance(presets, dict):
                presets = {}
            presets[name] = self._capture_state()
            mgr.set(self._graph_presets_key(), presets)
        except Exception:
            return

    def load_preset(self, name: str) -> bool:
        presets = self.get_saved_presets()
        state = presets.get(name)
        if not isinstance(state, dict):
            return False
        self._apply_state(state)
        return True

    def delete_preset(self, name: str) -> None:
        try:
            from logosforge.settings import get_manager
            mgr = get_manager()
            presets = mgr.get(self._graph_presets_key()) or {}
            if not isinstance(presets, dict):
                return
            presets.pop(name, None)
            mgr.set(self._graph_presets_key(), presets)
        except Exception:
            return

    def _refresh_preset_combo(self) -> None:
        if not hasattr(self, "_preset_combo"):
            return
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        self._preset_combo.addItem("— select —")
        for name in sorted(self.get_saved_presets().keys()):
            self._preset_combo.addItem(name)
        self._preset_combo.blockSignals(False)

    def _on_preset_picked(self, name: str) -> None:
        if not name or name.startswith("—"):
            return
        self.load_preset(name)

    def _on_save_preset_clicked(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, "Save Graph Preset", "Preset name:",
        )
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        self.save_preset(name)
        self._refresh_preset_combo()
        # Highlight the saved preset in the combo.
        idx = self._preset_combo.findText(name)
        if idx >= 0:
            self._preset_combo.blockSignals(True)
            self._preset_combo.setCurrentIndex(idx)
            self._preset_combo.blockSignals(False)

    def _build_ui(self) -> None:
        # Accept keyboard focus so arrow-key navigation works.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- Compact top bar: Search + grouped dropdown menus ----------------
        topbar = QWidget()
        topbar.setObjectName("graphTopBar")
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(10, 6, 10, 6)
        tb.setSpacing(6)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search node…")
        self._search_input.setMaximumWidth(200)
        self._search_input.returnPressed.connect(self._on_search)
        # Editing clears any "no match" indicator from a prior search.
        self._search_input.textChanged.connect(
            lambda *_: self._set_search_nomatch(False))
        tb.addWidget(self._search_input)

        self._clear_btn = QPushButton("Clear Focus")
        self._clear_btn.setFlat(True)
        self._clear_btn.setEnabled(False)   # enabled only while a node is focused
        self._clear_btn.clicked.connect(self.clear_focus)
        tb.addWidget(self._clear_btn)

        # Breadcrumb: focusing a node shrinks the graph to its neighbourhood, so
        # say so explicitly (which node, how many hops) — otherwise users don't
        # realise the full graph is hidden or how to get back.
        self._focus_label = QLabel("")
        self._focus_label.setObjectName("graphFocusLabel")
        self._focus_label.setStyleSheet(f"color: {theme.ACCENT}; font-size: 11px;")
        self._focus_label.setVisible(False)
        tb.addWidget(self._focus_label)

        tb.addStretch()

        self._mode_menu_btn = self._build_mode_menu_button()
        self._filters_menu_btn = self._build_filters_menu_button()
        self._layout_menu_btn = self._build_layout_menu_button()
        self._labels_menu_btn = self._build_labels_menu_button()
        self._actions_menu_btn = self._build_actions_menu_button()
        for _btn in (
            self._mode_menu_btn, self._filters_menu_btn, self._layout_menu_btn,
            self._labels_menu_btn, self._actions_menu_btn,
        ):
            tb.addWidget(_btn)

        outer.addWidget(topbar)

        # -- Main area: graph + suggestion / analysis panels -----------------
        content_area = QWidget()
        content_layout = QHBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._gscene = QGraphicsScene()
        self._gview = _ZoomGraphicsView(self._gscene, on_zoom=self._on_zoom)
        self._gview.setObjectName("focusGraphView")
        self._gview.setRenderHints(self._gview.renderHints())
        content_layout.addWidget(self._gview, stretch=3)

        self._suggest_panel = QFrame()
        self._suggest_panel.setObjectName("suggestPanel")
        self._suggest_panel.setMaximumWidth(280)
        self._suggest_panel.setMinimumWidth(200)
        sp_layout = QVBoxLayout(self._suggest_panel)
        sp_layout.setContentsMargins(8, 8, 8, 8)
        sp_layout.setSpacing(4)
        self._suggest_panel.hide()
        content_layout.addWidget(self._suggest_panel, stretch=1)

        self._analysis_panel = QFrame()
        self._analysis_panel.setObjectName("analysisPanel")
        self._analysis_panel.setMaximumWidth(320)
        self._analysis_panel.setMinimumWidth(220)
        ap_layout = QVBoxLayout(self._analysis_panel)
        ap_layout.setContentsMargins(8, 8, 8, 8)
        ap_layout.setSpacing(4)
        self._analysis_panel.hide()
        content_layout.addWidget(self._analysis_panel, stretch=1)

        outer.addWidget(content_area)

    # -- Compact dropdown menus ----------------------------------------------

    @staticmethod
    def _menu_button(text: str) -> tuple[QPushButton, QMenu]:
        btn = QPushButton(text)          # Qt draws its own menu-indicator arrow
        btn.setFlat(True)
        menu = QMenu(btn)
        btn.setMenu(menu)
        return btn, menu

    @staticmethod
    def _add_widget(menu: QMenu, widget: QWidget) -> None:
        act = QWidgetAction(menu)
        act.setDefaultWidget(widget)
        menu.addAction(act)

    def _build_mode_menu_button(self) -> QPushButton:
        btn, menu = self._menu_button("Mode")
        base_labels = {
            MODE_ALL: "All", MODE_RELATIONSHIP: "Relationships",
            MODE_THEME: "Themes", MODE_STRUCTURE: "Structure",
            MODE_QUANTUM: "Quantum", MODE_PSYKE: "PSYKE",
            MODE_MEANING: "Meaning",
        }

        def add_modes(order, labels, header=None):
            if header:
                menu.addSeparator()
            for m in order:
                b = QPushButton(labels[m])
                b.setCheckable(True)
                b.setFlat(True)
                b.setToolTip(MODE_PROFILES[m].description)
                b.clicked.connect(lambda _=False, mm=m: self._on_mode_changed(mm))
                self._add_widget(menu, b)
                self._mode_buttons[m] = b

        add_modes(MODE_ORDER, base_labels)
        self._mode_buttons[MODE_STRUCTURE].setChecked(True)
        if self._screenplay_mode:
            add_modes(SCREENPLAY_MODE_ORDER, {
                MODE_CAUSALITY: "Causality", MODE_SETUP_PAYOFF: "Setup/Payoff",
                MODE_KNOWLEDGE: "Knowledge", MODE_SUBTEXT: "Subtext",
                MODE_VISUAL_MOTIFS: "Motifs", MODE_CONTINUITY_GRAPH: "Continuity",
            }, header=True)
        if self._graphic_novel_mode:
            add_modes(GRAPHIC_NOVEL_MODE_ORDER, {
                MODE_GN_MOTIF: "Motifs", MODE_GN_PANEL_CAUSALITY: "Panel Flow",
                MODE_GN_SYMBOL_RECURRENCE: "Symbols",
                MODE_GN_PAGE_RHYTHM: "Page Rhythm",
                MODE_GN_OBJECT_CONTINUITY: "Objects", MODE_GN_CHARACTER: "Characters",
            }, header=True)
        if self._stage_script_mode:
            add_modes(STAGE_SCRIPT_MODE_ORDER, {
                MODE_SS_PRESSURE: "Pressure", MODE_SS_ENTRANCE_EXIT: "Entrances",
                MODE_SS_PROP: "Props", MODE_SS_BLOCKING: "Blocking",
                MODE_SS_SUBTEXT: "Subtext", MODE_SS_OFFSTAGE: "Offstage",
            }, header=True)
        if self._series_mode:
            add_modes(SERIES_MODE_ORDER, {
                MODE_SR_SEASON_ARC: "Season Arc", MODE_SR_EPISODE_DEP: "Episodes",
                MODE_SR_ABC_PLOT: "A/B/C", MODE_SR_MYSTERY: "Mystery/Payoff",
                MODE_SR_CHARACTER: "Progression", MODE_SR_RELATIONSHIP: "Relationships",
                MODE_SR_CONTINUITY: "Continuity",
            }, header=True)
        return btn

    def _build_filters_menu_button(self) -> QPushButton:
        btn, menu = self._menu_button("Filters")
        labels = {
            NODE_KIND_CHARACTER: "Characters", NODE_KIND_PLACE: "Places",
            NODE_KIND_OBJECT: "Objects", NODE_KIND_THEME: "Themes",
            NODE_KIND_LORE: "Lore", NODE_KIND_SCENE: "Scenes",
            NODE_KIND_ACT: "Acts", NODE_KIND_NOTE: "Notes",
            NODE_KIND_OTHER: "Other",
        }
        for kind in LAYER_KINDS:
            cb = QCheckBox(labels[kind])
            cb.setChecked(True)
            cb.toggled.connect(lambda c, k=kind: self._on_layer_toggled(k, c))
            self._add_widget(menu, cb)
            self._layer_checks[kind] = cb

        menu.addSeparator()
        self._hops_check = QCheckBox("Show 2-hop")
        self._hops_check.setToolTip("Expand to 2-hop neighbours")
        self._hops_check.toggled.connect(self._on_hops_toggled)
        self._add_widget(menu, self._hops_check)

        self._hide_isolated_check = QCheckBox("Hide isolated")
        self._hide_isolated_check.toggled.connect(self._on_hide_isolated_toggled)
        self._add_widget(menu, self._hide_isolated_check)

        self._temporal_check = QCheckBox("Temporal")
        self._temporal_check.setToolTip("Filter by story progression")
        self._temporal_check.toggled.connect(self._on_temporal_toggled)
        self._add_widget(menu, self._temporal_check)

        self._future_check = QCheckBox("Show future")
        self._future_check.setToolTip("Dim future nodes instead of hiding")
        self._future_check.setEnabled(False)
        self._future_check.toggled.connect(self._on_future_toggled)
        self._add_widget(menu, self._future_check)

        self._skeleton_btn = QPushButton("Skeleton only")
        self._skeleton_btn.setCheckable(True)
        self._skeleton_btn.setFlat(True)
        self._skeleton_btn.setToolTip("Narrative skeleton — Characters + Themes + Acts")
        self._skeleton_btn.toggled.connect(self._on_skeleton_toggled)
        self._add_widget(menu, self._skeleton_btn)

        self._mention_check = QCheckBox("Mention edges")
        self._mention_check.setChecked(self._edge_visibility.get(EDGE_MENTION, False))
        self._mention_check.toggled.connect(self._on_mentions_toggled)
        self._add_widget(menu, self._mention_check)

        # Kept for back-compat with the old single-type filter API.
        self._type_combo = QComboBox()
        self._type_combo.addItems(["All", "Character", "Place", "Scene", "Note", "PSYKE"])
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        self._type_combo.setVisible(False)
        return btn

    def _build_layout_menu_button(self) -> QPushButton:
        btn, menu = self._menu_button("Layout")
        self._layout_group = QActionGroup(menu)
        self._layout_group.setExclusive(True)
        options = [
            ("Auto", ""), ("Hierarchical", "hierarchical"),
            ("Act clusters", "act_clusters"), ("Timeline flow", "timeline"),
            ("Radial", "radial"), ("Force", "force"),
        ]
        for label, key in options:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(key == self._layout_override)
            self._layout_group.addAction(act)
            act.triggered.connect(lambda _=False, k=key: self._set_layout_override(k))

        menu.addSeparator()
        self._flow_check = QCheckBox("Flow overlay")
        self._flow_check.setToolTip("Draw the story's order as a path through scenes")
        self._flow_check.toggled.connect(self._on_flow_toggled)
        self._add_widget(menu, self._flow_check)
        self._flow_combo = QComboBox()
        self._flow_combo.addItem("Timeline", userData=FLOW_TIMELINE)
        self._flow_combo.addItem("Acts", userData=FLOW_ACTS)
        self._flow_combo.addItem("Arc", userData=FLOW_ARC)
        self._flow_combo.addItem("Causal", userData=FLOW_CAUSAL)
        self._flow_combo.setEnabled(False)
        self._flow_combo.currentIndexChanged.connect(self._on_flow_type_changed)
        self._add_widget(menu, self._flow_combo)
        return btn

    def _build_labels_menu_button(self) -> QPushButton:
        btn, menu = self._menu_button("Labels")
        self._label_group = QActionGroup(menu)
        self._label_group.setExclusive(True)
        for label, key in [("None", "none"), ("Focus only", "focus"),
                           ("Important only", "important"), ("All", "all")]:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(key == self._label_mode)
            self._label_group.addAction(act)
            act.triggered.connect(lambda _=False, k=key: self._set_label_mode(k))

        menu.addSeparator()
        self._meaning_check = QCheckBox("Meaning overlay")
        self._meaning_check.setToolTip("State colours, importance, arcs")
        self._meaning_check.toggled.connect(self._on_meaning_toggled)
        self._add_widget(menu, self._meaning_check)
        return btn

    def _build_actions_menu_button(self) -> QPushButton:
        btn, menu = self._menu_button("Actions")
        menu.addAction("Fit view", self._fit_view)
        menu.addAction("Reset layout", self._reset_layout)
        menu.addAction("Refresh graph", self.refresh)
        menu.addSeparator()
        self._gravity_check = QCheckBox("Story gravity")
        self._gravity_check.setChecked(True)
        self._gravity_check.setToolTip("Protagonists, themes and climaxes pull the graph")
        self._gravity_check.toggled.connect(self._on_gravity_toggled)
        self._add_widget(menu, self._gravity_check)
        self._suggest_check = QCheckBox("Suggestions panel")
        self._suggest_check.toggled.connect(self._on_suggestions_toggled)
        self._add_widget(menu, self._suggest_check)
        self._analysis_check = QCheckBox("Analysis panel")
        self._analysis_check.toggled.connect(self._on_analysis_toggled)
        self._add_widget(menu, self._analysis_check)
        menu.addSeparator()
        prow = QWidget(); pl = QHBoxLayout(prow)
        pl.setContentsMargins(6, 2, 6, 2); pl.setSpacing(4)
        pl.addWidget(QLabel("Preset:"))
        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(110)
        self._preset_combo.currentTextChanged.connect(self._on_preset_picked)
        pl.addWidget(self._preset_combo)
        self._save_preset_btn = QPushButton("Save…")
        self._save_preset_btn.setFlat(True)
        self._save_preset_btn.clicked.connect(self._on_save_preset_clicked)
        pl.addWidget(self._save_preset_btn)
        self._add_widget(menu, prow)
        self._refresh_preset_combo()
        return btn

    # -- Layout / label / filter handlers ------------------------------------

    def _set_layout_override(self, key: str) -> None:
        self._layout_override = key
        self._rebuild_view()

    def _set_label_mode(self, mode: str) -> None:
        self._label_mode = mode
        self._apply_label_visibility()

    def _on_hide_isolated_toggled(self, checked: bool) -> None:
        self._hide_isolated = checked
        self._rebuild_view()

    def _fit_view(self) -> None:
        rect = self._gscene.itemsBoundingRect()
        if not rect.isNull():
            self._gview.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _reset_layout(self) -> None:
        self._focus_node = None
        self._gview.reset_zoom()
        self._rebuild_view()
        self._sync_focus_chrome()


    def _on_mentions_toggled(self, checked: bool) -> None:
        self._edge_visibility[EDGE_MENTION] = checked
        self._rebuild_view()
        self._persist_state()

    def _on_layer_toggled(self, kind: str, checked: bool) -> None:
        if checked:
            self._active_layers.add(kind)
        else:
            self._active_layers.discard(kind)
        # Skeleton button stays pressed only while skeleton-set is active.
        if self._skeleton_btn.isChecked() and self._active_layers != set(SKELETON_LAYERS):
            self._skeleton_btn.blockSignals(True)
            self._skeleton_btn.setChecked(False)
            self._skeleton_btn.blockSignals(False)
        self._rebuild_view()
        self._persist_state()

    def _on_skeleton_toggled(self, checked: bool) -> None:
        target = set(SKELETON_LAYERS) if checked else set(LAYER_KINDS)
        self._active_layers = target
        for kind, cb in self._layer_checks.items():
            cb.blockSignals(True)
            cb.setChecked(kind in target)
            cb.blockSignals(False)
        self._rebuild_view()
        self._persist_state()

    # -- Narrative mode ------------------------------------------------------

    def _on_mode_changed(self, mode: str, user: bool = True) -> None:
        if mode not in MODE_PROFILES:
            mode = MODE_ALL
        # Any explicit mode switch lifts the series default restriction.
        if user and self._series_mode:
            self._series_default_active = False
        self._mode = mode
        profile = MODE_PROFILES[mode]

        for m, btn in self._mode_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(m == mode)
            btn.blockSignals(False)

        if mode == MODE_ALL:
            target_layers = set(LAYER_KINDS)
        else:
            target_layers = set(profile.visible_kinds)
        self._active_layers = target_layers
        for kind, cb in self._layer_checks.items():
            cb.blockSignals(True)
            cb.setChecked(kind in target_layers)
            cb.setEnabled(mode == MODE_ALL)
            cb.blockSignals(False)

        if profile.uses_quantum:
            self._load_quantum_data()
        else:
            self._quantum_nodes = {}
            self._quantum_edges = []

        self._meaning_enabled = profile.meaning_overlay
        if hasattr(self, "_meaning_check"):
            self._meaning_check.blockSignals(True)
            self._meaning_check.setChecked(profile.meaning_overlay)
            self._meaning_check.setEnabled(mode == MODE_ALL)
            self._meaning_check.blockSignals(False)

        if self._skeleton_btn.isChecked() and mode != MODE_ALL:
            self._skeleton_btn.blockSignals(True)
            self._skeleton_btn.setChecked(False)
            self._skeleton_btn.blockSignals(False)
        self._skeleton_btn.setEnabled(mode == MODE_ALL)

        self._rebuild_view()
        self._persist_state()

    def _load_quantum_data(self) -> None:
        """Pull live wavefunctions + branches into graph nodes for Quantum mode."""
        self._quantum_nodes = {}
        self._quantum_edges = []
        try:
            from logosforge.quantum_outliner import list_active_wavefunctions
            wfs = list_active_wavefunctions(self._project_id)
        except Exception:
            return
        for wf in wfs:
            wf_id_raw = wf.get("wavefunction_id") if isinstance(wf, dict) else getattr(wf, "id", None)
            anchor = wf.get("anchor") if isinstance(wf, dict) else getattr(wf, "anchor", "")
            if not wf_id_raw:
                continue
            wf_node_id = f"Wavefunction:{wf_id_raw}"
            self._quantum_nodes[wf_node_id] = GraphNode(
                wf_node_id, "Wavefunction", 0, anchor or "wavefunction",
                subtype=NODE_KIND_WAVEFUNCTION,
            )
            branches = wf.get("branches", []) if isinstance(wf, dict) else getattr(wf, "branches", [])
            for branch in branches:
                if isinstance(branch, dict):
                    b_id_raw = branch.get("id")
                    b_title = branch.get("title") or b_id_raw or "branch"
                else:
                    b_id_raw = getattr(branch, "id", None)
                    b_title = getattr(branch, "title", None) or b_id_raw or "branch"
                if not b_id_raw:
                    continue
                b_node_id = f"Branch:{b_id_raw}"
                self._quantum_nodes[b_node_id] = GraphNode(
                    b_node_id, "Branch", 0, b_title,
                    subtype=NODE_KIND_BRANCH,
                )
                self._quantum_edges.append(
                    GraphEdge(wf_node_id, b_node_id, edge_type=EDGE_QUANTUM),
                )

    def set_mode(self, mode: str) -> None:
        """Public API: switch the narrative mode."""
        self._on_mode_changed(mode)

    def get_mode(self) -> str:
        return self._mode

    # -- Keyboard navigation -------------------------------------------------

    def keyPressEvent(self, event) -> None:
        """Arrow keys cycle visible nodes; Enter focuses; Esc clears."""
        # Don't hijack keys while the user is typing in the Search box: Enter
        # runs the search and arrows move the text cursor — they must not also
        # cycle/focus graph nodes.
        if hasattr(self, "_search_input") and self._search_input.hasFocus():
            super().keyPressEvent(event)
            return
        key = event.key()
        if key in (Qt.Key.Key_Escape,):
            if self._focus_node is not None:
                self.clear_focus()
                event.accept()
                return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Left,
                   Qt.Key.Key_Up, Qt.Key.Key_Down,
                   Qt.Key.Key_Return, Qt.Key.Key_Enter):
            visible_ids = sorted(self._node_items.keys())
            if not visible_ids:
                super().keyPressEvent(event)
                return
            if self._focus_node in visible_ids:
                idx = visible_ids.index(self._focus_node)
            else:
                idx = -1
            if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
                target = visible_ids[(idx + 1) % len(visible_ids)]
            elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
                target = visible_ids[(idx - 1) % len(visible_ids)]
            else:  # Enter — re-focus the current node (or first if none).
                target = self._focus_node or visible_ids[0]
            self.focus_on(target)
            event.accept()
            return
        super().keyPressEvent(event)

    # -- Zoom + culling ------------------------------------------------------

    def _on_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self._apply_zoom_culling()

    def _apply_zoom_culling(self) -> None:
        """Hide labels and weak edges progressively as the user zooms out."""
        self._apply_label_visibility()

        for edge_item in self._edge_items:
            etype = edge_item.data(0)
            if self._zoom < _ZOOM_HIDE_WEAK_EDGES:
                edge_item.setVisible(etype == EDGE_CONTAINMENT)
            elif self._zoom < _ZOOM_HIDE_MENTIONS:
                edge_item.setVisible(etype != EDGE_MENTION)
            else:
                edge_item.setVisible(True)

    # -- Label density -------------------------------------------------------

    _STRUCTURAL_KINDS = frozenset({
        NODE_KIND_ACT, NODE_KIND_SEASON, NODE_KIND_EPISODE,
        NODE_KIND_ARC, NODE_KIND_MYSTERY,
    })

    def _node_kind_for(self, nid: str) -> str:
        active = self._active_graph_data()
        node = active.nodes.get(nid) if active else None
        return node_kind(node) if node else NODE_KIND_OTHER

    def _is_structural_node(self, nid: str) -> bool:
        return self._node_kind_for(nid) in self._STRUCTURAL_KINDS

    def _label_should_show(self, nid: str) -> bool:
        """Decide whether a node's label is drawn under the current
        Labels-density mode (none / focus / important / all)."""
        mode = self._label_mode
        if mode == "none":
            return False
        if mode == "all":
            return True

        # Focus neighbourhood is always labelled when a node is selected.
        if self._focus_node:
            if nid == self._focus_node:
                return True
            active = self._active_graph_data()
            if active and nid in active.adjacency.get(self._focus_node, set()):
                return True
            if mode == "focus":
                return False
        elif mode == "focus":
            # No selection yet — keep only the structural anchors labelled so
            # the canvas reads as a skeleton rather than going blank.
            return self._is_structural_node(nid)

        # "important": structural anchors + high-gravity + high-importance nodes.
        if self._is_structural_node(nid):
            return True
        g = self._gravity_map.get(nid)
        if g is not None and g.total >= GRAVITY_GLOW_THRESHOLD:
            return True
        if self._meaning_data:
            m = self._meaning_data.node_meanings.get(nid)
            if m is not None and m.importance >= 0.6:
                return True
        return False

    def _apply_label_visibility(self) -> None:
        """Apply both the zoom threshold and the Labels-density mode to every
        node label.  A label shows only when the zoom is high enough *and* the
        density mode admits it."""
        zoom_ok = self._zoom >= _ZOOM_HIDE_LABELS
        for nid, label in self._label_items.items():
            label.setVisible(zoom_ok and self._label_should_show(nid))

    # -- Data loading --------------------------------------------------------

    def refresh(self) -> None:
        self._graph_data = build_graph_data(self._db, self._project_id)
        if self._screenplay_mode:
            enrich_screenplay_edges(self._db, self._project_id, self._graph_data)
        if self._graphic_novel_mode:
            enrich_graphic_novel_graph(self._db, self._project_id, self._graph_data)
            enrich_graphic_novel_characters(self._db, self._project_id, self._graph_data)
        if self._stage_script_mode:
            enrich_stage_script_graph(self._db, self._project_id, self._graph_data)
        if self._series_mode:
            enrich_series_graph(self._db, self._project_id, self._graph_data)
        self._rebuild_view()

    def _active_graph_data(self) -> GraphData | None:
        """Return the GraphData backing the current mode.

        In Quantum mode the graph is built from live wavefunctions/branches
        and replaces the regular project graph entirely.  Otherwise the
        regular project graph is used.
        """
        if self._mode == MODE_QUANTUM:
            qdata = GraphData()
            qdata.nodes = dict(self._quantum_nodes)
            qdata.edges = list(self._quantum_edges)
            for nid in qdata.nodes:
                qdata.adjacency.setdefault(nid, set())
            for e in qdata.edges:
                qdata.adjacency.setdefault(e.source_id, set()).add(e.target_id)
                qdata.adjacency.setdefault(e.target_id, set()).add(e.source_id)
            return qdata
        return self._graph_data

    def _show_empty_message(self, title: str, hint: str) -> None:
        """Render a readable, centred empty-state in the scene.

        (addSimpleText defaults to black — invisible on the dark canvas — and
        sat in the corner; this is themed, wrapped, and centred in the view.)"""
        html = (
            f"<div style='text-align:center;'>"
            f"<span style='color:{theme.TEXT_SECONDARY}; font-size:14px; "
            f"font-weight:600;'>{title}</span><br>"
            f"<span style='color:{theme.TEXT_MUTED}; font-size:11px;'>{hint}"
            f"</span></div>"
        )
        item = self._gscene.addText("")
        item.setHtml(html)
        item.setTextWidth(380)
        br = item.boundingRect()
        try:
            vr = self._gview.mapToScene(
                self._gview.viewport().rect()).boundingRect()
            cx, cy = vr.center().x(), vr.center().y()
        except Exception:
            cx, cy = 0.0, 0.0
        item.setPos(cx - br.width() / 2, cy - br.height() / 2)

    def _rebuild_view(self) -> None:
        self._gscene.clear()
        self._node_items.clear()
        self._label_items.clear()
        self._edge_items.clear()

        active = self._active_graph_data()

        if not active or not active.nodes:
            if self._mode == MODE_QUANTUM:
                self._show_empty_message(
                    "No active wavefunctions",
                    "Generate quantum branches in the Quantum outliner — they "
                    "appear here as a branch tree.")
            else:
                self._show_empty_message(
                    "No graph yet",
                    "Link entities with [[Name]] in your scenes or notes, or add "
                    "relations in PSYKE — connections show up here as a network.")
            return

        visible = self._compute_visible_nodes()
        if not visible:
            self._show_empty_message(
                "No nodes match the current filters",
                "Loosen the Filters menu or switch Mode to reveal more of the "
                "graph.")
            return

        profile = MODE_PROFILES[self._mode]
        visible_edges = profile.visible_edge_types

        temporal_active = None
        if self._temporal_enabled and self._mode != MODE_QUANTUM:
            temporal_active = filter_by_scene_order(
                self._db, self._project_id, active, self._temporal_max_order,
            )

        if self._meaning_enabled and self._mode != MODE_QUANTUM:
            self._meaning_data = compute_meaning(self._db, self._project_id, visible)
        else:
            self._meaning_data = None

        if self._gravity_enabled:
            self._gravity_map = compute_gravity(
                self._db, self._project_id, active,
                screenplay_mode=self._screenplay_mode,
                graphic_novel_mode=self._graphic_novel_mode,
            )
        else:
            self._gravity_map = {}

        positions = self._layout_nodes(visible, data=active)

        if self._meaning_data:
            for arc_link in self._meaning_data.arc_links:
                src_pos = positions.get(arc_link.source_id)
                tgt_pos = positions.get(arc_link.target_id)
                if src_pos and tgt_pos:
                    self._draw_arc_link(src_pos, tgt_pos, arc_link.plotline)

        for edge in active.edges:
            if edge.source_id not in visible or edge.target_id not in visible:
                continue
            if edge.edge_type not in visible_edges:
                continue
            # Per-edge-type visibility override (user toggle in Layers panel).
            if not self._edge_visibility.get(edge.edge_type, True):
                continue
            src_pos = positions.get(edge.source_id)
            tgt_pos = positions.get(edge.target_id)
            if src_pos and tgt_pos:
                self._draw_edge(src_pos, tgt_pos, edge)

        if self._meaning_data:
            for src_id, tgt_id in self._meaning_data.flow_pairs:
                src_pos = positions.get(src_id)
                tgt_pos = positions.get(tgt_id)
                if src_pos and tgt_pos:
                    self._draw_flow_arrow(src_pos, tgt_pos)

        for nid in visible:
            pos = positions[nid]
            node = active.nodes[nid]
            is_focal = (nid == self._focus_node)
            is_dimmed = (
                temporal_active is not None
                and nid not in temporal_active
                and self._show_future
            )
            node_meaning = (
                self._meaning_data.node_meanings.get(nid) if self._meaning_data else None
            )
            self._draw_node(pos[0], pos[1], node, is_focal, is_dimmed, node_meaning)

        if self._flow_enabled and self._mode != MODE_QUANTUM:
            self._draw_flow_overlay(positions, visible)

        # Honour the Labels-density mode for the freshly drawn nodes.
        self._apply_label_visibility()

    def _draw_flow_overlay(
        self,
        positions: dict[str, tuple[float, float]],
        visible: set[str],
    ) -> None:
        """Draw the temporal narrative flow overlay above the existing graph."""
        from PySide6.QtGui import QPainterPath
        try:
            segments = compute_flow(self._db, self._project_id, self._flow_type)
        except Exception:
            return
        if not segments:
            return

        # Determine an arc apex offset for Arc flow (above the scene strip).
        arc_apex = 0.0
        if self._flow_type == FLOW_ARC and positions:
            ys = [p[1] for nid, p in positions.items() if nid.startswith("Scene:")]
            if ys:
                arc_apex = min(ys) - 180.0

        n_segs = len(segments)
        for i, seg in enumerate(segments):
            src_key = f"Scene:{seg.from_scene_id}"
            tgt_key = f"Scene:{seg.to_scene_id}"
            if src_key not in visible or tgt_key not in visible:
                continue
            src = positions.get(src_key)
            tgt = positions.get(tgt_key)
            if src is None or tgt is None:
                continue

            color = QColor(band_color(seg.band))
            color.setAlphaF(0.7)

            path = QPainterPath()
            path.moveTo(src[0], src[1])
            if self._flow_type == FLOW_ARC:
                # Quadratic curve whose control point arches upward; midway
                # segments arch the highest (climax over midpoint).
                progress = i / max(n_segs - 1, 1) if n_segs > 1 else 0.5
                arc_factor = 1.0 - abs(progress - 0.5) * 2.0  # 1 at midpoint, 0 at ends
                mid_x = (src[0] + tgt[0]) / 2
                ctrl_y = ((src[1] + tgt[1]) / 2) + (arc_apex * arc_factor)
                path.quadTo(mid_x, ctrl_y, tgt[0], tgt[1])
            else:
                mid_x = (src[0] + tgt[0]) / 2
                mid_y = (src[1] + tgt[1]) / 2 - 28.0  # gentle upward bow
                path.quadTo(mid_x, mid_y, tgt[0], tgt[1])

            item = QGraphicsPathItem(path)
            pen = QPen(color, 2.6)
            if self._flow_type == FLOW_CAUSAL:
                pen.setStyle(Qt.PenStyle.SolidLine)
                pen.setWidthF(2.0)
            elif self._flow_type == FLOW_ACTS and seg.act_boundary:
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setWidthF(3.2)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.GlobalColor.transparent))
            item.setZValue(-3)  # below nodes & gravity halos
            self._gscene.addItem(item)

    def _compute_visible_nodes(self) -> set[str]:
        active = self._active_graph_data()
        if not active:
            return set()

        visible = set(active.nodes.keys())

        focused = bool(self._focus_node and self._focus_node in active.nodes)
        if focused:
            visible = get_neighborhood(active, self._focus_node, self._hops)

        if self._type_filter != "All":
            type_nodes = filter_by_type(active, {self._type_filter})
            visible = visible & type_nodes

        # Layer mask — restrict to enabled semantic kinds.  A focus selection
        # bypasses the mask so the neighbourhood is revealed in full even from
        # a structure/theme mode that would otherwise hide those kinds.
        if not focused and self._active_layers != set(LAYER_KINDS):
            layer_nodes = filter_by_layers(active, self._active_layers)
            visible = visible & layer_nodes

        # Series default (§4): on first load, restrict to the current season
        # overview + active arcs so the graph never opens as a full hairball.
        if self._series_mode and self._series_default_active and not self._focus_node:
            default_nodes = series_default_node_ids(
                self._db, self._project_id, active,
            )
            if default_nodes:
                visible = visible & default_nodes

        if self._temporal_enabled and not self._show_future and self._mode != MODE_QUANTUM:
            temporal_active = filter_by_scene_order(
                self._db, self._project_id, active, self._temporal_max_order,
            )
            visible = visible & temporal_active

        # Drop nodes that have no visible neighbour (optional declutter).
        if self._hide_isolated and not self._focus_node:
            connected = {
                nid for nid in visible
                if active.adjacency.get(nid, set()) & visible
            }
            if connected:
                visible = connected

        return visible

    def _layout_nodes(
        self, visible: set[str], data: GraphData | None = None,
    ) -> dict[str, tuple[float, float]]:
        if data is None:
            data = self._active_graph_data()
        if not visible or data is None:
            return {}
        layout = self._effective_layout()
        if layout == "linear_timeline":
            return self._layout_linear_timeline(visible, data)
        if layout == "theme_centered":
            return self._layout_theme_centered(visible, data)
        if layout == "quantum_tree":
            return self._layout_quantum_tree(visible, data)
        if layout == "radial":
            return self._layout_radial(visible, data)
        return self._layout_circular(visible)

    def _effective_layout(self) -> str:
        """Resolve the layout to use — the user override wins over the mode's
        default profile layout.  ``""`` means "follow the mode"."""
        override = self._layout_override
        if not override:
            return MODE_PROFILES[self._mode].layout
        # Map the friendly menu keys onto the concrete layout engines.
        return {
            "hierarchical": "linear_timeline",
            "act_clusters": "linear_timeline",
            "timeline": "linear_timeline",
            "radial": "radial",
            "force": "circular",
        }.get(override, MODE_PROFILES[self._mode].layout)

    def _layout_circular(
        self, visible: set[str],
    ) -> dict[str, tuple[float, float]]:
        nodes_list = sorted(visible)
        count = len(nodes_list)
        if count == 0:
            return {}

        def _pull(nid: str) -> float:
            """Story-Gravity centrality multiplier — 1.0 if gravity off."""
            if not self._gravity_enabled:
                return 1.0
            g = self._gravity_map.get(nid)
            return gravity_centrality_pull(g) if g else 1.0

        if self._focus_node and self._focus_node in visible:
            center_id = self._focus_node
            others = [n for n in nodes_list if n != center_id]
            positions = {center_id: (0.0, 0.0)}
            radius = max(_GRAPH_RADIUS, len(others) * 18)
            for i, nid in enumerate(others):
                angle = 2 * math.pi * i / max(len(others), 1) - math.pi / 2
                r = radius * _pull(nid)
                positions[nid] = (r * math.cos(angle), r * math.sin(angle))
            return positions

        radius = max(_GRAPH_RADIUS, count * 18)
        positions: dict[str, tuple[float, float]] = {}
        for i, nid in enumerate(nodes_list):
            angle = 2 * math.pi * i / count - math.pi / 2
            r = radius * _pull(nid)
            positions[nid] = (r * math.cos(angle), r * math.sin(angle))
        return positions

    def _layout_linear_timeline(
        self, visible: set[str], data: GraphData,
    ) -> dict[str, tuple[float, float]]:
        """Acts on a top band, their scenes laid out left-to-right beneath."""
        positions: dict[str, tuple[float, float]] = {}
        scenes = self._db.get_all_scenes(self._project_id)
        scene_order = {f"Scene:{s.id}": s.sort_order for s in scenes}
        scene_act = {f"Scene:{s.id}": (s.act or "").strip() for s in scenes}

        # Group visible scenes per act.
        per_act: dict[str, list[str]] = {}
        unassigned: list[str] = []
        for nid in visible:
            if not nid.startswith("Scene:"):
                continue
            act = scene_act.get(nid, "")
            if act:
                per_act.setdefault(act, []).append(nid)
            else:
                unassigned.append(nid)
        for arr in per_act.values():
            arr.sort(key=lambda n: scene_order.get(n, 0))
        unassigned.sort(key=lambda n: scene_order.get(n, 0))

        # Act nodes — order by their first scene's sort_order so the timeline
        # progresses correctly across acts.
        act_nodes_visible = [nid for nid in visible if nid.startswith("Act:")]
        act_node_by_name: dict[str, str] = {}
        for nid in act_nodes_visible:
            node = data.nodes.get(nid)
            if node:
                act_node_by_name[node.name] = nid
        act_names_ordered = sorted(
            act_node_by_name.keys(),
            key=lambda name: min(
                (scene_order.get(s, 0) for s in per_act.get(name, [])),
                default=10_000,
            ),
        )

        x_step = 120.0
        y_act = -80.0
        y_scene = 60.0
        x_cursor = 0.0
        for act_name in act_names_ordered:
            act_id = act_node_by_name[act_name]
            scenes_for_act = per_act.get(act_name, [])
            act_width = max(len(scenes_for_act) - 1, 0) * x_step
            act_x = x_cursor + act_width / 2
            positions[act_id] = (act_x, y_act)
            for s_id in scenes_for_act:
                positions[s_id] = (x_cursor, y_scene)
                x_cursor += x_step
            x_cursor += x_step * 0.5  # gap between acts

        for s_id in unassigned:
            positions[s_id] = (x_cursor, y_scene)
            x_cursor += x_step

        # Centre the whole strip on 0.
        if positions:
            xs = [p[0] for p in positions.values()]
            shift = -(max(xs) + min(xs)) / 2
            positions = {nid: (p[0] + shift, p[1]) for nid, p in positions.items()}

        # Any leftover (non-scene non-act) visible nodes: ring around the centre.
        leftover = [
            nid for nid in visible if nid not in positions
        ]
        if leftover:
            radius = max(_GRAPH_RADIUS, len(leftover) * 16)
            for i, nid in enumerate(sorted(leftover)):
                angle = 2 * math.pi * i / len(leftover) - math.pi / 2
                positions[nid] = (
                    radius * math.cos(angle), radius * math.sin(angle) + 200,
                )
        return positions

    def _layout_theme_centered(
        self, visible: set[str], data: GraphData,
    ) -> dict[str, tuple[float, float]]:
        """Themes anchored at the centre, satellites radiating out."""
        themes = [
            nid for nid in visible
            if node_kind(data.nodes.get(nid, GraphNode("", "", 0, ""))) == NODE_KIND_THEME
        ]
        positions: dict[str, tuple[float, float]] = {}
        if not themes:
            return self._layout_circular(visible)
        # Place themes on an inner circle.
        inner_r = max(80.0, 30.0 * len(themes))
        for i, nid in enumerate(sorted(themes)):
            angle = 2 * math.pi * i / len(themes) - math.pi / 2
            positions[nid] = (inner_r * math.cos(angle), inner_r * math.sin(angle))

        # Satellites: orbit their nearest theme.
        satellites = [n for n in visible if n not in positions]
        theme_count = len(themes)
        for j, nid in enumerate(sorted(satellites)):
            theme_idx = j % theme_count
            theme_id = sorted(themes)[theme_idx]
            tx, ty = positions[theme_id]
            # Spread around the theme.
            local_angle = 2 * math.pi * (j // theme_count) / max(
                1, math.ceil(len(satellites) / theme_count),
            )
            r = inner_r * 0.9
            positions[nid] = (tx + r * math.cos(local_angle),
                              ty + r * math.sin(local_angle))
        return positions

    def _layout_quantum_tree(
        self, visible: set[str], data: GraphData,
    ) -> dict[str, tuple[float, float]]:
        """Wavefunctions across the top, their branches fanning down."""
        wfs = [nid for nid in visible if nid.startswith("Wavefunction:")]
        branches = [nid for nid in visible if nid.startswith("Branch:")]
        positions: dict[str, tuple[float, float]] = {}
        if not wfs:
            return self._layout_circular(visible)

        wf_step = 220.0
        for i, wf_id in enumerate(sorted(wfs)):
            positions[wf_id] = (i * wf_step, -100.0)

        # Children of each wavefunction = branches it edges to.
        for wf_id in wfs:
            children = [
                e.target_id for e in data.edges
                if e.source_id == wf_id and e.target_id in visible
            ]
            children.sort()
            wf_x, wf_y = positions[wf_id]
            child_step = 80.0
            child_width = max(0, len(children) - 1) * child_step
            start_x = wf_x - child_width / 2
            for k, ch in enumerate(children):
                positions[ch] = (start_x + k * child_step, wf_y + 160.0)

        # Centre on 0.
        if positions:
            xs = [p[0] for p in positions.values()]
            shift = -(max(xs) + min(xs)) / 2
            positions = {nid: (p[0] + shift, p[1]) for nid, p in positions.items()}

        # Any orphan branch (no parent in visible set): ring outside.
        leftover = [nid for nid in visible if nid not in positions]
        if leftover:
            radius = max(_GRAPH_RADIUS, len(leftover) * 14)
            for i, nid in enumerate(sorted(leftover)):
                angle = 2 * math.pi * i / len(leftover) - math.pi / 2
                positions[nid] = (
                    radius * math.cos(angle),
                    radius * math.sin(angle) + 100,
                )
        return positions

    def _layout_radial(
        self, visible: set[str], data: GraphData,
    ) -> dict[str, tuple[float, float]]:
        """Concentric rings by structural depth — anchors (acts/seasons) in the
        inner ring, scenes/episodes in the middle, entities on the outside.

        Keeps the project skeleton legible at the centre while pushing the
        long tail of characters/places/objects to the rim instead of mixing
        everything into one undifferentiated circle."""
        # Rank kinds into concentric tiers.  Lower tier = closer to centre.
        tier_for_kind = {
            NODE_KIND_ACT: 0, NODE_KIND_SEASON: 0, NODE_KIND_ARC: 0,
            NODE_KIND_EPISODE: 1, NODE_KIND_SCENE: 1, NODE_KIND_PAGE: 1,
            NODE_KIND_PANEL: 1, NODE_KIND_MYSTERY: 1, NODE_KIND_PLOTLINE: 1,
            NODE_KIND_THEME: 2, NODE_KIND_CHARACTER: 2,
        }
        rings: dict[int, list[str]] = {0: [], 1: [], 2: [], 3: []}
        for nid in visible:
            node = data.nodes.get(nid)
            kind = node_kind(node) if node else NODE_KIND_OTHER
            tier = tier_for_kind.get(kind, 3)
            rings[tier].append(nid)

        positions: dict[str, tuple[float, float]] = {}
        ring_radius = {0: 0.0, 1: _GRAPH_RADIUS * 0.55,
                       2: _GRAPH_RADIUS * 1.1, 3: _GRAPH_RADIUS * 1.7}
        for tier, members in rings.items():
            members.sort()
            count = len(members)
            if count == 0:
                continue
            radius = ring_radius[tier]
            if tier == 0 and count == 1:
                positions[members[0]] = (0.0, 0.0)
                continue
            # Spread the innermost ring a little even if it has few members.
            radius = max(radius, count * 16)
            for i, nid in enumerate(members):
                angle = 2 * math.pi * i / count - math.pi / 2
                positions[nid] = (radius * math.cos(angle),
                                  radius * math.sin(angle))
        return positions

    # -- Drawing -------------------------------------------------------------

    def _draw_node(
        self, x: float, y: float, node: GraphNode,
        is_focal: bool, is_dimmed: bool,
        meaning: NodeMeaning | None = None,
    ) -> None:
        radius = _FOCUS_RADIUS if is_focal else _NODE_RADIUS
        kind = node_kind(node)
        color_hex = _KIND_COLORS.get(kind, "#9e9e9e")

        # Mode-specific prominence multiplier — used to make certain kinds
        # visually dominant (e.g. themes in Theme mode, acts in Structure).
        prom = MODE_PROFILES[self._mode].prominence.get(kind, 1.0)
        radius = radius * prom

        gravity = (
            self._gravity_map.get(node.node_id)
            if self._gravity_enabled else None
        )
        if gravity is not None:
            radius *= gravity_radius_multiplier(gravity)

        if meaning:
            radius += importance_radius_delta(meaning.importance)
            if meaning.state_warmth != "neutral" and node.etype == "Character":
                color_hex = state_color(meaning.state_warmth)
            if meaning.psyke_glow and node.etype == "PSYKE":
                color_hex = QColor(color_hex).lighter(130).name()

        color = QColor(color_hex)

        if meaning and meaning.is_dead_zone:
            color.setHsvF(color.hueF(), color.saturationF() * 0.5, color.valueF())

        if gravity is not None and gravity.total >= GRAVITY_GLOW_THRESHOLD and not is_dimmed:
            self._draw_gravity_halo(x, y, radius, color_hex, gravity)

        if is_dimmed:
            color.setAlphaF(_DIM_OPACITY)

        item = _make_shape_node(
            kind, x, y, radius, node.node_id,
            on_click=self._on_node_click,
            on_hover=self._on_node_hover,
        )
        item.setBrush(QBrush(color))
        pen_color = color.darker(120) if not is_dimmed else QColor(color_hex)
        pen_color.setAlphaF(0.4 if is_dimmed else 1.0)
        pen_width = 3 if is_focal else 2
        if meaning and meaning.state_warmth != "neutral" and node.etype == "Character":
            pen_color = QColor(state_color(meaning.state_warmth))
            pen_width = 3
        item.setPen(QPen(pen_color, pen_width))
        item.setZValue(2 if is_focal else 1)
        # Hover tooltip — name, kind, and neighbour count.  Picked up by Qt
        # automatically when the user hovers over the node.
        neighbour_count = (
            len(self._active_graph_data().adjacency.get(node.node_id, set()))
            if self._active_graph_data() else 0
        )
        tip = f"{node.name}\nKind: {kind}\nNeighbours: {neighbour_count}"
        if gravity is not None:
            tip += f"\nGravity: {gravity.total:.2f}"
        item.setToolTip(tip)
        self._gscene.addItem(item)
        self._node_items[node.node_id] = item

        label = QGraphicsSimpleTextItem(node.name)
        font = QFont()
        font.setPointSize(9 if not is_focal else 10)
        if is_focal:
            font.setBold(True)
        label.setFont(font)
        # Stable label — keep constant screen size regardless of zoom level.
        label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations, True)
        text_color = QColor(theme.TEXT_PRIMARY)
        if is_dimmed:
            text_color.setAlphaF(_DIM_OPACITY)
        label.setBrush(QBrush(text_color))
        rect = label.boundingRect()
        label.setPos(x - rect.width() / 2, y + radius + 4)
        label.setZValue(3)
        self._gscene.addItem(label)
        self._label_items[node.node_id] = label

    def _draw_edge(
        self, src: tuple[float, float], tgt: tuple[float, float],
        edge: GraphEdge,
    ) -> None:
        is_highlight = (
            self._focus_node is not None
            and (edge.source_id == self._focus_node or edge.target_id == self._focus_node)
        )
        style = EDGE_STYLE.get(edge.edge_type, EDGE_STYLE[EDGE_LINK])
        if is_highlight:
            color = QColor(_EDGE_HIGHLIGHT)
            width = max(style["width"] + 0.8, 2.0)
        else:
            color = QColor(style["color"])
            width = style["width"]
        pen = QPen(color, width)
        if style.get("dash") == "dash":
            pen.setStyle(Qt.PenStyle.DashLine)
        elif style.get("dash") == "dot":
            pen.setStyle(Qt.PenStyle.DotLine)
        line = QGraphicsLineItem(src[0], src[1], tgt[0], tgt[1])
        line.setPen(pen)
        line.setZValue(0 if edge.edge_type != EDGE_CONTAINMENT else -1)
        # Tag with edge_type so zoom-culling can target specific kinds.
        line.setData(0, edge.edge_type)
        self._gscene.addItem(line)
        self._edge_items.append(line)

    def _draw_arc_link(
        self, src: tuple[float, float], tgt: tuple[float, float], plotline: str,
    ) -> None:
        color = QColor(_arc_color(plotline))
        color.setAlphaF(0.3)
        pen = QPen(color, 1.5, Qt.PenStyle.DashLine)
        line = QGraphicsLineItem(src[0], src[1], tgt[0], tgt[1])
        line.setPen(pen)
        line.setZValue(-1)
        self._gscene.addItem(line)

    def _draw_flow_arrow(
        self, src: tuple[float, float], tgt: tuple[float, float],
    ) -> None:
        dx = tgt[0] - src[0]
        dy = tgt[1] - src[1]
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        mid_x = (src[0] + tgt[0]) / 2
        mid_y = (src[1] + tgt[1]) / 2

        arrow_size = 4.0
        tip = QPointF(mid_x + ux * arrow_size, mid_y + uy * arrow_size)
        left = QPointF(
            mid_x - ux * arrow_size + uy * arrow_size * 0.6,
            mid_y - uy * arrow_size - ux * arrow_size * 0.6,
        )
        right = QPointF(
            mid_x - ux * arrow_size - uy * arrow_size * 0.6,
            mid_y - uy * arrow_size + ux * arrow_size * 0.6,
        )

        polygon = QPolygonF([tip, left, right])
        arrow = QGraphicsPolygonItem(polygon)
        color = QColor(theme.TEXT_MUTED)
        color.setAlphaF(0.4)
        arrow.setBrush(QBrush(color))
        arrow.setPen(QPen(Qt.PenStyle.NoPen))
        arrow.setZValue(-1)
        self._gscene.addItem(arrow)

    def _draw_gravity_halo(
        self, x: float, y: float, radius: float,
        color_hex: str, gravity: StoryGravity,
    ) -> None:
        """Translucent halo behind high-gravity nodes."""
        alpha = gravity_glow_alpha(gravity)
        if alpha <= 0:
            return
        halo_r = radius * 1.7
        halo = QGraphicsEllipseItem(x - halo_r, y - halo_r, halo_r * 2, halo_r * 2)
        glow_color = QColor(color_hex)
        glow_color.setAlphaF(alpha)
        halo.setBrush(QBrush(glow_color))
        halo.setPen(QPen(Qt.PenStyle.NoPen))
        halo.setZValue(-2)
        self._gscene.addItem(halo)

    # -- Interaction ---------------------------------------------------------

    def _on_node_click(self, node_id: str) -> None:
        if self._focus_node == node_id:
            self.clear_focus()
        else:
            self.focus_on(node_id)

    def _on_node_hover(self, node_id: str, entered: bool) -> None:
        if entered:
            neighbors = self._graph_data.adjacency.get(node_id, set()) if self._graph_data else set()
            highlight_set = {node_id} | neighbors
            for nid, item in self._node_items.items():
                if nid in highlight_set:
                    item.setOpacity(1.0)
                else:
                    item.setOpacity(0.3)
            for nid, label in self._label_items.items():
                if nid in highlight_set:
                    label.setOpacity(1.0)
                else:
                    label.setOpacity(0.3)
        else:
            for item in self._node_items.values():
                item.setOpacity(1.0)
            for label in self._label_items.values():
                label.setOpacity(1.0)

    def focus_on(self, node_id: str) -> None:
        if self._series_mode:
            self._series_default_active = False
        self._focus_node = node_id
        self._rebuild_view()
        self._sync_focus_chrome()
        if self._suggestions_visible:
            self._refresh_suggestions()
        if self._analysis_visible:
            self._refresh_analysis()
        if self._on_node_selected and self._graph_data:
            node = self._graph_data.nodes.get(node_id)
            if node:
                self._on_node_selected(node.etype, node.entity_id)

    def clear_focus(self) -> None:
        self._focus_node = None
        self._rebuild_view()
        self._sync_focus_chrome()
        if self._suggestions_visible:
            self._refresh_suggestions()
        if self._analysis_visible:
            self._refresh_analysis()

    def get_focus_node(self) -> str | None:
        return self._focus_node

    # -- Search --------------------------------------------------------------

    def _on_search(self) -> None:
        query = self._search_input.text().strip().lower()
        if not query or not self._graph_data:
            return
        for nid, node in self._graph_data.nodes.items():
            if query in node.name.lower():
                self._set_search_nomatch(False)
                self.focus_on(nid)
                return
        self._set_search_nomatch(True)   # no hit → visible feedback, not silent

    def _set_search_nomatch(self, on: bool) -> None:
        """Flag a failed search: red border + tooltip (cleared on next edit)."""
        if not hasattr(self, "_search_input"):
            return
        if on:
            self._search_input.setStyleSheet(
                "QLineEdit { border: 1px solid #e25555; }")
            self._search_input.setToolTip(
                f"No node matches “{self._search_input.text().strip()}”.")
        else:
            self._search_input.setStyleSheet("")
            self._search_input.setToolTip("")

    def _sync_focus_chrome(self) -> None:
        """Reflect the focus state in the top bar: a breadcrumb naming the
        focused node + neighbourhood depth, and Clear Focus enabled only while
        something is focused."""
        focused = self._focus_node is not None
        if hasattr(self, "_clear_btn"):
            self._clear_btn.setEnabled(focused)
        if not hasattr(self, "_focus_label"):
            return
        name = ""
        if focused and getattr(self, "_graph_data", None):
            node = self._graph_data.nodes.get(self._focus_node)
            if node:
                name = node.name
        if name:
            hops = getattr(self, "_hops", 1)
            self._focus_label.setText(f"◉ Focused: {name} · {hops}-hop")
            self._focus_label.setVisible(True)
        else:
            self._focus_label.setText("")
            self._focus_label.setVisible(False)

    # -- Filters -------------------------------------------------------------

    def _on_hops_toggled(self, checked: bool) -> None:
        self._hops = 2 if checked else 1
        if self._focus_node:
            self._rebuild_view()

    def _on_type_changed(self, text: str) -> None:
        self._type_filter = text
        self._rebuild_view()

    def _on_temporal_toggled(self, checked: bool) -> None:
        self._temporal_enabled = checked
        self._future_check.setEnabled(checked)
        self._rebuild_view()

    def _on_future_toggled(self, checked: bool) -> None:
        self._show_future = checked
        self._rebuild_view()

    def _on_gravity_toggled(self, checked: bool) -> None:
        self._gravity_enabled = checked
        self._rebuild_view()
        self._persist_state()

    def is_gravity_enabled(self) -> bool:
        return self._gravity_enabled

    def get_gravity_map(self) -> dict[str, StoryGravity]:
        return dict(self._gravity_map)

    # -- Temporal narrative flow --------------------------------------------

    def _on_flow_toggled(self, checked: bool) -> None:
        self._flow_enabled = checked
        self._flow_combo.setEnabled(checked)
        self._rebuild_view()
        self._persist_state()

    def _on_flow_type_changed(self, _idx: int) -> None:
        value = self._flow_combo.currentData() or FLOW_TIMELINE
        self._flow_type = value
        if self._flow_enabled:
            self._rebuild_view()
        self._persist_state()

    def is_flow_enabled(self) -> bool:
        return self._flow_enabled

    def get_flow_type(self) -> str:
        return self._flow_type

    def set_flow(self, enabled: bool, flow_type: str | None = None) -> None:
        """Public API: enable/disable the flow overlay and pick its type."""
        if flow_type and flow_type in FLOW_TYPES:
            self._flow_type = flow_type
            idx = self._flow_combo.findData(flow_type)
            if idx >= 0:
                self._flow_combo.blockSignals(True)
                self._flow_combo.setCurrentIndex(idx)
                self._flow_combo.blockSignals(False)
        self._flow_check.blockSignals(True)
        self._flow_check.setChecked(enabled)
        self._flow_check.blockSignals(False)
        self._flow_enabled = enabled
        self._flow_combo.setEnabled(enabled)
        self._rebuild_view()

    def _on_meaning_toggled(self, checked: bool) -> None:
        self._meaning_enabled = checked
        self._rebuild_view()

    def _on_suggestions_toggled(self, checked: bool) -> None:
        self._suggestions_visible = checked
        if checked:
            self._suggest_panel.show()
            self._refresh_suggestions()
        else:
            self._suggest_panel.hide()
            self._suggestions = None
            self.clear_trace()

    # -- Analysis panel ------------------------------------------------------

    def _on_analysis_toggled(self, checked: bool) -> None:
        self._analysis_visible = checked
        if checked:
            self._analysis_panel.show()
            self._refresh_analysis()
        else:
            self._analysis_panel.hide()

    def is_analysis_visible(self) -> bool:
        return self._analysis_visible

    def get_last_node_analysis(self) -> NodeAnalysis | None:
        return self._last_node_analysis

    def get_last_insights(self) -> list[GraphInsight]:
        return list(self._last_insights)

    def _refresh_analysis(self) -> None:
        """Repopulate the Analysis panel based on the current focal node."""
        layout = self._analysis_panel.layout()
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Per-node section.
        active = self._active_graph_data()
        self._last_node_analysis = None
        if self._focus_node and active:
            self._last_node_analysis = analyze_node(
                self._db, self._project_id, active, self._focus_node,
            )

        if self._last_node_analysis:
            self._build_node_analysis_widgets(layout, self._last_node_analysis)
        else:
            hint = QLabel("Click a node to see its themes, relations, scenes,"
                          " arcs, and Controlling Idea alignment.")
            hint.setObjectName("analysisHint")
            hint.setWordWrap(True)
            layout.addWidget(hint)

        # Global insights.
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER};")
        layout.addWidget(sep)

        header = QLabel("Insights")
        header.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(header)

        if active is None:
            self._last_insights = []
        else:
            ins: list[GraphInsight] = []
            ins.extend(find_disconnected_nodes(active))
            ins.extend(suggest_missing_relations(self._db, self._project_id, active))
            ins.extend(find_weak_thematic_clusters(self._db, self._project_id, active))
            self._last_insights = ins

        summary = explain_structure(self._db, self._project_id, active) if active else ""
        if summary:
            sumlbl = QLabel(summary)
            sumlbl.setWordWrap(True)
            sumlbl.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 10px; padding: 4px 0;"
            )
            layout.addWidget(sumlbl)

        if not self._last_insights:
            empty = QLabel("No structural issues detected.")
            empty.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
            layout.addWidget(empty)
        else:
            for ins in self._last_insights[:8]:
                tag = "!" if ins.severity == "warning" else "·"
                row = QLabel(f"{tag} {ins.title}\n  {ins.message}")
                row.setWordWrap(True)
                row.setStyleSheet(
                    f"color: {theme.TEXT_PRIMARY}; font-size: 11px;"
                    f" padding: 4px 0;"
                )
                layout.addWidget(row)

        if self._on_send_to_assistant:
            send_btn = QPushButton("Send insights to Assistant")
            send_btn.setObjectName("analysisSendBtn")
            send_btn.clicked.connect(self._send_insights_to_assistant)
            layout.addWidget(send_btn)

        layout.addStretch()

    def _build_node_analysis_widgets(self, layout, na: NodeAnalysis) -> None:
        title = QLabel(f"{na.name}")
        title.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;"
        )
        layout.addWidget(title)
        sub = QLabel(f"Kind: {na.kind}")
        sub.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px;")
        layout.addWidget(sub)

        def _section(label: str, items: list[str]) -> None:
            if not items:
                return
            box = QLabel(f"<b>{label}:</b> " + ", ".join(items[:8]))
            box.setWordWrap(True)
            box.setStyleSheet(
                f"color: {theme.TEXT_PRIMARY}; font-size: 11px; padding: 2px 0;"
            )
            layout.addWidget(box)

        _section("Themes", na.themes)
        _section("Relations", na.relations)
        _section("Scenes", na.scenes)
        _section("Arcs", na.arcs)
        if na.ci_alignment:
            ci = QLabel(
                f"<b>Controlling Idea alignment:</b> {na.ci_alignment}"
            )
            ci.setWordWrap(True)
            ci.setStyleSheet(
                f"color: {theme.TEXT_PRIMARY}; font-size: 11px; padding: 2px 0;"
            )
            layout.addWidget(ci)
        if na.ci_aligned_neighbours:
            cn = QLabel(
                "<b>CI-aligned neighbours:</b> "
                + ", ".join(na.ci_aligned_neighbours[:6])
            )
            cn.setWordWrap(True)
            cn.setStyleSheet(
                f"color: {theme.TEXT_PRIMARY}; font-size: 11px; padding: 2px 0;"
            )
            layout.addWidget(cn)

        if self._on_send_to_assistant:
            send_btn = QPushButton("Send to Assistant")
            send_btn.setObjectName("analysisSendBtn")
            send_btn.clicked.connect(self._send_node_to_assistant)
            layout.addWidget(send_btn)

    def _send_node_to_assistant(self) -> None:
        if not self._on_send_to_assistant or self._last_node_analysis is None:
            return
        try:
            self._on_send_to_assistant(
                compose_assistant_context(self._last_node_analysis),
            )
        except Exception:
            pass

    def _send_insights_to_assistant(self) -> None:
        if not self._on_send_to_assistant:
            return
        try:
            self._on_send_to_assistant(
                compose_assistant_context(self._last_insights),
            )
        except Exception:
            pass

    def set_temporal_max_order(self, order: int) -> None:
        self._temporal_max_order = order
        if self._temporal_enabled:
            self._rebuild_view()

    # -- Suggestion panel ----------------------------------------------------

    def _refresh_suggestions(self) -> None:
        """Regenerate suggestions based on current focus/context."""
        layout = self._suggest_panel.layout()
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        scene_id = self._get_focal_scene_id()
        if scene_id is None:
            lbl = QLabel("Focus on a scene node to see suggestions.")
            lbl.setObjectName("suggestHint")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
            layout.addStretch()
            self._suggestions = None
            return

        from logosforge.graph_suggestions import generate_graph_suggestions
        self._suggestions = generate_graph_suggestions(
            self._db, self._project_id, scene_id,
        )

        if not self._suggestions.suggestions:
            lbl = QLabel("No suggestions for this scene.")
            lbl.setObjectName("suggestHint")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
            layout.addStretch()
            return

        header = QLabel("Next Narrative Possibilities")
        header.setObjectName("suggestHeader")
        layout.addWidget(header)

        for idx, suggestion in enumerate(self._suggestions.suggestions):
            btn = QPushButton(f"{suggestion.category}")
            btn.setObjectName("suggestBtn")
            btn.setToolTip(
                f"{suggestion.text}\n\nTrace: {', '.join(suggestion.trace_nodes)}\n"
                f"Reason: {suggestion.reason}"
            )
            btn.setFlat(True)
            btn.clicked.connect(lambda _=False, s=suggestion: self._on_suggestion_clicked(s))
            layout.addWidget(btn)

            desc = QLabel(f"\u2192 {suggestion.text}")
            desc.setObjectName("suggestDesc")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        layout.addStretch()

    def _on_suggestion_clicked(self, suggestion) -> None:
        """Focus graph on suggestion's trace nodes."""
        self.clear_trace()
        if suggestion.trace_nodes:
            primary = suggestion.trace_nodes[0]
            if primary in (self._graph_data.nodes if self._graph_data else {}):
                self.focus_on(primary)
            self.highlight_trace(suggestion.trace_nodes)

    def highlight_trace(self, node_ids: list[str]) -> None:
        """Highlight specific nodes as suggestion trace."""
        self._trace_highlight = list(node_ids)
        accent = QColor(_EDGE_HIGHLIGHT)
        for nid in node_ids:
            item = self._node_items.get(nid)
            if item:
                item.setPen(QPen(accent, 3))
                item.setZValue(5)
            label = self._label_items.get(nid)
            if label:
                label.setBrush(QBrush(accent))

    def clear_trace(self) -> None:
        """Remove trace highlights."""
        for nid in self._trace_highlight:
            item = self._node_items.get(nid)
            if item and self._graph_data:
                node = self._graph_data.nodes.get(nid)
                if node:
                    color_hex = _TYPE_COLORS.get(node.etype, "#9e9e9e")
                    item.setPen(QPen(QColor(color_hex).darker(120), 2))
                    item.setZValue(1)
            label = self._label_items.get(nid)
            if label:
                label.setBrush(QBrush(QColor(theme.TEXT_PRIMARY)))
        self._trace_highlight = []

    def _get_focal_scene_id(self) -> int | None:
        """Get a scene ID for suggestion context."""
        if self._focus_node and self._focus_node.startswith("Scene:"):
            try:
                return int(self._focus_node.split(":")[1])
            except (ValueError, IndexError):
                pass
        if self._graph_data:
            for nid, node in self._graph_data.nodes.items():
                if node.etype == "Scene":
                    return node.entity_id
        return None

    # -- Public API ----------------------------------------------------------

    def get_visible_count(self) -> int:
        return len(self._node_items)

    def get_type_filter(self) -> str:
        return self._type_filter

    def is_temporal_enabled(self) -> bool:
        return self._temporal_enabled

    def is_meaning_enabled(self) -> bool:
        return self._meaning_enabled

    def get_meaning_data(self) -> MeaningData | None:
        return self._meaning_data

    def is_suggestions_visible(self) -> bool:
        return self._suggestions_visible

    def get_suggestions(self):
        return self._suggestions

    def get_trace_highlight(self) -> list[str]:
        return list(self._trace_highlight)


# ---------------------------------------------------------------------------
# Graphic Novel — character appearances + PSYKE motif linkage (Slice 8)
# ---------------------------------------------------------------------------

def _gn_name_index(db, project_id):
    """Map lowercased PSYKE name/alias -> (psyke_node_id, entry_type)."""
    index = {}
    for entry in db.get_all_psyke_entries(project_id):
        nid = f"PSYKE:{entry.id}"
        names = [entry.name] + db.csv_split(getattr(entry, "aliases", "") or "")
        for nm in names:
            key = (nm or "").strip().lower()
            if key:
                index.setdefault(key, (nid, (entry.entry_type or "").lower()))
    return index


def enrich_graphic_novel_characters(db, project_id, data):
    """Add character-appearance edges + PSYKE motif links to a GN graph.

    Runs AFTER enrich_graphic_novel_graph (which created GNPage / GNMotif
    nodes). Characters come from panel.characters_present, matched to a PSYKE
    character entry by name/alias when possible (else a standalone
    GNCharacter node). Motif nodes are linked to PSYKE theme/object entries
    by name. No hard foreign keys required.
    """
    pages = db.get_gn_pages(project_id)
    if not pages:
        return
    name_index = _gn_name_index(db, project_id)

    def _node(node_id, etype, eid, name, kind):
        if node_id not in data.nodes:
            data.nodes[node_id] = GraphNode(node_id, etype, eid, name, subtype=kind)
            data.adjacency.setdefault(node_id, set())

    def _edge(src, tgt, etype):
        if src not in data.nodes or tgt not in data.nodes:
            return
        data.edges.append(GraphEdge(src, tgt, edge_type=etype))
        data.adjacency.setdefault(src, set()).add(tgt)
        data.adjacency.setdefault(tgt, set()).add(src)

    seen_char = set()
    motifs = set()
    for page in pages:
        page_node = f"GNPage:{page.id}"
        if page_node not in data.nodes:
            continue
        for panel in db.get_gn_panels_for_page(page.id):
            for raw in db.csv_split(panel.characters_present):
                name = raw.strip()
                if not name:
                    continue
                match = name_index.get(name.lower())
                if match and match[1] == "character":
                    cnode = match[0]
                else:
                    cnode = f"GNCharacter:{name}"
                    _node(cnode, "GNCharacter", 0, name, NODE_KIND_CHARACTER)
                pair = (cnode, page_node)
                if pair not in seen_char:
                    seen_char.add(pair)
                    _edge(cnode, page_node, EDGE_GN_CHARACTER_PRESENT)
            for motif in db.csv_split(panel.visual_motifs):
                motifs.add(motif)

    # Link motif nodes to PSYKE theme/object entries by name.
    for motif in motifs:
        motif_node = f"GNMotif:{motif}"
        if motif_node not in data.nodes:
            continue
        match = name_index.get(motif.strip().lower())
        if match and match[1] in ("theme", "object"):
            _edge(motif_node, match[0], EDGE_GN_PSYKE_MOTIF)


def gn_default_mode(db, project_id):
    """Non-hairball default mode for a GN project: Visual Motif graph when
    motifs exist, otherwise Page Rhythm."""
    for page in db.get_gn_pages(project_id):
        for panel in db.get_gn_panels_for_page(page.id):
            if db.csv_split(panel.visual_motifs):
                return MODE_GN_MOTIF
    return MODE_GN_PAGE_RHYTHM
