"""Assistant response validation profiles (pure, no provider/UI calls).

Invalid direct output (planning/meta/markdown/context-dump) is blocked, not
apply/cache-allowed, and triggers a strict retry. Secrets / raw-audio /
hidden-context labels are invalid in ANY profile (diagnostic-only). Valid
mode-correct content and valid structure/suggestions pass.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from logosforge.assistant_contract import route, validate

# Bad-output fixtures (from the reported failures).
BAD_PLANNING = """\
### Suggested Scene Structure
- [INTRODUCING] establish the room
- [MAIN ACTION] confrontation
- [CULMINATING MOMENT] the reveal

## Production Notes
Key Questions to Explore:
1. What does she want?

Let me craft a taut scene. This creates visual rhythm.
Six-Task Line Test applies here.
"""
HIDDEN_CTX = "Based on PSYKE Context and Global Story Memory, [AI Mode: Balance]."
SECRET_OUT = "Use api_key: sk-deadbeef12345678 and save clip.wav."

GOOD_SCREENPLAY = """\
MILO VOSS
It was not open when I arrived.

ADA NORTH
Then someone wanted us to think it was.
"""
GOOD_NOVEL = ("Ada stepped into the archive. The dust hung in the dawn light, "
              "and Milo did not look up. \"You're late,\" he said.")
GOOD_OUTLINE = "## Act I\n- Scene 1: arrival\n- Scene 2: the gap\n- Scene 3: turn"
GOOD_SUGGESTIONS = "- Sharpen Milo's subtext\n- Cut the on-the-nose line\n- Add a beat"


def _direct(mode):
    return route(section="Manuscript", writing_mode=mode, action="Dialogue")


# 30-36. Planning/meta/context leakage is invalid for DIRECT manuscript output.
def test_direct_planning_is_invalid():
    res = validate(BAD_PLANNING, _direct("screenplay"))
    assert res.status == "invalid"
    assert res.apply_allowed is False and res.cache_allowed is False
    assert res.retry_recommended is True
    joined = " ".join(res.reasons).lower()
    for marker in ("suggested scene structure", "production notes",
                   "key questions", "let me", "markdown headings"):
        assert marker in joined


def test_hidden_context_labels_invalid_any_profile():
    # Direct manuscript:
    assert validate(HIDDEN_CTX, _direct("novel")).status == "invalid"
    # Even an analysis answer must not leak internal labels:
    analysis = route(section="Manuscript", writing_mode="novel",
                     action="summarize")
    assert validate(HIDDEN_CTX, analysis).status == "invalid"


# Secrets / raw audio → invalid + diagnostic-only (never shown/applied).
def test_secret_output_is_diagnostic_only():
    res = validate(SECRET_OUT, _direct("novel"))
    assert res.status == "invalid" and res.diagnostic_only is True
    assert res.apply_allowed is False and res.copy_allowed is False
    assert res.cache_allowed is False


# 37-39. Valid mode-correct direct content passes and is apply/cache-allowed.
def test_valid_screenplay_passes():
    res = validate(GOOD_SCREENPLAY, _direct("screenplay"))
    assert res.status == "valid"
    assert res.apply_allowed is True and res.cache_allowed is True


def test_valid_novel_passes():
    assert validate(GOOD_NOVEL, _direct("novel")).status == "valid"


# 40. Valid outline structure passes (markdown/lists are fine in Outline).
def test_valid_outline_structure_passes():
    c = route(section="Outline", writing_mode="novel", action="generate")
    res = validate(GOOD_OUTLINE, c)
    assert res.status == "valid"
    assert res.apply_allowed is False          # not a manuscript apply


# 41. Valid suggestions pass (and don't enable manuscript apply).
def test_valid_suggestions_pass():
    c = route(section="Manuscript", writing_mode="novel", action="suggest")
    res = validate(GOOD_SUGGESTIONS, c)
    assert res.status == "valid" and res.apply_allowed is False
    assert res.copy_allowed is True


# Markdown/bullets in DIRECT novel prose are invalid (structure leak).
def test_markdown_in_direct_novel_invalid():
    bad = "### Scene Plan\n- beat one\n- beat two\n- beat three"
    assert validate(bad, _direct("novel")).status == "invalid"


# Outline structure is NOT penalized for the markdown a direct profile forbids.
def test_outline_not_penalized_for_structure():
    c = route(section="Outline", writing_mode="screenplay", action="generate")
    assert validate("# Act I\n- s1\n- s2\n- s3", c).status == "valid"
