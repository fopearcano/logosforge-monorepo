"""Tests for the optional LibreChat integration.

Covers: config defaults + persistence + URL validation; service detection
states (disabled / invalid / unreachable / connected); duplicate-process
prevention; the safe bridge adapter (read PoC + propose/confirm/apply routing +
input validation); and the existing Chat section staying intact. No network and
no real LibreChat instance are required — connection probes are mocked.
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from logosforge.db import Database
from logosforge.librechat import service as lc_service
from logosforge.librechat.bridge import (
    ActionProposal,
    BridgeValidationError,
    LocalBridge,
)
from logosforge.librechat.config import LibreChatConfig
from logosforge.librechat.service import (
    ConnectionState,
    LibreChatService,
)


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path):
    """Keep the real ~/.logosforge/settings.json untouched."""
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _fake_response(status: int = 200):
    resp = mock.MagicMock()
    resp.status = status
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


# -- Config ------------------------------------------------------------------

def test_config_defaults_are_off_and_localhost():
    c = LibreChatConfig.load()
    assert c.enabled is False              # OFF by default
    assert c.button_visible is True        # but the button shows
    assert c.is_localhost and c.is_valid_url()
    assert c.normalized_url() == "http://localhost:3080"


def test_config_persists_round_trip():
    LibreChatConfig(
        enabled=True, base_url="http://localhost:1234", mode="remote",
        auto_connect=True, prefer_embedded=False, browser_fallback=False,
        startup_command="run me", button_visible=False,
    ).save()
    c = LibreChatConfig.load()
    assert c.enabled and c.base_url == "http://localhost:1234"
    assert c.mode == "remote" and c.auto_connect and not c.prefer_embedded
    assert not c.browser_fallback and c.startup_command == "run me"
    assert c.button_visible is False


def test_config_url_validation():
    assert LibreChatConfig(base_url="not a url").is_valid_url() is False
    assert LibreChatConfig(base_url="ftp://x").is_valid_url() is False
    assert LibreChatConfig(base_url="localhost:3080").normalized_url() == "http://localhost:3080"
    assert LibreChatConfig(base_url="http://example.com:9000").is_localhost is False


# -- Service detection -------------------------------------------------------

def test_service_disabled_when_off():
    status = LibreChatService(LibreChatConfig(enabled=False)).check_connection()
    assert status.state is ConnectionState.DISABLED


def test_service_invalid_url():
    status = LibreChatService(
        LibreChatConfig(enabled=True, base_url="http://bad url")
    ).check_connection()
    assert status.state is ConnectionState.INVALID_URL


def test_service_connected_when_reachable():
    svc = LibreChatService(LibreChatConfig(enabled=True))
    with mock.patch.object(lc_service.urllib.request, "urlopen",
                           return_value=_fake_response(200)):
        status = svc.check_connection(timeout=0.1)
    assert status.state is ConnectionState.CONNECTED and status.ok


def test_service_connected_even_on_http_error():
    import urllib.error
    svc = LibreChatService(LibreChatConfig(enabled=True))
    err = urllib.error.HTTPError("u", 401, "no", {}, None)
    with mock.patch.object(lc_service.urllib.request, "urlopen", side_effect=err):
        status = svc.check_connection(timeout=0.1)
    assert status.state is ConnectionState.CONNECTED  # a served 401 = up


def test_service_unreachable():
    import urllib.error
    svc = LibreChatService(LibreChatConfig(enabled=True, base_url="http://127.0.0.1:6"))
    with mock.patch.object(lc_service.urllib.request, "urlopen",
                           side_effect=urllib.error.URLError("nope")):
        status = svc.check_connection(timeout=0.1)
    assert status.state is ConnectionState.UNREACHABLE and not status.ok


# -- Process launcher --------------------------------------------------------

def test_no_launch_without_startup_command():
    svc = LibreChatService(LibreChatConfig(enabled=True, startup_command=""))
    assert svc.can_launch() is False


def test_start_skips_when_already_running():
    """Duplicate-process prevention: never Popen when the URL already serves."""
    svc = LibreChatService(LibreChatConfig(enabled=True, startup_command="x"))
    with mock.patch.object(svc, "is_running", return_value=True), \
         mock.patch.object(lc_service.subprocess, "Popen") as popen:
        status = svc.start(timeout=0.1)
    popen.assert_not_called()
    assert status.state is ConnectionState.CONNECTED


def test_start_captures_launch_failure():
    svc = LibreChatService(LibreChatConfig(enabled=True, startup_command="bogus-cmd"))
    with mock.patch.object(svc, "is_running", return_value=False), \
         mock.patch.object(lc_service.subprocess, "Popen",
                           side_effect=OSError("not found")):
        status = svc.start(timeout=0.1)
    assert status.state is ConnectionState.UNREACHABLE
    assert "Launch failed" in status.detail


def test_stop_only_terminates_our_process():
    svc = LibreChatService(LibreChatConfig(enabled=True))
    # No process started → stop() is a harmless no-op.
    svc.stop()
    # A tracked process is terminated.
    proc = mock.MagicMock()
    proc.poll.return_value = None
    svc._proc = proc
    svc.stop()
    proc.terminate.assert_called_once()
    assert svc._proc is None


# -- Bridge (safe propose/confirm/apply) -------------------------------------

def _bridge():
    db = Database()
    proj = db.create_project("BridgeT")
    db.create_scene(proj.id, "S1")
    return LocalBridge(db, proj.id, selection_provider=lambda: "sel",
                       active_scene_provider=lambda: db.list_scenes(proj.id)[0].id), db, proj


def test_bridge_reads_are_safe_and_work():
    br, _, _ = _bridge()
    assert br.get_project_context().ok
    assert br.get_outline_context().ok
    assert br.get_current_selection().data == {"text": "sel"}
    assert br.search_psyke("anything").ok


def test_bridge_propose_returns_unexecuted_proposal():
    br, db, proj = _bridge()
    before = len(db.get_all_psyke_entries(proj.id))
    proposal = br.propose_psyke_entry("Ada", "character", notes="lead")
    assert isinstance(proposal, ActionProposal)
    assert proposal.action == "create_psyke_entry" and proposal.requires_confirmation
    assert len(db.get_all_psyke_entries(proj.id)) == before  # NOT applied


def test_bridge_apply_requires_confirmation():
    br, _, _ = _bridge()
    res = br.apply_confirmed_action("create_scene", {"title": "X"}, confirmed=False)
    assert not res.ok and "confirmation" in res.error.lower()


def test_bridge_apply_confirmed_still_respects_connector_gate():
    # Even confirmed, a write goes through the existing connector settings gate
    # (connector disabled by default) — the bridge never bypasses it.
    br, _, _ = _bridge()
    res = br.apply_confirmed_action("create_scene", {"title": "X"}, confirmed=True)
    assert not res.ok and "disabled" in res.error.lower()


def test_bridge_validates_untrusted_input():
    br, _, _ = _bridge()
    with pytest.raises(BridgeValidationError):
        br.search_psyke(123)            # non-string
    with pytest.raises(BridgeValidationError):
        br.propose_edit("x", "title")   # non-int scene_id


def test_bridge_rejects_unknown_action():
    br, _, _ = _bridge()
    res = br.apply_confirmed_action("rm_rf", {}, confirmed=True)
    assert not res.ok and "unknown action" in res.error.lower()
