
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


try:
    from logosforge.plugins import PluginContext, PluginResult, Suggestion
except Exception:  # pragma: no cover
    PluginContext = Any
    PluginResult = Any
    Suggestion = Any


PLUGIN_ID = "psyke_outline_templates"


@dataclass
class OutlineNode:
    node_id: str
    label: str
    phase: str
    order: int
    description: str
    guidance: str = ""
    psyke_annotations: Dict[str, Any] = field(default_factory=dict)
    children: List["OutlineNode"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "phase": self.phase,
            "order": self.order,
            "description": self.description,
            "guidance": self.guidance,
            "psyke_annotations": self.psyke_annotations,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class StructureTemplate:
    template_id: str
    name: str
    category: str
    focus: str
    primary_goal: str
    beats: List[Dict[str, Any]]
    supports_chapters: bool = False
    tags: List[str] = field(default_factory=list)


class PsykeOutlineTemplatesPlugin:
    def __init__(self, app_api: Any):
        self.app_api = app_api
        self.templates = self._build_templates()

    def run(self, context: PluginContext) -> Any:
        config = self._get_config(context)
        story = self._extract_story_context(context)

        if not story:
            return self._result(
                ok=False,
                message="No PSYKE story context found. Expected structured story/project data in context.",
                suggestions=[
                    self._suggestion(
                        title="Provide PSYKE story context",
                        body=(
                            "Pass project, story, or psyke_story data with protagonist, premise, themes, arcs, "
                            "genre, tensions, and optional requested structure method."
                        ),
                    )
                ],
            )

        selected, candidates, reason = self._select_template(story, config)
        outline = self._instantiate_template(selected, story, config)
        alternatives = [t.template_id for t in candidates if t.template_id != selected.template_id][: config["max_candidates"]]

        data = {
            "selected_method": {
                "id": selected.template_id,
                "name": selected.name,
                "category": selected.category,
                "focus": selected.focus,
                "primary_goal": selected.primary_goal,
                "selection_reason": reason,
            },
            "alternative_methods": alternatives,
            "story_summary": self._story_summary(story),
            "outline": [node.to_dict() for node in outline],
            "actions": self._build_actions(selected, outline, story, config) if config["emit_actions"] else [],
        }

        suggestions = [
            self._suggestion(
                title="Review chosen structure",
                body=f"The plugin selected {selected.name}. Inspect whether its focus on {selected.focus.lower()} matches your current narrative goal.",
            )
        ]
        if alternatives:
            suggestions.append(
                self._suggestion(
                    title="Compare alternatives",
                    body=f"Also consider: {', '.join(alternatives)}.",
                )
            )

        return self._result(
            ok=True,
            message=f"Generated a PSYKE-aware outline using the {selected.name} template.",
            data=data,
            suggestions=suggestions,
        )

    def _get_config(self, context: PluginContext) -> Dict[str, Any]:
        defaults = {
            "default_method": "three_act",
            "selection_mode": "explicit_or_infer",
            "emit_actions": True,
            "max_candidates": 3,
            "include_psyke_annotations": True,
            "include_guidance": True,
            "chapter_expansion": False,
        }
        provided = getattr(context, "config", {}) or {}
        merged = dict(defaults)
        merged.update(provided)
        return merged

    def _extract_story_context(self, context: PluginContext) -> Dict[str, Any]:
        payload = getattr(context, "data", None) or getattr(context, "context", None) or {}
        return (
            payload.get("psyke_story")
            or payload.get("story")
            or payload.get("project")
            or payload.get("narrative")
            or {}
        )

    def _select_template(
        self,
        story: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Tuple[StructureTemplate, List[StructureTemplate], str]:
        requested = self._normalize_method_id(
            story.get("requested_method")
            or story.get("structure_method")
            or story.get("outline_method")
            or ""
        )
        selection_mode = config.get("selection_mode", "explicit_or_infer")

        if requested and requested in self.templates:
            template = self.templates[requested]
            return template, self._rank_candidates(story), f"Explicitly requested method '{requested}'."

        if selection_mode == "explicit_only":
            default_method = self.templates[config.get("default_method", "three_act")]
            return default_method, self._rank_candidates(story), "No explicit method provided; fell back to configured default."

        ranked = self._rank_candidates(story)
        best = ranked[0] if ranked else self.templates[config.get("default_method", "three_act")]
        return best, ranked, "Selected by heuristic match against PSYKE story signals (genre, pacing, conflict profile, and internal/external arc emphasis)."

    def _rank_candidates(self, story: Dict[str, Any]) -> List[StructureTemplate]:
        genre = str(story.get("genre") or "").lower()
        conflict_mode = str(story.get("conflict_mode") or "").lower()
        arc_mode = str(story.get("arc_mode") or "").lower()
        scope = str(story.get("scope") or "").lower()
        pacing = str(story.get("pacing") or "").lower()
        themes = " ".join(self._ensure_list(story.get("themes"))).lower()

        scores: List[Tuple[int, StructureTemplate]] = []
        for template in self.templates.values():
            score = 0
            tags_blob = " ".join(template.tags).lower()
            focus_blob = f"{template.focus} {template.primary_goal}".lower()

            if genre and genre in tags_blob:
                score += 4
            if conflict_mode:
                if conflict_mode == "low_conflict" and template.template_id == "kishotenketsu":
                    score += 6
                if conflict_mode == "high_tension" and template.template_id in {"fichtean_curve", "save_the_cat"}:
                    score += 5
                if conflict_mode == "mystery" and template.template_id == "mystery":
                    score += 6
                if conflict_mode == "romance" and template.template_id == "romcom":
                    score += 6
            if arc_mode:
                if arc_mode == "internal" and template.template_id in {"heroine_journey", "snowflake", "hero_journey"}:
                    score += 4
                if arc_mode == "mythic" and template.template_id in {"hero_journey", "story_circle", "quest"}:
                    score += 5
                if arc_mode == "procedural" and template.template_id in {"mystery", "three_act", "seven_point"}:
                    score += 3
            if scope:
                if scope == "epic" and template.template_id in {"hero_journey", "quest", "twenty_seven_chapter"}:
                    score += 4
                if scope == "compact" and template.template_id in {"story_circle", "fichtean_curve", "seven_point"}:
                    score += 4
            if pacing:
                if pacing == "commercial" and template.template_id == "save_the_cat":
                    score += 5
                if pacing == "fast" and template.template_id in {"fichtean_curve", "in_medias_res"}:
                    score += 5
                if pacing == "balanced" and template.template_id in {"three_act", "seven_point"}:
                    score += 3
            if "healing" in themes and template.template_id == "heroine_journey":
                score += 4
            if "transformation" in themes and template.template_id in {"hero_journey", "story_circle"}:
                score += 3
            if "twist" in themes and template.template_id == "kishotenketsu":
                score += 3
            if "investigation" in themes and template.template_id == "mystery":
                score += 5
            if template.template_id == "three_act":
                score += 1
            if genre and genre in focus_blob:
                score += 2

            scores.append((score, template))

        scores.sort(key=lambda item: (-item[0], item[1].name))
        return [tpl for _, tpl in scores]

    def _instantiate_template(
        self,
        template: StructureTemplate,
        story: Dict[str, Any],
        config: Dict[str, Any],
    ) -> List[OutlineNode]:
        outline: List[OutlineNode] = []
        for i, beat in enumerate(template.beats, start=1):
            node = OutlineNode(
                node_id=f"{template.template_id}:{i}",
                label=beat["label"],
                phase=beat.get("phase", "story"),
                order=i,
                description=self._render_beat_description(beat, story),
                guidance=beat.get("guidance", "") if config.get("include_guidance", True) else "",
                psyke_annotations=self._annotate_beat(template, beat, story) if config.get("include_psyke_annotations", True) else {},
            )
            if config.get("chapter_expansion", False) and beat.get("children"):
                node.children = [
                    OutlineNode(
                        node_id=f"{node.node_id}.{j}",
                        label=child["label"],
                        phase=child.get("phase", node.phase),
                        order=j,
                        description=self._render_beat_description(child, story),
                        guidance=child.get("guidance", "") if config.get("include_guidance", True) else "",
                        psyke_annotations=self._annotate_beat(template, child, story) if config.get("include_psyke_annotations", True) else {},
                    )
                    for j, child in enumerate(beat.get("children", []), start=1)
                ]
            outline.append(node)
        return outline

    def _render_beat_description(self, beat: Dict[str, Any], story: Dict[str, Any]) -> str:
        protagonist = self._story_protagonist(story)
        premise = str(story.get("premise") or story.get("logline") or "")
        central_goal = str(story.get("central_goal") or story.get("goal") or "")
        stakes = str(story.get("stakes") or "")
        beat_intent = beat.get("intent", "advance the story")

        parts = [f"This beat should {beat_intent}."]
        if protagonist:
            parts.append(f"Center it on {protagonist}.")
        if central_goal:
            parts.append(f"Tie it to the active goal: {central_goal}.")
        if stakes:
            parts.append(f"Escalate or clarify stakes around: {stakes}.")
        if premise:
            parts.append(f"Keep alignment with the premise/logline: {premise}.")
        return " ".join(parts)

    def _annotate_beat(self, template: StructureTemplate, beat: Dict[str, Any], story: Dict[str, Any]) -> Dict[str, Any]:
        protagonist = self._story_protagonist(story)
        entities = self._ensure_list(story.get("key_entities") or story.get("entities"))
        themes = self._ensure_list(story.get("themes"))
        tensions = self._ensure_list(story.get("tensions") or story.get("conflicts"))
        arcs = self._ensure_list(story.get("arcs"))
        settings = self._ensure_list(story.get("settings") or story.get("locations"))

        phase = beat.get("phase", "story")
        annotation = {
            "protagonist": protagonist,
            "themes": themes[:3],
            "relevant_entities": entities[:5],
            "active_tensions": tensions[:3],
            "candidate_arcs": arcs[:3],
            "suggested_settings": settings[:2],
            "beat_role": beat.get("intent", "advance the story"),
            "phase": phase,
            "template": template.template_id,
        }

        label_blob = (beat.get("label", "") + " " + beat.get("intent", "")).lower()
        if "twist" in label_blob:
            annotation["emphasis"] = "contrast or revelation"
        elif "climax" in label_blob or "all is lost" in label_blob:
            annotation["emphasis"] = "maximum stakes"
        elif "return" in label_blob or "resolution" in label_blob or "changed" in label_blob:
            annotation["emphasis"] = "integration and consequence"
        else:
            annotation["emphasis"] = "progression"
        return annotation

    def _build_actions(
        self,
        template: StructureTemplate,
        outline: List[OutlineNode],
        story: Dict[str, Any],
        config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return [
            {
                "connector": "workspace",
                "action": "outline.upsert",
                "payload": {
                    "structure_id": template.template_id,
                    "structure_name": template.name,
                    "project_id": story.get("project_id") or story.get("id") or "current",
                    "outline": [node.to_dict() for node in outline],
                    "replace": True,
                },
            },
            {
                "connector": "workspace",
                "action": "outline.template_applied",
                "payload": {
                    "template_id": template.template_id,
                    "template_name": template.name,
                    "story_summary": self._story_summary(story),
                },
            },
        ]

    def _story_summary(self, story: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "title": story.get("title") or story.get("name") or "Untitled Project",
            "genre": story.get("genre") or "",
            "premise": story.get("premise") or story.get("logline") or "",
            "protagonist": self._story_protagonist(story),
            "central_goal": story.get("central_goal") or story.get("goal") or "",
            "themes": self._ensure_list(story.get("themes")),
            "requested_method": story.get("requested_method") or story.get("structure_method") or "",
        }

    def _story_protagonist(self, story: Dict[str, Any]) -> str:
        protagonist = story.get("protagonist")
        if isinstance(protagonist, dict):
            return str(protagonist.get("title") or protagonist.get("name") or protagonist.get("id") or "")
        return str(protagonist or "")

    def _normalize_method_id(self, value: str) -> str:
        aliases = {
            "hero's journey": "hero_journey",
            "heros journey": "hero_journey",
            "hero journey": "hero_journey",
            "the hero's journey": "hero_journey",
            "three act": "three_act",
            "three-act": "three_act",
            "aristotle": "three_act",
            "freytag": "freytag",
            "freytag's pyramid": "freytag",
            "fichtean": "fichtean_curve",
            "save the cat": "save_the_cat",
            "story circle": "story_circle",
            "7-point": "seven_point",
            "7 point": "seven_point",
            "seven-point": "seven_point",
            "27 chapter": "twenty_seven_chapter",
            "27-chapter": "twenty_seven_chapter",
            "kishotenketsu": "kishotenketsu",
            "heroine's journey": "heroine_journey",
            "heroine journey": "heroine_journey",
            "in media res": "in_medias_res",
            "snowflake": "snowflake",
            "mystery": "mystery",
            "rom-com": "romcom",
            "romcom": "romcom",
            "quest": "quest",
        }
        key = str(value or "").strip().lower()
        return aliases.get(key, key.replace(" ", "_").replace("-", "_"))

    def _ensure_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v) for v in value if str(v).strip()]
        if isinstance(value, str):
            return [value] if value.strip() else []
        return [str(value)]

    def _suggestion(self, title: str, body: str) -> Any:
        try:
            return Suggestion(title=title, body=body)
        except Exception:
            return {"title": title, "body": body}

    def _result(self, ok: bool, message: str, data: Optional[Dict[str, Any]] = None, suggestions: Optional[List[Any]] = None) -> Any:
        payload = {
            "ok": ok,
            "message": message,
            "data": data or {},
            "suggestions": suggestions or [],
        }
        try:
            return PluginResult(**payload)
        except Exception:
            return payload

    def _build_templates(self) -> Dict[str, StructureTemplate]:
        return {
            "hero_journey": StructureTemplate(
                template_id="hero_journey",
                name="The Hero's Journey",
                category="classical_foundational",
                focus="Mythological / Internal",
                primary_goal="Transformation of the Self",
                tags=["mythic", "epic", "transformation", "quest"],
                beats=[
                    self._beat("Ordinary World", "Act I", "establish the hero's baseline world", "Show the protagonist before change begins."),
                    self._beat("Call to Adventure", "Act I", "introduce the disruption or invitation", "Present the challenge, need, or summons."),
                    self._beat("Refusal of the Call", "Act I", "surface fear, doubt, or resistance", "Let the protagonist resist the path."),
                    self._beat("Meeting the Mentor", "Act I", "provide perspective, training, or symbolic aid", "Introduce guidance or catalytic wisdom."),
                    self._beat("Crossing the Threshold", "Act I/II", "commit to the unknown world", "Make return to the old status quo difficult."),
                    self._beat("Tests, Allies, Enemies", "Act II", "stress identity through trials and relationships", "Build competence, friction, and alignment."),
                    self._beat("Approach to the Inmost Cave", "Act II", "move toward the deepest ordeal", "Tighten stakes before the central trial."),
                    self._beat("Ordeal", "Act II", "force crisis, sacrifice, or symbolic death", "This is a major turning confrontation."),
                    self._beat("Reward", "Act II", "gain insight, object, alliance, or power", "The protagonist earns something meaningful."),
                    self._beat("The Road Back", "Act III", "turn toward return while pressures intensify", "Consequences follow the reward."),
                    self._beat("Resurrection", "Act III", "test the transformed self at the highest stakes", "A final proving of change."),
                    self._beat("Return with the Elixir", "Act III", "reintegrate change into the world", "Show what transformation gives back to others."),
                ],
            ),
            "three_act": StructureTemplate(
                template_id="three_act",
                name="Aristotle's Three-Act Structure",
                category="classical_foundational",
                focus="Balanced story progression",
                primary_goal="Clear beginning, middle, and end",
                tags=["general", "balanced", "foundation", "dramatic"],
                beats=[
                    self._beat("Setup", "Act I", "establish world, characters, and initial imbalance", "Clarify who, where, and why the story matters."),
                    self._beat("Inciting Incident", "Act I", "disrupt equilibrium and launch the plot", "Introduce the event that forces engagement."),
                    self._beat("First Plot Point", "Act I/II", "push the protagonist into the core conflict", "Cross from setup into confrontation."),
                    self._beat("Confrontation", "Act II", "expand obstacles, reversals, and complications", "This act should apply pressure and evolve intent."),
                    self._beat("Midpoint", "Act II", "shift understanding, strategy, or stakes", "Give the story a central pivot."),
                    self._beat("Crisis", "Act II", "bring tension to its hardest choice", "The protagonist faces the cost of failure."),
                    self._beat("Climax", "Act III", "resolve the central dramatic question", "The decisive confrontation occurs here."),
                    self._beat("Resolution", "Act III", "show aftermath and new equilibrium", "Display consequence and closure."),
                ],
            ),
            "freytag": StructureTemplate(
                template_id="freytag",
                name="Freytag's Pyramid",
                category="classical_foundational",
                focus="Tragic dramatic escalation",
                primary_goal="Rise to climax and trace consequences",
                tags=["tragedy", "dramatic", "classical", "stakes"],
                beats=[
                    self._beat("Exposition", "Act I", "establish the dramatic situation", "Introduce the context and essential conflict seeds."),
                    self._beat("Inciting Moment", "Act I", "trigger movement away from equilibrium", "Set the dramatic engine in motion."),
                    self._beat("Rising Action", "Act II", "increase tension through linked complications", "Each event should intensify inevitability."),
                    self._beat("Climax", "Act III", "deliver the turning peak of the drama", "The central high point of tension."),
                    self._beat("Falling Action", "Act IV", "show consequences cascading from the climax", "Resolve threads downward from the peak."),
                    self._beat("Denouement", "Act V", "complete the emotional and causal aftermath", "End with restored order, catastrophe, or revelation."),
                ],
            ),
            "fichtean_curve": StructureTemplate(
                template_id="fichtean_curve",
                name="The Fichtean Curve",
                category="classical_foundational",
                focus="Tension / Stakes",
                primary_goal="Keep the reader on edge",
                tags=["fast", "high_tension", "crisis", "commercial"],
                beats=[
                    self._beat("Inciting Incident", "Opening", "begin with disruption immediately", "Start close to the first major problem."),
                    self._beat("Crisis 1", "Rising Action", "force a consequential decision", "Escalate quickly with limited downtime."),
                    self._beat("Crisis 2", "Rising Action", "complicate the prior choice", "Stack problems rather than resetting."),
                    self._beat("Crisis 3", "Rising Action", "tighten stakes and narrow options", "The protagonist should feel pressure mounting."),
                    self._beat("Climax", "Peak", "resolve the highest-stakes crisis", "The arc culminates in an unavoidable confrontation."),
                    self._beat("Falling Action", "Aftermath", "briefly stabilize and reveal consequences", "Keep this compact and earned."),
                ],
            ),
            "save_the_cat": StructureTemplate(
                template_id="save_the_cat",
                name="Save the Cat!",
                category="modern_blueprint",
                focus="Pacing / Commercial",
                primary_goal="Consistent Audience Engagement",
                tags=["commercial", "screenplay", "beats", "pacing"],
                beats=[
                    self._beat("Opening Image", "Act I", "present the before-state", "Offer a vivid snapshot of the world and tone."),
                    self._beat("Theme Stated", "Act I", "introduce the story's core lesson or tension", "A line, event, or motif should hint at what must be learned."),
                    self._beat("Set-Up", "Act I", "introduce character, flaw, and world dynamics", "Seed important future payoffs."),
                    self._beat("Catalyst", "Act I", "hit the protagonist with a disruptive event", "The story truly starts here."),
                    self._beat("Debate", "Act I", "let the protagonist hesitate or wrestle with change", "Explore doubt before commitment."),
                    self._beat("Break into Two", "Act II", "commit to the new world or plan", "Act II begins with a decisive move."),
                    self._beat("B Story", "Act II", "introduce the relational or thematic secondary line", "This often carries emotional truth."),
                    self._beat("Fun and Games", "Act II", "deliver the premise in action", "Show the audience the promised experience."),
                    self._beat("Midpoint", "Act II", "land a false victory or false defeat", "Raise stakes and shift momentum."),
                    self._beat("Bad Guys Close In", "Act II", "tighten internal and external pressures", "Complications converge."),
                    self._beat("All Is Lost", "Act II", "drop the protagonist to their lowest point", "A symbolic whiff of death belongs here."),
                    self._beat("Dark Night of the Soul", "Act II", "force reflection before reinvention", "The protagonist processes failure."),
                    self._beat("Break into Three", "Act III", "generate the new synthesis or final plan", "Lesson plus action create the path forward."),
                    self._beat("Finale", "Act III", "resolve plot and theme through decisive action", "Demonstrate transformed capability."),
                    self._beat("Final Image", "Act III", "mirror and contrast the opening image", "Show visible change."),
                ],
            ),
            "story_circle": StructureTemplate(
                template_id="story_circle",
                name="The Story Circle",
                category="modern_blueprint",
                focus="Cycle of change",
                primary_goal="Transformation through a simple loop",
                tags=["mythic", "compact", "character_arc", "transformation"],
                beats=[
                    self._beat("You", "1", "establish the character in a zone of comfort", "Define normality and lack."),
                    self._beat("Need", "2", "reveal what the character wants or lacks", "A need destabilizes comfort."),
                    self._beat("Go", "3", "enter an unfamiliar situation", "The boundary into the new world is crossed."),
                    self._beat("Search", "4", "adapt, struggle, or experiment", "Learning occurs through motion and friction."),
                    self._beat("Find", "5", "reach the apparent goal or truth", "The sought thing is attained or glimpsed."),
                    self._beat("Take", "6", "pay the price", "Acquisition comes with cost or wound."),
                    self._beat("Return", "7", "come back to the familiar world", "The character re-enters the old domain altered by experience."),
                    self._beat("Changed", "8", "show transformation", "Prove the internal shift."),
                ],
            ),
            "seven_point": StructureTemplate(
                template_id="seven_point",
                name="The 7-Point Story Structure",
                category="modern_blueprint",
                focus="Structural anchors",
                primary_goal="Control pacing through seven major turns",
                tags=["balanced", "plotting", "novel", "turning_points"],
                beats=[
                    self._beat("Hook", "Beginning", "introduce the protagonist and starting state", "Show the initial condition before transformation."),
                    self._beat("Plot Point 1", "Act I", "launch the protagonist into the main conflict", "Irreversible engagement begins."),
                    self._beat("Pinch Point 1", "Act II", "demonstrate antagonistic pressure", "Remind the audience of danger or opposition."),
                    self._beat("Midpoint", "Act II", "shift from reaction to action", "The protagonist changes approach."),
                    self._beat("Pinch Point 2", "Act II", "intensify pressure and narrow escape routes", "Make the opposition feel stronger."),
                    self._beat("Plot Point 2", "Act III", "set up the final resolution path", "The final move becomes possible."),
                    self._beat("Resolution", "End", "deliver outcome and transformed state", "Complete the character and plot arc."),
                ],
            ),
            "twenty_seven_chapter": StructureTemplate(
                template_id="twenty_seven_chapter",
                name="The 27-Chapter Method",
                category="modern_blueprint",
                focus="Granular pacing",
                primary_goal="Steady progression through nine blocks and 27 chapter units",
                supports_chapters=True,
                tags=["novel", "granular", "chaptered", "epic"],
                beats=self._build_27_chapter_beats(),
            ),
            "kishotenketsu": StructureTemplate(
                template_id="kishotenketsu",
                name="Kishōtenketsu",
                category="alternative_non_western",
                focus="Twist / Contrast",
                primary_goal="Exploration of Change without conflict dependence",
                tags=["low_conflict", "contrast", "twist", "reflective"],
                beats=[
                    self._beat("Ki — Introduction", "Act I", "introduce the situation and its components", "Establish the initial pattern clearly."),
                    self._beat("Shō — Development", "Act II", "develop the established elements", "Expand what was introduced without requiring confrontation."),
                    self._beat("Ten — Twist", "Act III", "introduce contrast or unexpected perspective", "This should recast what came before."),
                    self._beat("Ketsu — Reconciliation", "Act IV", "bring strands into meaningful relation", "Resolve through synthesis rather than victory."),
                ],
            ),
            "heroine_journey": StructureTemplate(
                template_id="heroine_journey",
                name="The Heroine's Journey",
                category="alternative_non_western",
                focus="Internal healing and integration",
                primary_goal="Balance the feminine and masculine within",
                tags=["internal", "healing", "identity", "psychological"],
                beats=[
                    self._beat("Separation from the Feminine", "Phase I", "establish the rupture from origins or embodied self", "Name the alienation clearly."),
                    self._beat("Identification with the Masculine", "Phase II", "pursue value through externalized systems", "Show adaptation to dominant frameworks."),
                    self._beat("Road of Trials", "Phase III", "test the current coping model", "The external path stops being sufficient."),
                    self._beat("Illusion of Success", "Phase IV", "reach a seemingly validating peak", "Success should feel incomplete or costly."),
                    self._beat("Descent / Initiation", "Phase V", "enter crisis and deeper self-contact", "The old identity begins to fail."),
                    self._beat("Yearning to Reconnect", "Phase VI", "seek the lost or rejected self", "Healing desire becomes conscious."),
                    self._beat("Healing the Split", "Phase VII", "integrate fractured identity", "Bring rejected parts into relation."),
                    self._beat("Integration", "Phase VIII", "embody a fuller selfhood", "End with balance, not conquest."),
                ],
            ),
            "in_medias_res": StructureTemplate(
                template_id="in_medias_res",
                name="In Media Res",
                category="alternative_non_western",
                focus="Immediate immersion",
                primary_goal="Hook through action, then reveal context strategically",
                tags=["fast", "hook", "non_linear", "flashback"],
                beats=[
                    self._beat("Open in Motion", "Opening", "begin in the middle of significant action", "Drop the reader into a meaningful unstable moment."),
                    self._beat("Context Fragments", "Development", "reveal prior causes selectively", "Backstory should answer active questions, not stop momentum."),
                    self._beat("Present Escalation", "Development", "continue the live thread while context accumulates", "Keep the present timeline primary."),
                    self._beat("Convergence", "Climax", "align past causes with present stakes", "The audience should understand how everything led here."),
                    self._beat("Resolution", "Ending", "resolve both present action and retrospective meaning", "The opening chaos now has shape."),
                ],
            ),
            "snowflake": StructureTemplate(
                template_id="snowflake",
                name="The Snowflake Method (Structural)",
                category="alternative_non_western",
                focus="Expansion from core premise",
                primary_goal="Build structure outward from a single thematic seed",
                tags=["planning", "theme", "expansion", "design"],
                beats=[
                    self._beat("Core Sentence", "Step 1", "define the story in one compelling line", "Capture premise and central movement succinctly."),
                    self._beat("Paragraph Expansion", "Step 2", "expand premise into major structural movements", "Identify beginning, middle, end, and key turns."),
                    self._beat("Character Expansion", "Step 3", "define primary character motivations and change", "Map the human engine of the story."),
                    self._beat("Scene / Summary Expansion", "Step 4", "grow the macro shape into scene-ready units", "Each expansion should preserve alignment with the core sentence."),
                    self._beat("Full Structural Synthesis", "Step 5", "integrate theme, characters, and plot into a coherent outline", "Use growth without losing conceptual clarity."),
                ],
            ),
            "mystery": StructureTemplate(
                template_id="mystery",
                name="The Mystery Structure",
                category="genre_specific",
                focus="Discovery arc",
                primary_goal="Reveal truth through investigation",
                tags=["mystery", "investigation", "discovery", "procedural"],
                beats=[
                    self._beat("The Crime", "Opening", "present the central wrong, absence, or puzzle", "Anchor the story with a compelling unanswered question."),
                    self._beat("The Investigation", "Middle", "pursue clues, witnesses, and theories", "Each step should produce evidence and complication."),
                    self._beat("The Red Herring", "Middle", "misdirect belief with plausible false interpretation", "Use misdirection fairly."),
                    self._beat("The Reveal", "Climax", "uncover the truth and its implications", "The answer must reframe earlier evidence."),
                ],
            ),
            "romcom": StructureTemplate(
                template_id="romcom",
                name="The Rom-Com Beats",
                category="genre_specific",
                focus="Romantic escalation with comedic/relational turns",
                primary_goal="Earn emotional union through attraction, rupture, and recommitment",
                tags=["romance", "romcom", "relationship", "comedy"],
                beats=[
                    self._beat("Meet-Cute", "Act I", "spark relational chemistry through memorable contact", "The connection should feel distinct."),
                    self._beat("Reluctant Attraction", "Act I/II", "build closeness while preserving friction", "Let desire and resistance coexist."),
                    self._beat("Midpoint Commitment", "Act II", "create a meaningful emotional or relational step forward", "The bond appears real here."),
                    self._beat("Big Misunderstanding", "Act II", "rupture trust or alignment", "The breakup or separation should test what matters."),
                    self._beat("Grand Gesture", "Act III", "resolve the emotional conflict through visible commitment", "End with action proving feeling."),
                ],
            ),
            "quest": StructureTemplate(
                template_id="quest",
                name="The Quest",
                category="genre_specific",
                focus="Physical journey mirroring internal progress",
                primary_goal="Bind travel, world, and transformation together",
                tags=["quest", "journey", "epic", "adventure"],
                beats=[
                    self._beat("Departure", "Act I", "leave the familiar world behind", "A destination or objective is defined."),
                    self._beat("Road of Trials", "Act II", "encounter obstacles across changing terrain", "Let the geography shape the arc."),
                    self._beat("Approach to Destination", "Act II", "bring external and internal pressure into alignment", "Nearness should intensify meaning."),
                    self._beat("Attainment / Confrontation", "Act III", "reach the objective and face its cost", "The destination delivers the real test."),
                    self._beat("Return / Aftermath", "Act III", "show how the traveler is altered", "The world is not the same on return."),
                ],
            ),
        }

    def _build_27_chapter_beats(self) -> List[Dict[str, Any]]:
        beats: List[Dict[str, Any]] = []
        chapter = 1
        blocks = [
            ("Act I", ["Setup 1", "Setup 2", "Catalyst"]),
            ("Act I", ["Reaction 1", "Reaction 2", "Commitment"]),
            ("Act I/II", ["Transition 1", "Transition 2", "Break into Act II"]),
            ("Act II", ["Progress 1", "Progress 2", "Pinch"]),
            ("Act II", ["Midpoint Build 1", "Midpoint", "Midpoint Consequence"]),
            ("Act II", ["Pressure 1", "Pressure 2", "Second Pinch"]),
            ("Act II/III", ["Collapse 1", "Collapse 2", "Break into Act III"]),
            ("Act III", ["Final Plan 1", "Final Plan 2", "Climactic Entry"]),
            ("Act III", ["Climax", "Aftermath", "Resolution"]),
        ]
        for phase, labels in blocks:
            children = []
            for label in labels:
                children.append(
                    {
                        "label": f"Chapter {chapter}: {label}",
                        "phase": phase,
                        "intent": f"advance the {label.lower()} movement",
                        "guidance": "Use this chapter slot to maintain pacing, consequence, and progression.",
                    }
                )
                chapter += 1
            beats.append(
                {
                    "label": labels[-1] if labels else phase,
                    "phase": phase,
                    "intent": f"anchor the {phase} block",
                    "guidance": "This block groups three chapter-sized movements.",
                    "children": children,
                }
            )
        return beats

    def _beat(self, label: str, phase: str, intent: str, guidance: str) -> Dict[str, Any]:
        return {
            "label": label,
            "phase": phase,
            "intent": intent,
            "guidance": guidance,
        }


def _to_outline_template(st: "StructureTemplate") -> Any:
    """Convert this plugin's StructureTemplate into the shared OutlineTemplate
    so it shows up in the Outline view + Assistant Outline mode."""
    from logosforge.outline_templates import OutlineTemplate, TemplateBeat

    def _beats(raw: List[Dict[str, Any]]) -> List[Any]:
        out: List[Any] = []
        for b in raw:
            title = b.get("label", "Beat")
            phase = b.get("phase", "")
            if phase:
                title = f"{phase} — {title}"
            desc = b.get("guidance") or b.get("intent") or ""
            children = _beats(b.get("children", [])) if b.get("children") else []
            out.append(TemplateBeat(title=title, description=desc, children=children))
        return out

    return OutlineTemplate(
        name=st.name,
        description=f"{st.focus} — {st.primary_goal}",
        beats=_beats(st.beats),
    )


# Plugin structures whose concept a richer, hierarchical built-in already
# covers (different key, so the registry wouldn't auto-skip them). We keep the
# built-in and don't add a flat near-duplicate — no redundant combo entries.
# Maps this plugin's key -> the built-in key that supersedes it.
_COVERED_BY_BUILTIN = {
    "hero_journey": "heros_journey",   # built-in "Hero's Journey" (3-act, nested)
    "freytag": "five_act",             # built-in "Five-Act Structure (Freytag)"
}


def register(app_api: Any) -> Any:
    plugin = PsykeOutlineTemplatesPlugin(app_api)

    # Contribute this plugin's structural templates to the shared Outline
    # catalog, so they appear in the Outline view + Assistant Outline mode and
    # are applyable through the existing (confirmation-guarded) flow. This is
    # exactly what logosforge.outline_templates.register_outline_template was
    # built for; without it the plugin loads but is otherwise inert. Built-in
    # keys are never overwritten (the registry ignores collisions), and we skip
    # structures a richer built-in already covers to avoid duplicate entries.
    try:
        from logosforge.outline_templates import (
            OUTLINE_TEMPLATES,
            register_outline_template,
        )
        for key, st in plugin.templates.items():
            covered = _COVERED_BY_BUILTIN.get(key)
            if covered and covered in OUTLINE_TEMPLATES:
                continue
            register_outline_template(key, _to_outline_template(st))
    except Exception as exc:  # pragma: no cover - defensive
        log = getattr(app_api, "log", None)
        if callable(log):
            log(f"PSYKE Outline Templates: catalog registration failed: {exc}")

    # Also support a connector-style host that consumes the run() entrypoint.
    register_fn = getattr(app_api, "register_plugin", None)
    if callable(register_fn):
        try:
            register_fn(id=PLUGIN_ID, name="PSYKE Outline Templates", run=plugin.run)
        except TypeError:
            pass
    return plugin
