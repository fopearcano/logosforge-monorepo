"""Tests for the Local PC Writer QA Agent Mode (logosforge/qa_mode.py).

Proves QA mode is OFF by default, that the deterministic fake provider is
reachable ONLY in QA mode (never in production), that structured QA logs redact
secrets / tokens / local paths / raw audio and truncate long content, that the
JSON+MD report exports cleanly, that the writer-QA sample projects exist and
load, and that normal (non-QA) startup behavior is unchanged — all without any
real provider, network, cloud, or credentials.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import pytest

from logosforge import qa_mode

REPO = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO / "sample_projects" / "writer_qa"
SAMPLES = [
    "novel_sample.json", "screenplay_sample.json", "graphic_novel_sample.json",
    "stage_script_sample.json", "series_sample.json", "notes_psyke_sample.json",
]


@pytest.fixture(autouse=True)
def _clean_qa_env(monkeypatch, tmp_path):
    """Each test starts with QA env unset and logs/reports redirected to tmp."""
    for var in (qa_mode.QA_ENV, qa_mode.PROFILE_ENV,
                qa_mode.LOG_DIR_ENV, qa_mode.REPORT_DIR_ENV):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv(qa_mode.LOG_DIR_ENV, str(tmp_path / "logs"))
    monkeypatch.setenv(qa_mode.REPORT_DIR_ENV, str(tmp_path / "reports"))
    qa_mode.reset_log()
    yield
    qa_mode.reset_log()


# 1. OFF by default.
def test_qa_mode_off_by_default():
    assert qa_mode.is_qa_mode() is False


# 2. Enabled only by the accepted truthy env values.
@pytest.mark.parametrize("val,expected", [
    ("1", True), ("true", True), ("YES", True), ("on", True),
    ("0", False), ("false", False), ("", False), ("nope", False),
])
def test_qa_mode_env_toggle(monkeypatch, val, expected):
    monkeypatch.setenv(qa_mode.QA_ENV, val)
    assert qa_mode.is_qa_mode() is expected


# 3. Fake completion is deterministic and offline.
def test_fake_completion_deterministic():
    a = qa_mode.fake_completion(profile="valid_novel_prose")
    b = qa_mode.fake_completion(profile="valid_novel_prose")
    assert a == b and a
    assert qa_mode.fake_completion(profile="valid_screenplay_dialogue") != a


# 4. Profiles A–O are all present and selectable.
def test_profiles_cover_a_to_o():
    assert len(qa_mode.QA_PROFILES) == 14   # A–N (O = provider_error, special)
    profs = qa_mode.list_profiles()
    assert "provider_error" in profs and "valid_auto" in profs
    for name in ("valid_novel_prose", "valid_screenplay_dialogue",
                 "valid_graphic_novel_panel", "valid_stage_script_dialogue",
                 "valid_series_scene", "valid_outline_structure",
                 "valid_psyke_entity", "valid_note_summary",
                 "invalid_planning_markdown", "invalid_context_dump",
                 "invalid_meta_reasoning", "invalid_wrong_mode",
                 "invalid_empty", "invalid_secret_leak"):
        assert name in qa_mode.QA_PROFILES


# 5. provider_error raises; empty returns "".
def test_provider_error_and_empty():
    with pytest.raises(qa_mode.FakeProviderError):
        qa_mode.fake_completion(profile="provider_error")
    assert qa_mode.fake_completion(profile="invalid_empty") == ""


# 6. valid_auto infers the writing mode from the prompt.
def test_valid_auto_infers_mode():
    from logosforge.assistant_contract import route, system_prompt_for
    for mode, marker in (("screenplay", "MILO VOSS"),
                         ("graphic_novel", "Panel 1"),
                         ("novel", "Ada stepped")):
        c = route(section="Manuscript", writing_mode=mode, action="generate")
        msgs = [{"role": "system", "content": system_prompt_for(c)},
                {"role": "user", "content": "continue"}]
        out = qa_mode.fake_completion(msgs, profile="valid_auto")
        assert marker in out


# 7. Unknown profile never crashes — falls back to a safe default.
def test_unknown_profile_safe_default():
    out = qa_mode.fake_completion([{"role": "system", "content": "novel"}],
                                  profile="does_not_exist")
    assert out  # non-empty, no raise


# 8. Profile precedence: settings → env → default.
def test_fake_provider_profile_precedence(monkeypatch):
    class _Mgr:
        def __init__(self, v):
            self._v = v

        def get(self, key):
            return self._v if key == "qa_fake_provider_profile" else ""

    import logosforge.settings as settings
    # settings wins over env
    monkeypatch.setattr(settings, "get_manager", lambda: _Mgr("valid_psyke_entity"))
    monkeypatch.setenv(qa_mode.PROFILE_ENV, "invalid_empty")
    assert qa_mode.fake_provider_profile() == "valid_psyke_entity"
    # env used when settings empty
    monkeypatch.setattr(settings, "get_manager", lambda: _Mgr(""))
    assert qa_mode.fake_provider_profile() == "invalid_empty"
    # default when both empty
    monkeypatch.delenv(qa_mode.PROFILE_ENV, raising=False)
    assert qa_mode.fake_provider_profile() == qa_mode.DEFAULT_PROFILE


# 9. chat_completion uses the fake provider ONLY in QA mode.
def test_chat_completion_fake_only_in_qa(monkeypatch):
    from logosforge import assistant
    monkeypatch.setattr(assistant, "resolve_api_key", lambda p: "k")
    monkeypatch.setattr(assistant, "get_api_format", lambda p: "openai")
    monkeypatch.setattr(assistant, "_openai_completion",
                        lambda *a, **k: "REAL_PATH_SENTINEL")
    msgs = [{"role": "user", "content": "hi"}]
    # QA OFF → real path (sentinel), fake NOT used.
    out, cached = assistant.chat_completion(msgs, use_cache=False)
    assert out == "REAL_PATH_SENTINEL"
    # QA ON → deterministic fake, real path NOT used.
    monkeypatch.setenv(qa_mode.QA_ENV, "1")
    out2, cached2 = assistant.chat_completion(msgs, use_cache=False)
    assert out2 != "REAL_PATH_SENTINEL" and out2 and cached2 is False


# 10. In QA mode, no credential resolution / no network call happens.
def test_chat_completion_no_provider_or_network_in_qa(monkeypatch):
    from logosforge import assistant

    def boom(*a, **k):
        raise AssertionError("no provider/credential/network call allowed in QA")

    monkeypatch.setattr(assistant, "resolve_api_key", boom)
    monkeypatch.setattr(assistant, "_openai_completion", boom)
    monkeypatch.setattr(assistant, "_anthropic_completion", boom)
    monkeypatch.setenv(qa_mode.QA_ENV, "1")
    out, cached = assistant.chat_completion([{"role": "user", "content": "x"}])
    assert out and cached is False


# 11. provider_error profile surfaces as an error through chat_completion.
def test_chat_completion_provider_error(monkeypatch):
    from logosforge import assistant
    monkeypatch.setenv(qa_mode.QA_ENV, "1")
    monkeypatch.setenv(qa_mode.PROFILE_ENV, "provider_error")
    with pytest.raises(qa_mode.FakeProviderError):
        assistant.chat_completion([{"role": "user", "content": "x"}])


# 12. Redaction removes secrets / api keys / tokens.
def test_redaction_secrets():
    out = qa_mode.redact("here api_key: sk-ABCD1234EFGH5678 token=abcd1234efgh")
    assert "sk-ABCD1234" not in out
    assert "api_key: sk" not in out
    assert "<redacted-secret>" in out


# 13. Redaction removes local / OS paths.
def test_redaction_paths():
    out = qa_mode.redact("see /Users/jane/Documents/secret.txt now")
    assert "/Users/jane" not in out and "<path>" in out
    win = qa_mode.redact(r"C:\Users\jane\private\notes.txt")
    assert "jane" not in win and "<path>" in win


# 14. Redaction removes raw-audio files / paths.
def test_redaction_audio():
    out = qa_mode.redact("clip /home/user/recordings/take_01.wav done")
    assert ".wav" not in out and "/home/user" not in out and "<audio>" in out


# 15. Redaction truncates long content (no full manuscript verbatim).
def test_redaction_truncates():
    long = "word " * 500
    out = qa_mode.redact(long, max_len=120)
    assert len(out) < len(long) and "chars redacted" in out


# 16. log_event redacts, buffers, and writes a JSONL line containing no secret.
def test_log_event_redacts_and_writes():
    rec = qa_mode.log_event(
        "assistant_response", section="Manuscript", writing_mode="screenplay",
        action="Dialogue", target="current_scene", output_kind="direct_content",
        validation_status="invalid", apply_allowed=False,
        response_excerpt="api_key: sk-SECRET1234ABCD path /Users/x/clip.wav",
    )
    assert "sk-SECRET1234" not in json.dumps(rec)
    assert rec["section"] == "Manuscript" and rec["apply_allowed"] is False
    path = qa_mode._session_log_path()
    assert path.exists()
    disk = path.read_text(encoding="utf-8")
    assert "sk-SECRET1234" not in disk and ".wav" not in disk
    assert qa_mode.buffered_events()[-1]["event"] == "assistant_response"


# 17. log_event carries the audit fields a QA agent needs.
def test_log_event_fields():
    rec = qa_mode.log_event(
        "assistant_response", section="Manuscript", writing_mode="novel",
        action="generate", target="current_scene", output_kind="direct_content",
        validator_profile="novel_direct", validation_status="valid",
        validation_reasons=[], response_valid=True, apply_allowed=True,
        copy_allowed=True, withheld=False, from_cache=False,
        profile="valid_auto", response_excerpt="Ada stepped into the archive.",
    )
    for key in ("ts", "event", "section", "writing_mode", "action", "target",
                "output_kind", "validator_profile", "validation_status",
                "apply_allowed", "response_excerpt", "profile"):
        assert key in rec


# 18. export_report writes parseable JSON + MD with no leaked secret.
def test_export_report(tmp_path):
    qa_mode.log_event(
        "assistant_response", section="Manuscript", writing_mode="screenplay",
        action="Dialogue", target="current_scene", output_kind="direct_content",
        validation_status="invalid", response_valid=False, apply_allowed=False,
        withheld=True, response_excerpt="api_key: sk-LEAK1234ABCD secret",
    )
    qa_mode.log_event(
        "assistant_response", section="Manuscript", writing_mode="novel",
        action="generate", target="current_scene", output_kind="direct_content",
        validation_status="valid", response_valid=True, apply_allowed=True,
        response_excerpt="Ada stepped into the archive.",
    )
    base = tmp_path / "local_latest"
    jp, mp = qa_mode.export_report(base)
    data = json.loads(Path(jp).read_text(encoding="utf-8"))
    assert data["summary"]["responses"] == 2
    assert data["summary"]["withheld_responses"] == 1
    assert data["summary"]["applyable_responses"] == 1
    md = Path(mp).read_text(encoding="utf-8")
    assert "# LogosForge — Local Writer QA Report" in md
    assert "sk-LEAK1234" not in (Path(jp).read_text() + md)


# 19. export_report defaults to reports/writer_qa/local_latest.* (git-ignored).
def test_export_report_default_path(monkeypatch):
    monkeypatch.delenv(qa_mode.REPORT_DIR_ENV, raising=False)
    base = qa_mode.default_report_base()
    assert base.name == "local_latest"
    assert base.parent.name == "writer_qa"


# 20. The six writer-QA sample projects exist and load via the real importer.
def test_sample_projects_exist_and_load():
    from logosforge.db import Database
    from logosforge.import_data import import_json, validate_import_data
    assert (SAMPLE_DIR / "README.md").exists()
    for name in SAMPLES:
        p = SAMPLE_DIR / name
        assert p.exists(), f"missing sample {name}"
        data, err = validate_import_data(p.read_text(encoding="utf-8"))
        assert data is not None, f"{name}: {err}"
        db = Database()
        pid = import_json(db, data)
        assert pid and db.get_project_by_id(pid) is not None


# 21. .gitignore keeps generated QA logs/reports/screenshots out of git.
def test_gitignore_excludes_generated_qa_artifacts():
    gi = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "logs/writer_qa/" in gi
    assert "reports/writer_qa/local_*.json" in gi
    assert "reports/writer_qa/screenshots/" in gi


# 22. Importing qa_mode is side-effect free (no QA enabled, no dirs created).
def test_import_is_side_effect_free():
    assert qa_mode.is_qa_mode() is False
    # The default settings key is empty → env/default decides; nothing forced on.
    from logosforge.settings import get_manager
    assert get_manager().get("qa_fake_provider_profile") == ""


# 23. The test-only local report CLI runs fully offline and writes a report.
def test_export_local_report_cli(tmp_path, monkeypatch):
    from tools.writer_qa import export_local_report
    monkeypatch.setattr(
        "logosforge.assistant.chat_completion",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("CLI must not call chat_completion")),
    )
    rc = export_local_report.main(
        ["--suite", "manuscript", "--report", str(tmp_path / "local_latest"),
         "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    assert (tmp_path / "local_latest.json").exists()
    assert (tmp_path / "local_latest.md").exists()
