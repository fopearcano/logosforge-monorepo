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

- **Windows** — the installer (`LogosForge.Whiteboard-<version>-x64.exe`) or the portable build (`LogosForge.Whiteboard-<version>-x64-portable.exe`).
- **macOS (Intel, macOS 12 Monterey or newer)** — the disk image (`LogosForge.Whiteboard-<version>-x64.dmg`).
- **Linux (x64)** — the AppImage (`LogosForge.Whiteboard-<version>-x86_64.AppImage`). Make it executable with `chmod +x "LogosForge.Whiteboard-<version>-x86_64.AppImage"`, then run it directly; installation and root access are not required.

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
- **Your work persists across sessions and switches.** Close the app, reopen it, and Whiteboard reloads each document's manuscript, Drafter pages, narrative/format settings, outline, comments, and PSYKE data. Each local JSON save also retains two previous generations for recovery.
- **Files are for sharing, not storing.** *Import* brings text in; *Export* sends a copy out. Neither is where your work "lives" — the app is.

See [Data location & backup](#15-data-location--backup) for where the store sits on disk and how to back it up.

---

## 3. Documents

Each **document** is an independent project with its own manuscript, Drafter pages, narrative voice/format settings, outline, comments, and PSYKE bible. Manage them from the **File** menu (top-left):

| Action | What it does |
|---|---|
| **New Document** | Creates a fresh, blank project and switches to it. Your previous document is untouched. (`Ctrl+N`) |
| **Open Document** | Lists every document — click one to switch. The current one is marked ✓; each has a **×** to delete. |
| **Rename current document…** | Opens a small dialog to rename the active document. |
| **Delete** | The **×** next to a document removes it *and* its Drafter pages, outline, comments, and story bible — this can't be undone, so it asks first. |

The **project name at the top** is also a quick document switcher (click it for the list). Both places are just two doors to the same library.

Whiteboard drains manuscript, Drafter, document-settings, outline, comment, PSYKE, title, and mode writes before changing projects. If the current document is associated with an external file, Whiteboard offers to save that file before switching and then clears the association, so saving the next document can never overwrite the previous document's file.

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

**Find & Replace:** Press `Ctrl+F` / `Cmd+F`, or choose **Edit → Find and Replace…** in the desktop app. The non-modal bar searches only the active Manuscript or Drafter page, keeps an exact result count, highlights a bounded window around the current result for large manuscripts, wraps Previous/Next navigation, and offers **Match case**, Unicode-aware **Whole word**, **Replace**, and single-undo **Replace all**.

**Typefaces:** Open **Editor Settings → Typeface** for expanded Serif, Sans serif, Mono & typewriter, and Handwritten groups. The four bundled faces work identically on every platform; the other presets use the closest installed platform face. Choose **Installed system font…** to enter a family name or explicitly load the local font list. Install new fonts through Windows, macOS, or Linux, then refresh the list. This preference stays on the computer and is not embedded in project exports.

### Drafter pages

The tabs above the editor contain one permanent **Manuscript** tab plus any project-owned **Drafter** pages. Drafter is for isolated scenes, alternate versions, notes, or exploratory prose that should not yet change the canonical manuscript.

- Create a page with **+** or `Ctrl+Shift+N`; rename or delete it from the **Drafter** menu.
- **Drafter → Import file as page…** copies a Text, Markdown, or Fountain file into a new internal page. It does not keep a live link to the source file.
- Pages inherit the document's writing mode and editor settings. Copy and paste into the Manuscript whenever material is ready.
- Billy and Logos use the active page selection and nearby prose while retaining the same project's canonical manuscript digest, manual Outline, narrative profile, and PSYKE. The AI context explicitly labels Drafter prose as provisional.
- Each Drafter page has its own isolated inline comments. Manuscript breadcrumbs, Story Map, manuscript file import, and ordinary publication exports remain attached to the **Manuscript** tab. Clicking an Outline or Story Map destination returns there automatically.
- Drafter has an independent revision and crash-recovery journal. A conflict cannot overwrite the manuscript or another saved Drafter version.

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
- **Link to cursor position** (row ⋯ menu) binds an item to the exact manuscript block. The anchor badge jumps back to it, and a breadcrumb above the editor shows where you are in the outline. Stable block IDs keep the link attached through inserted lines, full rewrites, duplicate headings, and empty paragraphs.
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

Comments are available on the **Manuscript** and every **Drafter** page. The panel shows only the active writing page's threads, and each new comment records that page together with a stable block ID, quoted text, and surrounding context. Highlights therefore follow the intended passage through inserted blocks, duplicate wording, and edits without leaking between Manuscript or Drafter pages. Legacy comments remain Manuscript comments; a comment is cleaned up only after its owning page is durably saved and its passage is genuinely gone.

---

## 10. AI — Billy & Logos

The AI is **optional** and **bring-your-own-endpoint** — nothing is sent anywhere unless you configure a provider.

- **Billy** — a hovering **chat** assistant for open-ended help. Toggle with `Ctrl+Shift+B`.
- **Logos** — works **inline and in context** (on your current selection / section) for surgical suggestions. Toggle with `Ctrl+Shift+L` (or `Ctrl+K`).

On a Drafter page, both assistants see that page's active selection and nearby text, but the same project's manuscript, Outline, narrative profile, and PSYKE remain their grounding. Drafter content is labelled provisional so it is not mistaken for canonical story text.

**Configure it** in **Settings ⚙** (top-right):

- **Provider** — LM Studio, Ollama, OpenAI, Anthropic, or OpenRouter.
- **Base URL** — the endpoint (a **Default** button fills the standard URL for the chosen provider — e.g. `http://localhost:1234/v1` for LM Studio).
- **Model**, **API key** (write-only; blank keeps the stored one), and **Timeout**.
- **Test connection** saves the form and round-trips a trivial prompt so you can confirm the provider actually responds.

For fully offline AI, run a local server (LM Studio or Ollama) and point the Base URL at it.

---

## 11. Import

**File → Import to Manuscript** brings external text into the canonical manuscript. On import you choose **Replace** (swap the manuscript) or **Append** (add to the end). To make a separate working page instead, choose **Drafter → Import file as page…** for Text, Markdown, or Fountain.

| Format | Notes |
|---|---|
| **Text** (`.txt`) | One block per line; `#` lines become headings. |
| **Markdown** (`.md`) | As above; Markdown is preserved as text. |
| **Fountain** (`.fountain`) | Switches the document to Screenplay. |
| **Final Draft** (`.fdx`) | Extracts the screenplay and switches to Screenplay. |
| **LogosForge** (`.logosforge`) | The app's JSON export (manuscript + outline). |

Whiteboard does **not** currently import or restore `.lfbundle` project bundles.
Those bundles are the migration/archive format consumed by **LogosForge Pro**;
see [Moving a project to LogosForge Pro](#16-moving-a-project-to-logosforge-pro).

---

## 12. Export & backup

**File → Export** writes a copy of the current document to a file.

| Format | Contains |
|---|---|
| **Export Project** (`.lfbundle`) | A complete portable snapshot — manuscript, Drafter pages, narrative/format settings, outline, comments, and PSYKE — for archiving or importing into LogosForge Pro. Whiteboard cannot import it yet. |
| Text / Markdown / Fountain | The manuscript as text. |
| HTML | A styled, self-contained web page of the manuscript. |
| JSON | Title, mode, and raw blocks. |
| LogosForge (`.logosforge`) | Manuscript + outline (JSON envelope). |
| Comments | A Markdown report of all comments, grouped open/resolved and labelled with their Drafter page when applicable. |
| PDF | The print path — a paginated script for screenplays, plain print otherwise. |

For a true "save everything" snapshot, use **Export Project (.lfbundle)** — it's the only single file that captures Drafter pages, document settings, outline, comments, *and* characters alongside the prose. Whiteboard aborts this export if any component cannot be read; it never reports success for a bundle that silently dropped Drafter, PSYKE, or damaged local state. Pro imports Drafter pages as tagged Notes and preserves their structured source blocks in project settings. To restore Whiteboard itself, restore the `~/.logosforge` data folder instead.

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
| New Drafter page | `Ctrl+Shift+N` |
| Move across focused writing tabs | `←` / `→` *(Home / End for first / last)* |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` |
| Find & Replace in the active writing page | `Ctrl+F` |
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
├── drafter/<id>.json         project-owned scratch pages
├── outlines/<id>.json        the manual outline — one file per document
├── comments/<id>.json        inline comments — one file per document
└── whiteboard.db             SQLite: projects + PSYKE story bibles
```

(On Windows, `~` is `%USERPROFILE%`.)

**To back up, move, or restore your Whiteboard workspace:** copy the whole `~/.logosforge` folder while Whiteboard is closed. **To archive a single project for migration to Pro:** use **File → Export → Export Project (.lfbundle)**. Whiteboard does not currently import `.lfbundle` files itself.

For manuscript, Drafter, outline, and comment JSON, Whiteboard keeps the two preceding
versions beside the current file as `.bak` and `.bak.1`. If the current copy is
unreadable, the newest valid backup is restored automatically, the damaged bytes
are preserved as `.corrupt-<timestamp>`, and a recovery notice appears in the app.
If no backup validates, loading and autosave stop with an error rather than
replacing the project with an empty document.

If a conflict or startup recovery banner offers **Save copy**, the exported
LogosForge JSON is also restorable through **File → Import to Manuscript →
LogosForge**. Whiteboard recognizes manuscript, Outline, and Drafter recovery
copies, validates them, identifies their source project, and asks before
replacing only that resource. Restoring Drafter replaces the project's scratch
pages without changing its manuscript, Outline, settings, or PSYKE knowledge.

---

## 16. Moving a project to LogosForge Pro

Whiteboard and Pro are separate apps. To graduate a project to Pro:

1. In Whiteboard: **File → Export → Export Project (.lfbundle)**.
2. In Pro: import that `.lfbundle`.

Pro converts the manuscript blocks to scenes; imports Drafter pages as tagged
Notes; imports the document settings, PSYKE entries, relationships, progression
beats, outline, and outline links; and preserves the exact structured Drafter
blocks plus other Whiteboard-only settings in the imported project's settings store.
Progression scene anchors are remapped only when their title uniquely matches an
imported scene; unresolved anchors keep their progression beat unlinked and are reported.
Whiteboard Manuscript comment threads are also recreated in Pro when their text span can be
mapped safely to the imported scene title/content. Replies, open/resolved state,
timestamps, cross-field or cross-scene ranges, and source provenance are
preserved; unmappable threads are skipped and reported rather than attached to
the wrong passage. Drafter-page comment threads remain in the source `.lfbundle`;
Pro currently reports them as skipped because it has no Drafter comment surface.

In Pro's Manuscript, safely mapped passages are visibly marked; activate a mark
to open its anchored thread. Select text in a scene title or prose and choose
**＋ COMMENT** to start a native thread. Drag a prose selection into another
scene to anchor one thread across both scenes and any fields between them. From the mark popover or dedicated
**Comments** panel you can reply, Resolve/Reopen, and delete a reply or thread;
the panel also edits the original comment and exports all threads as Markdown.
Its remembered **ALL / OPEN** choice controls both the list and whether resolved
marks appear in the Manuscript. Press **Alt+Down / Alt+Up** to cycle through open
anchored threads, or **Ctrl+Shift+C** to open Comments. Mention `@assistant` or
`@counterpart` in a reply to ask that project-aware companion to answer in the
same thread.

Pro's **Knowledge Graph** has four traceable views: **Project Map** for the whole
canonical story graph, **Structure** for hierarchy and recorded order,
**Recorded Risk** for saved risk/contradiction evidence, and **Saved Revision
Impact** for saved revision-analysis links. The separate **Evidence** control
switches any view between **Confirmed only** and **Inferred + Confirmed**. Only
Project Map provides orphan and weak-link story diagnostics; an empty
specialty view means no matching recorded evidence, not that the manuscript is
connected or risk-free. The complete hidden-edge review queue remains available
from every view.

Under **Visual Overlays**, node sizing defaults to **Story Gravity**, a
project-wide 0–100% narrative-importance signal. Choose **View Links** to size by
relationship degree in the complete selected view/evidence scope instead. Core
bridges Story Gravity only for uniquely matching Scene, Note, PSYKE, and Act
identities; a node that cannot be mapped safely stays at the neutral minimum
size rather than borrowing its link degree. If the optional gravity calculation
fails, the graph still loads and the panel explicitly falls back to View Links.
Mapped nodes at 55% or higher receive a halo.

**Story-order flow** is off by default. When enabled, curved green/gold/violet
arrows show the manuscript-order segments present in the returned, currently
filtered graph; heavier dashed segments mark act boundaries and the status text
calls out visible gaps. It is manuscript order, not causality. The overlay never
reconstructs omitted data: Confirmed only normally removes the inferred order
chain, Recorded Risk and Saved Revision Impact exclude it, and focus, response
caps, hidden node types, confidence, or source-system filters can leave only a
partial chain or none.

If you connect a local MCP client such as Codex or LibreChat to the optional Pro
gateway, it can list and search complete comment threads, propose a reply
attributed to **MCP assistant**, and propose Resolve/Reopen. The writer still
reviews and applies every proposal. Each comment proposal is bound to the exact
thread revision the agent read; if the root, a reply, its resolution, or its
anchor changes first, Pro rejects the stale apply and the agent must reread.
Comment text is treated as project content, not as instructions to the agent.
Creating anchored comments, changing their anchor or original body, and
deleting threads or replies remain actions for Pro's Comments UI.

The same Pro gateway can read and orchestrate the Timeline, Canvas Plot, and
Narrative Knowledge Graph. An agent can prepare one reviewed change at a time
against the exact surface revision it read, and Core checks that revision again
when applied. Timeline commands cover lanes, event membership, and
structural/custom ordering; Canvas commands cover cards, links, frames,
geometry, and stacking order. Its Knowledge Graph read can request any of the
four views and either evidence scope; it also receives the same Story Gravity
availability/value fields and returned story-order metadata as Pro. A null
gravity value means no safe exact mapping, not zero importance. Knowledge Graph
commands Confirm, Hide, or Restore one exact directional edge. Confirm and Hide
preflight plus apply/recovery result maps remain pinned to Project Map; Restore
preflight uses the paged hidden-edge read, which keeps the complete restore queue
available even when the main map is truncated.
Deleting a Timeline lane leaves its scenes Unassigned, removing an event leaves
the manuscript scene intact, and deleting a Canvas card preserves any linked
manuscript scene.

Timeline, Canvas Plot, and Knowledge Graph applies carry a durable project
receipt under the same reviewed proposal id. If a response is lost, the gateway
reconciles that exact proposal instead of duplicating the change; this also
works after restarting the MCP companion. Recovery never becomes a fresh
proposal. Other proposal types remain conservative: if their apply response is
uncertain, inspect current state and do not retry because the change may already
have committed.

Pro uses the stored quote and surrounding context to relocate marks after edits,
including imported spans that cross title/content or scene boundaries. It saves
only safe reanchors after scene edits settle and removes a thread only when its
passage and usable context are genuinely gone; imported threads retain their
source provenance throughout.

---

## 17. Troubleshooting

- **"Windows protected your PC" / "app can't be opened" (macOS)** — the build is unsigned. Windows: *More info → Run anyway*. macOS: `xattr -cr "/Applications/LogosForge Whiteboard.app"` then open.
- **The window is black on macOS** (older / non-Metal GPU) — relaunch with `open "/Applications/LogosForge Whiteboard.app" --args --disable-gpu`.
- **AI does nothing / "no response"** — check **Settings ⚙**: the Base URL must point at a running provider (start LM Studio/Ollama, or supply a cloud key). Use **Test connection** to confirm.
- **"Old outline, no project"** — an artefact of a much older build; just delete that stray document from the **File → Open Document** list. Current builds never create it.
- **Nothing seems to save** — it already did. There is no manual save; watch the **"Draft saved"** indicator.

---

*LogosForge Whiteboard is alpha software. For the one-page version of this guide, see [QUICK_START.md](QUICK_START.md) or press **?** in the app.*
