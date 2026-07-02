# Writer QA Agent — Plan & Harness

> A systematic "writer/tester" that uses LogosForge the way an author would and
> reports Assistant / routing / validation / cache / apply failures — instead of
> patching described symptoms. **Behavior testing, not code-style testing.**

LogosForge principle (unchanged): *the model generates; LogosForge remembers,
retrieves, structures, updates, and syncs.* The Writer QA Agent verifies that
the Assistant behaves like a usable writing system across sections, modes,
actions, and targets.

## Three testing levels

**Level 1 — Headless internal harness (implemented).** Runs in CI/local with a
deterministic **fake provider**. Drives the real Assistant contract layer
(`logosforge.assistant_contract`: `route` → `validate` → `cache_key`) over a
scenario matrix and emits bug reports. Fast, deterministic, no GUI, no network.
Files: `tools/writer_qa/` (`fake_provider`, `scenarios`, `validators`,
`reporting`, `run_writer_qa`) + `tests/test_writer_qa_harness.py`.

**Level 2 — App/API harness (planned).** Requires a running LogosForge and a
**test-only** interface to open projects, switch sections, set targets, invoke
the assistant, and inspect document/UI state. Preferred over raw GUI for
regression (deterministic, inspectable). Proposed commands:
```
logosforge qa open-project <path>      logosforge qa assistant-action <action> --instruction "..."
logosforge qa switch-section <section> logosforge qa get-response / validate-response
logosforge qa set-mode <mode>          logosforge qa apply-response <copy|replace|insert|append>
logosforge qa select-target <id>       logosforge qa get-document-state / get-ui-state
logosforge qa run-scenario <id>
```
Not implemented here (kept out of production by default); documented for a later,
opt-in test build.

**Level 3 — GUI computer-use writer agent (optional, local only).** Runs on the
user's PC/macOS, opens the real app, types writer requests, screenshots
responses, records failures. Useful for final human-like acceptance; slower and
less deterministic, so it must follow a scripted checklist
(`docs/LOCAL_WRITER_QA_AGENT_SCRIPT.md`, `docs/ASSISTANT_BEHAVIOR_MANUAL_TEST.md`).
PySide/`pytest-qt` for the Qt app, or an OS-level computer-use agent. The GUI
automation itself is not bundled (it is fragile and environment-specific), but
the **local QA mode it depends on is implemented** (below).

## Local QA mode (implemented)

`logosforge/qa_mode.py` makes the real app testable end-to-end **with no real
provider, network, cloud, or credentials** — so an external GUI/computer-use
writer agent (or a human) can drive the real UI deterministically.

- **OFF by default.** Enabled only by `LOGOSFORGE_QA_MODE` in {1,true,yes,on}.
- **Deterministic fake provider, reachable only in QA mode.** `chat_completion`
  short-circuits to `qa_mode.fake_completion` *before* any credential/network
  use; disabled → behavior is byte-for-byte unchanged. Profile selection:
  settings key `qa_fake_provider_profile` → env `LOGOSFORGE_FAKE_PROVIDER_PROFILE`
  → default `valid_auto` (mode-correct valid content). Profiles A–O cover valid
  per mode/section, planning/context/meta/wrong-mode/empty/secret-leak, and a
  provider error.
- **Redacted structured logging.** Each assistant response logs a redacted event
  (section/mode/action/target/output_kind/validation/apply) under
  `logs/writer_qa/`; secrets, tokens, local/OS paths, and raw audio are redacted
  and long content truncated — raw manuscripts are never written verbatim.
- **Report export.** `qa_mode.export_report()` and the test-only CLI
  `tools/writer_qa/export_local_report.py` write
  `reports/writer_qa/local_latest.{json,md}` (git-ignored).
- **Sample projects.** `sample_projects/writer_qa/` (one per mode + a Notes/PSYKE
  fixture) load via the app's own importer.
- **Agent script.** `docs/LOCAL_WRITER_QA_AGENT_SCRIPT.md` (setup, role, rules,
  20 scenarios, bug template). Tests: `tests/test_local_writer_qa_mode.py`.

## Setup options

- **A. GitHub-only / CI:** Level 1 headless harness + static tests. Catches
  contract / routing / validation / cache / apply failures. Cannot perceive real
  GUI rendering or fullscreen.
- **B. Local PC:** run the app with **local QA mode** (`LOGOSFORGE_QA_MODE=1`,
  fake provider — no real provider/network/keys) + the Level 1 harness;
  optionally let a computer-use agent operate the GUI (Level 3) and collect
  redacted logs/reports. See `docs/LOCAL_WRITER_QA_AGENT_SCRIPT.md`.
- **C. Internal API:** add the Level-2 test-only commands (preferred over raw
  GUI for reliability).

## Security / safety

Test projects only · no real provider keys · no real provider/network calls ·
no cloud sync · no GitHub writes · no private manuscripts · writes only under the
chosen `--report` path (never destructive outside a temp/report workspace).

## Writer QA Agent personas

Novelist · Screenwriter · Graphic novelist · Stage dramatist · Series showrunner
· Notes-heavy planner · PSYKE/codex user · Voice/Dexter (text transcript). Each
issues realistic requests ("continue this scene", "rewrite this dialogue",
"expand this paragraph", "generate next panel", "create a character profile",
"turn these notes into outline", "continue the current episode", "format this
transcript") and judges: right mode? right section? usable content? planning/
meta/context leak? formatting preserved? apply safe? state stable?

## Scenario matrix

`tools/writer_qa/scenarios.py` covers Manuscript (all 5 modes × Generate /
Rewrite / Expand / Dialogue + Suggest), Outline, Notes, PSYKE, Timeline, Chat
(direct / structure / analysis / clarification), and Dexter text — crossed with
provider response profiles: valid (per mode/section), invalid planning markdown,
invalid context dump, invalid meta reasoning, wrong mode, empty, and provider
error. Each scenario declares the **expected** output kind, validator status,
and apply allowance; a bug is emitted only when the system's actual behavior
diverges from the safe expectation.

## Severity rules

- **BLOCKER:** direct writing returns planning/meta/context as usable output;
  invalid/wrong-mode output is applyable; hidden context leaks into manuscript;
  data loss; fullscreen lock; manuscript reset; secret/raw-audio shown/stored.
- **HIGH:** wrong contract (even if blocked); stale cache replay; unreliable
  routing; Chat ignores project/mode; empty output applyable.
- **MEDIUM:** imperfect-but-usable formatting; missing clarification; verbose
  suggestions. **LOW:** minor wording/layout.

## Bug report format

`reports/writer_qa/latest.json` (machine) + `latest.md` (human). Each bug:
`bug_id, severity, area, writing_mode, section, action, target, scenario_name,
expected_behavior, actual_behavior, validator_result, cache_result, apply_state,
reproduction_steps, relevant_response_excerpt, suspected_root_cause,
suggested_fix_area, test_name, timestamp`. (Generated files are git-ignored; the
directory is kept via `.gitkeep`.)

## Running it

```
python tools/writer_qa/run_writer_qa.py --suite alpha  --report reports/writer_qa/latest
python tools/writer_qa/run_writer_qa.py --suite assistant
python tools/writer_qa/run_writer_qa.py --suite manuscript
```
Exit code is non-zero when BLOCKER findings exceed `--max-blocker` (default 0),
so it can gate CI. `--max-high N` optionally also gates on HIGH.

## Current findings (first run, 69 scenarios)

The harness immediately surfaced real validator gaps to fix next (it does **not**
fix them — this task only builds the harness):

- **BLOCKER ×5 — wrong-mode output is applyable.** A prose response in a
  Screenplay/Graphic-Novel/Stage/Series/(novel-as-screenplay) slot passes the
  marker validator (no forbidden markers) and is apply-eligible. Fix area:
  `assistant_contract.validate` (add mode-format checking, e.g. reuse
  `tools/writer_qa/validators.mode_format_ok`).
- **HIGH ×5 — empty output is applyable.** An empty response validates as
  "valid" and is apply-eligible. Fix area: `assistant_contract.validate`
  (reject empty/whitespace direct content).
- **MEDIUM ×1 — Chat with no target does not clarify.** A Chat "continue the
  scene" with no target routes to direct content instead of asking a short
  clarification. Fix area: `assistant_contract.route` (extend
  `needs_clarification` to Chat write intents without a target).

## Relationship to Alpha

Writer QA (Level 1) should run before Alpha release confirmation. GitHub-only
testing catches contract/cache/validation failures but **not** all GUI/render/
fullscreen issues — Level 2/3 (local PC) are recommended for final human-like
acceptance.
