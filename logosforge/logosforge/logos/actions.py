"""Logos action registry.

Mirrors the lightweight declarative style of ``connector_registry`` but for the
inline Logos layer. Phase 1 registers real, non-destructive Manuscript and
Outline actions (analysis, critique, and *preview* generation — alternatives are
returned for the author to consider, never auto-applied).

Destructive / auto-applying actions are listed in :data:`FUTURE_ACTIONS` as TODO
names and are intentionally NOT registered, so the controller can never run them
yet. Every registered action has ``destructive=False``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Section identifiers Logos integrates with.
SECTION_MANUSCRIPT = "Manuscript"
SECTION_OUTLINE = "Outline"
# Phase 3 — section-aware coverage.
SECTION_PSYKE = "PSYKE"
SECTION_PLOT = "Plot"
SECTION_TIMELINE = "Timeline"
SECTION_GRAPH = "Graph"
# Inline editor actions — selection transforms that return a clean, ready-to-apply
# result (not a labelled preview). These power lightweight inline assistants like
# the Whiteboard's Logos, where the writer applies the result straight into the
# draft. (The Manuscript-section generative actions are preview/options instead.)
SECTION_INLINE = "Inline"

# Categories are descriptive tags only; the binding safety invariant is
# ``destructive=False`` for everything registered in this phase.
CATEGORY_DIAGNOSTIC = "diagnostic"   # explain / identify / critique / check
CATEGORY_GENERATIVE = "generative"   # produce suggestions / alternatives (preview)


@dataclass(frozen=True)
class LogosAction:
    name: str
    label: str
    description: str
    category: str
    sections: tuple[str, ...]   # sections this action is offered in
    prompt: str                 # instruction sent to the shared chat backend
    needs_selection: bool = False
    destructive: bool = False
    # Writing modes this action is restricted to (Phase 10A). Empty = all modes.
    # Mode-restricted actions only surface when the project's writing_mode matches,
    # so e.g. screenplay-only actions never clutter a Novel project.
    modes: tuple[str, ...] = ()
    # Deterministic actions (Phase 10C) run a rule-based handler with NO LLM call.
    # The controller routes these to logosforge.logos.deterministic.
    deterministic: bool = False

    def applies_to(self, section_name: str) -> bool:
        return not self.sections or section_name in self.sections

    def applies_to_mode(self, writing_mode: str) -> bool:
        # Unrestricted actions always apply. Restricted actions apply when the
        # mode matches; an unknown/blank mode shows everything (back-compat).
        if not self.modes:
            return True
        if not writing_mode:
            return True
        return writing_mode in self.modes

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "category": self.category,
            "sections": list(self.sections),
            "needs_selection": self.needs_selection,
            "destructive": self.destructive,
            "modes": list(self.modes),
            "deterministic": self.deterministic,
        }


_REGISTRY: dict[str, LogosAction] = {}


def register(action: LogosAction) -> LogosAction:
    _REGISTRY[action.name] = action
    return action


def get_action(name: str) -> LogosAction | None:
    return _REGISTRY.get(name)


def list_actions() -> list[LogosAction]:
    return list(_REGISTRY.values())


def list_actions_for_section(
    section_name: str, *, writing_mode: str = "",
) -> list[LogosAction]:
    """Actions for a section, optionally filtered by the project writing mode.

    With no ``writing_mode`` the behavior is unchanged (all section actions).
    When a mode is given, mode-restricted actions only appear for their mode.
    """
    return [
        a for a in _REGISTRY.values()
        if a.applies_to(section_name) and a.applies_to_mode(writing_mode)
    ]


def describe_all_actions() -> list[dict[str, Any]]:
    return [a.describe() for a in _REGISTRY.values()]


# ---------------------------------------------------------------------------
# UX grouping (Phase 10 — readable dropdown). Pure helper: maps each action to a
# readable category and buckets a list into ordered groups. No Qt, no behavior
# change to the registry — purely for presentation.
# ---------------------------------------------------------------------------

UX_GROUP_ORDER: tuple[str, ...] = (
    "Planning", "Checks", "Reflection", "Rewrite", "Export", "Other",
)
_EXPORT_HINTS = ("fountain", "export", "output", "production", "pdf", "fdx",
                 "render", "prepare_for", "prepare_professional",
                 "prepare_production")


def ux_group(action: "LogosAction") -> str:
    """Readable UX category for an action (Planning/Checks/Reflection/Rewrite/
    Export/Other). Deterministic; based on name + category."""
    n = (action.name or "").lower()
    if any(h in n for h in _EXPORT_HINTS):
        return "Export"
    if "rewrite" in n:
        return "Rewrite"
    if "reflection" in n or n == "counterpart_critique":
        return "Reflection"
    if "beat_plan" in n and "alignment" not in n:
        return "Planning"
    if getattr(action, "category", "") == CATEGORY_GENERATIVE:
        return "Rewrite"
    return "Checks"


def group_actions(
    actions: list["LogosAction"],
) -> list[tuple[str, list["LogosAction"]]]:
    """Bucket *actions* into ordered UX groups, preserving each action's relative
    order within its group. Empty groups are omitted."""
    buckets: dict[str, list[LogosAction]] = {}
    for a in actions:
        buckets.setdefault(ux_group(a), []).append(a)
    return [(g, buckets[g]) for g in UX_GROUP_ORDER if buckets.get(g)]


def grouped_actions_for_section(
    section_name: str, *, writing_mode: str = "",
) -> list[tuple[str, list["LogosAction"]]]:
    """Section actions (mode-filtered) bucketed into ordered UX groups."""
    return group_actions(
        list_actions_for_section(section_name, writing_mode=writing_mode))


# ---------------------------------------------------------------------------
# Manuscript actions (selection-aware, non-destructive)
# ---------------------------------------------------------------------------

register(LogosAction(
    name="explain_selection", label="Explain Selection",
    description="Explain what the selected passage is doing and how it reads.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    needs_selection=True,
    prompt=(
        "Explain the selected passage: its intent, tone, technique, and how it "
        "reads. Note anything notable. Do not rewrite it."
    ),
))

register(LogosAction(
    name="suggest_revision", label="Suggest Revision",
    description="Suggest concrete revision directions (no rewrite).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    needs_selection=True,
    prompt=(
        "Suggest concrete revision directions for the selected passage "
        "(clarity, rhythm, imagery, tension). Present them as a short bullet "
        "list of options. Do NOT produce a finished rewrite."
    ),
))

register(LogosAction(
    name="rewrite_options", label="Rewrite Options",
    description="Offer 2–3 labelled alternate versions (preview only).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    needs_selection=True,
    prompt=(
        "Provide 2 to 3 distinct alternate versions of the selected passage, "
        "each preserving its meaning but varying voice/rhythm/emphasis. Label "
        "them clearly as 'Option 1:', 'Option 2:', 'Option 3:'. These are "
        "options for the author to consider — do not pick one or apply changes."
    ),
))

register(LogosAction(
    name="expand", label="Expand",
    description="Show a richer, expanded version of the selection (preview).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    needs_selection=True,
    prompt=(
        "Show an expanded version of the selected passage — add sensory detail, "
        "beats, or interiority where it serves the scene. Present it as a "
        "labelled 'Expanded version:' preview. Do not replace the original."
    ),
))

register(LogosAction(
    name="compress", label="Compress",
    description="Show a tighter, compressed version of the selection (preview).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    needs_selection=True,
    prompt=(
        "Show a tighter, compressed version of the selected passage that keeps "
        "its essential meaning and impact. Present it as a labelled 'Compressed "
        "version:' preview. Do not replace the original."
    ),
))

register(LogosAction(
    name="improve_dialogue", label="Improve Dialogue",
    description="Diagnose and suggest stronger dialogue (preview).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    needs_selection=True,
    prompt=(
        "Focus on the dialogue in the selection. Note what works and what is "
        "flat or on-the-nose, then offer a few sharper line options. Keep them "
        "as suggestions — do not rewrite the whole passage."
    ),
))

register(LogosAction(
    name="improve_subtext", label="Improve Subtext",
    description="Suggest ways to deepen subtext (preview).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    needs_selection=True,
    prompt=(
        "Analyse the subtext of the selection — what is left unsaid, the gap "
        "between surface and intent — and suggest concrete ways to deepen it. "
        "Offer suggestions, not a finished rewrite."
    ),
))

register(LogosAction(
    name="identify_weakness", label="Identify Weakness",
    description="Diagnose craft weaknesses in the selection/scene.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt=(
        "Identify the most likely craft weaknesses here (goal, conflict, "
        "stakes, pacing, POV, clarity, continuity). List them as concise "
        "diagnostics. Do not rewrite anything."
    ),
))

# ---------------------------------------------------------------------------
# Inline editor actions (clean, ready-to-apply selection transforms)
#
# Unlike the Manuscript "options/preview" actions above, these return ONLY the
# transformed text so an inline assistant (e.g. the Whiteboard Logos) can apply
# it straight into the draft. Generative => the result is proposed prose a UI may
# swap in; diagnostic => it only reports and must never replace the selection.
# ---------------------------------------------------------------------------

register(LogosAction(
    name="inline_rewrite", label="Rewrite",
    description="Rewrite the selection, preserving meaning and voice.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_INLINE,), needs_selection=True,
    prompt="Rewrite the text, preserving meaning and voice. Return only the rewrite.",
))

register(LogosAction(
    name="inline_expand", label="Expand",
    description="Expand the selection with more detail.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_INLINE,), needs_selection=True,
    prompt="Expand the text with more detail. Return only the expanded text.",
))

register(LogosAction(
    name="inline_compress", label="Compress",
    description="Tighten the selection to be shorter and punchier.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_INLINE,), needs_selection=True,
    prompt="Tighten the text to be shorter and punchier. Return only the result.",
))

register(LogosAction(
    name="inline_improve_dialogue", label="Improve Dialogue",
    description="Sharpen the dialogue (subtext, distinct voices, economy).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_INLINE,), needs_selection=True,
    prompt=(
        "Improve the dialogue: subtext, distinct voices, economy. "
        "Return only the result."
    ),
))

register(LogosAction(
    name="inline_improve_action", label="Improve Action",
    description="Sharpen the action lines (vivid, present-tense, visual).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_INLINE,), needs_selection=True,
    prompt=(
        "Improve the action lines: vivid, present-tense, visual. "
        "Return only the result."
    ),
))

register(LogosAction(
    name="inline_make_visual", label="Make More Visual",
    description="Make the selection more visual and concrete.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_INLINE,), needs_selection=True,
    prompt="Make the writing more visual and concrete. Return only the result.",
))

register(LogosAction(
    name="inline_summarize", label="Summarize",
    description="Summarize the selection in 1–3 sentences.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_INLINE,), needs_selection=True,
    prompt="Summarize the passage in 1-3 sentences.",
))

register(LogosAction(
    name="inline_suggest", label="Suggest",
    description="Suggest what could come next (brief, concrete).",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_INLINE,),
    prompt="Suggest what could come next. Be brief and concrete.",
))

register(LogosAction(
    name="inline_explain", label="Explain",
    description="Explain what the passage is doing (craft, intent).",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_INLINE,),
    prompt="Explain what the passage is doing (craft, intent). Be brief.",
))

register(LogosAction(
    name="connect_to_psyke", label="Connect to PSYKE",
    description="Find PSYKE bible entries related to the selection (deterministic).",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_INLINE, SECTION_MANUSCRIPT),
    deterministic=True,
    prompt="",  # deterministic — runs a rule-based handler, no LLM call
))

# ---------------------------------------------------------------------------
# Outline actions (node-aware, non-destructive)
# ---------------------------------------------------------------------------

register(LogosAction(
    name="summarize_node", label="Summarize Node",
    description="Summarize the selected outline node in context.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_OUTLINE,),
    prompt=(
        "Summarize the selected outline node (what it is about and the work it "
        "does in the story) in a few sentences, using the surrounding outline."
    ),
))

register(LogosAction(
    name="identify_structure_problem", label="Identify Structure Problem",
    description="Diagnose structural problems around the selected node.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_OUTLINE,),
    prompt=(
        "Using the outline context, identify likely structural problems around "
        "the selected node (missing turning points, pacing, act balance, "
        "cause/effect gaps). List them as diagnostics. Do not generate nodes."
    ),
))

register(LogosAction(
    name="suggest_next_beat", label="Suggest Next Beat",
    description="Suggest candidate next beats (suggestions only).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_OUTLINE,),
    prompt=(
        "Suggest 2 to 3 candidate next beats that could follow the selected "
        "node, each with a one-line rationale. These are suggestions only — do "
        "NOT create outline nodes."
    ),
))

register(LogosAction(
    name="strengthen_conflict", label="Strengthen Conflict",
    description="Suggest ways to raise conflict/stakes for the node.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_OUTLINE,),
    prompt=(
        "Suggest concrete ways to strengthen the conflict and stakes of the "
        "selected node and its surrounding beats. Offer suggestions only."
    ),
))

register(LogosAction(
    name="check_template_fit", label="Check Template Fit",
    description="Assess how the outline fits the selected template.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_OUTLINE,),
    prompt=(
        "Assess how well the current outline fits the selected structural "
        "template. Point out which template beats are present, missing, or "
        "out of place. Do not modify the outline."
    ),
))

# ---------------------------------------------------------------------------
# Cross-section
# ---------------------------------------------------------------------------

register(LogosAction(
    name="counterpart_critique", label="Counterpart Critique",
    description="A sharp, skeptical critique from an opposing viewpoint.",
    category=CATEGORY_DIAGNOSTIC,
    sections=(SECTION_MANUSCRIPT, SECTION_OUTLINE, SECTION_PSYKE,
              SECTION_PLOT, SECTION_TIMELINE, SECTION_GRAPH),
    prompt=(
        "Act as a sharp, skeptical counterpart critic. Challenge this "
        "selection/element: name its weakest assumptions, where it "
        "underdelivers, and what a demanding reader would object to. Be "
        "specific and honest, but constructive. Do not rewrite anything."
    ),
))


# ---------------------------------------------------------------------------
# PSYKE actions (entry-aware)
# ---------------------------------------------------------------------------

_PSYKE = (SECTION_PSYKE,)
for _name, _label, _desc, _cat, _prompt in [
    ("explain_entry_role", "Explain Entry Role",
     "Explain this entry's narrative role.", CATEGORY_DIAGNOSTIC,
     "Explain this PSYKE entry's role in the story — what it contributes and "
     "how it connects to the rest. Do not modify it."),
    ("find_missing_details", "Find Missing Details",
     "Point out gaps in this entry's details.", CATEGORY_DIAGNOSTIC,
     "Review this PSYKE entry and list the most important missing or thin "
     "details that would strengthen it. List them as diagnostics."),
    ("check_continuity", "Check Continuity",
     "Check this entry for continuity issues.", CATEGORY_DIAGNOSTIC,
     "Check this PSYKE entry for continuity issues against the scenes it "
     "appears in and its progressions. List concerns. Do not modify anything."),
    ("check_relationships", "Check Relationships",
     "Assess this entry's relationships.", CATEGORY_DIAGNOSTIC,
     "Assess this entry's relationships: which are strong, missing, or "
     "underused. List observations. Do not modify anything."),
    ("suggest_arc_development", "Suggest Arc Development",
     "Suggest how this entry could develop.", CATEGORY_GENERATIVE,
     "Suggest how this entry could develop across the story (an arc). Offer "
     "concrete progression ideas as suggestions only."),
    ("suggest_details", "Suggest Details",
     "Suggest concrete details to add.", CATEGORY_GENERATIVE,
     "Suggest concrete details (traits, history, specifics) that would enrich "
     "this entry. Offer them as suggestions for the author to add."),
    ("suggest_relations", "Suggest Relations",
     "Suggest relationships to other entries.", CATEGORY_GENERATIVE,
     "Suggest meaningful relationships between this entry and other story "
     "elements, with a one-line rationale each. Suggestions only."),
    ("suggest_progression", "Suggest Progression",
     "Suggest a progression note for this entry.", CATEGORY_GENERATIVE,
     "Suggest a single concrete progression note describing how this entry "
     "changes at this point in the story."),
    ("suggest_aliases", "Suggest Aliases",
     "Suggest alternate names/aliases.", CATEGORY_GENERATIVE,
     "Suggest a few fitting aliases or alternate names for this entry. "
     "Suggestions only."),
    ("suggest_notes", "Suggest Notes",
     "Suggest a note worth recording.", CATEGORY_GENERATIVE,
     "Suggest a useful note the author should record about this entry."),
]:
    register(LogosAction(name=_name, label=_label, description=_desc,
                         category=_cat, sections=_PSYKE, prompt=_prompt))


# ---------------------------------------------------------------------------
# Plot actions (block / structural-unit aware; Plot is scene-derived)
# ---------------------------------------------------------------------------

_PLOT = (SECTION_PLOT,)
for _name, _label, _desc, _cat, _prompt in [
    ("explain_plot_function", "Explain Plot Function",
     "Explain this block's plot function.", CATEGORY_DIAGNOSTIC,
     "Explain the function of this plot block / structural unit in the story. "
     "Do not modify anything."),
    ("identify_weak_conflict", "Identify Weak Conflict",
     "Diagnose weak conflict here.", CATEGORY_DIAGNOSTIC,
     "Identify where the conflict in this plot block is weak or unclear. List "
     "concrete diagnostics. Do not rewrite anything."),
    ("check_escalation", "Check Escalation",
     "Check whether tension escalates.", CATEGORY_DIAGNOSTIC,
     "Assess whether tension and stakes escalate across this block and its "
     "scenes. Note any plateaus or drops. Do not modify anything."),
    ("check_cause_effect", "Check Cause/Effect",
     "Check cause-and-effect logic.", CATEGORY_DIAGNOSTIC,
     "Check the cause-and-effect logic linking the scenes in this block. Flag "
     "gaps or coincidences. Do not modify anything."),
    ("suggest_stronger_turn", "Suggest Stronger Turn",
     "Suggest a stronger turning point.", CATEGORY_GENERATIVE,
     "Suggest how to make the turning point of this block sharper and more "
     "consequential. Suggestions only."),
    ("suggest_plot_block_summary", "Suggest Plot Block Summary",
     "Draft a summary for this block/scene.", CATEGORY_GENERATIVE,
     "Draft a concise summary capturing the dramatic function of this plot "
     "block or its selected scene."),
    ("suggest_scene_purpose", "Suggest Scene Purpose",
     "Clarify the scene's purpose.", CATEGORY_GENERATIVE,
     "Articulate the dramatic purpose this scene should serve within its "
     "plotline. Offer as a suggestion."),
    ("suggest_conflict_upgrade", "Suggest Conflict Upgrade",
     "Suggest ways to raise the conflict.", CATEGORY_GENERATIVE,
     "Suggest concrete ways to upgrade the conflict and stakes here. "
     "Suggestions only."),
    ("suggest_setup_payoff_link", "Suggest Setup/Payoff Link",
     "Suggest a setup/payoff connection.", CATEGORY_GENERATIVE,
     "Suggest a setup/payoff link this block could plant or resolve, with a "
     "rationale. Suggestion only — do not modify data."),
]:
    register(LogosAction(name=_name, label=_label, description=_desc,
                         category=_cat, sections=_PLOT, prompt=_prompt))


# ---------------------------------------------------------------------------
# Timeline actions (event / scene aware; chronology is sort-order based)
# ---------------------------------------------------------------------------

_TIMELINE = (SECTION_TIMELINE,)
for _name, _label, _desc, _cat, _prompt in [
    ("explain_timeline_position", "Explain Timeline Position",
     "Explain this event's place in time.", CATEGORY_DIAGNOSTIC,
     "Explain this event's position in the story's chronology and what it "
     "accomplishes there. Do not modify anything."),
    ("check_chronology", "Check Chronology",
     "Check chronology consistency.", CATEGORY_DIAGNOSTIC,
     "Check the chronology around this event for inconsistencies or ordering "
     "problems. List concerns. Do not reorder anything."),
    ("check_pacing", "Check Pacing",
     "Assess pacing around this event.", CATEGORY_DIAGNOSTIC,
     "Assess the pacing around this event — is it rushed or slack relative to "
     "its neighbours? Do not modify anything."),
    ("check_gap", "Check Gap",
     "Detect a gap before/after this event.", CATEGORY_DIAGNOSTIC,
     "Detect whether there is a narrative or temporal gap before or after this "
     "event that needs bridging. Do not modify anything."),
    ("check_causality", "Check Causality",
     "Check causal links to neighbours.", CATEGORY_DIAGNOSTIC,
     "Check the causal links between this event and the ones around it. Flag "
     "missing causation. Do not modify anything."),
    ("suggest_next_event", "Suggest Next Event",
     "Suggest what could come next.", CATEGORY_GENERATIVE,
     "Suggest 2-3 candidate next events that could follow, each with a brief "
     "rationale. Suggestions only — do not create events."),
    ("suggest_timeline_note", "Suggest Timeline Note",
     "Suggest a note for this point.", CATEGORY_GENERATIVE,
     "Suggest a useful timeline note to record at this point in the story."),
    ("suggest_event_summary", "Suggest Event Summary",
     "Draft a summary for this event.", CATEGORY_GENERATIVE,
     "Draft a concise summary of this timeline event / scene."),
    ("suggest_causal_link", "Suggest Causal Link",
     "Suggest a causal connection.", CATEGORY_GENERATIVE,
     "Suggest a causal link between this event and a neighbouring one, with a "
     "rationale. Suggestion only."),
    ("suggest_bridge_scene", "Suggest Missing Bridge Scene",
     "Suggest a bridge scene to fill a gap.", CATEGORY_GENERATIVE,
     "Suggest a bridge scene that would smooth a gap around this event. "
     "Describe it as a suggestion — do not create it."),
]:
    register(LogosAction(name=_name, label=_label, description=_desc,
                         category=_cat, sections=_TIMELINE, prompt=_prompt))


# ---------------------------------------------------------------------------
# Graph actions (node / relationship aware; graph is a view, not a source)
# ---------------------------------------------------------------------------

_GRAPH = (SECTION_GRAPH,)
for _name, _label, _desc, _cat, _prompt in [
    ("explain_node", "Explain Node",
     "Explain the selected node.", CATEGORY_DIAGNOSTIC,
     "Explain the selected graph node: what it represents and its role in the "
     "story network. Do not modify anything."),
    ("explain_relationship_cluster", "Explain Relationship Cluster",
     "Explain this node's cluster.", CATEGORY_DIAGNOSTIC,
     "Explain the cluster of relationships around the selected node — who/what "
     "it connects and why. Do not modify anything."),
    ("identify_missing_links", "Identify Missing Links",
     "Find likely missing connections.", CATEGORY_DIAGNOSTIC,
     "Identify likely missing links for the selected node given its "
     "neighbours. List them as diagnostics."),
    ("identify_isolated_node", "Identify Isolated Node",
     "Assess whether this node is isolated.", CATEGORY_DIAGNOSTIC,
     "Assess whether the selected node is under-connected or isolated, and why "
     "that might be a problem. Do not modify anything."),
    ("check_thematic_cluster", "Check Thematic Cluster",
     "Check thematic coherence of the cluster.", CATEGORY_DIAGNOSTIC,
     "Check whether the thematic cluster around this node is coherent. Note "
     "tensions or gaps. Do not modify anything."),
    ("suggest_relationship", "Suggest Relationship",
     "Suggest a relationship for this node.", CATEGORY_GENERATIVE,
     "Suggest a meaningful relationship the selected node could have, with a "
     "rationale. Suggestion only."),
    ("suggest_psyke_relation", "Suggest PSYKE Relation",
     "Suggest a PSYKE relation to add.", CATEGORY_GENERATIVE,
     "Suggest a PSYKE relation involving the selected entity, with a rationale. "
     "Suggestion only — applied via PSYKE if the author confirms."),
    ("suggest_note_from_graph", "Suggest Note",
     "Suggest a note about this node.", CATEGORY_GENERATIVE,
     "Suggest a useful note to record about the selected node."),
    ("suggest_setup_payoff_edge", "Suggest Setup/Payoff Edge",
     "Suggest a setup/payoff edge.", CATEGORY_GENERATIVE,
     "Suggest a setup/payoff connection involving this node, with a rationale. "
     "Suggestion only."),
    ("suggest_character_theme_link", "Suggest Character/Theme Link",
     "Suggest a character↔theme link.", CATEGORY_GENERATIVE,
     "Suggest a meaningful character-to-theme link involving this node, with a "
     "rationale. Suggestion only."),
]:
    register(LogosAction(name=_name, label=_label, description=_desc,
                         category=_cat, sections=_GRAPH, prompt=_prompt))


# ---------------------------------------------------------------------------
# Screenplay-mode actions (Phase 10A). Restricted to writing_mode="screenplay"
# via the `modes` field so they never clutter Novel projects. All non-destructive
# and run through the normal preview/confirm path. Existing mode-agnostic actions
# (improve_dialogue, improve_subtext, …) are unchanged and still apply.
# ---------------------------------------------------------------------------

_SP = ("screenplay",)

# Manuscript + Screenplay
for _name, _label, _desc, _cat, _needs_sel, _prompt in [
    ("sp_visual_action", "Convert Prose to Visual Action",
     "Recast novelistic prose as visible, filmable action.", CATEGORY_GENERATIVE, True,
     "Suggest how to recast the selected passage as visible, filmable screen "
     "action — what the camera sees and hears. Prefer concrete behavior over "
     "interior narration. Offer options; do not produce a finished rewrite."),
    ("sp_check_scene_turn", "Check Scene Turn",
     "Does the scene turn on a clear value shift?", CATEGORY_DIAGNOSTIC, False,
     "Assess whether this scene turns on a clear value shift (a change in the "
     "character's situation from start to end). If the turn is weak or missing, "
     "say so and point to where. Do not modify anything."),
    ("sp_reduce_interiority", "Reduce Novelistic Interior Exposition",
     "Flag interior exposition that can't be filmed.", CATEGORY_GENERATIVE, True,
     "Identify interior exposition in the selection that cannot be seen or heard "
     "on screen, and suggest how to externalize it as action, behavior, or "
     "subtextual dialogue. Suggestions only."),
    ("sp_clarify_objective", "Clarify Character Objective",
     "Is the character's scene objective clear?", CATEGORY_DIAGNOSTIC, False,
     "Identify what the viewpoint character wants in this scene and how visibly "
     "it drives the action. If the objective is unclear, explain why. Do not "
     "modify anything."),
    ("sp_scene_economy", "Improve Scene Economy",
     "Tighten the scene to its essential beats.", CATEGORY_GENERATIVE, True,
     "Suggest how to tighten the selected screenplay material to its essential "
     "beats — entering late, leaving early, cutting redundancy. Suggestions only."),
    ("sp_setup_payoff", "Strengthen Setup/Payoff",
     "Suggest setups/payoffs this scene could plant or land.", CATEGORY_GENERATIVE, True,
     "Suggest setups this passage could plant, or payoffs it could land, to "
     "strengthen the screenplay's causal weave. Suggestions only; do not rewrite."),
    ("sp_overwritten_action", "Detect Overwritten Action",
     "Flag dense/overwritten action lines.", CATEGORY_DIAGNOSTIC, True,
     "Identify action lines in the selection that are overwritten — too dense, "
     "novelistic, or describing the unfilmable — and point to where they could "
     "be lean and visual. Do not rewrite; just diagnose."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc, category=_cat,
        sections=(SECTION_MANUSCRIPT,), prompt=_prompt,
        needs_selection=_needs_sel, modes=_SP,
    ))

# Manuscript + Screenplay — Phase 10C.
# Deterministic diagnostic (no LLM; handler in logos.deterministic):
register(LogosAction(
    name="sp_diagnose_scene_economy", label="Diagnose Scene Economy",
    description="Run deterministic screenplay scene-economy diagnostics for this scene.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=_SP, deterministic=True,
))
# Manuscript + Screenplay — Phase 3 (unified scene health + beat-plan alignment).
# Both deterministic, full-scene (no selection needed), preview-only.
register(LogosAction(
    name="sp_scene_health", label="Screenplay Check",
    description="Full deterministic scene health: format, visual writing, dialogue "
                "economy, dramatic function, beat-plan alignment, and continuity.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=_SP, deterministic=True,
))
register(LogosAction(
    name="sp_beat_plan_alignment", label="Beat Plan Alignment",
    description="Check whether the scene body reflects its beat plan (conflict, "
                "turning point, emotional shift, objective).",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=_SP, deterministic=True,
))
# Manuscript + Screenplay — Phase 5 (Counterpart / Reflection).
# Deterministic two-stance scene reflection (internal character + external
# audience), full-scene, preview-only — never rewrites or auto-applies.
register(LogosAction(
    name="sp_counterpart_reflection", label="Counterpart Reflection",
    description="Reflect on this scene from the inside (each character) and the "
                "outside (audience/story): feedback and questions, never a rewrite.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=_SP, deterministic=True,
))
# Manuscript + Screenplay — Phase 6 (Controlled Rewrite). Generative, full-scene
# (no selection needed); shows a preview/diff before any confirmed apply — never
# auto-applies. The grounded preview→apply path lives in screenplay_rewrite.
register(LogosAction(
    name="sp_rewrite_from_counterpart", label="Rewrite from Counterpart Notes",
    description="Propose a revision that addresses the Counterpart reflection — "
                "shown as a preview to review and confirm, never auto-applied.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    prompt=(
        "Using the scene's diagnostics and beat plan in context, propose a "
        "revised version of this screenplay scene that addresses its most "
        "important internal-character and external-audience gaps. Return "
        "screenplay text only — no commentary or markdown. This is a preview "
        "for the writer to review; do not claim it is applied."
    ),
    modes=_SP,
))
# Phase 7 — multi-scene continuity / coherence. Deterministic, project-level
# (no selection or current scene needed); read-only report. Offered in the
# Manuscript, Timeline, and Outline sections so it's reachable as "Screenplay
# Continuity Check" / "Check Timeline Alignment" / "Check Scene Chain".
register(LogosAction(
    name="sp_continuity_check", label="Screenplay Continuity Check",
    description="Analyze how the scenes work together: causal flow, setup/payoff, "
                "character continuity, Timeline alignment, and PSYKE consistency.",
    category=CATEGORY_DIAGNOSTIC,
    sections=(SECTION_MANUSCRIPT, SECTION_TIMELINE, SECTION_OUTLINE),
    prompt="", modes=_SP, deterministic=True,
))
# Phase 8 — project-level Screenplay Review Dashboard. Deterministic, read-only
# roll-up of plan/body/health/continuity/Timeline/PSYKE/export status per scene.
register(LogosAction(
    name="sp_review_dashboard", label="Screenplay Review Dashboard",
    description="Project overview: which scenes are planned, written, weak, lack "
                "headings, have continuity/export warnings, or aren't linked to "
                "the Timeline — plus a recommended next action per scene.",
    category=CATEGORY_DIAGNOSTIC,
    sections=(SECTION_MANUSCRIPT, SECTION_TIMELINE, SECTION_OUTLINE),
    prompt="", modes=_SP, deterministic=True,
))
# Generative rewrite/suggestion actions (LLM only on explicit invocation):
for _name, _label, _desc, _prompt in [
    ("sp_tighten_dialogue", "Tighten Dialogue Economy",
     "Suggest leaner dialogue without losing intent.",
     "Suggest how to tighten the selected dialogue — cut throat-clearing, "
     "on-the-nose exposition and redundancy — while preserving intent and "
     "subtext. Suggestions only; do not produce a finished rewrite."),
    ("sp_suggest_visual_beat", "Suggest Visual Beat",
     "Propose a visual beat to externalize the moment.",
     "Suggest one or two concrete visual beats (behavior, business, image) that "
     "could externalize what this moment is doing internally. Suggestions only."),
    ("sp_suggest_action_interruption", "Suggest Action Interruption",
     "Break up dialogue with a visual action beat.",
     "Suggest where a short action beat could interrupt this dialogue to vary "
     "rhythm and show behavior. Suggestions only; do not rewrite the dialogue."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
        prompt=_prompt, needs_selection=True, modes=_SP,
    ))

# Manuscript + Screenplay — Phase 10D (setup/payoff + subtext).
# Deterministic (no LLM; handlers in logos.deterministic):
for _name, _label, _desc in [
    ("sp_detect_setup_payoff", "Detect Setup/Payoff Candidates",
     "Scan the project for setup/payoff candidates (deterministic)."),
    ("sp_track_unresolved_setups", "Track Unresolved Setups",
     "List planted setups that never recur."),
    ("sp_find_possible_payoffs", "Find Possible Payoffs",
     "List elements that recur as possible payoffs."),
    ("sp_check_subtext", "Check Dialogue Subtext",
     "Flag on-the-nose / expositional dialogue in this scene (deterministic)."),
    ("sp_find_exposition", "Find Exposition in Dialogue",
     "Surface exposition markers in this scene's dialogue."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", modes=_SP, deterministic=True,
    ))
# Manuscript — Phase 10L (Adaptive Rewrite Sandbox; writing-mode-aware, NOT
# screenplay-only). Deterministic status/score actions (mutations + generation go
# through the explicit engine API).
for _name, _label, _desc in [
    ("rw_sandbox_status", "Rewrite Sandbox",
     "Show the open rewrite session status (deterministic; nothing auto-applies)."),
    ("rw_explain_tradeoffs", "Explain Rewrite Tradeoffs",
     "Summarize the tradeoffs across the open session's variants."),
    ("rw_score_variants", "Score Rewrite Variants",
     "Re-score the open session's variants deterministically."),
    ("rw_check_psyke_preservation", "Check PSYKE Preservation",
     "Per-variant PSYKE preservation (preserved/removed/added)."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", deterministic=True,
    ))

# Manuscript — Phase 10N (Project Intelligence Dashboard; mode-agnostic, read-only).
for _name, _label, _desc in [
    ("pi_dashboard_status", "Project Intelligence",
     "Summarize project status, structure and PSYKE (deterministic)."),
    ("pi_decision_radar", "Decision Radar",
     "Ranked decisions/risks/opportunities for the project (deterministic)."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", deterministic=True,
    ))

register(LogosAction(
    name="pi_explain_dashboard", label="Explain Dashboard",
    description="Ask the Assistant to interpret the dashboard / suggest next steps.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    prompt=(
        "Given the project intelligence summary, interpret the most important "
        "current state and suggest a short prioritized list of next steps. "
        "Advisory only; do not rewrite or mutate anything."
    ),
))

# Manuscript — Phase 10Q (Semantic Continuity Engine; mode-agnostic, read-only).
for _name, _label, _desc in [
    ("ct_run_check", "Run Continuity Check",
     "Run a project continuity check and record the run (deterministic)."),
    ("ct_check_scene", "Check Current Scene Continuity",
     "Continuity issues touching the current scene (deterministic)."),
    ("ct_show_issues", "Show Continuity Issues",
     "List the top open continuity issues (deterministic)."),
    ("ct_decision_cards", "Continuity Decision Cards",
     "Continuity issues as ranked decision cards (deterministic)."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", deterministic=True,
    ))

register(LogosAction(
    name="ct_explain_issue", label="Explain Continuity Issue",
    description="Ask the Assistant to explain the top continuity issue / fix options.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    prompt=(
        "Given the continuity issue summary, explain the most important open issue "
        "and propose concrete fix options (e.g. a bridge beat or transition). "
        "Advisory only; do not rewrite, apply, auto-fix, or dismiss anything — the "
        "user decides, and any change must route through Controlled Apply."
    ),
))

# Manuscript — Phase 10P (Narrative Knowledge Graph; mode-agnostic, read-only).
for _name, _label, _desc in [
    ("kg_build_graph", "Build Knowledge Graph",
     "Build the narrative knowledge graph and summarize it (deterministic)."),
    ("kg_refresh_graph", "Refresh Knowledge Graph",
     "Rebuild the knowledge graph and record a snapshot (deterministic)."),
    ("kg_scene_neighborhood", "Show Scene Neighborhood",
     "What the current scene connects to (deterministic)."),
    ("kg_psyke_neighborhood", "Show PSYKE Neighborhood",
     "What the current PSYKE entry connects to (deterministic)."),
    ("kg_find_orphans", "Find Orphan Nodes",
     "Story elements with no connections (deterministic)."),
    ("kg_find_weak_links", "Find Weak Links",
     "Inferred edges that may need confirmation (deterministic)."),
    ("kg_find_undefined_terms", "Find Undefined Terms",
     "Note terms not defined in PSYKE (deterministic)."),
    ("kg_decision_cards", "Generate Decision Cards from Graph",
     "Graph-derived decisions/risks/opportunities (deterministic)."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", deterministic=True,
    ))

register(LogosAction(
    name="kg_explain_graph", label="Explain Knowledge Graph",
    description="Ask the Assistant to interpret the project's knowledge graph.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    prompt=(
        "Given the narrative knowledge graph summary, interpret the project's "
        "structure: which elements are central, which are isolated, and what the "
        "weak/inferred links suggest. Advisory only; do not rewrite, mutate, or "
        "confirm any edge — confirmation is the user's decision."
    ),
))

# Manuscript — Phase 10O (Guided Workflows; mode-agnostic, read-only).
for _name, _label, _desc in [
    ("wf_active_workflows", "Active Workflows",
     "Show active guided workflows and the current step (deterministic)."),
    ("wf_recommend_workflows", "Recommend Workflows",
     "Suggest guided workflows from the Decision Radar (deterministic)."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", deterministic=True,
    ))

register(LogosAction(
    name="wf_explain_next_step", label="Explain Workflow Step",
    description="Ask the Assistant to explain the current guided-workflow step.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    prompt=(
        "Given the active guided workflow and its current step, explain what the "
        "step is asking for and suggest a concrete way to accomplish it using the "
        "current project. Advisory only; do not rewrite or mutate anything, and do "
        "not mark the step done — that is the user's decision."
    ),
))

# Manuscript — Phase 10M (Controlled Apply; mode-agnostic, read-only status).
for _name, _label, _desc in [
    ("ca_apply_history", "Apply History",
     "Recent controlled-apply operations (deterministic)."),
    ("ca_explain_conflicts", "Explain Apply Conflicts",
     "Explain conflicts on the latest pending apply preview."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", deterministic=True,
    ))

register(LogosAction(
    name="rw_suggest_strategy", label="Suggest Rewrite Strategy",
    description="Suggest a rewrite strategy for the selection (advisory).",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    needs_selection=True,
    prompt=(
        "Suggest which rewrite strategy (clarify, compress, intensify, subtext, "
        "etc.) would most improve the selected passage, and why — one short "
        "paragraph. Advisory only; do not rewrite the passage."
    ),
))

# Manuscript + Screenplay — Phase 10K (revision intelligence, read-only/deterministic).
for _name, _label, _desc in [
    ("sp_revision_impact", "Generate Revision Impact Map",
     "Map what the current scene's change affects (deterministic)."),
    ("sp_check_psyke_impact", "Check PSYKE Impact",
     "PSYKE entries touched by the current scene."),
    ("sp_check_setup_payoff_impact", "Check Setup/Payoff Impact",
     "Setup/payoff chains connected to the current scene."),
    ("sp_check_continuity_impact", "Check Continuity Impact",
     "Deterministic continuity risks for the current scene."),
    ("sp_check_impacted_scenes", "Check Impacted Scenes",
     "Scenes that may depend on the current scene."),
    ("sp_prepare_revision_followup", "Prepare Revision Follow-up Checklist",
     "Checklist of follow-up checks after a revision."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", modes=_SP, deterministic=True,
    ))

# Manuscript + Screenplay — Phase 10J (production draft, read-only/deterministic).
for _name, _label, _desc in [
    ("sp_production_status", "Explain Production Draft Status",
     "Summarize production draft mode, numbering, revisions, page-locking."),
    ("sp_validate_production", "Validate Production Draft",
     "Validate production readiness (deterministic)."),
    ("sp_check_duplicate_scene_numbers", "Check Duplicate Scene Numbers",
     "Detect duplicate/empty production scene numbers."),
    ("sp_summarize_revision_set", "Summarize Revision Set",
     "Summarize the latest revision set and its scene changes."),
    ("sp_explain_page_locking", "Explain Page Locking Status",
     "Explain why page locking is approximate/deferred."),
    ("sp_check_fountain_production_export", "Check Fountain Production Export",
     "Check the production Fountain export (scene numbers)."),
    ("sp_prepare_production_export", "Prepare Screenplay for Production Export",
     "Checklist before exporting a production draft."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", modes=_SP, deterministic=True,
    ))

# Manuscript + Screenplay — Phase 10H (professional output, read-only/deterministic).
for _name, _label, _desc in [
    ("sp_validate_professional_output", "Validate Professional Output",
     "Validate DOCX/PDF/FDX output readiness (deterministic)."),
    ("sp_output_readiness_report", "Generate Output Readiness Report",
     "Summarize available formats, title page, and approximate length."),
    ("sp_preview_output", "Preview Screenplay Output",
     "Generate the professional HTML preview (print to PDF for fidelity)."),
    ("sp_check_pdf_readiness", "Check PDF Readiness",
     "Report PDF export status (pagination is approximate)."),
    ("sp_check_fdx_feasibility", "Check FDX Feasibility",
     "Report experimental Final Draft FDX status."),
    ("sp_explain_export_warnings", "Explain Export Warnings",
     "Explain professional-output warnings from deterministic evidence."),
    ("sp_prepare_professional_export", "Prepare Screenplay for Professional Export",
     "Checklist before DOCX/PDF/FDX export."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", modes=_SP, deterministic=True,
    ))

# Manuscript + Screenplay — Phase 10G (Fountain export, read-only/deterministic).
for _name, _label, _desc in [
    ("sp_validate_fountain_export", "Validate Fountain Export",
     "Validate the .fountain output (deterministic)."),
    ("sp_preview_fountain", "Preview Fountain Output",
     "Preview the first lines of the .fountain export."),
    ("sp_check_fountain_compatibility", "Check Fountain Compatibility",
     "Report blocks that don't map cleanly to Fountain."),
    ("sp_find_ambiguous_fountain", "Find Ambiguous Fountain Elements",
     "List elements that needed forcing syntax."),
    ("sp_explain_fountain_warning", "Explain Fountain Warning",
     "Explain Fountain export warnings from deterministic evidence."),
    ("sp_prepare_for_fountain", "Prepare Screenplay for Fountain Export",
     "Checklist of steps before exporting as .fountain."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", modes=_SP, deterministic=True,
    ))

# Manuscript + Screenplay — Phase 10F (export polish, read-only/deterministic).
for _name, _label, _desc in [
    ("sp_validate_export", "Validate Screenplay Export",
     "Check export readiness — blocking errors + warnings (deterministic)."),
    ("sp_export_readiness_report", "Generate Export Readiness Report",
     "Summarize export readiness, title, and approximate length."),
    ("sp_preview_render", "Preview Screenplay Render",
     "Build the render document and report block count / length (approximate)."),
    ("sp_find_orphan_dialogue", "Find Orphan Dialogue",
     "List dialogue blocks with no preceding character cue."),
    ("sp_find_orphan_parenthetical", "Find Orphan Parentheticals",
     "List parentheticals without dialogue context."),
    ("sp_check_production_polish", "Check Production Polish",
     "Summarize format issues to review before export."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", modes=_SP, deterministic=True,
    ))

# Manuscript + Screenplay — Phase 10E (story-link graph, read-only/deterministic).
for _name, _label, _desc in [
    ("sp_show_story_links", "Show Story Link Graph",
     "Summarize confirmed + candidate screenplay story links (deterministic)."),
    ("sp_explain_link", "Explain This Link",
     "Explain the current scene's story links from deterministic evidence."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
        prompt="", modes=_SP, deterministic=True,
    ))

# Generative subtext rewrites (LLM only on explicit invocation):
for _name, _label, _desc, _prompt in [
    ("sp_reduce_on_the_nose", "Reduce On-the-Nose Dialogue",
     "Make on-the-nose dialogue more subtextual.",
     "Suggest how to make the selected dialogue less on-the-nose — put the "
     "feeling/intent under the line rather than in it. Suggestions only."),
    ("sp_objective_gap", "Strengthen Character Objective Gap",
     "Sharpen the gap between want and spoken line.",
     "Suggest how to widen the gap between what the character wants and what they "
     "say here, so the scene plays with more subtext. Suggestions only."),
    ("sp_action_beat_subtext", "Add Action Beat for Subtext",
     "Add behavior that carries the subtext.",
     "Suggest a small action beat (behavior/business) that could carry the "
     "subtext of this moment instead of stating it. Suggestions only."),
    ("sp_emotion_to_behavior", "Convert Stated Emotion to Behavior",
     "Show the emotion through behavior.",
     "Suggest how to convert directly-stated emotion in the selection into "
     "observable behavior or action. Suggestions only; do not rewrite."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc,
        category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
        prompt=_prompt, needs_selection=True, modes=_SP,
    ))

# Outline + Screenplay
for _name, _label, _desc, _cat, _prompt in [
    ("sp_sequence_logic", "Check Sequence Logic",
     "Do the sequences build logically?", CATEGORY_DIAGNOSTIC,
     "Assess whether the sequences in this part build on each other with clear "
     "cause-and-effect toward the act turn. Note breaks in logic. Do not modify."),
    ("sp_act_turn", "Strengthen Act Turn",
     "Sharpen the act's turning point.", CATEGORY_GENERATIVE,
     "Suggest how to make this act's turning point sharper and more "
     "consequential for the central dramatic question. Suggestions only."),
    ("sp_central_question", "Clarify Central Dramatic Question",
     "Is the central dramatic question clear?", CATEGORY_DIAGNOSTIC,
     "Articulate the central dramatic question this structure poses and whether "
     "the outline keeps it active. If unclear, explain why. Do not modify."),
    ("sp_escalation", "Improve Escalation",
     "Do the beats escalate?", CATEGORY_DIAGNOSTIC,
     "Assess whether the beats in this structure escalate in stakes and pressure "
     "toward the act turn. Note flat or repetitive stretches. Do not modify."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc, category=_cat,
        sections=(SECTION_OUTLINE,), prompt=_prompt, modes=_SP,
    ))

# Plot + Screenplay
for _name, _label, _desc, _cat, _prompt in [
    ("sp_track_setup_payoff", "Track Setup/Payoff",
     "Trace setups and their payoffs.", CATEGORY_DIAGNOSTIC,
     "Trace the setups planted around this plot block and whether each pays off "
     "(or is paid off) elsewhere. Flag unpaid setups / unprepared payoffs. Do "
     "not modify anything."),
    ("sp_causal_chain", "Check Causal Chain",
     "Is the cause-effect chain intact?", CATEGORY_DIAGNOSTIC,
     "Check the cause-and-effect chain through this plot block — does each beat "
     "cause the next rather than merely following it? Note 'and then' gaps. Do "
     "not modify anything."),
    ("sp_visual_turn", "Check Visual Turn",
     "Does the beat turn on something visible?", CATEGORY_DIAGNOSTIC,
     "Assess whether this beat turns on something the audience can see or hear "
     "rather than only internal realization. Do not modify anything."),
]:
    register(LogosAction(
        name=_name, label=_label, description=_desc, category=_cat,
        sections=(SECTION_PLOT,), prompt=_prompt, modes=_SP,
    ))


# ---------------------------------------------------------------------------
# Graphic Novel mode (Phase 1). Restricted to writing_mode="graphic_novel".
# Deterministic, full-scene, preview/report-only — runs the page/panel validator.
# ---------------------------------------------------------------------------

register(LogosAction(
    name="gn_panel_check", label="Panel Check",
    description="Deterministic page/panel checks for this Graphic Novel scene: "
                "empty pages/panels, missing visual description, dialogue-heavy "
                "panels, long SFX/captions.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("graphic_novel",), deterministic=True,
))
# Phase 3 — unified Graphic Novel scene-script intelligence (deterministic,
# full-scene, report-only). Groups panel structure / visual clarity / dialogue-
# caption balance / page flow / dramatic function / plan alignment / continuity.
register(LogosAction(
    name="gn_scene_health", label="Graphic Novel Check",
    description="Full deterministic script check for this Graphic Novel scene: "
                "panel structure, visual clarity, dialogue/caption balance, page "
                "flow, dramatic function, plan alignment, and continuity.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("graphic_novel",), deterministic=True,
))

# Graphic Novel Reflection / Counterpart (Phase 4) — a deterministic, non-mutating
# multi-perspective reflection (reader / artist / story / dialogue) that produces
# feedback and revision questions, never a rewrite and never an image.
register(LogosAction(
    name="gn_reflection", label="Graphic Novel Reflection",
    description="Reflect on this Graphic Novel scene from the reader's, artist's, "
                "story, and dialogue/caption perspectives — feedback and revision "
                "questions, never a rewrite or an image.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("graphic_novel",), deterministic=True,
))

# Graphic Novel — Phase 5 (Controlled Rewrite). Generative; each action shows a
# preview/diff before any confirmed apply — never auto-applies and never produces
# images. Panel/text actions need a selection; full-scene actions do not. The
# grounded preview->apply path lives in graphic_novel_rewrite.
for _gn_name, _gn_label, _gn_desc, _gn_prompt, _gn_sel in [
    ("gn_rewrite_panel", "Rewrite Panel",
     "Propose a revision of the selected panel — shown as a preview to confirm, "
     "never auto-applied.",
     "Rewrite the selected graphic novel panel. Return only the panel's "
     "Visual/Caption/Dialogue/SFX/Notes fields — no markdown, no commentary, and "
     "no image-generation prompts. This is a preview for the writer to review; do "
     "not claim it is applied.", True),
    ("gn_rewrite_page", "Rewrite Page",
     "Propose a revision of the selected page's panels — preview to confirm.",
     "Rewrite the selected graphic novel page. Return its PANELs (PANEL n + "
     "Visual/Caption/Dialogue/SFX/Notes) — no markdown, no commentary, no image "
     "prompts. Preview only; do not claim it is applied.", True),
    ("gn_make_more_visual", "Make Panel More Visual",
     "Recast the selected panel as a concrete, drawable image.",
     "Recast the selected panel as concrete, drawable action — clear subject, "
     "setting, and behavior. Return panel fields only; no commentary, no image "
     "prompts. Preview only.", True),
    ("gn_reduce_dialogue", "Reduce Panel Dialogue",
     "Trim the dialogue in the selected panel; let the art carry it.",
     "Reduce the dialogue in the selected panel to its essential line and let the "
     "art carry the beat. Return panel fields only; no commentary, no image "
     "prompts. Preview only.", True),
    ("gn_caption_to_action", "Replace Caption with Action",
     "Turn caption exposition in the selection into visible action.",
     "Turn the selected panel's caption exposition into a visible action or image. "
     "Return panel fields only; no commentary, no image prompts. Preview only.",
     True),
    ("gn_strengthen_beat", "Strengthen Visual Beat",
     "Sharpen the selected panel's visual beat.",
     "Sharpen the selected panel's visual beat so its purpose reads at a glance. "
     "Return panel fields only; no commentary, no image prompts. Preview only.",
     True),
    ("gn_clarify_page_turn", "Clarify Page Turn",
     "Strengthen page turns across this scene — preview to confirm.",
     "Revise this graphic novel scene so each page ends on a turn, question, or "
     "reveal that pulls the reader onward. Return PAGE/PANEL script only — no "
     "markdown, no commentary, no image prompts. Preview only; do not claim it is "
     "applied.", False),
    ("gn_improve_flow", "Improve Panel Flow",
     "Smooth panel-to-panel flow across this scene — preview to confirm.",
     "Revise this graphic novel scene so the panel-to-panel progression reads "
     "clearly, each panel advancing the action. Return PAGE/PANEL script only — no "
     "markdown, no commentary, no image prompts. Preview only.", False),
    ("gn_rewrite_from_reflection", "Rewrite from Reflection Notes",
     "Propose a revision addressing the Reflection report — preview to confirm.",
     "Using the scene's reflection and diagnostics in context, propose a revised "
     "graphic novel page/panel script that addresses its most important reader, "
     "artist, and story gaps. Return PAGE/PANEL script only — no markdown, no "
     "commentary, no image prompts. Preview only; do not claim it is applied.",
     False),
]:
    register(LogosAction(
        name=_gn_name, label=_gn_label, description=_gn_desc,
        category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
        prompt=_gn_prompt, needs_selection=_gn_sel, modes=("graphic_novel",)))

# Graphic Novel — Phase 6 (cross-scene continuity / coherence). Deterministic,
# project-level (no selection or current scene needed); read-only report.
# Offered in Manuscript, Timeline, and Outline so it's reachable as the Graphic
# Novel Continuity Check / Visual Timeline Alignment / Scene Chain check.
register(LogosAction(
    name="gn_continuity_check", label="Graphic Novel Continuity Check",
    description="Analyze how the Graphic Novel scenes work together: visual flow, "
                "character/object/place continuity, recurring motifs, setup/payoff, "
                "Timeline alignment, and PSYKE consistency.",
    category=CATEGORY_DIAGNOSTIC,
    sections=(SECTION_MANUSCRIPT, SECTION_TIMELINE, SECTION_OUTLINE),
    prompt="", modes=("graphic_novel",), deterministic=True,
))
# Graphic Novel — Phase 7 (Review Dashboard). Deterministic, project-level
# (no selection / current scene needed); read-only roll-up of page breakdown /
# panel plan / body / health / flow / continuity / Timeline / PSYKE / export
# status per scene, rendered as Markdown. Offered in Manuscript/Timeline/Outline.
register(LogosAction(
    name="gn_review_dashboard", label="Graphic Novel Review Dashboard",
    description="Project overview of the Graphic Novel script: which scenes have "
                "page breakdowns, panel plans, scripted panels, missing visuals, "
                "dialogue/caption or flow/continuity warnings, Timeline links — "
                "plus a recommended next action per scene.",
    category=CATEGORY_DIAGNOSTIC,
    sections=(SECTION_MANUSCRIPT, SECTION_TIMELINE, SECTION_OUTLINE),
    prompt="", modes=("graphic_novel",), deterministic=True,
))
# Stage Script — Phase 1 (deterministic scene-body check). Report-only, mode-gated
# to stage_script; runs on the current Scene with no selection. No image gen.
register(LogosAction(
    name="stage_check", label="Stage Script Check",
    description="Deterministic check of this Stage Script scene: stage action, "
                "character/dialogue balance, entrances/exits, and lighting/sound "
                "cues. Report only — never rewrites or mutates.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("stage_script",), deterministic=True,
))
# Stage Script — Phase 4 (Counterpart / Reflection). Deterministic, non-mutating
# multi-perspective reflection (audience / actor / director / dramaturg) producing
# feedback and revision questions — never a rewrite.
register(LogosAction(
    name="stage_reflection", label="Stage Script Reflection",
    description="Reflect on this Stage Script scene from the audience, actor, "
                "director/blocking, and dramaturg perspectives — feedback and "
                "revision questions, never a rewrite.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("stage_script",), deterministic=True,
))

# Stage Script — Phase 5 (Controlled Rewrite). Generative; each action shows a
# preview/diff before any confirmed apply — never auto-applies. Block/text actions
# need a selection; full-scene actions do not. The grounded preview->apply path
# lives in stage_script_rewrite.
for _ss_name, _ss_label, _ss_desc, _ss_prompt, _ss_sel in [
    ("stage_rewrite_block", "Rewrite Stage Block",
     "Propose a revision of the selected stage block(s) — preview to confirm.",
     "Rewrite the selected stage-script block(s). Return stage-script blocks only "
     "(SCENE:/STAGE:/CHARACTER:/dialogue/(parenthetical)/ENTER:/EXIT:/LIGHT:/"
     "SOUND:/SET:/TRANSITION:/NOTE:) — no markdown, no commentary, no screenplay "
     "sluglines. This is a preview; do not claim it is applied.", True),
    ("stage_make_playable", "Make More Playable",
     "Recast the selection as playable, observable stage action.",
     "Recast the selected material as playable, observable stage action an actor "
     "can perform. Return stage blocks only; no commentary, no sluglines. Preview "
     "only.", True),
    ("stage_reduce_exposition", "Reduce Exposition",
     "Trim expositional dialogue in the selection.",
     "Reduce the exposition in the selected dialogue, turning told backstory into "
     "present action or implication. Return stage blocks only. Preview only.", True),
    ("stage_strengthen_objective", "Strengthen Actor Objective",
     "Make the character's active want playable in the selection.",
     "Revise the selection so the character's active want and tactic are playable "
     "in action and line. Return stage blocks only. Preview only.", True),
    ("stage_clarify_cue", "Clarify Cue",
     "Give the selected lighting/sound cue clear, motivated text.",
     "Clarify the selected lighting/sound cue: motivated text with a dramatic "
     "function. Return stage blocks only. Preview only.", True),
    ("stage_rewrite_scene", "Rewrite Stage Scene",
     "Propose a revision of the whole scene — preview to confirm.",
     "Rewrite this stage scene as stage-script blocks — no markdown, no "
     "commentary, no screenplay sluglines. Preview only; do not claim it is "
     "applied.", False),
    ("stage_clarify_blocking", "Clarify Blocking",
     "Revise the scene so movement/blocking is clear — preview to confirm.",
     "Revise this stage scene so stage geography, movement, and entrances/exits "
     "read clearly and support the conflict. Return stage blocks only. Preview "
     "only.", False),
    ("stage_strengthen_turn", "Strengthen Theatrical Turn",
     "Revise so the scene turns on a staged value shift — preview to confirm.",
     "Revise this stage scene so it turns on a clear, staged value shift by the "
     "last beat. Return stage blocks only. Preview only.", False),
    ("stage_rewrite_from_reflection", "Rewrite from Reflection Notes",
     "Propose a revision addressing the reflection — preview to confirm.",
     "Using the scene's reflection and diagnostics in context, propose a revised "
     "stage-script scene that addresses its most important audience, actor, "
     "director, and dramaturg gaps. Return stage blocks only — no markdown, no "
     "commentary, no sluglines. Preview only; do not claim it is applied.", False),
]:
    register(LogosAction(
        name=_ss_name, label=_ss_label, description=_ss_desc,
        category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
        prompt=_ss_prompt, needs_selection=_ss_sel, modes=("stage_script",)))

# Stage Script — Phase 6 (cross-scene continuity / coherence). Deterministic,
# project-level (no selection / current scene needed); read-only report. Offered
# in Manuscript, Timeline, and Outline.
register(LogosAction(
    name="stage_continuity_check", label="Stage Continuity Check",
    description="Analyze how the stage play works across scenes: character "
                "entrances/exits, blocking, props/set, lighting/sound cues, "
                "setup/payoff, Timeline alignment, and PSYKE consistency.",
    category=CATEGORY_DIAGNOSTIC,
    sections=(SECTION_MANUSCRIPT, SECTION_TIMELINE, SECTION_OUTLINE),
    prompt="", modes=("stage_script",), deterministic=True,
))
# Stage Script — Phase 7 (Review Dashboard). Deterministic, project-level
# (no selection / current scene needed); read-only roll-up rendered as Markdown.
register(LogosAction(
    name="stage_review_dashboard", label="Stage Script Review Dashboard",
    description="Project overview of the stage play: which scenes have beat plans, "
                "blocking/cue plans, written bodies, missing stage action, "
                "dialogue/cue/blocking/continuity warnings, Timeline links — plus "
                "a recommended next action per scene.",
    category=CATEGORY_DIAGNOSTIC,
    sections=(SECTION_MANUSCRIPT, SECTION_TIMELINE, SECTION_OUTLINE),
    prompt="", modes=("stage_script",), deterministic=True,
))
# Series — Phase 1 (deterministic scene-body check). Report-only, mode-gated to
# series; runs on the current Scene with no selection. No image generation.
register(LogosAction(
    name="series_check", label="Series Scene Check",
    description="Deterministic check of this Series scene: scene heading, action, "
                "character/dialogue balance, and act-break / teaser / tag markers. "
                "Report only — never rewrites or mutates.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
# Series — Phase 2 (deterministic episode/serial structure checks). Report-only,
# mode-gated to series; resolve the Episode from the current Scene. No mutation.
register(LogosAction(
    name="series_episode_check", label="Episode Structure Check",
    description="Deterministic check of this Episode (the current Scene's Chapter): "
                "scene count, beat-plan presence, teaser / act-break / climax / tag "
                "coverage. Report only — never rewrites or mutates.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
register(LogosAction(
    name="series_abc_check", label="A/B/C Story Check",
    description="Deterministic check of A/B/C story coverage for this Episode "
                "against its beat plan. Report only — never rewrites or mutates.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
# Series — Phase 3 (deterministic intelligence checks). Report-only, mode-gated to
# series; powered by series_diagnostics. Resolve scene/episode from the current
# Scene. No mutation, no LLM, no image generation.
register(LogosAction(
    name="series_act_break_check", label="Act Break Check",
    description="Deterministic check of Act Break placement in this scene and the "
                "Episode plan's act-break coverage. Report only — never mutates.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
register(LogosAction(
    name="series_cold_open_tag_check", label="Cold Open / Tag Check",
    description="Deterministic check of Cold Open / Teaser and Tag placement and "
                "the Episode plan's coverage. Report only — never mutates.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
register(LogosAction(
    name="series_dialogue_balance", label="Dialogue / Action Balance",
    description="Deterministic dialogue/action balance check for this scene "
                "(ratio, long runs, monologues, exposition). Report only.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
register(LogosAction(
    name="series_arc_alignment", label="Season Arc Alignment",
    description="Deterministic check of whether this Episode reflects the Season / "
                "Arc plan (arc question, setup/payoff, motifs). Report only.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
# Series — Phase 4 (Counterpart / Reflection). Deterministic, non-mutating
# multi-perspective reflection (audience / showrunner / character-arc / episode-
# structure / writers-room) producing feedback and revision questions — never a
# rewrite. The full report plus per-perspective views; powered by series_reflection.
register(LogosAction(
    name="series_reflection", label="Series Reflection",
    description="Reflect on this Series scene from the audience, showrunner, "
                "character-arc, episode-structure, and writers-room perspectives — "
                "feedback and revision questions, never a rewrite.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
register(LogosAction(
    name="series_audience_reflection", label="Audience Perspective",
    description="What plays for the viewer: hook, legible conflict, exposition load, "
                "and whether the act break / tag / reveal lands. Report only.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
register(LogosAction(
    name="series_showrunner_reflection", label="Showrunner Perspective",
    description="Does the scene serve the episode and the episode the season — "
                "A/B/C balance, escalation vs. repetition. Report only.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
register(LogosAction(
    name="series_character_reflection", label="Character Arc Perspective",
    description="Per character: want, change, reveal-through-action, and PSYKE "
                "consistency. Report only — never creates PSYKE entries.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
register(LogosAction(
    name="series_episode_structure_reflection", label="Episode Structure Perspective",
    description="Cold open / act breaks / climax / tag / sequence and alignment with "
                "the Episode beat plan. Report only.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
register(LogosAction(
    name="series_writers_room", label="Writers-Room Notes",
    description="Practical, writer-facing notes and the showrunner note (cut / "
                "combine / escalate / clarify / move). Report only.",
    category=CATEGORY_DIAGNOSTIC, sections=(SECTION_MANUSCRIPT,),
    prompt="", modes=("series",), deterministic=True,
))
# Series — Phase 5 (Controlled Rewrite). Generative; each action shows a
# preview/diff before any confirmed apply — never auto-applies. Block/text actions
# need a selection; full-scene actions do not. The grounded preview->apply path
# lives in series_rewrite. Output stays Series teleplay blocks (no Stage cues, no
# Graphic Novel panels, no novel prose). No image generation.
for _sr_name, _sr_label, _sr_desc, _sr_prompt, _sr_sel in [
    ("series_rewrite_block", "Rewrite Series Block",
     "Propose a revision of the selected Series block(s) — preview to confirm.",
     "Rewrite the selected teleplay block(s). Return teleplay blocks only (scene "
     "heading / action / CHARACTER cue / dialogue / (parenthetical) / CUT TO: / "
     "COLD OPEN / ACT BREAK / TAG) — no markdown, no commentary, no Stage cue "
     "labels, no page/panel structure. This is a preview; do not claim it is "
     "applied.", True),
    ("series_tighten_dialogue", "Tighten Dialogue",
     "Trim and sharpen the selected dialogue — preview to confirm.",
     "Tighten the selected dialogue — cut filler, keep subtext and voice. Return "
     "teleplay blocks only. Preview only.", True),
    ("series_reduce_exposition", "Reduce Exposition",
     "Trim expositional dialogue in the selection — preview to confirm.",
     "Reduce the exposition in the selection, dramatizing the information through "
     "action. Return teleplay blocks only. Preview only.", True),
    ("series_rewrite_scene", "Rewrite Series Scene",
     "Propose a revision of the whole scene — preview to confirm.",
     "Rewrite this Series scene as teleplay blocks — no markdown, no commentary, "
     "no Stage cue labels, no page/panel structure. Preview only; do not claim it "
     "is applied.", False),
    ("series_strengthen_act_break", "Strengthen Act Break",
     "Revise so the act break creates pressure — preview to confirm.",
     "Revise this scene so the Act Break builds to a reversal or decision that "
     "creates pressure for the next act. Return teleplay blocks only. Preview only.",
     False),
    ("series_sharpen_cold_open", "Sharpen Cold Open",
     "Revise so the cold open hooks the viewer — preview to confirm.",
     "Revise so the Cold Open / Teaser raises a sharp question that pulls the "
     "viewer in. Return teleplay blocks only. Preview only.", False),
    ("series_improve_tag", "Improve Tag / Button",
     "Revise so the tag lands — preview to confirm.",
     "Revise so the Tag / Button lands — an earned button tied to the episode's "
     "turn. Return teleplay blocks only. Preview only.", False),
    ("series_strengthen_a_story", "Strengthen A-Story",
     "Revise so the scene serves the A-story — preview to confirm.",
     "Revise so the scene serves the A-story more clearly and escalates it. Return "
     "teleplay blocks only. Preview only.", False),
    ("series_strengthen_b_story", "Strengthen B-Story",
     "Revise so the scene advances the B-story — preview to confirm.",
     "Revise so the scene advances the B-story meaningfully. Return teleplay blocks "
     "only. Preview only.", False),
    ("series_clarify_character_arc", "Clarify Character Arc",
     "Revise so the character arc beat reads — preview to confirm.",
     "Revise so the character's want and change are visible through action and "
     "line. Return teleplay blocks only. Preview only.", False),
    ("series_connect_season_arc", "Connect to Season Arc",
     "Revise so the scene ties to the season arc — preview to confirm.",
     "Revise so the scene ties to the season/arc question, a setup/payoff, or a "
     "recurring motif. Return teleplay blocks only. Preview only.", False),
    ("series_rewrite_from_showrunner", "Rewrite from Showrunner Notes",
     "Propose a revision addressing the showrunner notes — preview to confirm.",
     "Using the scene's diagnostics and showrunner perspective in context, propose "
     "a revised teleplay scene that addresses the scene's job, A/B/C balance, and "
     "escalation. Return teleplay blocks only. Preview only; do not claim it is "
     "applied.", False),
    ("series_rewrite_from_reflection", "Rewrite from Reflection Notes",
     "Propose a revision addressing the reflection — preview to confirm.",
     "Using the scene's reflection and diagnostics in context, propose a revised "
     "teleplay scene that addresses its most important audience, showrunner, "
     "character-arc, and episode-structure gaps. Return teleplay blocks only — no "
     "markdown, no commentary. Preview only; do not claim it is applied.", False),
]:
    register(LogosAction(
        name=_sr_name, label=_sr_label, description=_sr_desc,
        category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
        prompt=_sr_prompt, needs_selection=_sr_sel, modes=("series",)))
# Series — Phase 6 (cross-episode continuity / coherence). Deterministic,
# project-level (no selection / current scene needed); read-only report. Offered
# in Manuscript, Timeline, and Outline. No image generation.
register(LogosAction(
    name="series_continuity_check", label="Series Continuity Check",
    description="Analyze how the series works across episodes: season/arc coherence, "
                "episode chain, A/B/C story tracking, character arcs, setup/payoff, "
                "episode structure, Timeline alignment, and PSYKE consistency.",
    category=CATEGORY_DIAGNOSTIC,
    sections=(SECTION_MANUSCRIPT, SECTION_TIMELINE, SECTION_OUTLINE),
    prompt="", modes=("series",), deterministic=True,
))
# Series — Phase 7 (Review Dashboard). Deterministic, project-level, read-only
# status roll-up across Season -> Episode -> Scene. Offered in Manuscript, Outline,
# and Timeline. No image generation.
register(LogosAction(
    name="series_review_dashboard", label="Series Review Dashboard",
    description="Project-level Series status overview: per-season / per-episode / "
                "per-scene plan, body, A/B/C, act-break / cold-open-tag, continuity, "
                "Timeline, PSYKE/Notes, and a recommended next action — plus export "
                "readiness. Report only.",
    category=CATEGORY_DIAGNOSTIC,
    sections=(SECTION_MANUSCRIPT, SECTION_OUTLINE, SECTION_TIMELINE),
    prompt="", modes=("series",), deterministic=True,
))
# Series — Phase 2 (planning pipeline). Generative; each action produces a preview
# the writer reviews and confirms — never auto-applied, and the AI never overwrites
# the body. The structured store/parse/apply lives in series_pipeline. The
# Season / Arc and Episode plans live in project settings (Act-/Chapter-name keyed),
# not the Manuscript body, and not a new Season/Episode storage. No image generation.
register(LogosAction(
    name="series_season_plan", label="Generate Season / Arc Plan",
    description="Propose a Season / Arc plan for this Act / Season from its Outline "
                "summary and its episodes — a preview to review and store, never "
                "written into the body.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_OUTLINE,),
    prompt="Using the Act / Season summary and the ordered episode summaries, "
           "produce a SEASON / ARC PLAN — the serialized spine, not script. Use "
           "labelled lines: Premise:, Arc Question:, Episode Progression:, "
           "Character Arcs:, Recurring Motifs:, Setup / Payoff:, Cliffhangers / "
           "Reveals:, Continuity Notes:. No markdown, no commentary. This is a "
           "preview; do not claim it is applied.",
    modes=("series",)))
register(LogosAction(
    name="series_episode_plan", label="Generate Episode Beat Plan",
    description="Propose an Episode beat plan for this Episode from its Outline "
                "summary, the parent Season / Arc plan, and its scenes — a preview "
                "to review and store, never written into the body.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_OUTLINE,),
    prompt="Using the Episode summary, the parent Season / Arc plan, and the "
           "ordered scene summaries, produce an EPISODE BEAT PLAN. Use labelled "
           "lines: Premise:, Objective:, Dramatic Question:, A Story:, B Story:, "
           "C Story:, Teaser / Cold Open:, Act Breaks:, Turning Points:, Climax:, "
           "Tag / Button:, Character Arc Beats:, Continuity Notes:. No markdown, "
           "no commentary. This is a preview; do not claim it is applied.",
    modes=("series",)))
register(LogosAction(
    name="series_draft_scene", label="Draft Series Scene from Episode Plan",
    description="Draft a teleplay scene from the Episode beat plan and the scene's "
                "intent — shown as a preview to review and confirm, never "
                "auto-applied.",
    category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
    prompt="Realizing ONLY the Episode beat plan and the scene's intent, write a "
           "teleplay SCENE using teleplay lines: scene headings (INT./EXT.), "
           "action, CHARACTER cues in caps, dialogue, (parentheticals), "
           "transitions (CUT TO:), and serial markers on their own line "
           "(COLD OPEN, ACT BREAK, TAG). No markdown, no commentary, no image "
           "prompts. This is a preview for the writer to review; do not claim it "
           "is applied.",
    modes=("series",)))
# Stage Script — Phase 2 (planning pipeline). Generative, full-scene; each action
# produces a preview the writer reviews and confirms — never auto-applied, and the
# AI never overwrites the body. The structured store/parse/apply lives in
# stage_script_pipeline. No image generation.
for _ss_name, _ss_label, _ss_desc, _ss_prompt in [
    ("stage_beat_plan", "Generate Stage Beat Plan",
     "Propose a stage beat plan from the scene's Outline summary — a preview to "
     "review and store, never written into the body.",
     "Using the scene's summary and context, produce a STAGE BEAT PLAN — the "
     "dramatic spine, not stage script. Use labelled lines: Objective:, Dramatic "
     "Question:, Conflict:, Turning Point:, Emotional Shift:, Dialogue Beats:, "
     "Stage Action Beats:, Entrances:, Exits:, Continuity Notes:. No markdown, no "
     "commentary. This is a preview; do not claim it is applied."),
    ("stage_blocking_plan", "Generate Blocking / Cue Plan",
     "Propose a blocking / cue plan from the beat plan — a preview to review and "
     "store, never written into the body.",
     "Using the scene's beat plan and context, produce a BLOCKING / CUE PLAN — "
     "staging, movement, entrances/exits, lighting and sound cues. Use labelled "
     "lines: Staging Area:, Character Positions:, Movement Beats:, Entrance / Exit "
     "Plan:, Lighting Cues:, Sound Cues:, Prop Notes:, Set Notes:, Transition "
     "Notes:. No markdown, no commentary. Preview only; do not claim it is applied."),
    ("stage_draft_scene", "Draft Stage Scene from Plan",
     "Draft a stage script from the beat + blocking plans — shown as a preview to "
     "review and confirm, never auto-applied.",
     "Realizing ONLY the beat plan and blocking/cue plan, write a stage-play "
     "SCRIPT using labelled lines: SCENE:, STAGE:, CHARACTER:, dialogue lines, "
     "(parentheticals), ENTER:, EXIT:, LIGHT:, SOUND:, SET:, TRANSITION:, NOTE:. "
     "No markdown, no commentary, no image prompts. This is a preview for the "
     "writer to review; do not claim it is applied."),
]:
    register(LogosAction(
        name=_ss_name, label=_ss_label, description=_ss_desc,
        category=CATEGORY_GENERATIVE, sections=(SECTION_MANUSCRIPT,),
        prompt=_ss_prompt, modes=("stage_script",)))


# ---------------------------------------------------------------------------
# Deferred to later phases (NOT registered — TODO only).
# These will require explicit preview + confirmation before any mutation.
# ---------------------------------------------------------------------------

FUTURE_ACTIONS: tuple[str, ...] = (
    "rewrite_selection",       # apply a rewrite to the manuscript
    "replace_selection",       # replace the selected text
    "expand_selection",        # apply an expansion in place
    "generate_scene",          # create a scene
    "generate_outline_node",   # create an outline node
)
