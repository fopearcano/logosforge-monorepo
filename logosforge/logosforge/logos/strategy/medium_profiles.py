"""Medium-specific strategy profiles.

Each profile declares, for a writing medium, the craft priorities, which context
blocks matter, which diagnostics are most relevant, which Logos actions to
surface first, and the medium's stance on key craft principles (so conflict
resolution can be deterministic — e.g. screenplay suppresses interiority).

No philosophy is hardcoded as universal: each medium sets its own stances, and a
template/plugin can still override at routing time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Engine ids (mirror project_compat.ALL_ENGINES).
NOVEL = "novel"
SCREENPLAY = "screenplay"
GRAPHIC_NOVEL = "graphic_novel"
STAGE_SCRIPT = "stage_script"
SERIES = "series"

# Context block ids the router can request (names are stable strings).
CTX_SCENE = "scene"
CTX_OUTLINE = "outline"
CTX_PSYKE = "psyke"
CTX_NOTES = "notes"
CTX_GRAPH = "graph"
CTX_STORY_MEMORY = "story_memory"
CTX_HEALTH = "health"


@dataclass
class MediumProfile:
    engine: str
    name: str
    priorities: tuple[str, ...]              # craft focuses, ordered
    context_blocks: tuple[str, ...]          # default context blocks
    diagnostic_categories: tuple[str, ...]   # which diagnostics matter most
    preferred_actions: tuple[str, ...]       # logos action ids to surface first
    # Stance on craft principles ("emphasize" | "allow" | "suppress").
    principles: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "name": self.name,
            "priorities": list(self.priorities),
            "context_blocks": list(self.context_blocks),
            "diagnostic_categories": list(self.diagnostic_categories),
            "preferred_actions": list(self.preferred_actions),
            "principles": dict(self.principles),
        }


_PROFILES: dict[str, MediumProfile] = {
    NOVEL: MediumProfile(
        engine=NOVEL, name="Novel",
        priorities=("prose rhythm", "narrative voice", "interiority",
                    "scene causality", "chapter rhythm", "character depth",
                    "thematic recurrence"),
        context_blocks=(CTX_SCENE, CTX_OUTLINE, CTX_PSYKE, CTX_NOTES,
                        CTX_STORY_MEMORY),
        diagnostic_categories=("character", "theme", "continuity", "structure"),
        preferred_actions=("suggest_revision", "improve_subtext", "expand",
                           "explain_selection", "identify_weakness"),
        principles={"interiority": "emphasize", "conflict": "emphasize",
                    "visual_action": "allow"},
    ),
    SCREENPLAY: MediumProfile(
        engine=SCREENPLAY, name="Screenplay",
        priorities=("visual action", "dialogue economy", "subtext",
                    "scene duration", "pacing per page", "setup/payoff",
                    "cinematic continuity"),
        context_blocks=(CTX_SCENE, CTX_PSYKE, CTX_OUTLINE),
        diagnostic_categories=("conflict", "setup_payoff", "structure",
                               "continuity"),
        preferred_actions=(
            # Phase 10A screenplay-specific actions surface first…
            "sp_diagnose_scene_economy",
            # Phase 3 — unified scene health + beat-plan alignment near the top.
            "sp_scene_health", "sp_beat_plan_alignment",
            # Phase 5 — Counterpart two-stance reflection.
            "sp_counterpart_reflection",
            # Phase 6 — controlled rewrite from Counterpart notes (preview-first).
            "sp_rewrite_from_counterpart",
            # Phase 7 — multi-scene continuity / coherence.
            "sp_continuity_check",
            # Phase 8 — project-level Screenplay Review Dashboard.
            "sp_review_dashboard",
            "sp_detect_setup_payoff",
            "sp_check_subtext", "sp_show_story_links", "sp_explain_link",
            "sp_revision_impact", "sp_check_impacted_scenes", "sp_check_psyke_impact",
            "sp_check_setup_payoff_impact", "sp_check_continuity_impact",
            "sp_prepare_revision_followup",
            "sp_production_status", "sp_validate_production",
            "sp_check_duplicate_scene_numbers", "sp_summarize_revision_set",
            "sp_explain_page_locking", "sp_check_fountain_production_export",
            "sp_prepare_production_export",
            "sp_validate_professional_output", "sp_output_readiness_report",
            "sp_preview_output", "sp_check_pdf_readiness", "sp_check_fdx_feasibility",
            "sp_explain_export_warnings", "sp_prepare_professional_export",
            "sp_validate_fountain_export", "sp_preview_fountain",
            "sp_check_fountain_compatibility", "sp_find_ambiguous_fountain",
            "sp_explain_fountain_warning", "sp_prepare_for_fountain",
            "sp_validate_export", "sp_export_readiness_report", "sp_preview_render",
            "sp_check_production_polish", "sp_find_orphan_dialogue",
            "sp_find_orphan_parenthetical",
            "sp_track_unresolved_setups",
            "sp_find_possible_payoffs", "sp_find_exposition",
            "sp_visual_action", "sp_check_scene_turn", "sp_reduce_interiority",
            "sp_clarify_objective", "sp_scene_economy", "sp_setup_payoff",
            "sp_overwritten_action", "sp_tighten_dialogue", "sp_suggest_visual_beat",
            "sp_suggest_action_interruption", "sp_reduce_on_the_nose",
            "sp_objective_gap", "sp_action_beat_subtext", "sp_emotion_to_behavior",
            "sp_sequence_logic", "sp_act_turn", "sp_central_question",
            "sp_escalation",
            "sp_track_setup_payoff", "sp_causal_chain", "sp_visual_turn",
            # …then the mode-agnostic craft actions.
            "improve_dialogue", "improve_subtext", "compress",
            "identify_weakness", "suggest_revision",
        ),
        # Screenplay suppresses prose interiority in favour of action/subtext.
        principles={"interiority": "suppress", "visual_action": "emphasize",
                    "conflict": "emphasize", "dialogue_economy": "emphasize"},
    ),
    GRAPHIC_NOVEL: MediumProfile(
        engine=GRAPHIC_NOVEL, name="Graphic Novel",
        priorities=("page turns", "panel rhythm", "visual motifs",
                    "spatial continuity", "dialogue compression",
                    "image/text balance", "recurring symbols"),
        context_blocks=(CTX_SCENE, CTX_PSYKE, CTX_GRAPH),
        diagnostic_categories=("theme", "graph", "continuity", "structure"),
        preferred_actions=("improve_subtext", "compress", "check_thematic_cluster",
                           "suggest_relations"),
        principles={"interiority": "suppress", "visual_action": "emphasize",
                    "visual_motif": "emphasize", "conflict": "allow"},
    ),
    STAGE_SCRIPT: MediumProfile(
        engine=STAGE_SCRIPT, name="Stage Script",
        priorities=("playable conflict", "blocking", "entrances/exits",
                    "dialogue performability", "scene economy",
                    "actor-driven subtext"),
        context_blocks=(CTX_SCENE, CTX_PSYKE),
        diagnostic_categories=("conflict", "character", "continuity", "structure"),
        preferred_actions=("improve_dialogue", "improve_subtext",
                           "identify_weakness", "suggest_revision"),
        principles={"interiority": "suppress", "conflict": "emphasize",
                    "blocking": "emphasize", "visual_action": "allow"},
    ),
    SERIES: MediumProfile(
        engine=SERIES, name="Series",
        priorities=("episode arcs", "season arcs", "character continuity",
                    "cliffhangers", "A/B/C plots", "long-term payoff"),
        context_blocks=(CTX_SCENE, CTX_OUTLINE, CTX_PSYKE, CTX_STORY_MEMORY),
        diagnostic_categories=("structure", "character", "setup_payoff",
                               "continuity", "timeline"),
        preferred_actions=("suggest_next_beat", "suggest_arc_development",
                           "identify_structure_problem", "strengthen_conflict"),
        principles={"interiority": "allow", "conflict": "emphasize",
                    "long_term_payoff": "emphasize"},
    ),
}


def get_profile(engine: str) -> MediumProfile:
    """Profile for an engine, defaulting safely to Novel."""
    return _PROFILES.get(engine, _PROFILES[NOVEL])


def all_profiles() -> dict[str, MediumProfile]:
    return dict(_PROFILES)
