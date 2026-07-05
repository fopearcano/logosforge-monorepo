# LogosForge Whiteboard — User Guide

LogosForge Whiteboard is a focused, offline-first **writing workstation** for long-form narrative. It supports four formats — **Novel, Screenplay, Graphic Novel, and Stage Play** — and pairs a distraction-light editor with three planning surfaces (Outline, Story Map, and the PSYKE story bible), inline Comments, and an optional local or cloud AI assistant.

This is the deep guide. For a one-page cheat sheet, see **[QUICK_START.md](QUICK_START.md)** (also available inside the app via the **?** button, top-right).

> **Keys are written for Windows.** On **macOS**, use **⌘ Cmd** wherever you see **Ctrl**.

---

## Contents

1. [Installing & first run](#1-installing--first-run)
2. [How it stores your work](#2-how-it-stores-your-work)
3. [Documents](#3-documents)
4. [Writing modes](#4-writing-modes)
5. [The editor](#5-the-editor)
6. [The Outline](#6-the-outline)
7. [The Story Map](#7-the-story-map)
8. [PSYKE — the story bible](#8-psyke--the-story-bible)
9. [Comments](#9-comments)
10. [AI — Billy & Logos](#10-ai--billy--logos)
11. [Import](#11-import)
12. [Export & backup](#12-export--backup)
13. [Themes & focus](#13-themes--focus)
14. [Full hotkey reference](#14-full-hotkey-reference)
15. [Data location & backup](#15-data-location--backup)
16. [Moving a project to LogosForge Pro](#16-moving-a-project-to-logosforge-pro)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Installing & first run

Download the build for your platform from the Releases page:

- **Windows** — the installer (`LogosForge.Whiteboard-<version>-x64.exe`) or the portable build (`…-x64-portable.exe`).
- **macOS (Intel)** — the disk image (`LogosForge.Whiteboard-<version>-x64.dmg`).

The builds are currently **unsigned**, so the OS will warn on first launch:

- **Windows** — SmartScreen may say "Windows protected your PC." Choose **More info → Run anyway**.
- **macOS** — Gatekeeper will block an unsigned app. After copying it to Applications, clear the quarantine flag (recursively — this matters, or the bundled engine won't start):

  ```bash
  xattr -cr "/Applications/LogosForge Whiteboard.app"
  ```

  Then open it normally. If the Dock shows a stale icon, `killall Dock` refreshes it.

Everything runs **locally** — the app bundles its own writing engine. No account, no internet connection required (AI is optional and points wherever you tell it).

---

## 2. How it stores your work

Whiteboard is **database-backed**, like a project workspace — not a file-per-document editor. This is the single most important thing to understand:

- **Everything auto-saves.** As you type, edits are written to the app's local store within a second. The **"Draft saved"** note near the top-right is your save indicator. There is no "Save" button because you never need one.
- **Your work is safe across sessions and switches.** Close the app, reopen it — your documents, outlines, comments, and characters are exactly as you left them. Switch between documents freely; nothing is lost.
- **Files are for sharing, not storing.** *Import* brings text in; *Export* sends a copy out. Neither is where your work "lives" — the app is.

See [Data location & backup](#15-data-location--backup) for where the store sits on disk and how to back it up.

---

## 3. Documents

Each **document** is an independent project with its own manuscript, outline, comments, and PSYKE bible. Manage them from the **File** menu (top-left):

| Action | What it does |
|---|---|
| **New Document** | Creates a fresh, blank project and switches to it. Your previous document is untouched. (`Ctrl+N`) |
| **Open Document** | Lists every document — click one to switch. The current one is marked ✓; each has a **×** to delete. |
| **Rename current document…** | Opens a small dialog to rename the active document. |
| **Delete** | The **×** next to a document removes it *and* its outline, comments, and story bible — this can't be undone, so it asks first. |

The **project name at the top** is also a quick document switcher (click it for the list). Both places are just two doors to the same library.

Two projects are fully isolated: a character named "Mara" created in Project A never appears in Project B.

---

## 4. Writing modes

The **Mode** dropdown (top toolbar) sets how the current document is formatted:

- **Novel** — flowing prose. Paragraphs, chapter/section headings, real *italic* and **bold**, optional dialogue colour-coding.
- **Screenplay** — industry formatting via **Fountain**. Scene headings, action, character cues, dialogue, parentheticals, transitions, dual dialogue, lyrics, notes and boneyard. A live **Preview** paginates it like a real script (`Ctrl+Shift+E`).
- **Graphic Novel** — pages, panels, and captions/dialogue.
- **Stage Play** — stage directions, character cues, dialogue, and cues.

Switching mode **reformats the current document in place** — the text stays, but the structure is re-read for the new format. Because that's permanent and easy to trigger by accident, the app **asks first** whenever the document already has text. (New or empty documents switch freely.) If you want a different format for a *different* story, make a **New Document** instead.

---

## 5. The editor

The centre pane is your writing surface. It formats as you type, so what you see reflects the current mode.

**Prose (Novel / notes):** Standard rich text — `Ctrl+B` bold, `Ctrl+I` italic, `Ctrl+U` underline. Headings become chapter/section markers and feed the outline.

**Screenplay:** A true inline Fountain editor. `Tab` runs autocomplete and cycles the element type (scene heading → action → character → dialogue…). Emphasis markers wrap with `Ctrl+B/I/U`. Add a **note** with `Ctrl+Alt+N` (`[[ … ]]`) or send text to the **boneyard/omit** with `Ctrl+Alt+O`. Centre a line with `Ctrl+\`. Turn on **Preview** (`Ctrl+Shift+E`) for an accurate, paginated read with a title page; `Esc` exits.

**View controls:** Zoom the page with `Ctrl+=` / `Ctrl+-`, reset with `Ctrl+0`.

**Nerd Mode (optional editor aids, all off by default):**

- **Line numbers** — `Ctrl+L`
- **Code folding** — `Ctrl+Shift+F`
- **Syntax highlighting** — `Ctrl+Shift+H`

---

## 6. The Outline

The left panel holds your **manual story structure** — separate from, and richer than, the document's own headings. It's a Dynalist-style tree of typed nodes.

**Two views** (toggle at the top of the panel):

- **Outline** — the editable, persisted story outliner (this is the one you build).
- **From Document** — a read-only navigator derived from the current manuscript (headings, scene headings, synopses); click an entry to jump there.

**Building structure:**

- **+ Add ▾** is a split button. The main button adds an item at the current level; the **▾** menu lets you add a specific **type** — *Act, Part, Chapter, Sequence, Scene, Beat, Custom* — which **auto-nests** by rank (add a Scene while an Act is selected and it becomes the Act's child).
- **Structure templates** (in the ▾ menu → *Structure templates…*) bootstrap a whole skeleton from a proven method: **Three-Act, Save the Cat!, Hero's Journey, Story Circle, Seven-Point, Freytag's Pyramid, Kishōtenketsu**. Append to your outline or replace it.

**Editing each item:**

- Hover a row for inline pickers — **type**, **status** (To do / Drafting / Revised / Done), and a **colour** label.
- **Drag** to reorder: dropping on the top/bottom third makes a sibling, the middle third nests it as a child.
- **Multi-select** with `Ctrl`-click (or `Shift`-click for a range) then batch-set status/colour or delete.
- **Zoom (hoist)** into any item with `Ctrl+]` to focus on its subtree; `Ctrl+[` climbs back out.
- **Search / filter** (the search box) by title, `#tag`, type, status, or colour.
- **Reveal in editor** (row ⋯ menu) jumps to the matching passage in the manuscript.

The full keyboard model for the outline is in the [hotkey reference](#14-full-hotkey-reference).

---

## 7. The Story Map

The strip along the bottom is a **visual overview** of the story, derived from the document's structure (acts → chapters/sequences → scenes → beats). Nodes are **tinted with your outline's colour labels** where titles match, so your colour-coding carries across. Click a node to jump to that part of the manuscript. Toggle it with `Ctrl+Shift+M`.

---

## 8. PSYKE — the story bible

**PSYKE** is your project's reference of everything that isn't prose: **characters, places, objects, lore, and themes** (plus a catch-all *other*). Open it with `Ctrl+Shift+P`.

- Each entry has a **name**, a **type**, a **description**, and **notes**.
- Search the bible by name/alias/notes.
- PSYKE is **scoped to the document** — every project has its own isolated bible, so casts never bleed between stories.

---

## 9. Comments

Comments are inline notes pinned to a span of text — for revision passes, editorial feedback, or reminders.

- **Add:** select text in the editor; a floating **Comment** button appears above the selection — click it and type your note.
- **Threads:** each comment can take replies. Submit a comment or reply with `Ctrl+Enter`.
- **Resolve:** mark a comment resolved once it's handled; resolved comments can be hidden.
- **Panel:** toggle the comments side panel with `Ctrl+Shift+C`.

Comments are anchored to the quoted text, so they follow it as you edit (and are cleaned up if the passage they point to is deleted).

---

## 10. AI — Billy & Logos

The AI is **optional** and **bring-your-own-endpoint** — nothing is sent anywhere unless you configure a provider.

- **Billy** — a hovering **chat** assistant for open-ended help. Toggle with `Ctrl+Shift+B`.
- **Logos** — works **inline and in context** (on your current selection / section) for surgical suggestions. Toggle with `Ctrl+Shift+L` (or `Ctrl+K`).

**Configure it** in **Settings ⚙** (top-right):

- **Provider** — LM Studio, Ollama, OpenAI, or Anthropic.
- **Base URL** — the endpoint (a **Default** button fills the standard URL for the chosen provider — e.g. `http://localhost:1234/v1` for LM Studio).
- **Model**, **API key** (write-only; blank keeps the stored one), and **Timeout**.
- **Test connection** saves the form and round-trips a trivial prompt so you can confirm the provider actually responds.

For fully offline AI, run a local server (LM Studio or Ollama) and point the Base URL at it.

---

## 11. Import

**File → Import** brings external text into the **current** document. On import you choose **Replace** (swap the document) or **Append** (add to the end).

| Format | Notes |
|---|---|
| **Text** (`.txt`) | One block per line; `#` lines become headings. |
| **Markdown** (`.md`) | As above; Markdown is preserved as text. |
| **Fountain** (`.fountain`) | Switches the document to Screenplay. |
| **Final Draft** (`.fdx`) | Extracts the screenplay and switches to Screenplay. |
| **LogosForge** (`.logosforge`) | The app's JSON export (manuscript + outline). |

---

## 12. Export & backup

**File → Export** writes a copy of the current document to a file.

| Format | Contains |
|---|---|
| **Export Project** (`.lfbundle`) | **The whole project** — manuscript, outline, comments, and PSYKE — in one file. Your backup, and the file you hand to LogosForge Pro. |
| Text / Markdown / Fountain | The manuscript as text. |
| HTML | A styled, self-contained web page of the manuscript. |
| JSON | Title, mode, and raw blocks. |
| LogosForge (`.logosforge`) | Manuscript + outline (JSON envelope). |
| Comments | A Markdown report of all comments, grouped open/resolved. |
| PDF | The print path — a paginated script for screenplays, plain print otherwise. |

For a true "save everything" file, use **Export Project (.lfbundle)** — it's the only single file that captures your outline, comments, *and* characters alongside the prose.

---

## 13. Themes & focus

- **Themes** — the **Theme** menu (top-right) offers six built-ins — *Manuscript, Chroma, Forge, Deepdark, Violet, Blueprint* — plus **Custom** (pick six colours and the whole theme derives from them).
- **Focus Mode** (`Ctrl+Shift+D`) hides the chrome for distraction-free writing; `Esc` restores it.
- **Panel toggles** — Outline `Ctrl+Shift+O`, Story Map `Ctrl+Shift+M`, PSYKE `Ctrl+Shift+P`, Comments `Ctrl+Shift+C`, the top panel `Ctrl+Shift+T`.

---

## 14. Full hotkey reference

### Panels & view
| Action | Keys |
|---|---|
| Focus Mode *(Esc restores)* | `Ctrl+Shift+D` |
| Toggle top panel | `Ctrl+Shift+T` |
| Toggle Outline | `Ctrl+Shift+O` |
| Toggle Story Map | `Ctrl+Shift+M` |
| Toggle PSYKE | `Ctrl+Shift+P` |
| Toggle Comments panel | `Ctrl+Shift+C` |
| Screenplay Preview *(Esc exits)* | `Ctrl+Shift+E` |

### Documents & editing
| Action | Keys |
|---|---|
| New Document | `Ctrl+N` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` |
| Zoom in / out / reset | `Ctrl+=` / `Ctrl+-` / `Ctrl+0` |

### Writing (editor)
| Action | Keys |
|---|---|
| Bold / Italic / Underline | `Ctrl+B` / `Ctrl+I` / `Ctrl+U` |
| Screenplay autocomplete / cycle element | `Tab` |
| Note `[[ … ]]` | `Ctrl+Alt+N` |
| Omit / boneyard | `Ctrl+Alt+O` |
| Centre a line (screenplay) | `Ctrl+\` |
| Line numbers / Folding / Syntax | `Ctrl+L` / `Ctrl+Shift+F` / `Ctrl+Shift+H` |

### AI
| Action | Keys |
|---|---|
| Billy (chat) | `Ctrl+Shift+B` |
| Logos (inline) | `Ctrl+Shift+L` *(or `Ctrl+K`)* |

### Comments
| Action | Keys |
|---|---|
| Submit comment / reply | `Ctrl+Enter` |
| Toggle Comments panel | `Ctrl+Shift+C` |

### Outline *(while a row is selected)*
| Action | Keys |
|---|---|
| New item (sibling) | `Enter` |
| Add child | `Ctrl+Enter` |
| Edit details | `Shift+Enter` |
| Indent / Outdent | `Tab` / `Shift+Tab` |
| Move selection | `↑` / `↓` |
| Move item | `Ctrl+↑` / `Ctrl+↓` |
| Collapse / Expand (or select parent / first child) | `←` / `→` |
| Zoom into / out of item | `Ctrl+]` / `Ctrl+[` |
| Delete (when the title is empty) | `Backspace` |
| Multi-select / range-select | `Ctrl`-click / `Shift`-click |
| Collapse/expand whole branch | `Alt`-click the ▸ |
| Deselect | `Esc` |

---

## 15. Data location & backup

Everything you write lives under one folder in your home directory:

```
~/.logosforge/
├── whiteboards/<id>.json     manuscript (blocks) — one file per document
├── outlines/<id>.json        the manual outline — one file per document
├── comments/<id>.json        inline comments — one file per document
└── whiteboard.db             SQLite: projects + PSYKE story bibles
```

(On Windows, `~` is `%USERPROFILE%`.)

**To back up or move your entire workspace:** copy the whole `~/.logosforge` folder. **To back up a single project as a portable file:** use **File → Export → Export Project (.lfbundle)**.

---

## 16. Moving a project to LogosForge Pro

Whiteboard and Pro are separate apps. To graduate a project to Pro:

1. In Whiteboard: **File → Export → Export Project (.lfbundle)**.
2. In Pro: import that `.lfbundle`.

The bundle carries your manuscript (converted from blocks to scenes on import), your PSYKE characters, and your outline and comments — so the whole project moves, not just the prose.

---

## 17. Troubleshooting

- **"Windows protected your PC" / "app can't be opened" (macOS)** — the build is unsigned. Windows: *More info → Run anyway*. macOS: `xattr -cr "/Applications/LogosForge Whiteboard.app"` then open.
- **The window is black on macOS** (older / non-Metal GPU) — relaunch with `open "/Applications/LogosForge Whiteboard.app" --args --disable-gpu`.
- **AI does nothing / "no response"** — check **Settings ⚙**: the Base URL must point at a running provider (start LM Studio/Ollama, or supply a cloud key). Use **Test connection** to confirm.
- **"Old outline, no project"** — an artefact of a much older build; just delete that stray document from the **File → Open Document** list. Current builds never create it.
- **Nothing seems to save** — it already did. There is no manual save; watch the **"Draft saved"** indicator.

---

*LogosForge Whiteboard is alpha software. For the one-page version of this guide, see [QUICK_START.md](QUICK_START.md) or press **?** in the app.*
