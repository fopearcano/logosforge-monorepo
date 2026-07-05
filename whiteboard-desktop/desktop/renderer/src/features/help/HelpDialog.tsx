/**
 * In-app Quick Start / Help panel — a theme-styled modal that mirrors the repo
 * QUICK_START.md (the miniguide). Opened from the ? button in the title bar.
 * Escape or an overlay click closes it.
 */

import { useEffect } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
}

const BASICS: [string, string][] = [
  ['Documents', 'Your work auto-saves and lives in the app. Manage everything from the File menu — New / Open / Rename / Delete Document.'],
  ['Writing modes', 'The Mode dropdown reformats the current document: Novel, Screenplay, Graphic Novel, or Stage Play.'],
  ['Three surfaces', 'Editor (centre) to write, Outline (left) for structure, Story Map (bottom) for a visual overview.'],
  ['Outline', '+ Add ▾ inserts a typed item (auto-nested) or applies a writing-method template — Three-Act, Save the Cat!, Hero’s Journey, and more.'],
  ['PSYKE', 'Your per-project story bible — characters, places, objects, lore, themes. Isolated per document.'],
  ['Comments', 'Highlight text, then click Comment to leave a threaded note pinned to that passage.'],
  ['AI — Billy & Logos', 'Billy is a chat assistant; Logos works inline. Point them at your provider in Settings ⚙.'],
  ['Export & backup', 'File → Export → Export Project (.lfbundle) saves a whole project in one file — your backup, and the file you hand to Pro.'],
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
      ['Undo / Redo', 'Ctrl+Z / Ctrl+Shift+Z'],
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
      ['Logos — inline', 'Ctrl+Shift+L'],
    ],
  },
  {
    title: 'Comments',
    rows: [
      ['Add', 'select text → Comment'],
      ['Submit comment / reply', 'Ctrl+Enter'],
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
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="cf-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="help-title">
        <div className="settings-head">
          <h2 id="help-title" className="settings-title">
            Quick Start
          </h2>
          <button type="button" className="settings-close" aria-label="Close help" onClick={onClose}>
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
  );
}
