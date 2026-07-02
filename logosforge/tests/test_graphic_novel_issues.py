"""Tests for the GraphicNovelIssue domain model + services."""

import sqlite3

import pytest
from sqlalchemy import text

from logosforge.db import Database
from logosforge.models import GN_ISSUE_STATUSES, GraphicNovelIssue


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _gn(db):
    return db.create_project(
        "GN", narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )


# =========================================================================
# 1. Model
# =========================================================================

def test_issue_statuses_constant():
    for s in ("planned", "drafting", "complete", "published"):
        assert s in GN_ISSUE_STATUSES


def test_issue_defaults_optional():
    db = Database()
    p = _gn(db)
    issue = db.create_gn_issue(p.id)
    assert isinstance(issue, GraphicNovelIssue)
    assert issue.issue_number == 1   # auto-numbered
    assert issue.title == ""
    assert issue.status == ""
    assert issue.project_id == p.id


# =========================================================================
# 2. Create / get / update
# =========================================================================

def test_create_and_get_issues():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="Origins")
    b = db.create_gn_issue(p.id, title="Fallout")
    issues = db.get_gn_issues(p.id)
    assert [i.id for i in issues] == [a.id, b.id]
    assert [i.issue_number for i in issues] == [1, 2]
    assert [i.title for i in issues] == ["Origins", "Fallout"]


def test_update_issue():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="Origins")
    db.update_gn_issue(a.id, title="Origins, Pt. 1", status="drafting",
                       summary="the beginning", notes="hold the splash")
    got = db.get_gn_issue_by_id(a.id)
    assert got.title == "Origins, Pt. 1"
    assert got.status == "drafting"
    assert got.summary == "the beginning"
    assert got.notes == "hold the splash"


# =========================================================================
# 3. Reorder
# =========================================================================

def test_reorder_issues():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="A")
    b = db.create_gn_issue(p.id, title="B")
    c = db.create_gn_issue(p.id, title="C")
    db.reorder_gn_issues(p.id, [c.id, a.id, b.id])
    issues = db.get_gn_issues(p.id)
    assert [i.id for i in issues] == [c.id, a.id, b.id]
    assert [i.issue_number for i in issues] == [1, 2, 3]


def test_reorder_ignores_foreign_issues():
    db = Database()
    p1 = _gn(db)
    p2 = _gn(db)
    a = db.create_gn_issue(p1.id, title="A")
    foreign = db.create_gn_issue(p2.id, title="X")
    db.reorder_gn_issues(p1.id, [foreign.id, a.id])  # foreign ignored
    assert db.get_gn_issue_by_id(foreign.id).project_id == p2.id
    assert db.get_gn_issue_by_id(a.id).issue_number == 2


# =========================================================================
# 4. Delete — safe by default, never loses pages
# =========================================================================

def test_delete_empty_issue():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="Empty")
    assert db.delete_gn_issue(a.id) is True
    assert db.get_gn_issue_by_id(a.id) is None


def test_delete_nonempty_issue_blocked_by_default():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="Has pages")
    page = db.create_gn_page(p.id, issue_id=a.id)
    # Refuses to delete; nothing is lost.
    assert db.delete_gn_issue(a.id) is False
    assert db.get_gn_issue_by_id(a.id) is not None
    assert db.get_gn_page_by_id(page.id).issue_id == a.id


def test_delete_nonempty_issue_force_detaches_pages():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="Has pages")
    page = db.create_gn_page(p.id, issue_id=a.id)
    assert db.delete_gn_issue(a.id, force=True) is True
    assert db.get_gn_issue_by_id(a.id) is None
    # Page survives, just unassigned — never silently deleted.
    survived = db.get_gn_page_by_id(page.id)
    assert survived is not None
    assert survived.issue_id is None


def test_delete_missing_issue_returns_false():
    db = Database()
    p = _gn(db)
    assert db.delete_gn_issue(999) is False


# =========================================================================
# 5. Page ↔ Issue linkage (optional, None = unassigned)
# =========================================================================

def test_pages_default_to_unassigned():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    assert page.issue_id is None


def test_assign_and_unassign_page():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="One")
    page = db.create_gn_page(p.id)
    db.assign_gn_page_to_issue(page.id, a.id)
    assert db.get_gn_page_by_id(page.id).issue_id == a.id
    assert [pg.id for pg in db.get_gn_pages_for_issue(a.id)] == [page.id]
    db.assign_gn_page_to_issue(page.id, None)
    assert db.get_gn_page_by_id(page.id).issue_id is None
    assert db.get_gn_pages_for_issue(a.id) == []


def test_create_page_with_issue():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id)
    page = db.create_gn_page(p.id, issue_id=a.id)
    assert page.issue_id == a.id


# =========================================================================
# 6. Project isolation
# =========================================================================

def test_issues_scoped_to_project():
    db = Database()
    p1 = _gn(db)
    p2 = _gn(db)
    db.create_gn_issue(p1.id, title="P1")
    db.create_gn_issue(p2.id, title="P2")
    assert [i.title for i in db.get_gn_issues(p1.id)] == ["P1"]
    assert [i.title for i in db.get_gn_issues(p2.id)] == ["P2"]


# =========================================================================
# 7. Persistence + backward compatibility
# =========================================================================

def test_issue_persists_and_reloads(tmp_path):
    path = str(tmp_path / "gn.db")
    db = Database(path)
    p = _gn(db)
    issue = db.create_gn_issue(p.id, title="Origins", status="published")
    page = db.create_gn_page(p.id, issue_id=issue.id)
    pid, iid, page_id = p.id, issue.id, page.id

    db2 = Database(path)
    issues = db2.get_gn_issues(pid)
    assert len(issues) == 1
    assert issues[0].title == "Origins"
    assert issues[0].status == "published"
    assert db2.get_gn_page_by_id(page_id).issue_id == iid


def test_existing_page_panel_project_loads(tmp_path):
    """A project created before Issues existed (page row lacks issue_id)
    still loads, keeps its pages/panels, and pages read as unassigned."""
    path = str(tmp_path / "legacy.db")
    db = Database(path)
    p = _gn(db)
    page = db.create_gn_page(p.id, summary="legacy")
    db.create_gn_panel(page.id, description="legacy panel")
    pid, page_id = p.id, page.id
    db._engine.dispose()

    # Simulate an old schema: rebuild graphicnovelpage without issue_id.
    con = sqlite3.connect(path)
    cur = con.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(graphicnovelpage)")]
    keep = ",".join(c for c in cols if c != "issue_id")
    cur.execute("ALTER TABLE graphicnovelpage RENAME TO _old_gp")
    cur.execute(f"CREATE TABLE graphicnovelpage AS SELECT {keep} FROM _old_gp")
    cur.execute("DROP TABLE _old_gp")
    con.commit()
    after = {r[1] for r in cur.execute("PRAGMA table_info(graphicnovelpage)")}
    assert "issue_id" not in after
    con.close()

    # Reopen with current code → _migrate() adds the column back.
    db2 = Database(path)
    with db2._engine.connect() as conn:
        cols2 = {
            r[1] for r in conn.execute(
                text("PRAGMA table_info(graphicnovelpage)")
            ).fetchall()
        }
    assert "issue_id" in cols2
    pages = db2.get_gn_pages(pid)
    assert len(pages) == 1
    assert pages[0].summary == "legacy"
    assert pages[0].issue_id is None   # legacy page is unassigned
    assert len(db2.get_gn_panels_for_page(page_id)) == 1
    # New Issue features work on the migrated DB.
    issue = db2.create_gn_issue(pid, title="New")
    db2.assign_gn_page_to_issue(page_id, issue.id)
    assert db2.get_gn_page_by_id(page_id).issue_id == issue.id


def test_old_project_without_gn_data_safe(tmp_path):
    path = str(tmp_path / "novel.db")
    db = Database(path)
    p = db.create_project("Novel")
    db.create_scene(p.id, "Chapter 1", content="prose")
    db2 = Database(path)
    assert db2.get_gn_issues(p.id) == []
    assert db2.get_gn_pages(p.id) == []
