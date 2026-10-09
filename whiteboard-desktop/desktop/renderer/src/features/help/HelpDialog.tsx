/**
 * In-app Quick Start / Help panel — a theme-styled modal that mirrors the repo
 * QUICK_START.md (the miniguide). Opened from the ? button in the title bar.
 * Escape or an overlay click closes it.
 */

import { Fragment, useRef } from 'react';

import { ModalPortal } from '../../components/ModalPortal';
import { useModalDialog } from '../../components/useModalDialog';

interface Props {
  open: boolean;
  onClose: () => void;
}

const BASICS: [string, string][] = [
  ['Documents', 'Your work auto-saves in isolated projects. Each document keeps its own manuscript, voice/format settings, outline, comments, and PSYKE.'],
  ['Drafter', 'Use the tabs above the editor for project-owned scratch pages and isolated scene drafts. The active page shares the project’s mode, PSYKE, and AI context but stays outside the canonical manuscript until you copy text across.'],
  ['Writing modes', 'The Mode dropdown reformats the current document: Novel, Screenplay, Graphic Novel, or Stage Play.'],
  ['Three surfaces', 'Editor (centre) to write, Outline (left) for structure, Story Map (bottom) for a visual overview.'],
  ['Outline', '+ Add ▾ inserts typed items or templates. A row’s ⋯ → Link to cursor position creates a stable manuscript anchor and live breadcrumb. Shift+Enter opens all item details.'],
  ['Narrative voice', 'Settings ⚙ → Narrative voice sets this document’s person, style, register, and slang guidance for Billy and Logos.'],
  ['PSYKE', 'Your per-project story bible — characters, places, objects, lore, themes, and ordered Progressions. Open an entry, then choose Progressions to build its arcs.'],
  ['Comments', 'On the Manuscript or any Drafter page, highlight text and click Comment to leave a threaded note pinned to that writing page.'],
  ['Find & Replace', 'Edit → Find and Replace… (Ctrl/Cmd+F) searches the active Manuscript or Drafter page without covering your prose. It supports case-sensitive and whole-word searches, Replace, and Replace all.'],
  ['Editor typefaces', 'Editor Settings → Typeface includes serif, sans, mono, typewriter, and handwritten presets. Choose Installed system font… to load or enter a family installed on this computer.'],
  ['AI — Billy & Logos', 'Billy is a chat assistant; Logos works inline. Point them at your provider in Settings ⚙.'],
  ['Export & backup', 'Export Project (.lfbundle) saves manuscript, Drafter pages, document settings, outline, comments, PSYKE, and Progression tracks. Incomplete exports are blocked.'],
];

interface Guide {
  title: string;
  rows: [label: string, detail: string][];
}

const GUIDES: Guide[] = [
  {
    title: 'Progressions',
    rows: [
      ['Open a track', 'Open PSYKE, select a bible entry, then choose its Progressions tab. Tracks can describe story, character, relationship, theme, world, or custom change.'],
      ['Add beats', 'Add ordered changes inside a track; edit, delete, or move tracks and beats with the arrow controls.'],
      ['Anchor a beat', 'Place the caret in the main Manuscript, then choose Anchor here. The beat stores that stable manuscript block id and its readable heading.'],
      ['Drafter boundary', 'Drafter pages share project knowledge, but they are provisional and cannot become canonical Progression anchors.'],
      ['AI and Pro', 'Billy and Logos receive a bounded relevant Progressions summary. Project export carries canonical tracks one-way into Pro.'],
    ],
  },
  {
    title: 'Find & Replace',
    rows: [
      ['Open', 'Choose Edit → Find and Replace… or press Ctrl/Cmd+F. A short selected phrase is copied into Find automatically.'],
      ['Scope', 'Only the active Manuscript or Drafter page is searched. Switch tabs to run the same search on that page.'],
      ['Refine', 'Match case distinguishes capitals; Whole word uses Unicode word boundaries, including accented letters.'],
      ['Navigate', 'Press Enter or ↓ for the next result; Shift+Enter or ↑ for the previous one. Navigation wraps at either end.'],
      ['Replace safely', 'Replace changes the selected result. Replace all is a single auto-saved edit, so one Undo restores every replacement.'],
      ['Close', 'Press Esc or × to close the bar and return focus to the editor.'],
    ],
  },
  {
    title: 'Typefaces & installed fonts',
    rows: [
      ['Presets', 'Choose a grouped Serif, Sans serif, Mono & typewriter, or Handwritten voice in Editor Settings → Typeface.'],
      ['Use an OS font', 'Choose Installed system font…, then Load installed fonts and allow access when your operating system asks.'],
      ['Install another font', 'Install it through Windows, macOS, or Linux first, then return here and refresh the installed-font list.'],
      ['Enter it directly', 'You can type the exact family name and Apply without loading the list. Whiteboard falls back to the mode default if the OS cannot resolve it.'],
      ['Local preference', 'Typography overrides stay on this computer; they do not embed or redistribute font files in project exports.'],
    ],
  },
];

interface Group {
  title: string;
  rows: [action: string, combo: string][];
}

const GROUPS: Group[] = [
  {
    title: 'Panels & view',
    rows: [
      ['Focus Mode (Esc restores)', 'Ctrl+Shift+D'],
      ['Toggle top panel', 'Ctrl+Shift+T'],
      ['Toggle Outline', 'Ctrl+Shift+O'],
      ['Toggle Story Map', 'Ctrl+Shift+M'],
      ['Toggle PSYKE', 'Ctrl+Shift+P'],
      ['Toggle Comments panel', 'Ctrl+Shift+C'],
      ['Screenplay Preview (Esc exits)', 'Ctrl+Shift+E'],
    ],
  },
  {
    title: 'Documents & editing',
    rows: [
      ['New Document', 'Ctrl+N'],
      ['New Drafter page', 'Ctrl+Shift+N'],
      ['Move across writing tabs', '← / →'],
      ['Undo / Redo', 'Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y'],
      ['Find & Replace', 'Ctrl+F'],
      ['Previous / next match', 'Shift+Enter / Enter'],
      ['Close Find & Replace', 'Esc'],
      ['Zoom in / out / reset', 'Ctrl+= / Ctrl+- / Ctrl+0'],
    ],
  },
  {
    title: 'Writing (editor)',
    rows: [
      ['Bold / Italic / Underline', 'Ctrl+B / Ctrl+I / Ctrl+U'],
      ['Screenplay: autocomplete / cycle', 'Tab'],
      ['Note [[ … ]] / Omit', 'Ctrl+Alt+N / Ctrl+Alt+O'],
      ['Centre a line (screenplay)', 'Ctrl+\\'],
      ['Line #s / Fold / Syntax', 'Ctrl+L / Ctrl+Shift+F / Ctrl+Shift+H'],
    ],
  },
  {
    title: 'AI',
    rows: [
      ['Billy — chat', 'Ctrl+Shift+B'],
      ['Logos — inline', 'Ctrl+Shift+L / Ctrl+K'],
    ],
  },
  {
    title: 'Comments',
    rows: [
      ['Add', 'select text → Comment'],
      ['Submit comment / reply', 'Ctrl+Enter'],
      ['Next / previous unresolved', 'Alt+↓ / Alt+↑'],
    ],
  },
  {
    title: 'Outline (row selected)',
    rows: [
      ['New item / Add child', 'Enter / Ctrl+Enter'],
      ['Edit details', 'Shift+Enter'],
      ['Indent / Outdent', 'Tab / Shift+Tab'],
      ['Move selection / item', '↑↓ / Ctrl+↑↓'],
      ['Collapse / Expand', '← / →'],
      ['Zoom into / out', 'Ctrl+] / Ctrl+['],
      ['Delete (empty title)', 'Backspace'],
      ['Multi / range select', 'Ctrl-click / Shift-click'],
      ['Deselect', 'Esc'],
    ],
  },
];

interface SyntaxGroup {
  title: string;
  rows: [syntax: string, meaning: string][];
}

// Mirrors MANUSCRIPT_SYNTAX.md — the patterns each mode's live formatter reads.
const SYNTAX: SyntaxGroup[] = [
  {
    title: 'Every mode',
    rows: [
      ['[[note]]', 'Private note — dimmed, not printed'],
      ['@@Name', 'PSYKE bible mention (character / place / lore)'],
      ['[text](url)', 'Link (a bare https://… works too)'],
      ['TODO  FIXME  XXX', 'Flagged for follow-up'],
    ],
  },
  {
    title: 'Novel',
    rows: [
      ['#  ##  ###', 'Title / Heading / Subheading (or Format ▾)'],
      ['Ctrl+B  Ctrl+I', 'Bold / italic — real rich text'],
      ['"…"', 'Dialogue — auto colour-coded'],
      ['- item   * item', 'Bullet'],
      ['- [ ]   - [x]', 'Task / done'],
      ['#tag   @tag', 'Tag'],
    ],
  },
  {
    title: 'Screenplay (Fountain)',
    rows: [
      ['INT.  EXT.  EST.', 'Scene heading — force any line with a leading .'],
      ['MARA', 'Character cue — ALL-CAPS (force with @)'],
      ['(whispering)', 'Parenthetical, under a cue'],
      ['SARAH ^', 'Dual dialogue'],
      ['CUT TO:', 'Transition (or force with a leading >)'],
      ['>THE END<', 'Centred'],
      ['#  ##  ###', 'Section — outline only, not printed'],
      ['= synopsis', 'Synopsis — not printed'],
      ['~lyric', 'Lyrics'],
      ['===', 'Page break'],
      ['*i*  **b**  _u_', 'Italic / bold / underline (***bold-italic*** too)'],
      ['Title: …', 'Title page keys, at the very top'],
      ['/* … */', 'Boneyard — hide text without deleting it'],
      ['!action', 'Force an action line'],
    ],
  },
  {
    title: 'Graphic Novel',
    rows: [
      ['PAGE ONE   PAGE 1', 'Page (or a Heading)'],
      ['PANEL 1', 'Panel (or a Subheading)'],
      ['CAPTION:', 'Caption (also CAPTION (Name): )'],
      ['SFX:  SOUND:  FX:', 'Sound effect'],
      ['MARA: speech', 'Inline dialogue (or a cue + line below)'],
      ['(beat)', 'Parenthetical'],
    ],
  },
  {
    title: 'Stage Script',
    rows: [
      ['ACT  SCENE  CURTAIN', 'Scene heading (or a Heading)'],
      ['MARA:', 'Character cue — a trailing “:” is fine'],
      ['line under a cue', 'Dialogue — centred'],
      ['(crosses left)', 'Stage direction'],
    ],
  },
];

function Keys({ combo }: { combo: string }) {
  const alts = combo.split(' / ');
  return (
    <span className="help-keys">
      {alts.map((alt, ai) => (
        <span key={ai} className="help-alt">
          {alt.includes(' ') ? (
            <span className="help-plain">{alt}</span>
          ) : (
            alt.split('+').map((k, ki, ks) => (
              <span key={ki}>
                <kbd>{k}</kbd>
                {ki < ks.length - 1 && <span className="help-sep">+</span>}
              </span>
            ))
          )}
          {ai < alts.length - 1 && <span className="help-or">/</span>}
        </span>
      ))}
    </span>
  );
}

export function HelpDialog({ open, onClose }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useModalDialog({ open, dialogRef, initialFocusRef: closeRef, onClose });

  if (!open) return null;

  return (
    <ModalPortal>
      <div
        data-wb-modal-layer
        className="cf-overlay"
        onClick={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      >
      <div
        ref={dialogRef}
        className="help-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="help-title"
        tabIndex={-1}
      >
        <div className="settings-head">
          <h2 id="help-title" className="settings-title">
            Quick Start
          </h2>
          <button ref={closeRef} type="button" className="settings-close" aria-label="Close help" onClick={onClose}>
            ×
          </button>
        </div>
        <p className="settings-sub">
          A calm, auto-saving workstation for novels, screenplays, graphic novels, and stage plays. On
          macOS, use ⌘ Cmd wherever you see Ctrl.
        </p>

        <div className="help-body">
          <div className="help-eyebrow">Getting your bearings</div>
          <ul className="help-basics">
            {BASICS.map(([term, desc]) => (
              <li key={term}>
                <span className="help-term">{term}</span>
                <span className="help-desc">{desc}</span>
              </li>
            ))}
          </ul>

          <div className="help-eyebrow">Find, replace &amp; fonts</div>
          <div className="help-keys-grid">
            {GUIDES.map((guide) => (
              <div key={guide.title} className="help-group">
                <h3>{guide.title}</h3>
                <dl className="help-guide-list">
                  {guide.rows.map(([label, detail]) => (
                    <Fragment key={label}>
                      <dt>{label}</dt>
                      <dd>{detail}</dd>
                    </Fragment>
                  ))}
                </dl>
              </div>
            ))}
          </div>

          <div className="help-eyebrow">Manuscript syntax</div>
          <p className="settings-sub help-syntax-intro">
            You type plain text — the editor formats each line live for the current mode. The markers
            below only matter when you want to force or fine-tune a type.
          </p>
          <div className="help-keys-grid">
            {SYNTAX.map((g) => (
              <div key={g.title} className="help-group">
                <h3>{g.title}</h3>
                <div className="help-syntax-list">
                  {g.rows.map(([syntax, meaning]) => (
                    <Fragment key={syntax}>
                      <code className="help-syntax">{syntax}</code>
                      <span className="help-desc">{meaning}</span>
                    </Fragment>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="help-eyebrow">Hotkeys</div>
          <div className="help-keys-grid">
            {GROUPS.map((g) => (
              <div key={g.title} className="help-group">
                <h3>{g.title}</h3>
                {g.rows.map(([action, combo]) => (
                  <div key={action} className="help-row">
                    <span className="help-act">{action}</span>
                    <Keys combo={combo} />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
      </div>
    </ModalPortal>
  );
}
