"""ProactiveEngine — runs rule-based detectors and filters the results.

Phase 4 is rule-based and fast: a scan reads the DB, runs the section's
detectors, then filters by confidence threshold, severity settings and
suppression, and dedupes by stable id. It never calls an LLM, never mutates the
DB, and never blocks on the network.
"""

from __future__ import annotations

from logosforge.logos.proactive import scoring
from logosforge.logos.proactive.detectors import SECTION_DETECTORS
from logosforge.logos.proactive.suggestion import (
    SEVERITY_IMPORTANT,
    SEVERITY_INFO,
    SEVERITY_WARNING,
)
from logosforge.logos.proactive.suppression import SuppressionStore


class ProactiveConfig:
    """Resolved proactive settings (read from the global SettingsManager)."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        threshold: float = scoring.DEFAULT_CONFIDENCE_THRESHOLD,
        show_info: bool = True,
        show_warning: bool = True,
        ai_scan_enabled: bool = False,
    ) -> None:
        self.enabled = enabled
        self.threshold = threshold
        self.show_info = show_info
        self.show_warning = show_warning
        self.ai_scan_enabled = ai_scan_enabled

    @classmethod
    def from_settings(cls) -> "ProactiveConfig":
        try:
            from logosforge.settings import get_manager
            mgr = get_manager()
            return cls(
                enabled=bool(_get(mgr, "logos_proactive_enabled", True)),
                threshold=float(_get(mgr, "logos_confidence_threshold", 0.65)),
                show_info=bool(_get(mgr, "logos_show_info", True)),
                show_warning=bool(_get(mgr, "logos_show_warning", True)),
                ai_scan_enabled=bool(_get(mgr, "logos_ai_scan_enabled", False)),
            )
        except Exception:
            return cls()

    def severity_allowed(self, severity: str) -> bool:
        if severity == SEVERITY_INFO:
            return self.show_info
        if severity == SEVERITY_WARNING:
            return self.show_warning
        return True  # important is always allowed


def _get(mgr, key, default):
    val = mgr.get(key)
    return default if val is None else val


class ProactiveEngine:
    def __init__(
        self,
        db,
        project_id: int,
        *,
        config: ProactiveConfig | None = None,
        suppression: SuppressionStore | None = None,
    ) -> None:
        self._db = db
        self._project_id = project_id
        self._config = config or ProactiveConfig.from_settings()
        self._suppression = suppression or SuppressionStore(db, project_id)

    @property
    def suppression(self) -> SuppressionStore:
        return self._suppression

    @property
    def config(self) -> ProactiveConfig:
        return self._config

    def scan_section(self, section_name: str, context=None) -> list:
        """Run the detectors for *section_name* and return visible suggestions."""
        if not self._config.enabled:
            return []
        detectors = SECTION_DETECTORS.get(section_name, [])
        raw: list = []
        for detect in detectors:
            try:
                raw.extend(detect(self._db, self._project_id, context))
            except Exception:
                continue  # a flaky detector never breaks the scan
        return self._filter(raw)

    def _filter(self, suggestions: list) -> list:
        seen: set[str] = set()
        out: list = []
        for s in suggestions:
            if s.confidence < self._config.threshold:
                continue
            if not self._config.severity_allowed(s.severity):
                continue
            if self._suppression.is_suppressed(s):
                continue
            if s.id in seen:
                continue
            seen.add(s.id)
            out.append(s)
        # Most severe / most confident first.
        out.sort(key=lambda s: (s.severity_rank, s.confidence), reverse=True)
        return out
