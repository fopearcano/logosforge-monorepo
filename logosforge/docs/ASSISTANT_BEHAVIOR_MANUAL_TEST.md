# Assistant Behavior — Manual Test

> Verifies the assistant adapts to the current **section**, **writing mode**,
> **action**, and the user's request. Automated coverage:
> `tests/test_assistant_action_routing.py`. These manual checks confirm the real
> UI end-to-end. Assistant output is always **preview-first** — Copy / Replace /
> Insert / Append are explicit; nothing auto-applies.

Behavior model (implemented in `logosforge/assistant_contract.py`, wired in
`ui/assistant_view.py`): direct manuscript-writing actions (Generate / Dialogue
/ Rewrite / Expand / Continue / Tension) produce **mode-formatted manuscript
content**; planning structure / analysis belong to Outline/planning sections or
explicit analysis actions (Suggest / Summarize / Diagnose / Next Beat /
Alternatives). A response validator flags structure/analysis leakage before it
is shown, and never auto-applies.

---

## A. Screenplay · Manuscript · Dialogue  (the reported bug)

1. Open a Screenplay project (e.g. `sample_projects/manual_alpha/alpha_sample_screenplay.json`).
2. Go to **Manuscript**. Use a scene like:
   ```
   INT. ARCHIVE - DAWN

   Ada North enters carrying a notebook.

   MILO VOSS
   You are late.

   ADA NORTH
   The door was not supposed to be open.
   ```
3. In the Assistant panel type: `continue the dialogue between Milo and Ada`.
4. Click **Dialogue**.

**Expected:** direct screenplay continuation — CHARACTER cues + dialogue, minimal
action lines. **No** markdown, **no** "Suggested Scene Structure", **no**
"Production Notes", **no** "Key Questions", **no** bracketed `[INTRODUCING]`
labels, **no** prose/analysis. If the model still leaks structure, a ⚠ warning
banner appears above the response and nothing is auto-applied.

## B. Screenplay · Manuscript · Generate
Type a request, click the main send (Generate). **Expected:** screenplay scene
content, not an outline/analysis.

## C. Novel · Manuscript · Generate / Dialogue
**Expected:** pure prose (narrative + integrated dialogue); no screenplay slugs
or CHARACTER-cue blocks unless explicitly requested; no outline/analysis.

## D. Graphic Novel · Manuscript · Dialogue
**Expected:** panel-level content (Panel N · Visual / Caption / Dialogue / SFX /
Notes), Act → Page → Scene → Panel. **No** old "Comics Script"/page-manager
language and **no** ComfyUI/image prompts.

## E. Stage Script · Manuscript · Dialogue
**Expected:** CHARACTER cues + dialogue with (stage directions) where needed; no
novel narration; no screenplay slugs unless requested.

## F. Outline · Generate
**Expected:** structured outline (acts/chapters/scenes/beats) — structure is
allowed here.

## G. PSYKE · Generate
**Expected:** codex / story-bible entity content; no manuscript scene prose
unless requested.

## H. Notes · Generate
**Expected:** note content — organize / brainstorm / summarize.

## I. Action routing
- The **Dialogue** button must produce dialogue, not a "Structure" response.
- **Suggest** may return concise suggestions (analysis) — that is expected and
  is *not* flagged by the validator.
- A "Structure"/planning notion must not override the **Dialogue**/**Generate**
  buttons in Manuscript.

## J. Apply targets
- **Replace** only when a selection / current block exists.
- **Insert / Append** target the current scene/block and preserve mode format.
- No auto-apply — every apply is an explicit click.

---

### Notes / limitations
- Output quality still depends on the selected model backend (LM Studio /
  Ollama / vLLM / OpenAI / Anthropic / OpenRouter). The contract + validator
  make the *instruction* and *guardrails* mode-correct; a weak local model may
  still drift — the ⚠ validator warning surfaces that and blocks silent apply.
- Providers remain generation backends only; this change adds no provider, no
  network call, and no memory writes.

---

## Full routing contract + validation + apply/cache safety

Every request is routed to an **AssistantTaskContract**
(`logosforge/assistant_contract.route`) =
**section × writing mode × action × target × user request** → `output_kind`
(direct_content / structure / codex / notes / timeline / analysis / suggestions
/ answer / transcript / clarification), a `validator_profile`, `apply_allowed`,
and a `cache_key`. The response is validated (`validate`) before it is usable.

| Section / action | Expected output kind | Forbidden | Apply | Cache |
|---|---|---|---|---|
| Manuscript · Generate/Rewrite/Expand/Dialogue/Continue | direct content (mode format) | planning/markdown/analysis/context dumps | Replace/Insert/Append (valid only) | only valid |
| Manuscript · Suggest | suggestions | applying as manuscript by default | Copy only | only valid |
| Manuscript · Structure (explicit) | structure | — | Apply-to-Outline | only valid |
| Outline · Generate/Suggest | structure | full prose pages | Apply-to-Outline | only valid |
| Notes · summarize/organize/extract/convert | note ops | direct manuscript | Copy | only valid |
| PSYKE · create/update/extract | codex/entity | direct manuscript | Copy | only valid |
| Timeline · event/continuity/reorder | timeline ops | direct manuscript | Copy | only valid |
| Chat · "continue/rewrite" (context) | direct content | planning essay | Copy | only valid |
| Chat · "analyze" / "structure" / "what is…" | analysis / structure / answer | — | Copy | only valid |
| Dexter · format/route transcript | transcript | raw audio / audio paths | route to target | only valid |

**Hard rules verified by tests:** invalid direct output (planning/meta/markdown
/ "Key Questions" / "Production Notes" / "Let me" / "PSYKE Context" / "Global
Story Memory" / "[AI Mode:]") is **not shown as valid, not cached as valid, and
Apply is disabled** — for cached responses too; secrets / raw-audio output is
**withheld**; hidden context (PSYKE / memory / mode labels) never appears in
user-facing output; assistant mode/personality are modifiers that cannot change
the output kind. Missing target for a direct-writing request → a short
clarification, never a planning essay.

Automated: `tests/test_assistant_routing_matrix.py`,
`tests/test_assistant_response_validation.py`,
`tests/test_assistant_apply_safety.py`, `tests/test_assistant_action_routing.py`.

## Writer QA harness

Automated behavior coverage of this matrix lives in the Writer QA harness (`tools/writer_qa/`, `tests/test_writer_qa_harness.py`): `python tools/writer_qa/run_writer_qa.py --suite all`. See `docs/WRITER_QA_AGENT_PLAN.md`.

## Local QA mode (drive the real UI deterministically)

To run these checks in the real app with a deterministic fake provider (no real
provider / network / cloud / keys), enable local QA mode: `LOGOSFORGE_QA_MODE=1`
(default OFF), open a `sample_projects/writer_qa/` project, and optionally force a
response shape with `LOGOSFORGE_FAKE_PROVIDER_PROFILE` (e.g.
`invalid_planning_markdown` to confirm leakage is blocked, `invalid_secret_leak`
to confirm withholding). Full scripted checklist + 20 scenarios + bug template:
`docs/LOCAL_WRITER_QA_AGENT_SCRIPT.md`. Tests: `tests/test_local_writer_qa_mode.py`.
