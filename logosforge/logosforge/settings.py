"""Persistent settings manager — loads once, auto-saves on change."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".logosforge"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DEFAULTS: dict[str, object] = {
    "appearance": "Dark",
    "ai_provider": "LM Studio",
    "ai_model": "",
    "ai_api_key": "",
    "ai_base_url": "",
    "sidebar_collapsed": False,
    "sidebar_groups_expanded": {},
    "assistant_open": False,
    "assistant_pinned": False,
    "assistant_collapsed": False,
    "assistant_panel_mode": "assistant",
    "assistant_include_outline": False,
    "assistant_include_memory": False,
    "assistant_include_bible": False,
    "assistant_include_notes": True,
    "assistant_irrational": False,
    # -- Logos inline contextual layer (left-panel ON/OFF toggle) ------------
    # Master switch for the ambient inline Logos layer (toolbar + contextual
    # suggestions). Off by default — non-intrusive until the user turns it on.
    "logos_enabled": False,
    # -- Logos proactive suggestions (Phase 4) -------------------------------
    "logos_proactive_enabled": True,
    "logos_confidence_threshold": 0.65,
    "logos_show_info": True,
    "logos_show_warning": True,
    "logos_ai_scan_enabled": False,   # AI-assisted scan deferred; off by default
    # -- Narrative Health (Phase 6) ------------------------------------------
    "health_enabled": True,
    "health_auto_refresh_on_load": True,
    "health_include_in_assistant": False,
    "health_show_unknown": True,
    # -- Strategy layer (Phase 7) --------------------------------------------
    "strategy_enabled": True,
    "strategy_show_indicator": True,
    "strategy_debug_explanation": False,
    "strategy_user_mode_override": "",   # "" = auto; else an engine id
    # -- Assistant context injection (Phase 8B / 9 / 10C) --------------------
    "include_project_mode_in_assistant_context": True,
    "include_screenplay_diagnostics_in_assistant_context": True,
    "include_screenplay_tracking_in_assistant_context": True,
    "include_screenplay_links_in_assistant_context": True,
    "include_screenplay_export_in_assistant_context": True,
    # Professional output (DOCX/PDF/FDX) — opt-in to avoid prompt bloat.
    "include_professional_output_in_assistant_context": False,
    # Production draft status — shown only when production mode is active.
    "include_production_draft_in_assistant_context": True,
    # Revision impact — shown only when a saved impact report exists.
    "include_revision_impact_in_assistant_context": True,
    # Rewrite sandbox — shown only when an open rewrite session exists.
    "include_rewrite_sandbox_in_assistant_context": True,
    # Controlled apply — shown only when a pending apply preview exists.
    "include_controlled_apply_in_assistant_context": True,
    # Project intelligence — concise dashboard state (light, opt-out).
    "include_project_intelligence_in_assistant_context": True,
    # Guided workflow — shown only when a guided workflow is active.
    "include_guided_workflow_in_assistant_context": True,
    # Knowledge graph — shown only when a scene is open (scene-scoped).
    "include_knowledge_graph_in_assistant_context": True,
    # Continuity — shown only when there are open continuity issues.
    "include_continuity_in_assistant_context": True,
    "include_strategy_in_assistant_context": True,
    "include_health_in_assistant_context": False,
    "include_diagnostics_in_assistant_context": True,
    "max_health_risks_in_context": 3,
    "max_diagnostics_in_context": 5,
    "last_project_path": "",
    "plugin_states": {},
    "auto_link_ignored": [],
    "context_assistant_enabled": True,
    "context_assistant_ignored": [],
    # -- LogosForge passive memory context (Phase 6) -------------------------
    # Opt-in, default-OFF. When enabled AND a memory store is registered, the
    # assistant prompt builder may append a read-only LogosForge ContextBundle
    # (scoped memory + provider capabilities). No memory is ever written by
    # this; disabled keeps prompt behavior exactly as before.
    "assistant_memory_context_enabled": False,
    # Dev/diagnostics: also surface retrieval warnings/exclusions (labelled,
    # never secrets). Default-OFF.
    "assistant_memory_context_diagnostics_enabled": False,
    # -- LogosForge automatic memory capture (controlled passive runtime) ----
    # Opt-in, default-OFF. When enabled AND a memory store is registered, after
    # a completed assistant exchange LogosForge may build a safe event and run
    # the policy pipeline (safe memory auto-saves active; risky/uncertain goes
    # to review). Never runs before response generation; never calls a provider;
    # disabled keeps runtime behavior exactly as before.
    "assistant_auto_memory_enabled": False,
    # Dev/diagnostics: return safe processing summaries/counts (never secrets,
    # never raw chat, never raw audio paths). Default-OFF.
    "assistant_auto_memory_diagnostics_enabled": False,
    # -- Local Writer QA agent mode (OFF by default) -------------------------
    # Optional fake-provider profile used ONLY when LOGOSFORGE_QA_MODE is
    # enabled (see logosforge/qa_mode.py). Empty → the env var
    # LOGOSFORGE_FAKE_PROVIDER_PROFILE (or the "valid_auto" default) decides.
    # Has NO effect unless QA mode is explicitly turned on.
    "qa_fake_provider_profile": "",
    "connector_enabled": False,
    "connector_allow_writes": False,
    "connector_confirm_writes": True,
    "connector_disabled_actions": [],
    "assistant_api_timeout": 0,
    "default_projects_folder": "",
    "open_anyway_on_lock": False,
    "graph_state": {},
    "graph_presets": {},
    # -- Language system (multi-language infrastructure) ----------------------
    # Software UI Language — GLOBAL, separate from any project's writing
    # language ("en" default; only translated locales are selectable).
    "ui_language_code": "en",
    # Default Writing Language for NEW projects (per-project value lives in
    # the project's settings_json: writing_language_code).
    "default_writing_language": "en",
    # Dexter transcription mode: "project" (follow the project's writing
    # language) | "auto" | "explicit" (use voice_language). "" = infer from
    # voice_language for pre-existing installs (concrete code → explicit).
    "voice_language_mode": "",
    # -- Local voice-to-script (MVP) — OFF by default; local/LAN-first; no cloud --
    # When enabled but the selected backend is not configured, the voice UI shows
    # a non-blocking setup message (the app stays usable).
    "enable_voice_mode": False,
    # Backend mode: "disabled" | "mock" | "local_process" | "lan_server".
    "voice_backend_mode": "disabled",
    # Local PC backend (local_process): kind + local model (no auto-download).
    "voice_whisper_backend": "faster-whisper",   # local kind: "faster-whisper" | "mock"
    "voice_whisper_model_path": "",              # local model dir/file (no auto-download)
    "voice_whisper_executable_path": "",          # whisper.cpp binary (Phase 8)
    "voice_performance_profile": "balanced",      # fast_draft|balanced|accurate|custom
    "voice_beam_size": 0,                         # 0 = backend default
    "voice_local_device": "auto",                 # "auto" | "cpu" | "cuda"
    "voice_local_compute_type": "int8",
    # Optional CUDA runtime DLL directories added to the DLL search path at
    # startup so device="cuda" works without a launcher wrapper (Windows). Put
    # ONLY the cuBLAS/cuDNN DLLs in such a folder. Empty = no GPU auto-wiring.
    "voice_cuda_dll_dirs": [],
    "voice_language": "auto",                     # "auto" | "en" | "it" | ...
    "voice_auto_commit": False,                   # commit transcript without click
    # -- Voice glossary / corrections (Phase 7) — local, project-scoped --
    "enable_voice_glossary": True,
    "voice_spoken_punctuation": True,
    "voice_fuzzy_suggestions": False,             # conservative default
    "voice_auto_apply_exact": False,              # Alpha: review-first
    "voice_auto_apply_punctuation": False,
    "voice_learn_corrections": "ask",
    "voice_silence_ms": 900,
    "voice_max_segment_seconds": 25,
    "voice_overlap_ms": 0,
    # LAN backend (lan_server): a trusted Whisper server on the LOCAL network.
    # Private/loopback hosts only by default — public URLs are blocked for Alpha.
    "voice_lan_base_url": "",
    "voice_lan_api_type": "openai_compatible",   # | "whisper_cpp" | "custom"
    "voice_lan_transcription_endpoint": "",       # custom api_type only
    "voice_lan_health_endpoint": "",              # default: /health
    "voice_lan_timeout_seconds": 60,
    "voice_lan_auth_header_name": "",             # optional static local token
    "voice_lan_auth_token": "",                   # never logged
    "voice_lan_allow_only_private_hosts": True,
    "voice_lan_max_audio_seconds": 60,
    "voice_lan_max_payload_mb": 25,
    # -- LibreChat integration (optional advanced chat sidecar) --------------
    # OFF by default; LogosForge behaves exactly as before until enabled. The
    # nav button shows unless explicitly hidden (button_visible). Localhost-
    # first; LibreChat manages its own AI-provider config (no keys stored here).
    "librechat_enabled": False,
    "librechat_base_url": "http://localhost:3080",
    "librechat_mode": "local",                 # "local" | "remote"
    "librechat_auto_connect": False,
    "librechat_prefer_embedded": True,
    "librechat_browser_fallback": True,
    "librechat_startup_command": "",
    "librechat_button_visible": True,
    # -- Embedded in-process API (gives agents LIVE context) -----------------
    # OFF by default. When ON, the desktop app hosts the FastAPI server in-
    # process (localhost), sharing the live Database + a live-context registry
    # (current project / active scene / selection) so an MCP/agent sees live
    # editing state, not just persisted data. Takes effect on app start.
    "api_embedded_enabled": False,
    "api_embedded_port": 8765,
}


class SettingsManager:
    def __init__(self) -> None:
        self._data: dict[str, object] = dict(DEFAULTS)
        self._load()

    def _load(self) -> None:
        if not SETTINGS_FILE.exists():
            return
        try:
            raw = SETTINGS_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                self._data.update(data)
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(
                json.dumps(self._data, indent=2), encoding="utf-8",
            )
        except OSError:
            pass

    def get(self, key: str) -> object:
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: object) -> None:
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self._save()


_instance: SettingsManager | None = None


def get_manager() -> SettingsManager:
    global _instance
    if _instance is None:
        _instance = SettingsManager()
    return _instance
