"""The writing-modes catalog route exposes the core's five modes over HTTP."""

from fastapi.testclient import TestClient

from logosforge.api import create_api
from logosforge.db import Database


def _client() -> TestClient:
    return TestClient(create_api(db=Database()))  # in-memory DB


def test_writing_modes_lists_the_five_modes_in_order():
    with _client() as c:
        r = c.get("/api/writing-modes")
        assert r.status_code == 200
        data = r.json()
        assert [m["id"] for m in data["modes"]] == [
            "novel", "screenplay", "graphic_novel", "stage_script", "series",
        ]
        assert data["default_mode"] == "novel"


def test_writing_modes_shape_matches_the_frontend_contract():
    with _client() as c:
        modes = {m["id"]: m for m in c.get("/api/writing-modes").json()["modes"]}
        novel = modes["novel"]
        assert novel["label"] == "Novel"
        assert novel["structural_units"] == ["Acts", "Chapters", "Scenes"]
        assert novel["default_writing_format"] == "novel"
        assert "prose voice" in novel["medium_constraints"]
        # Series suggests the screenplay format.
        assert modes["series"]["default_writing_format"] == "screenplay"
        assert modes["graphic_novel"]["structural_units"] == [
            "Chapters", "Pages", "Panels",
        ]
