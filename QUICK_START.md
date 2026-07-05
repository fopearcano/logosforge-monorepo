# LogosForge Whiteboard — Quick Start

A calm, database-backed writing workstation for **novels, screenplays, graphic novels, and stage plays**. Every document saves itself — you write, structure, and annotate; the app keeps the rest.

> **Keys below are written for Windows.** On **macOS**, use **⌘ Cmd** wherever you see **Ctrl**.

---

## Getting your bearings

- **Documents** — your work lives in the app, not in loose files, and it **auto-saves** continuously. Manage everything from the **File** menu: *New / Open / Rename / Delete Document*. The project name at the top is also a quick document switcher.
- **Writing modes** — the **Mode** dropdown reformats the current document live: **Novel**, **Screenplay** (Fountain), **Graphic Novel**, or **Stage Play**. It asks first if the page already has text, since the reformat is permanent.
- **The three surfaces** — the **Editor** (centre) is where you write; the **Outline** (left) holds your manual story structure; the **Story Map** (bottom) is a visual overview derived from the document.
- **Outline** — build structure by hand — **Acts, Chapters, Scenes, Beats** — with drag-to-reorder, colours, and status. **+ Add ▾** inserts a typed item (auto-nested) or applies a **writing-method template** (Three-Act, Save the Cat!, Hero's Journey, and more).
- **PSYKE — the story bible** — keep **characters, places, objects, lore, and themes** per project. PSYKE is scoped to each document, so two projects never share a cast.
- **Comments** — highlight any text and click **Comment** to leave a threaded note pinned to that passage. Resolve them when handled.
- **AI — Billy & Logos** — **Billy** is a hovering chat assistant; **Logos** works inline and in context. Point them at your provider (LM Studio, Ollama, OpenAI, Anthropic) in **Settings ⚙** (top-right).
- **Export & backup** — **File → Export → Export Project (.lfbundle)** saves an entire project — manuscript, outline, comments, and PSYKE — as one file. That's your backup, and the file you hand to LogosForge Pro. Plain Text, Markdown, Fountain, and PDF export too.

---

## Hotkeys

Outline keys apply while a row is selected; editor keys apply while you're writing.

### Panels & view

| Action | Keys |
|---|---|
| Focus Mode *(Esc restores)* | `Ctrl` `Shift` `D` |
| Toggle top panel | `Ctrl` `Shift` `T` |
| Toggle Outline | `Ctrl` `Shift` `O` |
| Toggle Story Map | `Ctrl` `Shift` `M` |
| Toggle PSYKE | `Ctrl` `Shift` `P` |
| Toggle Comments panel | `Ctrl` `Shift` `C` |
| Screenplay Preview *(Esc exits)* | `Ctrl` `Shift` `E` |

### Documents & editing

| Action | Keys |
|---|---|
| New Document | `Ctrl` `N` |
| Undo / Redo | `Ctrl` `Z` / `Ctrl` `Shift` `Z` |
| Zoom in / out | `Ctrl` `=` / `Ctrl` `-` |
| Reset zoom | `Ctrl` `0` |

### Writing (in the editor)

| Action | Keys |
|---|---|
| Bold / Italic / Underline | `Ctrl` `B` / `I` / `U` |
| Screenplay: autocomplete / cycle element | `Tab` |
| Note `[[ … ]]` | `Ctrl` `Alt` `N` |
| Omit / boneyard | `Ctrl` `Alt` `O` |
| Centre a line (screenplay) | `Ctrl` `\` |

### Nerd Mode (editor aids)

| Action | Keys |
|---|---|
| Line numbers | `Ctrl` `L` |
| Code folding | `Ctrl` `Shift` `F` |
| Syntax highlighting | `Ctrl` `Shift` `H` |

### AI

| Action | Keys |
|---|---|
| Billy — chat assistant | `Ctrl` `Shift` `B` |
| Logos — inline / contextual | `Ctrl` `Shift` `L` *(or `Ctrl` `K`)* |

### Comments

| Action | Keys |
|---|---|
| Add | select text, click **Comment** |
| Submit comment / reply | `Ctrl` `Enter` |
| Toggle Comments panel | `Ctrl` `Shift` `C` |

### Outline *(while a row is selected)*

| Action | Keys |
|---|---|
| New item (sibling) | `Enter` |
| Add child | `Ctrl` `Enter` |
| Edit details | `Shift` `Enter` |
| Indent / Outdent | `Tab` / `Shift` `Tab` |
| Move selection | `↑` / `↓` |
| Move item | `Ctrl` `↑` / `Ctrl` `↓` |
| Collapse / Expand | `←` / `→` |
| Zoom into / out of item | `Ctrl` `]` / `Ctrl` `[` |
| Delete (empty title) | `Backspace` |
| Multi-select / range | `Ctrl`-click / `Shift`-click |
| Deselect | `Esc` |

---

**Tip** — nothing here needs a manual save. Watch the *"Draft saved"* note; your work is in the app the moment you type it.
**Backups** live in `~/.logosforge` — copy that folder to move your whole workspace to another machine.
