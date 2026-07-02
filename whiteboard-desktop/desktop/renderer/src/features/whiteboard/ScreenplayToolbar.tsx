/** Compact, writing-first Screenplay toolbar: Preview, Settings, scale,
 *  Format (Capitalization / Center) and Export, plus an approximate page count. */

import type { Editor } from '@tiptap/react';

import { Popover } from '../../components/Popover';
import {
  EXPORT_TARGETS,
  blocksToFdx,
  blocksToFountainText,
  toFountainBlocks,
} from '../screenplay/screenplayExport';
import { cycleSelectionCase, toggleCenterLine } from '../screenplay/screenplayKeyboard';
import { buildPreview, previewToPlainText } from '../screenplay/screenplayPreview';
import { printScreenplayPdf } from '../screenplay/printScreenplay';
import { DocumentSettingsPanel } from './DocumentSettingsPanel';
import { scaleToPct, type ScaleAction } from './editorScale';
import type { WhiteboardBlock } from './types';
import type { DocumentSettingsApi } from './useDocumentSettings';

interface Props {
  editor: Editor | null;
  blocks: WhiteboardBlock[];
  settingsApi: DocumentSettingsApi;
  preview: boolean;
  onTogglePreview: () => void;
  scale: number;
  onScale: (action: ScaleAction) => void;
  pageCount: number;
}

function downloadText(name: string, text: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function copyText(text: string) {
  void navigator.clipboard?.writeText(text);
}

export function ScreenplayToolbar({
  editor,
  blocks,
  settingsApi,
  preview,
  onTogglePreview,
  scale,
  onScale,
  pageCount,
}: Props) {
  const { settings, update } = settingsApi;

  const runExport = (id: string, close: () => void) => {
    if (id === 'fountain') downloadText('screenplay.fountain', blocksToFountainText(blocks));
    else if (id === 'fdx') downloadText('screenplay.fdx', blocksToFdx(blocks));
    else if (id === 'copy-fountain') copyText(blocksToFountainText(blocks));
    else if (id === 'copy-preview')
      copyText(previewToPlainText(buildPreview(toFountainBlocks(blocks), settings)));
    else if (id === 'pdf' || id === 'print') {
      // Print-to-PDF with industry pagination (1.5in left margin, element
      // columns, page numbers, (MORE)/(CONT'D)). Close the menu first so the
      // popover isn't captured in the print.
      close();
      setTimeout(() => printScreenplayPdf(toFountainBlocks(blocks)), 60);
      return;
    }
    close();
  };

  return (
    <div className="wb-toolbar" role="toolbar" aria-label="Screenplay tools">
      <button
        type="button"
        className={`wb-tool${preview ? ' is-active' : ''}`}
        aria-pressed={preview}
        title="Toggle Preview (Ctrl/Cmd+Shift+E · Esc to exit)"
        onClick={onTogglePreview}
      >
        {preview ? 'Editing' : 'Preview'}
      </button>

      <Popover label="⚙ Settings" title="Document Settings">
        {() => <DocumentSettingsPanel settings={settings} update={update} />}
      </Popover>

      <span className="wb-tool-group" aria-label="View scale">
        <button type="button" className="wb-tool" title="Smaller (Ctrl/Cmd+-)" onClick={() => onScale('smaller')}>
          −
        </button>
        <button
          type="button"
          className="wb-tool wb-scale-pct"
          title="Actual size (Ctrl/Cmd+0)"
          onClick={() => onScale('actual')}
        >
          {scaleToPct(scale)}%
        </button>
        <button type="button" className="wb-tool" title="Bigger (Ctrl/Cmd+=)" onClick={() => onScale('bigger')}>
          +
        </button>
      </span>

      <Popover label="Format ▾" title="Format">
        {(close) => (
          <div className="wb-menu">
            <button
              type="button"
              className="wb-menu-item"
              disabled={!editor || preview}
              onClick={() => {
                if (editor) cycleSelectionCase(editor);
                close();
              }}
            >
              Capitalization (cycle)
            </button>
            <button
              type="button"
              className="wb-menu-item"
              disabled={!editor || preview}
              onClick={() => {
                if (editor) toggleCenterLine(editor);
                close();
              }}
            >
              Center line (Ctrl/Cmd+\)
            </button>
          </div>
        )}
      </Popover>

      <Popover label="Export ▾" title="Export">
        {(close) => (
          <div className="wb-menu">
            {EXPORT_TARGETS.map((t) => (
              <button
                key={t.id}
                type="button"
                className="wb-menu-item"
                disabled={!t.available}
                title={t.available ? undefined : t.note ?? 'Planned'}
                onClick={() => runExport(t.id, close)}
              >
                {t.label}
                {!t.available && <span className="wb-menu-soon"> · {t.note}</span>}
              </button>
            ))}
          </div>
        )}
      </Popover>

      <span className="wb-spacer" />
      <span className="wb-pages" title="Live page count — matches the exported PDF's pagination">
        Pages: {pageCount}
      </span>
    </div>
  );
}
