"""Step 16 — provider / timeout / Assistant-language stabilization (lock tests).

The provider layer was audited stable; these tests lock the behaviors the task
calls out so they can't silently regress.
"""

import socket

import pytest
from PySide6.QtWidgets import QApplication, QComboBox

import logosforge.assistant as assistant
from logosforge.providers import (
    PROVIDER_CAPABILITIES,
    build_active_provider,
    validate_provider,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json",
                        raising=False)
    yield
    settings._instance = None


# ==========================================================================
# Provider settings persistence (single resolver reads what the UI saves)
# ==========================================================================


def test_provider_settings_persist_via_single_resolver():
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", "Anthropic")
    mgr.set("ai_base_url", "https://api.anthropic.com")
    mgr.set("ai_model", "claude-opus-4-8")
    mgr.set("ai_api_key", "sk-test-123")
    cfg = build_active_provider()
    assert cfg.name == "Anthropic"
    assert cfg.base_url == "https://api.anthropic.com"
    assert cfg.model == "claude-opus-4-8"
    assert cfg.api_key == "sk-test-123"


def test_local_server_url_persists():
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", "Ollama")
    mgr.set("ai_base_url", "http://192.168.1.50:11434/v1")
    assert build_active_provider().base_url == "http://192.168.1.50:11434/v1"


def test_require_configured_returns_none_when_blank():
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("ai_provider", "")
    mgr.set("ai_base_url", "")
    assert build_active_provider(require_configured=True) is None


# ==========================================================================
# Provider switch — Anthropic does not open a blank/tiny window
# ==========================================================================


def test_anthropic_switch_populates_form_no_blank_window():
    from logosforge.ui.provider_settings import ProviderSettingsWidget
    w = ProviderSettingsWidget()
    w._on_provider_changed("Anthropic")
    # Form populated (not blank): default base url + model list + key field shown.
    assert w._url_input.text() == "https://api.anthropic.com"
    assert w._model_combo.count() > 0
    assert w._key_input.isHidden() is False        # key required -> shown
    # The editable model combo must have NO completer (the stray-popup fix that
    # caused the tiny floating window on provider switch).
    assert w._model_combo.completer() is None
    assert w._model_combo.insertPolicy() == QComboBox.InsertPolicy.NoInsert


def test_custom_model_name_allowed():
    from logosforge.ui.provider_settings import ProviderSettingsWidget
    w = ProviderSettingsWidget()
    assert w._model_combo.isEditable() is True
    w._model_combo.setCurrentText("my-local-model:latest")
    assert w._model_combo.currentText() == "my-local-model:latest"


def test_invalid_config_returns_readable_error():
    from logosforge.providers import ProviderConfig
    # Anthropic requires a key — missing key -> readable message.
    err = validate_provider(ProviderConfig(name="Anthropic",
                                           base_url="https://api.anthropic.com"))
    assert err and "API key" in err
    err2 = validate_provider(ProviderConfig(name="OpenAI", base_url=""))
    assert err2 and "Base URL" in err2


# ==========================================================================
# Timeout: exists, configurable, local longer, persists, readable errors
# ==========================================================================


def test_timeout_persists_and_overrides_default():
    from logosforge.settings import get_manager
    get_manager().set("assistant_api_timeout", 240)
    assert assistant.get_configured_timeout("Anthropic") == 240


def test_timeout_zero_falls_back_to_provider_default():
    from logosforge.settings import get_manager
    get_manager().set("assistant_api_timeout", 0)
    local = assistant.default_timeout_for_provider("Ollama")
    cloud = assistant.default_timeout_for_provider("Anthropic")
    # Slow local models get at least as long a default as cloud.
    assert local >= cloud
    assert assistant.get_configured_timeout("Ollama") == local


def test_timeout_error_is_readable_and_hides_api_key(monkeypatch):
    from logosforge.providers import ProviderConfig

    def _boom(*a, **k):
        raise socket.timeout("timed out")

    monkeypatch.setattr(assistant, "_openai_completion", _boom)
    cfg = ProviderConfig(name="LM Studio", base_url="http://localhost:1234/v1",
                         api_key="sk-secret-should-not-leak", model="x")
    with pytest.raises(Exception) as ei:
        assistant.chat_completion(
            [{"role": "user", "content": "hi"}], provider=cfg, timeout=5,
            use_cache=False)
    msg = str(ei.value)
    assert "timed out" in msg.lower()
    assert "LM Studio" in msg
    assert "Assistant Settings" in msg
    assert "sk-secret-should-not-leak" not in msg   # key never leaks into errors


# ==========================================================================
# Assistant language — instruction, not hardcoded translation
# ==========================================================================


def test_language_instruction_injected_for_non_english():
    msgs = [{"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hola"}]
    out = assistant._inject_language_instruction(msgs, "es")
    sys = next(m for m in out if m["role"] == "system")
    assert "Spanish" in sys["content"]
    assert "project writing language" in sys["content"].lower()


def test_english_adds_no_language_instruction():
    msgs = [{"role": "system", "content": "You are helpful."}]
    out = assistant._inject_language_instruction(msgs, "en")
    assert out == msgs  # no-op for English


def test_explicit_language_override_is_used(monkeypatch):
    from logosforge.providers import ProviderConfig
    captured = {}

    def _capture(messages, provider, api_key, timeout):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(assistant, "_openai_completion", _capture)
    cfg = ProviderConfig(name="LM Studio", base_url="http://localhost:1234/v1")
    # User writes English, but explicitly overrides the response language.
    assistant.chat_completion(
        [{"role": "system", "content": "Be brief."},
         {"role": "user", "content": "Summarize this scene."}],
        provider=cfg, timeout=5, use_cache=False, response_language="es")
    sys = next(m for m in captured["messages"] if m["role"] == "system")
    assert "Spanish" in sys["content"]  # override preserved over detection


# ==========================================================================
# Context — capped, gated, Notes control present, no key leakage in exports
# ==========================================================================


def test_assistant_context_is_capped_not_a_huge_dump():
    from logosforge.assistant_context_policy import gather_injected_context
    from logosforge.db import Database
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    for i in range(40):
        db.create_psyke_entry(pid, f"Char{i}", "character", notes="x" * 200)
        db.create_scene(pid, f"S{i}", content="word " * 100, summary="s")
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=1)
    # A bounded, summarized context — never the whole project dumped in.
    assert len(ctx) < 20000


def test_notes_context_control_exists():
    import inspect
    from logosforge.ui.assistant_view import AssistantPanel
    src = inspect.getsource(AssistantPanel)
    assert "Include Notes" in src  # Notes checkbox present


def test_api_key_not_in_full_export(monkeypatch):
    from logosforge.settings import get_manager
    from logosforge.data_export import build_full_export, to_json
    from logosforge.db import Database
    get_manager().set("ai_api_key", "sk-secret-key-xyz")
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_scene(pid, "S", content="x")
    blob = to_json(build_full_export(db, pid))
    assert "sk-secret-key-xyz" not in blob
    assert "api_key" not in blob.lower()
