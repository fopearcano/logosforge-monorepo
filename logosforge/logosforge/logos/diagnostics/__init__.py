"""Logos PSYKE narrative diagnostics (Phase 5).

A rule-based, PSYKE-aware analysis layer that turns the story bible (characters,
themes, relations, progressions, notes, scene appearances) into structured
diagnostics with evidence, severity, confidence and suggested Logos actions.
High-severity diagnostics feed the Phase-4 proactive suggestion bar. It reads
the authoritative Database only, never mutates data, and never calls an LLM in
the background.
"""

from logosforge.logos.diagnostics.diagnostic import (
    SEVERITY_CRITICAL,
    SEVERITY_IMPORTANT,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    NarrativeDiagnostic,
)
from logosforge.logos.diagnostics.engine import DiagnosticsEngine
from logosforge.logos.diagnostics.model import ProjectFacts, build_facts

__all__ = [
    "DiagnosticsEngine",
    "NarrativeDiagnostic",
    "ProjectFacts",
    "build_facts",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "SEVERITY_IMPORTANT",
    "SEVERITY_CRITICAL",
]
