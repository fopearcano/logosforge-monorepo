# Alpha Manual Release Confirmation — LogosForge Desktop 0.9.0-alpha

**Status values:** PASS · FAIL · PARTIAL · NOT TESTED · BLOCKED.
An item is PASS only when directly tested or explicitly confirmed by the
user. Automated evidence alone never marks a *manual* item PASS.

## 1. Release candidate metadata

- Product: Logosforge — local-first creative writing system (Desktop Alpha).
- Version: `0.9.0-alpha` (`logosforge/__init__.py`).
- Branch: `claude/setup-logosforge-app-5cVxF`
  (mirror of `claude/sweet-sagan-0Zwgc`; refs identical).
- Candidate commit: `439a68a` (clean tree).
- Existing tags: **none**.
- Entry point: `run.py`.

## 2. Automated gate summary (machine-verified — PASS)

Final Alpha RC re-certification at this tree (2026-06-11): broad
certification sweep **1527** + full voice/Dexter + language **638** +
Phase-2 verification matrix **740** = **2905 passed, 0 failures**, plus the
session's prior gates (GN refactor, multi-language, scope cleanup, shared-
renderer Phase 2 — all classification A; see `docs/ALPHA_RC_STATUS.md`).
Confirmed by automation: GN Manuscript = shared `WritingCoreView`, GN
Outline = shared `PlanView` GN schema (Act → Page → Scene → Panel); legacy
Comics-Script/page-manager/tree renderers unreachable and unconstructed;
Pages inert; mode lock, isolation, dirty close-save, exports clean of
secrets/image/UI metadata; Dexter local-only, preview-first, no grammar;
UI English-only; grammar deferred; Unicode/CJK/RTL round-trips; alpha gate
**35 passed** re-run at confirmation time.

## 3. Manual checklist (requires a human on a real machine)

| # | Check | Status | Notes |
|---|-------|--------|-------|
| A | Real microphone / Dexter (capture → transcript → edit → commit to Manuscript + GN Panel → Billy preview → explicit Apply; graceful no-mic/no-model; no grammar action; no audio off-machine) | NOT TESTED | Headless CI cannot drive audio. Automated equivalents green (mock/local backends, commit router, privacy scans). |
| B | macOS fullscreen / window safety (all sections incl. GN Manuscript/Outline, add Act/Page/Scene/Panel, Manuscript↔Outline switching; no minimize/disappear; Pages absent/inert) | NOT TESTED | Qt offscreen cannot reproduce macOS Spaces. Automated equivalents green (no parentless windows, no minimize calls, Pages never mounted). |
| C | Optional-dependency exports (pip install -r requirements.txt → PDF/reportlab + DOCX/python-docx work or degrade gracefully; Markdown/TXT/Fountain/JSON; GN export Act→Page→Scene→Panel, no dupes/secrets/old-UI/image metadata) | NOT TESTED | CI lacks reportlab/python-docx — graceful-degradation paths are the ones automated. Visual PDF/DOCX output needs eyes. |
| D | Graphic Novel real UI (no Comics Script / PAGE-manager / Delete-Page / +Panel-header / +Add-Page chrome; shared editor blocks Act/Page/Scene/Panel; five semantic panel fields; shared block/card Outline, chapter absent; mirroring; save/reload; Pages inert; no minimize) | NOT TESTED | All items have green automated pins; the screenshot-level acceptance is the human call this gate exists for. |
| E | Multilingual/Unicode spot check (zh/ja/ar/mixed strings in Manuscript + GN Panel; save/reload; UTF-8 exports; PDF glyph behavior; UI stays English; Dexter "Use project language") | NOT TESTED | Automated round-trips green incl. the exact strings; PDF glyph rendering needs visual confirmation. |

## 4. Release blockers

**None found by automation.** Blocker policy (per
`docs/ALPHA_MANUAL_SMOKE_TEST.md`): startup/save/dirty/isolation/mode-lock
breakage, any reachable legacy GN UI, GN Panel data loss, Manuscript not
deriving from Outline, broken Series hierarchy, raw audio to AI/cloud,
auto-apply, Unicode corruption, Pages minimize regression, export crash,
secret leaks. All have green automated pins; a manual FAIL on any of these
re-opens the gate.

## 5. Non-blocking limitations (documented)

Grammar/deep text correction deferred (future Review/Correction phase) ·
UI localization deferred (English-only Alpha) · imperfect Whisper
transcription (model/mic dependent) · PDF Unicode glyph coverage depends on
system/ReportLab fonts (no fonts bundled) · RTL layout polish partial (text
storage/edit/export safe) · ComfyUI/image generation, Canvas Plot,
standalone Pages, cloud/web/sync deferred · legacy GN view modules retained
unreachable pending safe deletion.

## 6. Tag-readiness

- Working tree: clean at `439a68a`; both branch refs identical; no tags.
- Release notes / changelog / Alpha docs: current through the final
  re-certification (see `RELEASE_NOTES_ALPHA.md`, `CHANGELOG.md`,
  `docs/ALPHA_RC_STATUS.md`, `docs/PORTING_ARCHITECTURE_ALPHA.md`).
- **Recommended tag name:** `v0.9.0-alpha.1` (first tag; matches the
  `0.9.0-alpha` metadata).
- Prepared commands — **DO NOT RUN until the user says exactly `TAG IT`**:

```bash
git tag -a v0.9.0-alpha.1 -m "LogosForge Desktop Alpha RC v0.9.0-alpha.1"
git push origin v0.9.0-alpha.1
```

- Prepared rollback — do not run:

```bash
git tag -d v0.9.0-alpha.1
git push origin :refs/tags/v0.9.0-alpha.1
```

- Gate to tagging: all §3 manual items must be PASS (or explicitly
  user-approved as accepted-pending), and the user must say `TAG IT`.

## 7. Final user confirmation

- [ ] Manual check A (microphone/Dexter): ________
- [ ] Manual check B (macOS fullscreen): ________
- [ ] Manual check C (optional exports): ________
- [ ] Manual check D (Graphic Novel real UI): ________
- [ ] Manual check E (Unicode/PDF spot check): ________
- [ ] **User authorization to tag (`TAG IT`):** ________

Signed off by: ____________________  Date: ____________


## Manuscript navigation + fullscreen stability (manual)

> See `docs/ALPHA_UI_STABILITY_NOTES.md`. Mark PASS only when directly tested.

1. [ ] Open a sample Screenplay project → Manuscript; type a line: ____
2. [ ] Switch to Outline, back to Manuscript — line remains: ____
3. [ ] Switch to Notes, back — line remains: ____
4. [ ] Switch to Assistant, back — line remains; scroll/focus acceptable: ____
5. [ ] Enter full screen (View → Toggle Full Screen / F11 / native control): ____
6. [ ] In full screen: type, switch sections, return — text + render OK: ____
7. [ ] Exit full screen (View → Exit Full Screen / native) — app exits cleanly: ____
8. [ ] Toggle full screen 3× — no lock; main navigation stays visible: ____
9. [ ] Save + reload — text persists: ____
10. [ ] Graphic Novel Manuscript (full screen) uses shared renderer; old page manager absent: ____
11. [ ] Graphic Novel Outline uses shared block/card outline; standalone Pages disabled: ____
12. [ ] Dexter opens after full screen; no raw-audio/memory side effect: ____

13. [ ] Writer QA harness run, **0 BLOCKER**: `python tools/writer_qa/run_writer_qa.py --suite all`: ____
14. [ ] Local QA mode (`LOGOSFORGE_QA_MODE=1`) drives the real UI with the fake
    provider — no real provider/network/keys; run the 20-scenario script in
    `docs/LOCAL_WRITER_QA_AGENT_SCRIPT.md` (planning leak blocked, secret
    withheld, empty/provider-error handled, navigation + fullscreen stable);
    confirm QA mode is OFF by default: ____
