/**
 * Import / Export orchestration. Extends the file system without touching
 * New/Open/Save/Save As. Wires the (shared) menu actions to native dialogs,
 * pure format conversions, and the editor:
 *
 *   Import  : pick file → parse → ask Replace/Append → (Replace+dirty → confirm)
 *             → apply to the editor (which marks the document dirty), keep the
 *             active file path unchanged.
 *   Export  : build the chosen format → native Save dialog → write. Never clears
 *             dirty state and never changes the active file path (it's a copy).
 *
 * Both the native File menu and the in-app File dropdown call THIS pathway.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { createPsykeElement } from '../psyke/psykeApi';
import type { PsykeElementType } from '../psyke/types';
import { emitOutlineRefresh, getOutlineItems, saveOutlineItems } from '../outline/outlineApi';
import type { OutlineNode } from '../outline/outlineModel';
import type { DocumentSettings } from '../whiteboard/documentSettings';
import type { WhiteboardBlock } from '../whiteboard/types';
import { onMenuFile } from './fileApi';
import { exportSave, importConfirmMode, importOpen } from './importExportApi';
import {
  EXPORT_BY_ID,
  IMPORT_BY_ID,
  ImportError,
  buildExport,
  parseImport,
  suggestedExportName,
  type ExportComment,
  type ExportFormatId,
  type ExportPayload,
  type ImportFormatDef,
  type ImportFormatId,
  type ImportResult,
} from './importExportFormats';

export interface ImportExportFeedback {
  kind: 'ok' | 'error';
  message: string;
}

interface Options {
  baseUrl: string;
  getBlocks: () => WhiteboardBlock[];
  getMode: () => string;
  getTitle: () => string;
  getFileLabel: () => string; // current fileName (e.g. "script.fountain" or "Untitled")
  getSettings: () => DocumentSettings;
  getComments: () => ExportComment[];
  applySettings: (s: Partial<DocumentSettings>) => void;
  loadBlocks: (blocks: WhiteboardBlock[]) => void;
  setMode: (mode: string) => void;
  markDirty: () => void;
  confirmProceedPastUnsavedChanges: (reason: string) => Promise<boolean>;
}

export interface ImportExportApi {
  feedback: ImportExportFeedback | null;
  clearFeedback: () => void;
  runImport: (id: ImportFormatId) => void;
  runExport: (id: ExportFormatId) => void;
}

const FEEDBACK_MS = 3600;
const PSYKE_TYPES: PsykeElementType[] = ['character', 'place', 'object', 'lore', 'theme', 'other'];

const reid = (blocks: WhiteboardBlock[]): WhiteboardBlock[] =>
  blocks.map((b, i) => ({ ...b, id: `b${i}` }));

const blank = (): WhiteboardBlock => ({ id: 'sep', type: 'paragraph', text: '' });

export function useImportExport(opts: Options): ImportExportApi {
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const [feedback, setFeedback] = useState<ImportExportFeedback | null>(null);
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const say = useCallback((kind: 'ok' | 'error', message: string) => {
    setFeedback({ kind, message });
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    feedbackTimer.current = setTimeout(() => setFeedback(null), FEEDBACK_MS);
  }, []);
  const clearFeedback = useCallback(() => setFeedback(null), []);

  // --- apply an import to the editor -----------------------------------------
  const restoreOutline = useCallback(async (outline: OutlineNode[]) => {
    try {
      await saveOutlineItems(optsRef.current.baseUrl, outline);
      emitOutlineRefresh();
    } catch {
      /* best-effort: the document content already imported fine */
    }
  }, []);

  const restorePsyke = useCallback(async (elements: unknown[]) => {
    for (const raw of elements) {
      if (!raw || typeof raw !== 'object') continue;
      const el = raw as Record<string, unknown>;
      const name = typeof el.name === 'string' ? el.name.trim() : '';
      if (!name) continue;
      const rawType = typeof el.entry_type === 'string' ? el.entry_type : el.type;
      const type = (PSYKE_TYPES as string[]).includes(String(rawType))
        ? (rawType as PsykeElementType)
        : 'other';
      try {
        await createPsykeElement(optsRef.current.baseUrl, {
          type,
          name,
          description: typeof el.description === 'string' ? el.description : '',
          notes: typeof el.notes === 'string' ? el.notes : '',
        });
      } catch {
        /* skip an element that fails to import; never abort the whole import */
      }
    }
  }, []);

  const applyImport = useCallback(
    (def: ImportFormatDef, parsed: ImportResult, mode: 'replace' | 'append') => {
      const o = optsRef.current;
      if (mode === 'replace') {
        const targetMode = parsed.mode ?? def.forcesMode;
        if (parsed.settings) o.applySettings(parsed.settings);
        if (targetMode) o.setMode(targetMode);
        o.loadBlocks(reid(parsed.blocks));
        // Document-scoped restores only happen on a full replace.
        if (parsed.outline) void restoreOutline(parsed.outline);
        if (parsed.psyke?.elements.length) void restorePsyke(parsed.psyke.elements);
      } else {
        // Append: keep the active document; Fountain/FDX still force Screenplay.
        if (def.forcesMode) o.setMode(def.forcesMode);
        const cur = o.getBlocks();
        const needsSep = cur.length > 0 && (cur[cur.length - 1]?.text ?? '').trim() !== '';
        const combined = needsSep ? [...cur, blank(), ...parsed.blocks] : [...cur, ...parsed.blocks];
        o.loadBlocks(reid(combined));
      }
      // loadBlocks already marks dirty via the editor update; be explicit too.
      o.markDirty();
    },
    [restoreOutline, restorePsyke],
  );

  // --- import flow -----------------------------------------------------------
  const doImport = useCallback(
    async (id: ImportFormatId) => {
      const def = IMPORT_BY_ID.get(id);
      if (!def) return;
      try {
        const res = await importOpen(def.filters);
        if (res.canceled) return;
        if (!res.ok) {
          say('error', res.error ?? 'Could not open the file.');
          return;
        }

        let parsed: ImportResult;
        try {
          parsed = parseImport(id, res.content ?? '');
        } catch (err) {
          say('error', err instanceof ImportError ? err.message : 'Could not read this file.');
          return;
        }

        const applyMode = await importConfirmMode();
        if (applyMode === 'cancel') return;
        if (applyMode === 'replace') {
          const ok = await optsRef.current.confirmProceedPastUnsavedChanges(
            'Importing will replace the current document. Save changes first?',
          );
          if (!ok) return;
        }

        applyImport(def, parsed, applyMode);
        say('ok', `Imported ${res.fileName ?? 'file'} (${applyMode === 'replace' ? 'replaced' : 'appended'}).`);
      } catch (err) {
        console.error('[import] failed:', err);
        say('error', 'Import failed.');
      }
    },
    [applyImport, say],
  );

  // --- export flow -----------------------------------------------------------
  const doExport = useCallback(
    async (id: ExportFormatId) => {
      const def = EXPORT_BY_ID.get(id);
      if (!def) return;
      const o = optsRef.current;
      if (id === 'comments' && o.getComments().length === 0) {
        say('ok', 'No comments to export.');
        return;
      }
      try {
        // The LogosForge envelope embeds the (backend-persisted) manual outline.
        let outline: OutlineNode[] = [];
        if (id === 'logosforge') {
          try {
            outline = await getOutlineItems(o.baseUrl);
          } catch {
            outline = [];
          }
        }
        const label = o.getFileLabel();
        const title = label && label !== 'Untitled' ? label.replace(/\.[^./\\]+$/, '') : o.getTitle();
        const payload: ExportPayload = {
          title: title || 'Untitled',
          mode: o.getMode(),
          blocks: o.getBlocks(),
          settings: o.getSettings(),
          outline,
          psyke: { elements: [] },
          comments: o.getComments(),
        };

        const content = buildExport(id, payload);
        const suggested =
          id === 'comments'
            ? suggestedExportName(label || payload.title, 'md').replace(/\.md$/i, '-comments.md')
            : suggestedExportName(label || payload.title, def.ext);
        const res = await exportSave(content, suggested, def.filters);
        if (res.canceled) return;
        if (!res.ok) {
          say('error', res.error ?? 'Export failed.');
          return;
        }
        // Intentionally does NOT clear dirty state or change the active file path
        // — an export is a copy; only Save/Save As own the active document.
        say('ok', `Exported ${res.fileName ?? suggested}.`);
      } catch (err) {
        console.error('[export] failed:', err);
        say('error', 'Export failed.');
      }
    },
    [say],
  );

  const runImport = useCallback((id: ImportFormatId) => void doImport(id), [doImport]);
  const runExport = useCallback((id: ExportFormatId) => void doExport(id), [doExport]);

  // Native File-menu Import/Export actions (mouse + any future accelerators).
  useEffect(
    () =>
      onMenuFile((action) => {
        if (action.startsWith('import:')) void doImport(action.slice('import:'.length) as ImportFormatId);
        else if (action.startsWith('export:')) void doExport(action.slice('export:'.length) as ExportFormatId);
      }),
    [doImport, doExport],
  );

  useEffect(
    () => () => {
      if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    },
    [],
  );

  return { feedback, clearFeedback, runImport, runExport };
}
