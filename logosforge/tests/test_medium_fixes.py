"""Regression tests for the medium QA fixes:
  MED-4 slugline-aware continuity (a slugline TITLE is the production heading),
  MED-6 screenplay/manuscript export via the API,
  MED-7 quantum generative flag reachable over the API.
See memory ``logosforge-pro-writer-qa``.
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from logosforge.api.app import create_api  # noqa: E402
from logosforge.api.config import ApiConfig  # noqa: E402
from logosforge.db import Database  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)


class _Scene:
    """Minimal scene stand-in for the heading detector."""
    def __init__(self, **k):
        for f in ("title", "content", "slugline", "interior_exterior", "time_of_day"):
            setattr(self, f, "")
        self.id = 1
        self.__dict__.update(k)


# -- MED-4 -------------------------------------------------------------------

def test_slugline_title_satisfies_production_heading():
    from logosforge.continuity.issue_detector import _heading_signals
    # A proper slugline TITLE supplies all three signals -> not "missing".
    assert _heading_signals(_Scene(title="INT. SONAR SHACK — NIGHT (DAY 61)")) == (True, True, True)
    # A bare title supplies none -> still flagged (true positive preserved).
    assert _heading_signals(_Scene(title="The Sonar Shack")) == (False, False, False)
    # A plain title but a slugline first line of content also satisfies it.
    assert _heading_signals(_Scene(title="Scene 3", content="EXT. BEACH - DAY\n\nWaves.")) == (True, True, True)


# -- MED-6 / MED-7 (need an API client) --------------------------------------

def _screenplay_client():
    db = Database()
    project = db.create_project("Test Script", narrative_engine="screenplay")
    db.create_scene(project.id, "INT. ROOM — NIGHT", content="A small room.\n\nMARA\nHello?")
    client = TestClient(create_api(db=db, config=ApiConfig(mode="desktop")))
    return client, project.id


def test_export_screenplay_fountain_via_api():
    client, pid = _screenplay_client()
    r = client.post(f"/api/projects/{pid}/export",
                    json={"export_type": "screenplay_fountain", "format": "text"})
    assert r.status_code == 200
    body = r.json()
    assert body["format"] == "fountain"
    assert body["content"].strip()  # a real rendered script came back


def test_export_manuscript_via_api():
    client, pid = _screenplay_client()
    r = client.post(f"/api/projects/{pid}/export", json={"export_type": "manuscript"})
    assert r.status_code == 200
    assert r.json()["content"].strip()


def test_export_screenplay_fdx_via_api():
    """FDX (Final Draft XML) is returned as text (XML), gated through the experimental
    acknowledgement server-side."""
    client, pid = _screenplay_client()
    r = client.post(f"/api/projects/{pid}/export", json={"export_type": "screenplay_fdx"})
    assert r.status_code == 200
    body = r.json()
    assert body["format"] == "fdx" and body["filename"].endswith(".fdx")
    assert "<FinalDraft" in (body["content"] or "")  # real FDX XML


def test_export_binary_pdf_docx_via_api():
    """PDF/DOCX come back as base64 file bytes (decode → valid magic numbers).
    Skips cleanly if the optional render deps aren't installed."""
    import base64
    pytest.importorskip("reportlab")
    pytest.importorskip("docx")
    client, pid = _screenplay_client()

    r = client.post(f"/api/projects/{pid}/export", json={"export_type": "screenplay_pdf"})
    assert r.status_code == 200
    body = r.json()
    assert body["mime_type"] == "application/pdf" and body["filename"].endswith(".pdf")
    assert base64.b64decode(body["content_base64"])[:4] == b"%PDF"

    r = client.post(f"/api/projects/{pid}/export", json={"export_type": "screenplay_docx"})
    assert r.status_code == 200
    assert base64.b64decode(r.json()["content_base64"])[:2] == b"PK"  # docx = zip


def test_quantum_generative_flag_accepted():
    client, pid = _screenplay_client()
    # generative=False stays on the deterministic classical path (no LLM needed).
    r = client.post(f"/api/projects/{pid}/quantum/outline",
                    json={"premise": "A test premise.", "generative": False})
    assert r.status_code == 200
    assert r.json()["kind"] == "classical_outline"
    # The flag is accepted (generative=True would hit the LLM; we only assert it's a valid field).
    r2 = client.post(f"/api/projects/{pid}/quantum/branches",
                     json={"situation": "A choice.", "generative": False})
    assert r2.status_code == 200
