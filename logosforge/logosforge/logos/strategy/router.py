"""StrategyRouter — deterministic narrative strategy routing.

Given the project mode, section, active plugins, Lambda/Classical mode, selected
template and health state, it decides which strategies are active, which one
dominates, which context blocks to include, which diagnostics matter, and which
Logos actions to surface — with explainable reasoning. No LLM, no DB mutation.
"""

from __future__ import annotations

from logosforge.logos.strategy import conflicts, context_policy, explanation
from logosforge.logos.strategy import medium_profiles as mp
from logosforge.logos.strategy import registry as reg
from logosforge.logos.strategy.strategy import StrategyDecision


class StrategyRouter:
    def __init__(self, db, project_id: int) -> None:
        self._db = db
        self._project_id = project_id

    # -- Inputs (read-only, deterministic) -----------------------------------

    def _engine(self) -> str:
        try:
            from logosforge.project_compat import get_project_narrative_engine
            return get_project_narrative_engine(self._db.get_project_by_id(self._project_id))
        except Exception:
            return mp.NOVEL

    def _writing_format(self) -> str:
        try:
            from logosforge.project_compat import get_project_writing_format
            return get_project_writing_format(self._db.get_project_by_id(self._project_id))
        except Exception:
            return mp.NOVEL

    def _outline_template(self) -> str:
        try:
            settings = self._db.get_project_settings(self._project_id)
            return settings.get("outline_template", "") or ""
        except Exception:
            return ""

    def _gomckee_enabled(self) -> bool:
        try:
            from logosforge.gomckee_bridge import is_gomckee_enabled
            return is_gomckee_enabled()
        except Exception:
            return False

    def _controlling_idea_enabled(self) -> bool:
        try:
            from logosforge.controlling_idea import load as load_ci
            return bool(load_ci(self._db, self._project_id).enabled)
        except Exception:
            return False

    def _lambda_on(self) -> bool:
        try:
            from logosforge.quantum_outliner.state import OutlineMode, get_outline_mode
            return get_outline_mode(self._project_id) is OutlineMode.LAMBDA
        except Exception:
            return False

    def _user_override(self) -> str:
        try:
            from logosforge.settings import get_manager
            return str(get_manager().get("strategy_user_mode_override") or "")
        except Exception:
            return ""

    def _strategy_enabled(self) -> bool:
        try:
            from logosforge.settings import get_manager
            val = get_manager().get("strategy_enabled")
            return True if val is None else bool(val)
        except Exception:
            return True

    # -- Decision ------------------------------------------------------------

    def decide(self, section_name: str = "") -> StrategyDecision:
        engine = self._engine()
        override = self._user_override()
        # A user override forces the medium strategy of the named engine.
        if override in reg.MEDIUM_STRATEGY:
            engine = override

        decision = StrategyDecision(
            project_id=self._project_id,
            section_name=section_name,
            narrative_engine=engine,
            writing_format=self._writing_format(),
            outline_template=self._outline_template(),
            user_override=override,
        )

        if not self._strategy_enabled():
            decision.dominant_strategy = reg.S_DEFAULT
            decision.active_strategies = [reg.S_DEFAULT]
            decision.reasoning_notes = ["Strategy layer disabled — using Default."]
            decision.explanation = explanation.explain(decision)
            return decision

        active: list[str] = []
        notes: list[str] = []

        # 1. Medium strategy from project mode (the strong default).
        medium_id = reg.MEDIUM_STRATEGY.get(engine, reg.S_DEFAULT)
        active.append(medium_id)
        profile = mp.get_profile(engine)
        notes.append(f"Project mode '{engine}' -> {profile.name} Strategy.")

        # 2. Plugin-gated strategies (only when actually enabled).
        gomckee = self._gomckee_enabled()
        if gomckee:
            active.append(reg.S_GOMCKEE)
            notes.append("Go McKee plugin enabled -> conflict-centric pressure added.")
        if self._controlling_idea_enabled():
            active.append(reg.S_CONTROLLING_IDEA)
            notes.append("Controlling Idea enabled -> thematic alignment added.")

        # 3. PSYKE continuity for entity-centric sections.
        if section_name in ("PSYKE", "Graph"):
            active.append(reg.S_PSYKE_CONTINUITY)
            notes.append(f"{section_name} section -> PSYKE Continuity Strategy.")

        # 4. Quantum mode strategy.
        lambda_on = self._lambda_on()
        active.append(reg.S_QUANTUM_LAMBDA if lambda_on else reg.S_QUANTUM_CLASSICAL)
        causality, c_note = conflicts.resolve_causality(
            lambda_on=lambda_on, user_override="",
        )
        notes.append(c_note)

        # -- Dominant strategy: highest-priority *active* strategy ------------
        def _prio(sid: str) -> int:
            s = reg.get_strategy(sid)
            return s.priority if s else -1
        # Go McKee can dominate only when enabled; medium otherwise.
        dominant = max(active, key=_prio)
        # The medium strategy stays dominant for context/action selection unless
        # a higher-priority plugin strategy is active AND relevant.
        decision.dominant_strategy = dominant

        # -- Conflict resolution on the 'conflict' principle ------------------
        project_conflict_stance = profile.principles.get("conflict", "allow")
        if gomckee:
            project_conflict_stance = "emphasize"
        stance, note = conflicts.resolve_conflict_principle(
            "conflict", project_stance=project_conflict_stance,
            template_key=decision.outline_template, user_override="",
        )
        notes.append(note)
        # If the template defused conflict, McKee is suppressed for this task.
        suppressed: list[str] = []
        if gomckee and stance != "emphasize":
            suppressed.append(reg.S_GOMCKEE)
            notes.append(
                "Go McKee suppressed: the selected template is contrast-based."
            )
        # Suppress the inactive quantum mode for clarity.
        suppressed.append(reg.S_QUANTUM_CLASSICAL if lambda_on else reg.S_QUANTUM_LAMBDA)

        # -- Context, diagnostics, actions ------------------------------------
        extra_blocks = ()
        if reg.S_NARRATIVE_HEALTH in active:
            extra_blocks = (mp.CTX_HEALTH,)
        decision.included_context_blocks = context_policy.select_context_blocks(
            engine, section_name, extra_blocks=extra_blocks,
        )
        decision.active_diagnostics = list(profile.diagnostic_categories)
        if gomckee and reg.S_GOMCKEE not in suppressed:
            for c in ("conflict", "setup_payoff"):
                if c not in decision.active_diagnostics:
                    decision.active_diagnostics.append(c)

        decision.recommended_logos_actions = self.recommended_logos_actions(
            section_name, engine=engine,
        )
        decision.active_strategies = [s for s in active if s not in suppressed]
        decision.suppressed_strategies = suppressed
        decision.reasoning_notes = notes
        decision.explanation = explanation.explain(decision)
        return decision

    # -- Logos action ordering ----------------------------------------------

    def recommended_logos_actions(
        self, section_name: str, *, engine: str | None = None,
    ) -> list[str]:
        """Section's Logos actions, reordered so the medium's preferred ones
        come first. Never invents actions — only reorders the real ones.

        Mode-restricted actions (e.g. screenplay-only) are filtered to the active
        engine, so a Novel project never surfaces screenplay-only actions.
        """
        from logosforge.logos.actions import list_actions_for_section
        engine = engine or self._engine()
        profile = mp.get_profile(engine)
        available = [
            a.name for a in list_actions_for_section(section_name, writing_mode=engine)
        ]
        preferred = [a for a in profile.preferred_actions if a in available]
        rest = [a for a in available if a not in preferred]
        return preferred + rest
