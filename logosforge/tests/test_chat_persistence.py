"""Tests for chat message persistence in the Database."""

from logosforge.db import Database
from logosforge.models import ChatMessage, ChatSummary


def _setup():
    db = Database()
    proj = db.create_project("ChatTest")
    return db, proj


def test_add_chat_message_persists():
    db, proj = _setup()
    msg = db.add_chat_message(proj.id, "user", "Hello there.")
    assert msg.id is not None
    assert msg.role == "user"
    assert msg.content == "Hello there."


def test_get_chat_messages_returns_in_order():
    db, proj = _setup()
    db.add_chat_message(proj.id, "user", "first")
    db.add_chat_message(proj.id, "assistant", "second")
    db.add_chat_message(proj.id, "user", "third")
    msgs = db.get_chat_messages(proj.id)
    assert [m.content for m in msgs] == ["first", "second", "third"]


def test_get_chat_messages_limit():
    db, proj = _setup()
    for i in range(20):
        db.add_chat_message(proj.id, "user", f"msg-{i}")
    msgs = db.get_chat_messages(proj.id, limit=5)
    assert len(msgs) == 5
    assert msgs[0].content == "msg-15"
    assert msgs[-1].content == "msg-19"


def test_messages_isolated_per_project():
    db = Database()
    proj_a = db.create_project("A")
    proj_b = db.create_project("B")
    db.add_chat_message(proj_a.id, "user", "in A")
    db.add_chat_message(proj_b.id, "user", "in B")
    assert [m.content for m in db.get_chat_messages(proj_a.id)] == ["in A"]
    assert [m.content for m in db.get_chat_messages(proj_b.id)] == ["in B"]


def test_clear_chat_messages():
    db, proj = _setup()
    db.add_chat_message(proj.id, "user", "x")
    db.add_chat_message(proj.id, "assistant", "y")
    db.update_chat_summary(proj.id, "summary", 1)
    db.clear_chat_messages(proj.id)
    assert db.get_chat_messages(proj.id) == []
    assert db.get_chat_summary(proj.id) is None


def test_chat_summary_round_trip():
    db, proj = _setup()
    rec = db.update_chat_summary(proj.id, "earlier...", 12)
    assert rec.summary == "earlier..."
    assert rec.last_summarized_message_id == 12
    fetched = db.get_chat_summary(proj.id)
    assert fetched is not None
    assert fetched.summary == "earlier..."


def test_chat_summary_update_overwrites():
    db, proj = _setup()
    db.update_chat_summary(proj.id, "first", 1)
    db.update_chat_summary(proj.id, "second", 5)
    fetched = db.get_chat_summary(proj.id)
    assert fetched.summary == "second"
    assert fetched.last_summarized_message_id == 5


def test_metadata_json_round_trip():
    db, proj = _setup()
    msg = db.add_chat_message(
        proj.id, "assistant", "I can do that.",
        metadata={"proposals": [{"action": "create_note", "args": {"text": "x"}}]},
    )
    fetched = db.get_chat_message_metadata(msg.id)
    assert fetched["proposals"][0]["action"] == "create_note"


def test_metadata_update():
    db, proj = _setup()
    msg = db.add_chat_message(proj.id, "assistant", "...")
    db.update_chat_message_metadata(msg.id, {"executed": {"foo": "Applied"}})
    fetched = db.get_chat_message_metadata(msg.id)
    assert fetched == {"executed": {"foo": "Applied"}}


def test_messages_after_id():
    db, proj = _setup()
    m1 = db.add_chat_message(proj.id, "user", "1")
    m2 = db.add_chat_message(proj.id, "user", "2")
    m3 = db.add_chat_message(proj.id, "user", "3")
    later = db.get_chat_messages_after(proj.id, m1.id)
    assert [m.content for m in later] == ["2", "3"]
