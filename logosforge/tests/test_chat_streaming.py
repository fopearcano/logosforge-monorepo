"""Chat streaming: OpenAI SSE parsing + worker fallback (no network, no LLM)."""

import io
from unittest import mock

from logosforge import assistant
from logosforge.providers import ProviderConfig
from logosforge.ui.chat_view import _ChatWorker


class _FakeResp(io.BytesIO):
    """A urlopen() result: context manager + line-iterable byte stream."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _provider():
    return ProviderConfig(name="LM Studio", base_url="http://x/v1", model="m")


def _stream(sse: bytes):
    chunks: list[str] = []
    with mock.patch.object(assistant.urllib.request, "urlopen",
                           return_value=_FakeResp(sse)):
        text = assistant._openai_completion_stream(
            [{"role": "user", "content": "hi"}], _provider(), "", 10, chunks.append,
        )
    return chunks, text


# -- SSE parsing -------------------------------------------------------------

def test_stream_parses_deltas_in_order():
    sse = (
        b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        b'data: [DONE]\n\n'
    )
    chunks, text = _stream(sse)
    assert chunks == ["Hel", "lo", " world"]
    assert text == "Hello world"


def test_stream_ignores_junk_and_bad_json():
    sse = (
        b': keep-alive comment\n\n'
        b'\n'
        b'data: {bad json}\n\n'
        b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
        b'data: {"choices":[{"delta":{}}]}\n\n'   # no content key
        b'data: [DONE]\n\n'
    )
    chunks, text = _stream(sse)
    assert chunks == ["ok"]
    assert text == "ok"


def test_stream_stops_on_done_sentinel():
    sse = (
        b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
        b'data: [DONE]\n\n'
        b'data: {"choices":[{"delta":{"content":"SHOULD NOT APPEAR"}}]}\n\n'
    )
    chunks, text = _stream(sse)
    assert text == "a"


# -- chat_completion_stream QA short-circuit ---------------------------------

def test_chat_completion_stream_qa_mode_emits_once(monkeypatch):
    import logosforge.qa_mode as qa_mode
    monkeypatch.setattr(qa_mode, "is_qa_mode", lambda: True)
    monkeypatch.setattr(qa_mode, "fake_completion", lambda msgs: "FAKE REPLY")
    seen: list[str] = []
    text, cached = assistant.chat_completion_stream(
        [{"role": "user", "content": "hi"}], on_chunk=seen.append,
    )
    assert text == "FAKE REPLY"
    assert cached is False
    assert seen == ["FAKE REPLY"]


# -- Worker: streaming happy path + fallback ---------------------------------

def test_worker_streams_then_completes(qtbot_unused=None):
    worker = _ChatWorker([{"role": "user", "content": "hi"}], _provider())
    got_chunks: list[str] = []
    completed: list[tuple] = []
    worker.chunk.connect(got_chunks.append)
    worker.completed.connect(lambda t, c: completed.append((t, c)))

    def fake_stream(messages, provider=None, on_chunk=None):
        on_chunk("a")
        on_chunk("b")
        return "ab", False

    with mock.patch("logosforge.ui.chat_view.chat_completion_stream", fake_stream):
        worker.run()  # synchronous in this thread; signals fire directly
    assert got_chunks == ["a", "b"]
    assert completed == [("ab", False)]


def test_worker_falls_back_when_stream_raises():
    worker = _ChatWorker([{"role": "user", "content": "hi"}], _provider())
    completed: list[tuple] = []
    worker.completed.connect(lambda t, c: completed.append((t, c)))

    def boom(*a, **k):
        raise RuntimeError("no streaming")

    with mock.patch("logosforge.ui.chat_view.chat_completion_stream", boom), \
         mock.patch("logosforge.ui.chat_view.chat_completion",
                    return_value=("plain reply", False)) as cc:
        worker.run()
    assert completed == [("plain reply", False)]
    assert cc.called  # the non-streaming fallback was used
