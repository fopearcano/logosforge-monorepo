"""Tests for recent_projects module — add, remove, clean."""

import json
from pathlib import Path

from logosforge import recent_projects


def _setup(tmp_path, monkeypatch):
    cfg = tmp_path / ".logosforge"
    monkeypatch.setattr(recent_projects, "CONFIG_DIR", cfg)
    monkeypatch.setattr(recent_projects, "RECENT_FILE", cfg / "recent_projects.json")
    return cfg


def test_load_empty(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert recent_projects.load() == []


def test_add_and_load(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    recent_projects.add("/foo/bar.json")
    assert recent_projects.load() == ["/foo/bar.json"]


def test_add_moves_to_front(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    recent_projects.add("/a.json")
    recent_projects.add("/b.json")
    recent_projects.add("/a.json")
    assert recent_projects.load() == ["/a.json", "/b.json"]


def test_remove(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    recent_projects.add("/a.json")
    recent_projects.add("/b.json")
    recent_projects.remove("/a.json")
    assert recent_projects.load() == ["/b.json"]


def test_remove_nonexistent(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    recent_projects.add("/a.json")
    recent_projects.remove("/missing.json")
    assert recent_projects.load() == ["/a.json"]


def test_clean_drops_missing(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    real = tmp_path / "exists.json"
    real.write_text("{}")
    recent_projects.add("/gone.json")
    recent_projects.add(str(real))
    result = recent_projects.clean()
    assert result == [str(real)]
    assert recent_projects.load() == [str(real)]


def test_clean_empty(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert recent_projects.clean() == []


def test_clean_all_missing(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    recent_projects.add("/gone1.json")
    recent_projects.add("/gone2.json")
    result = recent_projects.clean()
    assert result == []
    assert recent_projects.load() == []


def test_max_recent(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    for i in range(15):
        recent_projects.add(f"/{i}.json")
    assert len(recent_projects.load()) == recent_projects.MAX_RECENT
