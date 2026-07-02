"""Tests for Assistant model/API timeout handling."""

from __future__ import annotations

import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest


class TestDefaultTimeoutForProvider:
    def test_local_provider_lm_studio(self):
        from logosforge.assistant import default_timeout_for_provider
        assert default_timeout_for_provider("LM Studio") == 300

    def test_local_provider_ollama(self):
        from logosforge.assistant import default_timeout_for_provider
        assert default_timeout_for_provider("Ollama") == 300

    def test_cloud_provider_openai(self):
        from logosforge.assistant import default_timeout_for_provider
        assert default_timeout_for_provider("OpenAI") == 120

    def test_cloud_provider_anthropic(self):
        from logosforge.assistant import default_timeout_for_provider
        assert default_timeout_for_provider("Anthropic") == 120

    def test_cloud_provider_openrouter(self):
        from logosforge.assistant import default_timeout_for_provider
        assert default_timeout_for_provider("OpenRouter") == 120

    def test_unknown_provider_gets_cloud_default(self):
        from logosforge.assistant import default_timeout_for_provider
        assert default_timeout_for_provider("SomeNew") == 120


class TestGetConfiguredTimeout:
    def test_auto_zero_uses_provider_default_local(self):
        from logosforge.assistant import get_configured_timeout
        with patch("logosforge.settings.get_manager") as mock_mgr:
            mock_mgr.return_value.get.return_value = 0
            assert get_configured_timeout("LM Studio") == 300

    def test_auto_zero_uses_provider_default_cloud(self):
        from logosforge.assistant import get_configured_timeout
        with patch("logosforge.settings.get_manager") as mock_mgr:
            mock_mgr.return_value.get.return_value = 0
            assert get_configured_timeout("OpenAI") == 120

    def test_explicit_value_overrides_default(self):
        from logosforge.assistant import get_configured_timeout
        with patch("logosforge.settings.get_manager") as mock_mgr:
            mock_mgr.return_value.get.return_value = 45
            assert get_configured_timeout("LM Studio") == 45

    def test_none_uses_provider_default(self):
        from logosforge.assistant import get_configured_timeout
        with patch("logosforge.settings.get_manager") as mock_mgr:
            mock_mgr.return_value.get.return_value = None
            assert get_configured_timeout("Anthropic") == 120

    def test_negative_uses_provider_default(self):
        from logosforge.assistant import get_configured_timeout
        with patch("logosforge.settings.get_manager") as mock_mgr:
            mock_mgr.return_value.get.return_value = -10
            assert get_configured_timeout("Ollama") == 300

    def test_no_provider_name_defaults_to_cloud(self):
        from logosforge.assistant import get_configured_timeout
        with patch("logosforge.settings.get_manager") as mock_mgr:
            mock_mgr.return_value.get.return_value = 0
            assert get_configured_timeout("") == 120


class TestIsTransient:
    def test_socket_timeout_is_transient(self):
        from logosforge.assistant import _is_transient
        assert _is_transient(socket.timeout("timed out")) is True

    def test_url_error_with_socket_timeout_is_transient(self):
        from logosforge.assistant import _is_transient
        err = urllib.error.URLError(socket.timeout("timed out"))
        assert _is_transient(err) is True

    def test_url_error_with_os_error_is_transient(self):
        from logosforge.assistant import _is_transient
        err = urllib.error.URLError(OSError("connection reset"))
        assert _is_transient(err) is True

    def test_connection_error_is_transient(self):
        from logosforge.assistant import _is_transient
        assert _is_transient(ConnectionError("refused")) is True

    def test_os_error_is_transient(self):
        from logosforge.assistant import _is_transient
        assert _is_transient(OSError("broken pipe")) is True

    def test_http_error_is_not_transient(self):
        from logosforge.assistant import _is_transient
        from http.client import HTTPResponse
        from unittest.mock import MagicMock
        err = urllib.error.HTTPError("http://x", 500, "error", {}, MagicMock())
        assert _is_transient(err) is False

    def test_runtime_error_is_not_transient(self):
        from logosforge.assistant import _is_transient
        assert _is_transient(RuntimeError("bad data")) is False

    def test_value_error_is_not_transient(self):
        from logosforge.assistant import _is_transient
        assert _is_transient(ValueError("bad")) is False


class TestChatCompletionRetry:
    @patch("logosforge.assistant.get_configured_timeout", return_value=120)
    @patch("logosforge.assistant._detect_response_language", return_value="en")
    @patch("logosforge.assistant._openai_completion")
    def test_succeeds_on_first_try(self, mock_comp, _mock_lang, _mock_timeout):
        from logosforge.assistant import chat_completion
        from logosforge.providers import ProviderConfig
        mock_comp.return_value = "Hello"
        provider = ProviderConfig(name="LM Studio", base_url="http://localhost:1234/v1")
        result, cached = chat_completion(
            [{"role": "user", "content": "hi"}],
            provider=provider, use_cache=False,
        )
        assert result == "Hello"
        assert cached is False
        assert mock_comp.call_count == 1

    @patch("logosforge.assistant.time.sleep")
    @patch("logosforge.assistant.get_configured_timeout", return_value=120)
    @patch("logosforge.assistant._detect_response_language", return_value="en")
    @patch("logosforge.assistant._openai_completion")
    def test_retries_once_on_transient_error(self, mock_comp, _mock_lang, _mock_timeout, mock_sleep):
        from logosforge.assistant import chat_completion
        from logosforge.providers import ProviderConfig
        mock_comp.side_effect = [
            urllib.error.URLError(socket.timeout("timed out")),
            "Recovered",
        ]
        provider = ProviderConfig(name="OpenAI", base_url="https://api.openai.com/v1")
        result, cached = chat_completion(
            [{"role": "user", "content": "hi"}],
            provider=provider, use_cache=False,
        )
        assert result == "Recovered"
        assert mock_comp.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @patch("logosforge.assistant.time.sleep")
    @patch("logosforge.assistant.get_configured_timeout", return_value=60)
    @patch("logosforge.assistant._detect_response_language", return_value="en")
    @patch("logosforge.assistant._openai_completion")
    def test_raises_after_retry_exhausted(self, mock_comp, _mock_lang, _mock_timeout, mock_sleep):
        from logosforge.assistant import chat_completion
        from logosforge.providers import ProviderConfig
        mock_comp.side_effect = urllib.error.URLError(socket.timeout("timed out"))
        provider = ProviderConfig(name="LM Studio", base_url="http://localhost:1234/v1")
        with pytest.raises(ConnectionError, match="timed out after 60s"):
            chat_completion(
                [{"role": "user", "content": "hi"}],
                provider=provider, use_cache=False,
            )
        assert mock_comp.call_count == 2

    @patch("logosforge.assistant.get_configured_timeout", return_value=120)
    @patch("logosforge.assistant._detect_response_language", return_value="en")
    @patch("logosforge.assistant._openai_completion")
    def test_no_retry_on_http_error(self, mock_comp, _mock_lang, _mock_timeout):
        from logosforge.assistant import chat_completion
        from logosforge.providers import ProviderConfig
        mock_comp.side_effect = urllib.error.HTTPError(
            "http://x", 429, "rate limit", {}, MagicMock(),
        )
        provider = ProviderConfig(name="OpenAI", base_url="https://api.openai.com/v1")
        with pytest.raises(RuntimeError, match="HTTP 429"):
            chat_completion(
                [{"role": "user", "content": "hi"}],
                provider=provider, use_cache=False,
            )
        assert mock_comp.call_count == 1

    @patch("logosforge.assistant.get_configured_timeout", return_value=120)
    @patch("logosforge.assistant._detect_response_language", return_value="en")
    @patch("logosforge.assistant._openai_completion")
    def test_no_retry_on_parse_error(self, mock_comp, _mock_lang, _mock_timeout):
        import json
        from logosforge.assistant import chat_completion
        from logosforge.providers import ProviderConfig
        mock_comp.side_effect = json.JSONDecodeError("bad", "", 0)
        provider = ProviderConfig(name="OpenAI", base_url="https://api.openai.com/v1")
        with pytest.raises(RuntimeError, match="Unexpected response"):
            chat_completion(
                [{"role": "user", "content": "hi"}],
                provider=provider, use_cache=False,
            )
        assert mock_comp.call_count == 1


class TestTimeoutErrorMessages:
    @patch("logosforge.assistant.time.sleep")
    @patch("logosforge.assistant.get_configured_timeout", return_value=300)
    @patch("logosforge.assistant._detect_response_language", return_value="en")
    @patch("logosforge.assistant._openai_completion")
    def test_timeout_error_includes_provider_name(self, mock_comp, _mock_lang, _mock_timeout, _mock_sleep):
        from logosforge.assistant import chat_completion
        from logosforge.providers import ProviderConfig
        mock_comp.side_effect = urllib.error.URLError(socket.timeout("timed out"))
        provider = ProviderConfig(name="LM Studio", base_url="http://localhost:1234/v1")
        with pytest.raises(ConnectionError) as exc_info:
            chat_completion(
                [{"role": "user", "content": "hi"}],
                provider=provider, use_cache=False,
            )
        msg = str(exc_info.value)
        assert "LM Studio" in msg
        assert "300s" in msg
        assert "Assistant Settings" in msg

    @patch("logosforge.assistant.time.sleep")
    @patch("logosforge.assistant.get_configured_timeout", return_value=120)
    @patch("logosforge.assistant._detect_response_language", return_value="en")
    @patch("logosforge.assistant._openai_completion")
    def test_connection_error_includes_url(self, mock_comp, _mock_lang, _mock_timeout, _mock_sleep):
        from logosforge.assistant import chat_completion
        from logosforge.providers import ProviderConfig
        mock_comp.side_effect = urllib.error.URLError("connection refused")
        provider = ProviderConfig(name="Anthropic", base_url="https://api.anthropic.com")
        with pytest.raises(ConnectionError) as exc_info:
            chat_completion(
                [{"role": "user", "content": "hi"}],
                provider=provider, use_cache=False,
            )
        msg = str(exc_info.value)
        assert "Anthropic" in msg
        assert "api.anthropic.com" in msg
        assert "120s" in msg


class TestChatCompletionTimeoutParam:
    @patch("logosforge.assistant.get_configured_timeout", return_value=120)
    @patch("logosforge.assistant._detect_response_language", return_value="en")
    @patch("logosforge.assistant._openai_completion")
    def test_explicit_timeout_used(self, mock_comp, _mock_lang, _mock_timeout):
        from logosforge.assistant import chat_completion
        from logosforge.providers import ProviderConfig
        mock_comp.return_value = "ok"
        provider = ProviderConfig(name="LM Studio", base_url="http://localhost:1234/v1")
        chat_completion(
            [{"role": "user", "content": "hi"}],
            provider=provider, timeout=45, use_cache=False,
        )
        _, kwargs = mock_comp.call_args
        assert kwargs.get("timeout") == 45 or mock_comp.call_args[0][3] == 45

    @patch("logosforge.assistant.get_configured_timeout", return_value=300)
    @patch("logosforge.assistant._detect_response_language", return_value="en")
    @patch("logosforge.assistant._openai_completion")
    def test_zero_timeout_uses_configured(self, mock_comp, _mock_lang, _mock_timeout):
        from logosforge.assistant import chat_completion
        from logosforge.providers import ProviderConfig
        mock_comp.return_value = "ok"
        provider = ProviderConfig(name="Ollama", base_url="http://localhost:11434/v1")
        chat_completion(
            [{"role": "user", "content": "hi"}],
            provider=provider, timeout=0, use_cache=False,
        )
        call_args = mock_comp.call_args[0]
        assert call_args[3] == 300


class TestSettingsDefault:
    def test_default_timeout_in_settings(self):
        from logosforge.settings import DEFAULTS
        assert "assistant_api_timeout" in DEFAULTS
        assert DEFAULTS["assistant_api_timeout"] == 0


class TestTestConnectionTimeout:
    @patch("logosforge.assistant.chat_completion")
    def test_test_connection_uses_short_timeout(self, mock_cc):
        from logosforge.assistant import test_connection
        from logosforge.providers import ProviderConfig
        mock_cc.return_value = ("OK", False)
        provider = ProviderConfig(name="LM Studio", base_url="http://localhost:1234/v1")
        ok, msg = test_connection(provider)
        assert ok is True
        call_kwargs = mock_cc.call_args[1]
        assert call_kwargs["timeout"] == 15


class TestAssistantWorkerTimeout:
    def test_worker_stores_timeout(self):
        from logosforge.providers import ProviderConfig
        from logosforge.ui.assistant_view import _AssistantWorker
        provider = ProviderConfig(name="LM Studio", base_url="http://localhost:1234/v1")
        worker = _AssistantWorker(
            [{"role": "user", "content": "hi"}], provider, timeout=200,
        )
        assert worker._timeout == 200

    def test_worker_default_timeout_zero(self):
        from logosforge.providers import ProviderConfig
        from logosforge.ui.assistant_view import _AssistantWorker
        provider = ProviderConfig(name="LM Studio", base_url="http://localhost:1234/v1")
        worker = _AssistantWorker(
            [{"role": "user", "content": "hi"}], provider,
        )
        assert worker._timeout == 0
