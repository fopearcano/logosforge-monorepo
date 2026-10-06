# LogosForge Whiteboard — Keyboard Shortcuts

`Mod` = **Ctrl** on Windows/Linux, **Cmd (⌘)** on macOS.

## Panels & View  (`Mod + Shift + …`)
| Shortcut | Action |
|----------|--------|
| `Mod + Shift + O` | Toggle the Outline panel |
| `Mod + Shift + M` | Toggle the Story Map strip |
| `Mod + Shift + T` | Toggle the Top panel |
| `Mod + Shift + P` | Toggle PSYKE |
| `Mod + Shift + D` | Focus Mode (hide all chrome) |
| `Esc` | Close the active overlay, then restore hidden panels / exit Focus Mode |

## Comments
| Shortcut | Action |
|----------|--------|
| `Mod + Shift + C` | Toggle the Comments panel |
| `Alt + ↓` / `Alt + ↑` | Jump to next / previous unresolved comment (scrolls to it + opens it) |

Comments are isolated to the active writing page: the Manuscript and each Drafter
page keep their own anchored threads.

## AI agents — LittleBoy  (`Mod + Shift + …`)
| Shortcut | Action |
|----------|--------|
| `Mod + Shift + B` | Toggle the **LittleBoy** hovering chat (Billy) |
| `Mod + Shift + L` | Toggle **Logos** (inline assistant) — legacy alias: `Mod + K` |
| `Esc` | Close the active AI box |

*(Both also have title-bar buttons next to Theme / PSYKE.)*

## File  (desktop app)
| Shortcut | Action |
|----------|--------|
| `Mod + N` | New document |
| `Mod + O` | Open… |
| `Mod + S` | Save |
| `Mod + Shift + S` | Save As… |

## Drafter pages

| Shortcut | Action |
|----------|--------|
| `Mod + Shift + N` | Create a project-owned Drafter page |
| `←` / `→` | Move between Manuscript and Drafter tabs while a tab is focused |
| `Home` / `End` | Move to the first / last writing tab |

Drafter pages inherit the project writing mode, settings, PSYKE, and AI grounding,
but remain outside the canonical manuscript. Importing a text, Markdown, or Fountain
file creates an internal project copy; it does not keep a live link to the disk file.

## Writing & formatting  (inside the editor)
| Shortcut | Action |
|----------|--------|
| `Mod + F` | Open advanced Find & Replace for the active Manuscript or Drafter page |
| `Mod + Z` | Undo · `Mod + Shift + Z` / `Mod + Y` | Redo |
| `Mod + B` | Bold — real formatting in prose modes; inserts Fountain `**…**` in Screenplay |
| `Mod + I` | Italic — real formatting in prose modes; inserts Fountain `*…*` in Screenplay |

Find & Replace searches only the active writing page and supports match case,
Unicode-aware whole words, wrapping previous/next navigation, Replace, and a
single-undo Replace All. It is also available from the desktop **Edit** menu.

### Screenplay mode only (Fountain markup)
These insert Fountain syntax and apply **only in Screenplay mode**; in prose modes they do nothing.
| Shortcut | Action |
|----------|--------|
| `Tab` | Screenplay element cycle / accept autocomplete |
| `Mod + U` | Underline `_…_` |
| `Mod + Alt + N` | Note `[[ … ]]` |
| `Mod + Alt + O` | Omit selection to the boneyard `/* … */` |
| `Mod + \` | Center line `> … <` |

> Note: in a **web browser**, a few `Mod+Shift+…` combos collide with built-in
> browser shortcuts (e.g. `Mod+Shift+P` = Private Window, `Mod+Shift+M` =
> Responsive Design Mode, `Mod+Shift+C` = Inspect Element in Firefox/Chrome). In
> the **desktop app** they all work cleanly. (Comments also has a title-bar button
> between Logos and PSYKE, so the hotkey collision is only a minor inconvenience.)
