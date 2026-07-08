# LogosForge Whiteboard — Manuscript Syntax Guide

Whiteboard's editor is **plain text you type normally** — there's no hidden markup and no formatting toolbar to fight. A live formatter reads each line as you write and styles it for the current **writing mode**. Everything stays readable text, so your manuscript is never locked into a proprietary format, and switching modes just re-reads the same words a different way.

Pick the mode from the **Mode** dropdown in the toolbar. Whiteboard has four:

| Mode | Best for | Structure it thinks in |
|---|---|---|
| **Novel** | prose fiction | Acts › Chapters › Scenes |
| **Screenplay** | film / TV scripts (Fountain) | Acts › Sequences › Scenes |
| **Graphic Novel** | comic scripts | Chapters › Pages › Panels |
| **Stage Script** | theatre | Acts › Scenes › Beats › Stage Directions |

**How to read this guide:** each line below is one paragraph in the editor (press Enter for a new line). "Force" means you can override the auto-detection with a leading marker character.

---

## Universal — works in every mode

These inline annotations are recognised no matter which mode you're in:

| You type | Meaning |
|---|---|
| `[[a private note]]` | **Note** — dimmed, for yourself; not part of the prose |
| `@@Mara Vinter` | **PSYKE mention** — links to a character/place/lore entry in your story bible |
| `[read more](https://…)` or a bare `https://…` | **Link** |
| `TODO`, `FIXME`, `XXX` | **Flag** — highlighted so you can find unfinished spots |

Notes and PSYKE mentions are also fed to the AI (Billy / Logos) as context, so they're a good way to leave yourself — and the assistant — reminders.

---

## Novel

Prose fiction. You mostly just write; formatting is for structure and emphasis.

**Headings / structure** — use the **Format ▾** menu, or type the Markdown shortcut at the start of a line:

| Format menu | Shortcut | Result |
|---|---|---|
| Title | `# ` | Chapter / part title (H1) |
| Heading | `## ` | Section heading (H2) |
| Subheading | `### ` | Sub-section (H3) |
| Body text | — | normal paragraph |

**Emphasis** — select the text and press **Ctrl/Cmd + B** (bold) or **Ctrl/Cmd + I** (italic). Novel emphasis is true rich text (WYSIWYG) — there are no `*asterisks*` to type.

**Dialogue** — text inside straight `"…"` or curly `“…”` quotes is auto **colour-coded** so speech stands out from narration. (Toggle this with **Colour-code text** in the editor settings; it's on by default.)

**Lists & tasks** (highlighted inline):

```
- a bullet point
* also a bullet
- [ ] an unchecked task
- [x] a done task
```

**Tags** — `#theme` or `@character` anywhere in a line are highlighted as tags.

---

## Screenplay (Fountain)

Whiteboard's screenplay mode reads **Fountain**, the plain-text screenplay standard. Type naturally and it formats to industry layout; the markers below only matter when you want to force or fine-tune something.

### Elements

| Element | How to write it | Example |
|---|---|---|
| **Scene heading** | line starts with `INT.`, `EXT.`, `EST.`, `INT./EXT.`, `I/E.` | `INT. FERRY - NIGHT` |
| — *force* any line | leading `.` (dot) | `.ROOFTOP - DAWN` |
| **Action** | any ordinary line | `The rain hasn't stopped for days.` |
| — *force* | leading `!` | `!lowercase action line` |
| **Character cue** | an ALL-CAPS name on its own line (≤ 3 words), with a real line beneath it | `MARA` |
| — *force* | leading `@` (keeps lowercase / odd names) | `@McClane` |
| — with extension | add `(V.O.)`, `(O.S.)`, `(CONT'D)` | `MARA (V.O.)` |
| **Dialogue** | the line(s) directly under a cue | `It's keeping time.` |
| **Parenthetical** | `(…)` on its own line under a cue | `(whispering)` |
| **Dual dialogue** | add `^` after the *second* speaker's cue | `SARAH ^` |
| **Transition** | short line ending in `TO:` | `CUT TO:` |
| — *force* | leading `>` | `> SMASH CUT` |
| **Centered** | wrap the line in `>` … `<` | `>THE END<` |
| **Section** (outline only, not printed) | `#`, `##`, `###` | `## Act Two` |
| **Synopsis** (not printed) | leading `=` | `= Mara learns the truth` |
| **Note** (not printed) | `[[ … ]]` | `[[check the ferry timetable]]` |
| **Lyrics** | leading `~` | `~And the tide rolls low` |
| **Page break** | a line of three or more `=` | `===` |

### Emphasis (inline)

| You type | Renders as |
|---|---|
| `*italic*` | *italic* |
| `**bold**` | **bold** |
| `***bold italic***` | ***bold italic*** |
| `_underline_` | underline |

### Title page

At the **very top** of the script, `Key: Value` lines become a formatted title page. Recognised keys include **Title, Credit, Author, Source, Draft date, Contact, Copyright**. End the block with a blank line; continuation lines are indented.

```
Title: The Sounding
Credit: Written by
Author: Fern Arcano
Draft date: 8 July 2026
```

### Cut a passage without deleting it

Wrap text in `/* … */` (the **boneyard**) to omit it from the script — it can span several lines and stays in your document, just dimmed and unformatted.

> **Forgiving by design:** single-spaced scripts still format — a fresh ALL-CAPS cue is recognised right after a dialogue line even without a blank line between. And emphatic ALL-CAPS lines like `SUDDENLY`, `THE END`, `CUT`, `BEAT` are *not* mistaken for character names.

---

## Graphic Novel

Comic scripts, organised into pages and panels.

| Element | How to write it | Example |
|---|---|---|
| **Page** | `PAGE ONE` / `PAGE 1` (short, ALL-CAPS or numbered), or a **Heading** (H1/H2) | `PAGE ONE` |
| **Panel** | `PANEL 1` / `PANEL ONE`, or a **Subheading** (H3) | `PANEL 3` |
| **Panel description** | any ordinary line | `Mara stands at the rail, lantern swinging.` |
| **Caption** | `CAPTION:` — optionally with a speaker | `CAPTION (Narrator): Years later…` |
| **Sound effect** | `SFX:` (also `SOUND:` / `FX:`) | `SFX: KRAKOOM` |
| **Dialogue — cue + speech** | speaker on one line, speech below (like screenplay) | `MARA`  ⏎  `It's keeping time.` |
| **Dialogue — inline** | speaker and speech on one line | `MARA: It's keeping time.` |
| **Parenthetical** | `(…)` under a cue | `(under her breath)` |

Only confident matches are formatted — a line like "Page after page, she read." or ordinary description prose is **never** mistaken for a page marker or a dialogue cue.

---

## Stage Script

Theatre scripts — character cues and dialogue are centred; stage directions read as italic action.

| Element | How to write it | Example |
|---|---|---|
| **Scene heading** | a line starting `ACT`, `SCENE`, `PROLOGUE`, `EPILOGUE`, `INTERMISSION`, `INTERVAL`, `CURTAIN` — or a **Heading** | `ACT I, SCENE 1` |
| **Character cue** | a short name on its own line (a trailing `:` is fine), with a line beneath it | `MARA:` or `MARA` |
| **Dialogue** | the line directly under a cue | `The clock's still keeping time.` |
| **Stage direction** | a parenthetical `(…)` | `(she crosses to the window)` |
| **Action** | any other line | `A long silence. The lights dim.` |

As with the other script modes, only clear cues are detected, so descriptive stage prose is never accidentally centred as a character name.

---

## Tips

- **Nothing is destructive.** Formatting is a live *reading* of your plain text — you can always see and edit the raw words, and switching modes re-interprets the same text.
- **Autocomplete (Screenplay):** once you've named characters, scene headings, or transitions, Whiteboard suggests them as you type.
- **Invisible markers:** in Screenplay, the forcing/emphasis markers (`.`, `>`, `*`, `_`) can be dimmed or hidden via the editor settings so the page reads clean.
- **Outline ↔ manuscript:** you can hard-link an outline node to any passage (⚓) so you always know which section you're writing in — see the outline panel's ⋯ menu.

*This guide reflects the syntax the editor actually recognises. If a pattern here doesn't behave as described, it's a bug worth reporting.*
