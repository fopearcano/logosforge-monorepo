# Writer QA Sample Projects

Small, **non-production** project files for the **Local Writer QA Agent Mode**
(`docs/LOCAL_WRITER_QA_AGENT_SCRIPT.md`). They let a human or an external GUI /
computer-use writer agent open a real LogosForge project per writing mode and
exercise the Assistant (routing → validation → apply), Manuscript navigation,
and fullscreen — **without any real provider, network, cloud, or credentials**
(QA mode swaps in a deterministic fake provider; see `logosforge/qa_mode.py`).

These are **test fixtures, not user data and not app code.** They are safe to
commit. Generated QA logs / reports / screenshots are **not** (they are
git-ignored).

## Format

Each file is in the app's native interchange format (the one used by **Open
Project** and **Export → Full Project**): required keys `project`,
`characters`, `places`, `notes`, `scenes` (plus `psyke_entries`, `chapters`,
`outline`, `continuity`, `plot_timeline`). They load with the app's own
importer (`validate_import_data` + `import_json`). The writing mode is carried
by `project.narrative_engine` + `project.default_writing_format`.

## Files

| File | Mode / focus |
|------|--------------|
| `novel_sample.json` | Novel — prose Manuscript |
| `screenplay_sample.json` | Screenplay — INT./EXT. + CHARACTER cues |
| `graphic_novel_sample.json` | Graphic Novel — Act → Page → Scene → Panel |
| `stage_script_sample.json` | Stage Script — CHARACTER cues + (stage directions) |
| `series_sample.json` | Series — episode/scene Manuscript |
| `notes_psyke_sample.json` | Notes + PSYKE codex actions (extra notes & entries) |

Each project includes the recurring cast (**Ada North**, **Milo Voss**), the
**Threshold** theme, a minimal Manuscript for its mode, and a Unicode-stress
note. `notes_psyke_sample.json` adds planning/PSYKE seed notes and a second
codex entry for exercising the Notes and PSYKE assistant actions.

## How they are used

1. Enable QA mode: `LOGOSFORGE_QA_MODE=1` (default OFF).
2. Optionally pick a fake-provider profile, e.g.
   `LOGOSFORGE_FAKE_PROVIDER_PROFILE=invalid_planning_markdown`
   (default `valid_auto` → mode-correct valid content).
3. Open one of these files and run the scripted scenarios in
   `docs/LOCAL_WRITER_QA_AGENT_SCRIPT.md`.

No file here is ever modified by QA mode; copy a file first if you want to edit
freely.
