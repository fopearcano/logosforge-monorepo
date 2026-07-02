# Local PC Writer QA Agent Script

> A scripted checklist for an **external GUI / computer-use writer agent** (or a
> human) running LogosForge on a real machine, to test it like an author —
> Assistant behavior, Manuscript navigation, and fullscreen — **without any real
> AI provider, network, cloud, or credentials**. Local QA mode swaps in a
> deterministic **fake provider** so results are reproducible.

LogosForge principle (unchanged): *the model generates; LogosForge remembers,
retrieves, structures, updates, and syncs.* QA mode replaces only the generator.

Companion automated coverage:
- Headless contract harness: `tools/writer_qa/` + `tests/test_writer_qa_harness.py`.
- QA-mode unit tests: `tests/test_local_writer_qa_mode.py`.
- Manual UI checklist: `docs/ASSISTANT_BEHAVIOR_MANUAL_TEST.md`.

---

## 1. Setup (local PC only)

1. Install deps and confirm the app launches normally first (QA mode OFF):
   `pip install -r requirements.txt` then `python run.py`.
2. **Enable QA mode** (default OFF):
   - macOS / Linux: `export LOGOSFORGE_QA_MODE=1`
   - Windows (PowerShell): `$env:LOGOSFORGE_QA_MODE = "1"`
3. (Optional) **Pick a fake-provider profile** (default `valid_auto` → mode-correct
   valid content):
   - `export LOGOSFORGE_FAKE_PROVIDER_PROFILE=invalid_planning_markdown`
   - The same value can be set via the settings key `qa_fake_provider_profile`
     (settings take precedence over the env var).
4. (Optional) redirect generated artifacts (both git-ignored):
   - `export LOGOSFORGE_QA_LOG_DIR=logs/writer_qa`
   - report export defaults to `reports/writer_qa/local_latest.{json,md}`.
5. Launch: `python run.py`. While QA mode is on, **every** assistant request is
   answered by the fake provider — no provider, network, key, or cloud is touched.
6. Open a sample project from `sample_projects/writer_qa/` (one per mode, plus a
   Notes/PSYKE sample). These are test fixtures; copy first if you want to edit.

When finished, unset `LOGOSFORGE_QA_MODE` to return to normal behavior.

## 2. Agent role

You are a **writer using LogosForge**, not a code reviewer. Open a project,
choose a section + writing mode, type a realistic request, click an action, and
judge the **result a writer would see**:

- Right **mode** format? (prose vs screenplay vs panel vs stage vs series)
- Right **section** behavior? (Manuscript writes; Outline/PSYKE/Notes/Timeline do
  their own jobs)
- **Usable** content — or planning / meta / context-dump leakage?
- **Apply** safe? (Replace/Insert/Append enabled only for valid direct content;
  nothing auto-applies — every apply is an explicit click)
- **State** stable across navigation and fullscreen?

## 3. Rules (safety)

- Use only `sample_projects/writer_qa/` fixtures (or your own throwaway copies).
- Never use real provider keys; QA mode needs none. Do not disable QA mode
  mid-run if you intend to keep using the fake provider.
- Do not paste real secrets, tokens, or raw-audio paths into requests. (If you
  do, the QA log redacts them, but don't rely on it.)
- Generated logs / reports / screenshots are **git-ignored** — never commit them,
  never commit a copy of a real user manuscript.
- This is read/observe + transient edits in a sample project only — no
  destructive operations outside the temp/sample workspace.

## 4. Fake-provider profiles (A–O)

Set `LOGOSFORGE_FAKE_PROVIDER_PROFILE` to one of these to force a response shape:

| | Profile | What it returns / tests |
|---|---|---|
| A | `valid_novel_prose` | valid novel prose |
| B | `valid_screenplay_dialogue` | valid screenplay (cues + dialogue) |
| C | `valid_graphic_novel_panel` | valid Panel N / Visual / Caption / Dialogue / SFX |
| D | `valid_stage_script_dialogue` | valid stage cues + (stage directions) |
| E | `valid_series_scene` | valid series scene content |
| F | `valid_outline_structure` | valid outline (acts/scenes/beats) |
| G | `valid_psyke_entity` | valid codex / story-bible entity |
| H | `valid_note_summary` | valid note summary |
| I | `invalid_planning_markdown` | planning/markdown leak → must be **blocked** |
| J | `invalid_context_dump` | hidden-context dump → must be **blocked** |
| K | `invalid_meta_reasoning` | "I'll… / Let me…" meta → must be **blocked** |
| L | `invalid_wrong_mode` | prose in a non-prose slot → must be **blocked** |
| M | `invalid_empty` | empty output → not applyable |
| N | `invalid_secret_leak` | secret + audio path → must be **withheld** (never shown) |
| O | `provider_error` | simulated provider failure → graceful error, app stays usable |

Default (no profile set): `valid_auto` returns **mode-correct valid** content.

## 5. Scenarios (20)

For each: set the profile if noted, open the listed sample, perform the steps,
compare to **Expected**, and file a bug if it diverges.

1. **Novel · Manuscript · Generate** (`novel_sample`, default profile). Type
   "write the next beat", click Generate. *Expected:* prose; no slugs/cues; Apply
   enabled.
2. **Screenplay · Manuscript · Dialogue** (`screenplay_sample`, default). In the
   scene, type "continue the dialogue between Milo and Ada", click Dialogue.
   *Expected:* CHARACTER cues + dialogue; no markdown, no "Production Notes", no
   "Key Questions"; Apply enabled.
3. **Graphic Novel · Manuscript · Dialogue** (`graphic_novel_sample`, default).
   *Expected:* Panel N / Visual / Caption / Dialogue / SFX; no "Comics Script"/
   page-manager language; no image/ComfyUI prompts.
4. **Stage Script · Manuscript · Generate** (`stage_script_sample`, default).
   *Expected:* CHARACTER cues + (stage directions); no novel narration; no
   screenplay slugs unless asked.
5. **Series · Manuscript · Expand** (`series_sample`, default). *Expected:*
   episode/scene manuscript content; no outline/analysis.
6. **Planning leak blocked** (any mode, profile **I**
   `invalid_planning_markdown`). Manuscript · Dialogue. *Expected:* ⚠ "invalid
   output" banner; Apply disabled; raw output shown clearly as not applied.
7. **Context dump blocked** (profile **J**). Manuscript · Generate. *Expected:*
   blocked as above (hidden-context labels never appear as usable content).
8. **Meta reasoning blocked** (profile **K**). Manuscript · Rewrite. *Expected:*
   blocked; Apply disabled.
9. **Wrong-mode blocked** (Screenplay, profile **L** `invalid_wrong_mode`).
   Manuscript · Dialogue. *Expected:* prose in a screenplay slot is **not**
   applyable.
10. **Empty output** (profile **M**). Manuscript · Generate. *Expected:* no
    crash; nothing applyable.
11. **Secret withheld** (profile **N** `invalid_secret_leak`). Manuscript ·
    Generate. *Expected:* response **withheld** ("contained sensitive content");
    nothing shown or applied; nothing leaked into logs.
12. **Provider error** (profile **O** `provider_error`). Manuscript · Generate.
    *Expected:* a graceful error message; the app stays usable.
13. **Manuscript · Suggest** (`novel_sample`, profile **H**). *Expected:* concise
    suggestions (analysis); Copy only — not applied as manuscript by default; no ⚠
    banner (suggestions are allowed here).
14. **Outline · Generate** (`novel_sample`, profile **F**). Switch to Outline.
    *Expected:* structure (acts/scenes/beats); not pushed into Manuscript prose.
15. **Notes** (`notes_psyke_sample`, profile **H**). In Notes, "summarize these
    notes". *Expected:* note summary; not manuscript content.
16. **PSYKE** (`notes_psyke_sample`, profile **G**). In PSYKE, "create a
    character profile for Ada". *Expected:* codex/entity content; not scene prose.
17. **Chat with no target → clarify** (`novel_sample`, default). In Chat, with
    nothing selected/open, "continue the scene". *Expected:* a short clarifying
    question, not a planning essay.
18. **Manuscript navigation state.** Type a line in Manuscript → switch to
    Outline → Notes → Assistant → back to Manuscript. *Expected:* your text
    **remains**; no reset/re-render loss.
19. **Fullscreen reversibility.** View → Toggle Full Screen (or F11). Type, switch
    sections, return; then Exit Full Screen. Toggle 3×. *Expected:* no lock/
    minimize; main navigation stays visible; text + render OK.
20. **Save / reload.** Save the project, reopen it. *Expected:* Manuscript, Notes,
    PSYKE, and mode persist; Unicode (curly quotes, em dash, emoji, accents)
    round-trips.

## 6. Exporting a report

A redacted machine + human report can be produced two ways:

- **From the app session:** with QA mode on, each assistant response logs a
  redacted event under `LOGOSFORGE_QA_LOG_DIR` (default `logs/writer_qa/`).
- **Headless (no GUI), test-only CLI** — drives the same scenario matrix through
  the real `route → validate` layer with the fake provider:
  ```
  python tools/writer_qa/export_local_report.py --suite all
  python tools/writer_qa/export_local_report.py --profile invalid_secret_leak
  ```
  Writes `reports/writer_qa/local_latest.{json,md}` (git-ignored). All content
  excerpts in both outputs are redacted (secrets/tokens/paths/audio) and
  truncated.

## 7. Bug report template

```
bug_id:
severity:            BLOCKER | HIGH | MEDIUM | LOW
area:                Assistant | Manuscript | Routing | Validation | Apply |
                     Cache | Navigation | Fullscreen | Export | Other
writing_mode:        novel | screenplay | graphic_novel | stage_script | series
section:             Manuscript | Outline | Notes | PSYKE | Timeline | Chat | Dexter
action:              Generate | Dialogue | Rewrite | Expand | Continue | Suggest | …
fake_provider_profile:
scenario_number:     (1–20 above, or describe)
expected_behavior:
actual_behavior:
applied_or_blocked:  (was Apply enabled? did anything auto-apply?)
state_stable:        (navigation/fullscreen/save-reload OK?)
reproduction_steps:
relevant_excerpt:    (REDACTED — no secrets/tokens/paths/raw audio)
screenshot:          (local path only; never commit screenshots)
suspected_area:      (e.g. assistant_contract.validate / route / UI cache)
```

Severity guide (matches `docs/WRITER_QA_AGENT_PLAN.md`): **BLOCKER** =
planning/meta/context usable as output, invalid/wrong-mode applyable, hidden
context in manuscript, data loss, fullscreen lock, manuscript reset, secret/raw
audio shown or stored. **HIGH** = wrong contract even if blocked, stale cache
replay, Chat ignores project/mode, empty applyable. **MEDIUM** = imperfect but
usable formatting, missing clarification. **LOW** = minor wording/layout.

## 8. What this does NOT cover

QA mode tests behavior/routing/validation/apply and (via a human/agent at the
GUI) real rendering, navigation, and fullscreen. It does **not** call real
models, so output *quality* is not assessed here, and it adds **no** cloud sync,
Memory Review UI, image generation, or UI redesign.
