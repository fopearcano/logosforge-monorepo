"""HealthEngine — builds an explainable project-level NarrativeHealthReport.

Runs the Phase-5 diagnostics once over a shared facts snapshot, aggregates them
into the 12 health metrics, derives an explainable overall status, and produces
prioritized recommendations. Rule-based only — no LLM during a scan, no DB
mutation, never blocks on the network.
"""

from __future__ import annotations

from logosforge.logos.diagnostics.engine import _ALL_DETECTORS
from logosforge.logos.diagnostics.model import build_facts
from logosforge.logos.health import metric as M
from logosforge.logos.health.aggregators import aggregate_metrics
from logosforge.logos.health.recommendations import build_recommendations
from logosforge.logos.health.report import NarrativeHealthReport

# Core categories whose weakness dominates the overall status.
_CORE = {M.CAT_STRUCTURE, M.CAT_CONTINUITY, M.CAT_CHARACTER}


class HealthEngine:
    def __init__(
        self, db, project_id: int, *, suppression=None, writing_mode: str = "",
    ) -> None:
        self._db = db
        self._project_id = project_id
        self._suppression = suppression
        # Phase 9 — the project's writing mode. Resolved from the project when
        # not supplied so Health is always mode-aware. Recorded on the report;
        # no metrics are invented from it (it only contextualizes wording).
        self._writing_mode = writing_mode or self._resolve_writing_mode()

    def _resolve_writing_mode(self) -> str:
        try:
            from logosforge.writing_modes import get_project_writing_mode_by_id
            return get_project_writing_mode_by_id(self._db, self._project_id)
        except Exception:
            return "novel"

    def generate_report(self) -> NarrativeHealthReport:
        facts = build_facts(self._db, self._project_id)

        diagnostics = []
        for detect in _ALL_DETECTORS:
            try:
                diagnostics.extend(detect(facts))
            except Exception:
                continue
        diagnostics = self._dedup(diagnostics)

        presence = self._data_presence(facts)
        metrics = aggregate_metrics(diagnostics, presence)

        # Phase 10C — append deterministic screenplay metrics for screenplay
        # projects (additive; never affects Novel/other modes). No LLM/DB write.
        if self._writing_mode == "screenplay":
            try:
                from logosforge.screenplay_diagnostics import (
                    screenplay_health_metrics,
                )
                metrics = metrics + screenplay_health_metrics(
                    self._db, self._project_id,
                )
            except Exception:
                pass

        # Phase 10L — cross-mode rewrite-sandbox metrics (only when an open
        # session exists; never affects canonical content). Additive, no LLM/DB.
        try:
            from logosforge.rewrite_sandbox.engine import rewrite_health_metrics
            metrics = metrics + rewrite_health_metrics(self._db, self._project_id)
        except Exception:
            pass

        overall = self._overall_status(metrics)

        report = NarrativeHealthReport(
            project_id=self._project_id,
            project_title=self._project_title(),
            overall_status=overall,
            metrics=metrics,
            diagnostic_ids=[d.id for d in diagnostics],
            recommendations=build_recommendations(diagnostics),
            writing_mode=self._writing_mode,
        )
        report.top_risks = self._top_risks(metrics)
        report.strengths = self._strengths(metrics)
        report.section_summaries = self._section_summaries(metrics)
        return report

    # -- Internals -----------------------------------------------------------

    def _dedup(self, diagnostics):
        seen: set[str] = set()
        out = []
        for d in diagnostics:
            if self._suppression is not None:
                try:
                    if self._suppression.is_suppressed(d.to_suggestion()):
                        continue
                except Exception:
                    pass
            if d.id in seen:
                continue
            seen.add(d.id)
            out.append(d)
        return out

    def _data_presence(self, facts) -> dict:
        scenes = facts.scenes
        entries = facts.entries
        has_scenes = bool(scenes)
        has_entries = bool(entries)
        has_chars = any(e.entry_type == "character" for e in entries)
        has_themes = any(e.entry_type == "theme" for e in entries)
        has_objects = any(e.entry_type in ("object", "lore") for e in entries)
        any_relations = any(facts.relations.get(e.id) for e in entries)
        any_progressions = any(facts.progressions.get(e.id) for e in entries)
        multi_act = len({(s.act or "").strip() for s in scenes if (s.act or "").strip()}) >= 2
        return {
            M.CAT_STRUCTURE: has_scenes,
            M.CAT_CHARACTER: has_chars,
            M.CAT_RELATIONSHIP: has_entries,
            M.CAT_THEME: has_themes,
            # Continuity needs progressions to judge; else unknown.
            M.CAT_CONTINUITY: any_progressions,
            M.CAT_TIMELINE: has_scenes and multi_act,
            M.CAT_PACING: has_scenes,
            M.CAT_SCENE_PURPOSE: has_scenes,
            # Setup/payoff needs objects/lore or notes to judge.
            M.CAT_SETUP_PAYOFF: has_objects or bool(facts.notes),
            M.CAT_PSYKE: has_entries,
            M.CAT_GRAPH: has_entries,
            M.CAT_NOTES: bool(facts.notes),
        }

    def _overall_status(self, metrics) -> str:
        known = [m for m in metrics if m.is_known]
        if not known:
            return M.STATUS_UNKNOWN
        if any(m.status == M.STATUS_CRITICAL for m in known):
            return M.STATUS_CRITICAL
        weak_core = sum(
            1 for m in known if m.category in _CORE and m.status == M.STATUS_WEAK
        )
        n_weak = sum(1 for m in known if m.status == M.STATUS_WEAK)
        if weak_core >= 2:
            return M.STATUS_CRITICAL
        if n_weak >= 1:
            return M.STATUS_WEAK
        if any(m.status == M.STATUS_WATCH for m in known):
            return M.STATUS_WATCH
        return M.STATUS_STABLE

    def _top_risks(self, metrics) -> list[str]:
        risky = [m for m in metrics if m.is_problem]
        risky.sort(key=lambda m: (m.status_rank, m.confidence), reverse=True)
        return [f"{m.name}: {m.status_label} — {m.evidence}" for m in risky[:5]]

    def _strengths(self, metrics) -> list[str]:
        stable = [m for m in metrics if m.status == M.STATUS_STABLE]
        return [f"{m.name}: Stable" for m in stable[:5]]

    def _section_summaries(self, metrics) -> dict:
        return {m.category: m.status_label for m in metrics}

    def _project_title(self) -> str:
        try:
            project = self._db.get_project_by_id(self._project_id)
            return project.title if project else ""
        except Exception:
            return ""
