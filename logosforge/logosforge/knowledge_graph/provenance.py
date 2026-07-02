"""Narrative Knowledge Graph vocabulary: node types, edge types, confidence,
provenance and source systems (Phase 10P).

Plain constants so every extractor speaks the same language and nothing is
stringly-typed by accident.
"""

from __future__ import annotations

# -- Node types -------------------------------------------------------------
NT_PROJECT = "project"
NT_ACT = "act"
NT_CHAPTER = "chapter"
NT_SCENE = "scene"
NT_SCREENPLAY_BLOCK = "screenplay_block"
NT_PSYKE_ENTRY = "psyke_entry"
NT_CHARACTER = "character"
NT_PLACE = "place"
NT_OBJECT = "object"
NT_LORE = "lore"
NT_THEME = "theme"
NT_MOTIF = "motif"
NT_NOTE = "note"
NT_PLOT_BLOCK = "plot_block"
NT_TIMELINE_EVENT = "timeline_event"
NT_SETUP = "setup"
NT_PAYOFF = "payoff"
NT_REVISION_IMPACT = "revision_impact"
NT_REWRITE_VARIANT = "rewrite_variant"
NT_CONTROLLED_APPLY = "controlled_apply_operation"
NT_DECISION_CARD = "decision_card"
NT_WORKFLOW_RUN = "workflow_run"

# PSYKE entry_type -> graph node type.
PSYKE_TYPE_TO_NODE = {
    "character": NT_CHARACTER,
    "place": NT_PLACE,
    "location": NT_PLACE,
    "object": NT_OBJECT,
    "lore": NT_LORE,
    "theme": NT_THEME,
    "motif": NT_MOTIF,
}

# -- Edge types -------------------------------------------------------------
ET_CONTAINS = "contains"
ET_APPEARS_IN = "appears_in"
ET_MENTIONS = "mentions"
ET_RELATES_TO = "relates_to"
ET_DEPENDS_ON = "depends_on"
ET_PRECEDES = "precedes"
ET_FOLLOWS = "follows"
ET_CAUSES = "causes"
ET_CONTRASTS = "contrasts"
ET_RESOLVES = "resolves"
ET_SETS_UP = "sets_up"
ET_PAYS_OFF = "pays_off"
ET_CONTRADICTS = "contradicts"
ET_REVISES = "revises"
ET_RISKS = "risks"
ET_BELONGS_TO = "belongs_to"
ET_DERIVED_FROM = "derived_from"
ET_INFERRED_FROM = "inferred_from"
ET_SUGGESTED_BY = "suggested_by"

# -- Confidence -------------------------------------------------------------
CONF_CONFIRMED = "confirmed"
CONF_LIKELY = "likely"
CONF_POSSIBLE = "possible"
CONF_UNKNOWN = "unknown"
CONFIDENCE_LEVELS = (CONF_CONFIRMED, CONF_LIKELY, CONF_POSSIBLE, CONF_UNKNOWN)
_CONF_RANK = {CONF_CONFIRMED: 0, CONF_LIKELY: 1, CONF_POSSIBLE: 2, CONF_UNKNOWN: 3}


def confidence_rank(confidence: str) -> int:
    return _CONF_RANK.get(confidence, 4)


def stronger_confidence(a: str, b: str) -> str:
    """Return the stronger (lower-rank) of two confidence levels."""
    return a if confidence_rank(a) <= confidence_rank(b) else b


# -- Source systems ---------------------------------------------------------
SS_PSYKE = "psyke"
SS_STRUCTURE = "structure"
SS_MANUSCRIPT = "manuscript"
SS_OUTLINE = "outline"
SS_PLOT = "plot"
SS_TIMELINE = "timeline"
SS_GRAPH = "graph"
SS_NOTES = "notes"
SS_SETUP_PAYOFF = "setup_payoff"
SS_REVISION = "revision_intelligence"
SS_REWRITE = "rewrite_sandbox"
SS_CONTROLLED_APPLY = "controlled_apply"
SS_RADAR = "decision_radar"
SS_WORKFLOW = "guided_workflows"
SS_USER = "user"

# -- Provenance (human-readable, traceable) ---------------------------------
PROV_PSYKE_RELATION = "explicit PSYKE relation"
PROV_PSYKE_PROGRESSION = "PSYKE progression"
PROV_GLOBAL_THEME = "global PSYKE entry"
PROV_SCENE_TEXT_MATCH = "scene text match"
PROV_OUTLINE_STRUCTURE = "outline structure"
PROV_CHAPTER_MEMBERSHIP = "chapter membership"
PROV_ACT_MEMBERSHIP = "act membership"
PROV_PLOT_MEMBERSHIP = "plot block membership"
PROV_SCENE_ORDER = "scene order"
PROV_NOTE_REFERENCE = "note reference"
PROV_NOTE_WIKILINK = "note wikilink"
PROV_REVISION_IMPACT = "revision impact report"
PROV_REWRITE_TARGET = "rewrite session target"
PROV_APPLY_TARGET = "controlled apply target"
PROV_APPLY_CONFLICT = "controlled apply conflict"
PROV_RADAR_CARD = "dashboard radar card"
PROV_USER_GRAPH_LINK = "user-created graph link"
PROV_STORY_LINK = "confirmed story link"
PROV_SETUP_PAYOFF = "setup/payoff link"
PROV_WORKFLOW = "guided workflow run"
