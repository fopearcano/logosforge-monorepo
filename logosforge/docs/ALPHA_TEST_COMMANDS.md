# Alpha — Test Commands

Reproducible verification commands for the Alpha Release Candidate. All commands
run headless (Qt offscreen). Run from the repository root with the project's
virtualenv active.

```bash
export QT_QPA_PLATFORM=offscreen      # headless Qt (no display needed)
```

## 1. Focused Alpha Release Gate

The single cross-mode integrity suite (fast):

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_alpha_release_gate.py -q -p no:cacheprovider
```

Expected: **35 passed** (~5s).

## 2. Broad certification sweep

The blast-radius sweep used for the Alpha gate — every writing mode + cross-cutting
surface. This is the authoritative green check:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest \
  tests/test_alpha_release_gate.py tests/test_logos_integration.py \
  tests/test_series_phase1.py tests/test_series_phase2.py tests/test_series_phase3.py \
  tests/test_series_phase4.py tests/test_series_phase5.py tests/test_series_phase6.py \
  tests/test_series_phase7.py tests/test_series_phase8.py \
  tests/test_screenplay_phase1.py tests/test_screenplay_phase2.py tests/test_screenplay_phase3.py \
  tests/test_screenplay_phase4.py tests/test_screenplay_phase5.py tests/test_screenplay_phase6.py \
  tests/test_screenplay_phase7.py tests/test_screenplay_phase8.py tests/test_screenplay_phase9_integration.py \
  tests/test_screenplay_phase10_ux.py tests/test_phase10b_screenplay_blocks.py tests/test_phase10f_screenplay_export.py \
  tests/test_graphic_novel_phase1.py tests/test_graphic_novel_phase2.py tests/test_graphic_novel_phase3.py \
  tests/test_graphic_novel_phase4.py tests/test_graphic_novel_phase5.py tests/test_graphic_novel_phase6.py \
  tests/test_graphic_novel_phase7.py tests/test_graphic_novel_phase8.py \
  tests/test_stage_script_phase1.py tests/test_stage_script_phase2.py tests/test_stage_script_phase3.py \
  tests/test_stage_script_phase4.py tests/test_stage_script_phase5.py tests/test_stage_script_phase6.py \
  tests/test_stage_script_phase7.py tests/test_stage_script_phase8.py \
  tests/test_multi_mode_integrity.py tests/test_writing_mode_integrity.py tests/test_phase9_writing_modes.py \
  tests/test_structure_invariant.py tests/test_structure_integration.py tests/test_timeline_canonical_order.py \
  tests/test_project_isolation_p0.py tests/test_project_switch_isolation.py \
  tests/test_manuscript_outline_separation.py tests/test_outline_mode.py \
  tests/test_timeline_mode_display.py tests/test_notes_context.py tests/test_psyke_project_isolation.py \
  tests/test_logos_toolbar_dropdown.py tests/test_logos_phase0.py \
  -q -p no:cacheprovider
```

Expected: **1527 passed, 0 failures** (~5 min in the gate environment).

## 3. Per-mode test groups

Run a single mode's phase suites:

```bash
# Series (Phases 1–8)
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_series_phase*.py -q -p no:cacheprovider

# Stage Script (Phases 1–8)
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_stage_script_phase*.py -q -p no:cacheprovider

# Graphic Novel (Phases 1–8)
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_graphic_novel_phase*.py -q -p no:cacheprovider

# Screenplay (Phases 1–10)
QT_QPA_PLATFORM=offscreen python -m pytest tests/test_screenplay_phase*.py "tests/test_phase10*screenplay*.py" -q -p no:cacheprovider
```

## 4. Cross-cutting groups

```bash
# Mode integrity + structure invariant + isolation
QT_QPA_PLATFORM=offscreen python -m pytest \
  tests/test_multi_mode_integrity.py tests/test_writing_mode_integrity.py \
  tests/test_structure_invariant.py tests/test_project_isolation_p0.py \
  tests/test_project_switch_isolation.py tests/test_psyke_project_isolation.py \
  -q -p no:cacheprovider
```

## Notes on optional-dependency behavior

- **PDF / DOCX export** requires optional packages (`reportlab` / `python-docx`).
  When absent, the app shows a readable "install …" message and other export
  formats still work; the related optional-export tests degrade/skip gracefully
  rather than fail. This is expected and **not** a release blocker.
- A non-Windows **"Segoe UI" font warning** is harmless (font fallback applies).

## Complete suite

The complete release gate runs every test module in its own Python process.
This preserves all test coverage while giving Qt modules a fresh
`QApplication` and native heap:

```bash
QT_QPA_PLATFORM=offscreen python tools/run_pytest_modules.py
```

The runner discovers both standard pytest module patterns recursively, executes
each module exactly once in deterministic path order, and reports all failed
modules after the remaining modules have run. Successful child output is hidden
to keep CI logs compact; failure output and native faulthandler diagnostics are
retained.

Avoid replacing this gate with one monolithic `python -m pytest` process. The
desktop suite intentionally exercises thousands of Qt object lifecycles, and a
native lifetime fault in one module can otherwise surface much later in an
unrelated test.
