"""Assistant apply-safety enforcement in the live panel.

Invalid output (planning leak / secret) is never shown as usable and Apply is
disabled — for cached responses too. Valid direct content enables Apply.
"""

import pytest

from logosforge.assistant_contract import route
from logosforge.db import Database
from logosforge.ui.main_window import MainWindow

BAD = ("### Suggested Scene Structure\n- [INTRODUCING] x\n- y\n- z\n\n"
       "## Production Notes\nKey Questions to Explore:\nLet me craft this.")
SECRET = "Use api_key: sk-deadbeef12345678 then save clip.wav."
GOOD = "MILO VOSS\nIt was not open when I arrived.\n\nADA NORTH\nThen someone lied."


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _panel(engine="screenplay"):
    db = Database()
    pid = db.create_project("P", narrative_engine=engine).id
    db.create_scene(pid, "S1", content="INT. ARCHIVE - DAWN", act="Act I")
    win = MainWindow(db, pid)
    panel = win._assistant_panel
    panel._active_section = "Manuscript"
    panel._task_contract = route(
        section="Manuscript", writing_mode=engine, action="Dialogue")
    return win, panel


def test_invalid_output_blocks_apply():
    _win, panel = _panel()
    panel._on_response(BAD, False)
    assert panel._response_valid is False
    assert panel._get_response_text() is None          # central apply guard
    assert panel._replace_content_btn.isEnabled() is False
    assert panel._insert_cursor_btn.isEnabled() is False
    assert panel._append_btn.isEnabled() is False


def test_invalid_cached_output_also_blocked():
    _win, panel = _panel()
    panel._on_response(BAD, True)                       # from_cache=True
    assert panel._response_valid is False
    assert panel._get_response_text() is None


def test_secret_output_withheld():
    _win, panel = _panel("novel")
    panel._on_response(SECRET, False)
    shown = panel._response_output.toPlainText()
    assert "sk-deadbeef" not in shown                   # never displayed
    assert panel._response_valid is False
    assert panel._get_response_text() is None


def test_valid_direct_output_enables_apply():
    _win, panel = _panel()
    panel._on_response(GOOD, False)
    assert panel._response_valid is True
    assert panel._get_response_text() is not None
    assert panel._replace_content_btn.isEnabled() is True
    assert panel._copy_btn.isEnabled() is True


def test_apply_handler_guard_blocks_invalid(monkeypatch):
    _win, panel = _panel()
    panel._on_response(BAD, False)
    # Even if a handler is invoked directly, the central guard blocks it.
    calls = {"n": 0}
    monkeypatch.setattr(panel, "_notify_data_changed",
                        lambda: calls.__setitem__("n", calls["n"] + 1))
    panel._apply_replace()
    panel._apply_insert()
    panel._apply_append()
    assert calls["n"] == 0                              # nothing applied


# Insert must not wedge the response against adjacent text ("patient.The dim").
def _insert_into(monkeypatch, panel, before_text, response):
    from PySide6.QtWidgets import QMessageBox, QTextEdit
    ed = QTextEdit()
    ed.setPlainText(before_text)
    cur = ed.textCursor()
    cur.movePosition(cur.MoveOperation.End)
    ed.setTextCursor(cur)
    monkeypatch.setattr(panel, "_active_editor", lambda: ed)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel._on_response(response, False)
    assert panel._get_response_text() is not None       # valid → insertable
    panel._apply_insert()
    return ed.toPlainText()


def test_insert_adds_separating_space_when_wedged(monkeypatch):
    _win, panel = _panel("novel")
    out = _insert_into(monkeypatch, panel, "She waited.", "The door opened.")
    assert out == "She waited. The door opened."        # one space inserted


def test_insert_no_double_space_when_already_separated(monkeypatch):
    _win, panel = _panel("novel")
    out = _insert_into(monkeypatch, panel, "She waited. ", "The door opened.")
    assert out == "She waited. The door opened."        # no doubled space


# Counterpart output is analysis. The fix routes a non-direct ANALYSIS contract
# at SEND time (_set_analysis_contract) so the response validates against the
# truthful profile: manuscript markdown/list/planning rules don't misfire, the
# profile-independent secret / hidden-context guards still apply, and
# apply_allowed=False keeps it out of the manuscript.
LEAK = "Based on PSYKE Context and Global Story Memory, [AI Mode: Balance]."


def _analysis_contract():
    # What _set_analysis_contract produces for a counterpart send.
    return route(entry_point="counterpart_panel", section="manuscript",
                 writing_mode="novel", action="Critique")


def test_counterpart_set_analysis_contract_overrides_stale_direct():
    # Root cause: a counterpart send replaces any stale Assistant *_direct
    # contract with its own non-direct analysis contract (apply-disabled).
    _win, panel = _panel("novel")
    panel._task_contract = route(
        section="Manuscript", writing_mode="novel", action="Dialogue")
    assert panel._task_contract.validator_profile == "novel_direct"
    panel._set_analysis_contract(entry_point="counterpart_panel",
                                 action="Critique")
    assert panel._task_contract.validator_profile == "analysis_answer"
    assert panel._task_contract.apply_allowed is False


def test_counterpart_send_sets_analysis_contract(monkeypatch):
    # The send path actually wires _set_analysis_contract before the request.
    _win, panel = _panel("novel")
    panel._task_contract = route(
        section="Manuscript", writing_mode="novel", action="Dialogue")
    monkeypatch.setattr(panel, "_build_context",
                        lambda *a, **k: ("scene ctx",) + ("",) * 10)
    monkeypatch.setattr(panel, "_start_request", lambda *a, **k: None)
    panel._send_counterpart("Critique")
    assert panel._task_contract.validator_profile == "analysis_answer"


def test_analysis_contract_passes_critique_no_banner():
    # Critique with markdown + a numbered list is valid analysis — no banner,
    # Markdown rendered for reading, Copy on, never apply-eligible.
    _win, panel = _panel("novel")
    panel._task_contract = _analysis_contract()
    panel._panel_mode = "counterpart"
    panel._on_response(BAD, False)
    shown = panel._response_output.toPlainText()
    assert "Invalid output" not in shown                 # no banner
    assert "Suggested Scene Structure" in shown          # content present...
    assert "###" not in shown                            # ...but Markdown rendered
    assert panel._response_valid is True
    assert panel._apply_ok is False
    assert panel._copy_btn.isEnabled() is True


def test_direct_content_shown_verbatim_not_markdown():
    # Direct manuscript output is shown as-is (line breaks preserved, Apply gets
    # the exact source) — Markdown rendering is only for read-only analysis.
    _win, panel = _panel("novel")
    panel._task_contract = route(
        section="Manuscript", writing_mode="novel", action="Dialogue")
    panel._panel_mode = "assistant"
    body = "First line of prose.\nSecond line of prose."
    panel._on_response(body, False)
    assert panel._response_output.toPlainText() == body  # verbatim, not collapsed
    assert panel._get_response_text() == body            # Apply reads exact source


def test_quantum_markdown_renders_structure():
    # The Quantum report is rendered via Markdown: section banners/option
    # headers bolded, and every detail line kept (hard breaks) so Stakes /
    # Consequence don't collapse into one paragraph.
    from logosforge.ui.assistant_view import AssistantPanel
    body = ("═══ QUANTUM FIELD ═══\n"
            "Superposition: 2 possible futures\n\n"
            "▸ Option 1: Retreat  [b1]  26%\n"
            "  Stakes: Momentum\n"
            "  Consequence: Pressure builds elsewhere.\n")
    lines = AssistantPanel._quantum_markdown("Possibilities", body).split("\n")
    assert "**QUANTUM FIELD**  " in lines                      # banner bolded
    assert any(l.startswith("**▸ Option 1:") for l in lines)   # option bolded
    assert "  Stakes: Momentum  " in lines                     # detail preserved
    assert "  Consequence: Pressure builds elsewhere.  " in lines


def test_quantum_markdown_fences_factor_table():
    # The aligned factor-comparison matrix (header + solid rule + column rows)
    # is wrapped in a monospace code fence so its columns stay lined up, while
    # the surrounding option header is still bolded.
    from logosforge.ui.assistant_view import AssistantPanel
    body = ("▸ Option 1: Solo Pursuit  [b1]  26%\n"
            "  Stakes: Momentum\n\n"
            "  Factor            [A]  [B]\n"
            "  ──────────────────────────\n"
            "  Tension            ↑    ↓\n"
            "  Novelty            →    ↑\n")
    lines = AssistantPanel._quantum_markdown("Compare", body).split("\n")
    assert lines.count("```") == 2                             # matrix fenced
    fi = lines.index("```")
    fence = lines[fi + 1:lines.index("```", fi + 1)]
    assert any(set(l.strip()) == {"─"} for l in fence)         # rule kept verbatim
    assert any("Tension" in l for l in fence)                  # rows kept
    assert any(l.startswith("**▸ Option 1:") for l in lines)   # option still bold


def test_analysis_contract_still_withholds_secrets():
    # The analysis profile keeps the profile-independent secret/raw-audio guard.
    _win, panel = _panel("novel")
    panel._task_contract = _analysis_contract()
    panel._panel_mode = "counterpart"
    panel._on_response(SECRET, False)
    shown = panel._response_output.toPlainText()
    assert "sk-deadbeef" not in shown                    # never displayed
    assert panel._response_valid is False
    assert panel._copy_btn.isEnabled() is False


def test_analysis_contract_still_flags_hidden_context():
    # A genuine internal-label leak stays invalid under the analysis profile.
    _win, panel = _panel("novel")
    panel._task_contract = _analysis_contract()
    panel._panel_mode = "counterpart"
    panel._on_response(LEAK, False)
    assert panel._response_valid is False
    assert "Invalid output" in panel._response_output.toPlainText()


def test_counterpart_outline_mode_not_apply_eligible(monkeypatch):
    # The outline-apply clause is Assistant-only: counterpart analysis output is
    # never apply-eligible, even when the Outline section happens to be active.
    _win, panel = _panel("novel")
    panel._task_contract = _analysis_contract()           # apply_allowed=False
    panel._panel_mode = "counterpart"
    monkeypatch.setattr(panel, "_is_outline_mode", lambda: True)
    panel._on_response("Some neutral analysis prose.", False)
    assert panel._response_valid is True
    assert panel._apply_ok is False                       # not enabled via outline


def test_counterpart_contract_not_outline_applyable_after_mode_switch(monkeypatch):
    # Race guard: a Counterpart analysis response stays apply-disabled even if
    # the panel is toggled back to Assistant (in the Outline section) while the
    # response is in flight — the outline-apply gate keys on the contract's
    # provenance (entry_point), not the live panel toggle.
    _win, panel = _panel("novel")
    panel._set_analysis_contract(entry_point="counterpart_panel",
                                 action="Critique")
    monkeypatch.setattr(panel, "_is_outline_mode", lambda: True)
    panel._panel_mode = "assistant"                       # mid-flight toggle back
    panel._on_response("Some neutral analysis prose.", False)
    assert panel._response_valid is True
    assert panel._apply_ok is False                       # entry_point guards it


def test_assistant_outline_response_is_apply_eligible(monkeypatch):
    # Regression: the outline-apply override still fires for a genuine Assistant
    # outline response (entry_point="assistant_panel").
    _win, panel = _panel("novel")
    panel._task_contract = route(
        entry_point="assistant_panel", section="Outline",
        writing_mode="novel", action="generate")
    monkeypatch.setattr(panel, "_is_outline_mode", lambda: True)
    panel._panel_mode = "assistant"
    panel._on_response(
        "## Act I\n- Scene 1: arrival\n- Scene 2: the gap\n- Scene 3: turn", False)
    assert panel._response_valid is True
    assert panel._apply_ok is True                        # assistant outline → applyable
