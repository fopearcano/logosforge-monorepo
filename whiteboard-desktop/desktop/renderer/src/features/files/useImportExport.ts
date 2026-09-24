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

import { isModalDialogOpen } from '../../components/useModalDialog';
import {
  captureDocumentIncarnation,
  flushPendingDocSaves,
  getCurrentDocId,
  markPendingDocSave,
  runPendingDocWrite,
} from '../../state/currentDocument';
import { backendFetch, withExpectedDocumentIncarnation } from '../../api/backendAuth';
import {
  persistPendingDocument,
  persistPendingDocumentOnUnload,
  retainPendingDocumentConflict,
} from '../../api/pendingDocumentPersistence';
import { responseError } from '../../api/responseError';
import { createPsykeElementForDocument } from '../psyke/psykeApi';
import type { PsykeElementType } from '../psyke/types';
import { emitOutlineRefresh } from '../outline/outlineApi';
import type { OutlineNode } from '../outline/outlineModel';
import {
  flushOutlineSnapshots,
  queueOutlineSnapshot,
} from '../outline/pendingOutlineRecovery';
import {
  normalizeDocumentSettings,
  type DocumentSettings,
} from '../whiteboard/documentSettings';
import { freshBlockIds, normalizeBlockIds } from '../whiteboard/blockIdentity';
import { getWhiteboardForDocument } from '../whiteboard/whiteboardApi';
import type { WhiteboardBlock } from '../whiteboard/types';
import {
  acquireTrackedDocumentOperation,
  isDocumentInteractionLocked,
  lockDocumentInteraction,
} from '../whiteboard/documentOperationGuard';
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
  applySettings: (s: Partial<DocumentSettings>) => void;
  loadBlocks: (blocks: WhiteboardBlock[]) => void;
  setMode: (mode: string) => Promise<boolean>;
  markDirty: () => void;
  confirmProceedPastUnsavedChanges: (reason: string) => Promise<boolean>;
}

export interface ImportExportApi {
  feedback: ImportExportFeedback | null;
  clearFeedback: () => void;
  runImport: (id: ImportFormatId) => void;
  runExport: (id: ExportFormatId) => void;
}

const PSYKE_TYPES: PsykeElementType[] = ['character', 'place', 'object', 'lore', 'theme', 'other'];

const withStableIds = (blocks: WhiteboardBlock[]): WhiteboardBlock[] => {
  const ids = normalizeBlockIds(blocks.map((block) => block.id));
  return blocks.map((block, index) => ({ ...block, id: ids[index] }));
};

const withFreshIds = (blocks: WhiteboardBlock[]): WhiteboardBlock[] => {
  const ids = freshBlockIds(blocks.length);
  return blocks.map((block, index) => ({ ...block, id: ids[index] }));
};

const blank = (): WhiteboardBlock => ({ id: 'sep', type: 'paragraph', text: '' });

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

/** Adapt the backend's one-request project snapshot to the format exporters. */
function exportPayloadFromProjectBundle(content: string): ExportPayload {
  const root = asRecord(JSON.parse(content));
  const project = asRecord(root?.project);
  const manuscript = asRecord(project?.manuscript);
  if (!project || !manuscript || !Array.isArray(manuscript.blocks)) {
    throw new Error('The backend returned an invalid project snapshot.');
  }
  const rawComments = Array.isArray(project.comments) ? project.comments : [];
  const comments: ExportComment[] = rawComments.flatMap((value) => {
    const comment = asRecord(value);
    const anchor = asRecord(comment?.anchor);
    if (!comment || !anchor) return [];
    return [{
      quote: typeof comment.quote === 'string' ? comment.quote : '',
      body: typeof comment.body === 'string' ? comment.body : '',
      resolved: comment.resolved === true,
      blockIndex: typeof anchor.block_index === 'number' ? anchor.block_index : 0,
      ...(typeof comment.created_at === 'string' ? { createdAt: comment.created_at } : {}),
    }];
  });
  const psyke = asRecord(project.psyke);
  return {
    title: typeof project.title === 'string' ? project.title : 'Untitled',
    mode: typeof project.mode === 'string' ? project.mode : 'novel',
    blocks: manuscript.blocks as WhiteboardBlock[],
    settings: normalizeDocumentSettings(project.settings),
    outline: Array.isArray(project.outline) ? project.outline as OutlineNode[] : [],
    psyke: { elements: psyke && Array.isArray(psyke.elements) ? psyke.elements : [] },
    comments,
  };
}

export function useImportExport(opts: Options): ImportExportApi {
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const [feedback, setFeedback] = useState<ImportExportFeedback | null>(null);

  const say = useCallback((kind: 'ok' | 'error', message: string) => {
    setFeedback({ kind, message });
  }, []);
  const clearFeedback = useCallback(() => setFeedback(null), []);

  // --- apply an import to the editor -----------------------------------------
  const restoreOutline = useCallback(async (documentId: string, outline: OutlineNode[]) => {
    const baseUrl = optsRef.current.baseUrl;
    const incarnation = captureDocumentIncarnation(documentId);
    await runPendingDocWrite(async () => {
      queueOutlineSnapshot(documentId, outline, {
        incarnation,
        write: (targetDocumentId, snapshot, revision) => persistPendingDocument(
          baseUrl,
          'outline',
          targetDocumentId,
          revision,
          { items: snapshot },
          incarnation,
        ),
        writeOnUnload: (targetDocumentId, snapshot, revision) => {
          persistPendingDocumentOnUnload(
            baseUrl,
            'outline',
            targetDocumentId,
            revision,
            { items: snapshot },
            incarnation,
          );
        },
        retainConflict: (targetDocumentId, snapshot, revision, recovery) =>
          retainPendingDocumentConflict(
            'outline',
            targetDocumentId,
            revision,
            { items: snapshot },
            recovery,
            incarnation,
          ),
      });
      markPendingDocSave();
      // Synchronously cancels any older GET and installs this exact snapshot in
      // a mounted Outline store before the persistence await can yield.
      emitOutlineRefresh(documentId, outline);
      await flushOutlineSnapshots(documentId);
    }, documentId);
  }, []);

  const restorePsyke = useCallback(async (documentId: string, elements: unknown[]): Promise<number> => {
    let failed = 0;
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
        await createPsykeElementForDocument(optsRef.current.baseUrl, documentId, {
          type,
          name,
          description: typeof el.description === 'string' ? el.description : '',
          notes: typeof el.notes === 'string' ? el.notes : '',
        });
      } catch {
        failed += 1;
      }
    }
    return failed;
  }, []);

  const applyImport = useCallback(
    async (
      def: ImportFormatDef,
      parsed: ImportResult,
      mode: 'replace' | 'append',
      targetDocumentId: string,
    ) => {
      const o = optsRef.current;
      const warnings: string[] = [];
      if (mode === 'replace') {
        const targetMode = parsed.mode ?? def.forcesMode;
        if (parsed.settings) o.applySettings(parsed.settings);
        // A LogosForge envelope carries an outline whose stable block ids must
        // remain aligned. Plain-text replacements are a new manuscript identity.
        // Install the replacement before the first await so typing during a slow
        // mode/outline request can extend it, never be overwritten by it.
        o.loadBlocks(parsed.outline !== undefined
          ? withStableIds(parsed.blocks)
          : withFreshIds(parsed.blocks));
        if (targetMode && !(await o.setMode(targetMode))) warnings.push('writing mode');
        // Document-scoped restores only happen on a full replace.
        if (parsed.outline) {
          try {
            await restoreOutline(targetDocumentId, parsed.outline);
          } catch {
            warnings.push('outline');
          }
        }
        if (parsed.psyke?.elements.length) {
          const failed = await restorePsyke(targetDocumentId, parsed.psyke.elements);
          if (failed) warnings.push(`${failed} PSYKE ${failed === 1 ? 'entry' : 'entries'}`);
        }
      } else {
        // Append: keep the active document; Fountain/FDX still force Screenplay.
        const cur = o.getBlocks();
        const needsSep = cur.length > 0 && (cur[cur.length - 1]?.text ?? '').trim() !== '';
        const combined = needsSep ? [...cur, blank(), ...parsed.blocks] : [...cur, ...parsed.blocks];
        // As with replace, install the manuscript before any async mode save so
        // a fault-boundary remount cannot retire the imperative editor first.
        o.loadBlocks(withStableIds(combined));
        if (def.forcesMode && !(await o.setMode(def.forcesMode))) warnings.push('writing mode');
      }
      // loadBlocks already marks dirty via the editor update; be explicit too.
      o.markDirty();
      return warnings;
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

        // Pin every part of the import to one document. Navigation and close
        // wait for this lease, while outline/PSYKE transports use the captured
        // id instead of consulting mutable global state between awaits.
        const finishImport = await acquireTrackedDocumentOperation();
        const releaseImportInteraction = lockDocumentInteraction();
        let warnings: string[];
        try {
          const targetDocumentId = getCurrentDocId();
          if (!targetDocumentId) throw new Error('No active document to import into.');
          warnings = await applyImport(def, parsed, applyMode, targetDocumentId);
          // Confirm that every imported snapshot reached the local backend
          // before claiming success. A failed flush retains it for retry.
          await flushPendingDocSaves();
        } finally {
          releaseImportInteraction();
          finishImport();
        }
        const summary = `Imported ${res.fileName ?? 'file'} (${applyMode === 'replace' ? 'replaced' : 'appended'}).`;
        if (warnings.length) {
          say('error', `${summary} Could not restore: ${warnings.join(', ')}.`);
        } else {
          say('ok', summary);
        }
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
      try {
        let content = '';
        let suggested = '';
        let noComments = false;
        const finishExportSnapshot = await acquireTrackedDocumentOperation();
        const releaseExportInteraction = lockDocumentInteraction();
        try {
          // Drain first, then read every persisted subsystem by the same explicit
          // id. Renderer stores intentionally update in separate passive effects
          // after navigation, so they are not a coherent export source.
          await flushPendingDocSaves();
          const documentId = getCurrentDocId();
          if (!documentId) throw new Error('No active document to export.');
          const baseUrl = optsRef.current.baseUrl;

          if (id === 'project-bundle' || id === 'logosforge' || id === 'comments') {
            // One backend request captures manuscript, outline, comments, and
            // PSYKE together; separate GETs could observe different edit epochs.
            const url = new URL(`${baseUrl}/api/export/project`);
            url.searchParams.set('doc', documentId);
            const resp = await backendFetch(url.toString(), {
              headers: withExpectedDocumentIncarnation(
                captureDocumentIncarnation(documentId),
              ),
            });
            if (!resp.ok) throw await responseError(resp, 'Could not assemble the project bundle');
            const projectContent = await resp.text();
            if (id === 'project-bundle') {
              content = projectContent;
              let projectTitle = '';
              try {
                const bundle = JSON.parse(content) as { project?: { title?: unknown } };
                if (typeof bundle.project?.title === 'string') projectTitle = bundle.project.title;
              } catch {
                /* the native save still receives the backend's original payload */
              }
              suggested = suggestedExportName(projectTitle || `project-${documentId}`, 'lfbundle');
            } else {
              const payload = exportPayloadFromProjectBundle(projectContent);
              if (id === 'comments' && (payload.comments?.length ?? 0) === 0) {
                noComments = true;
              } else {
                content = buildExport(id, payload);
                suggested = id === 'comments'
                  ? suggestedExportName(payload.title, 'md').replace(/\.md$/i, '-comments.md')
                  : suggestedExportName(payload.title, def.ext);
              }
            }
          } else {
            const whiteboard = await getWhiteboardForDocument(
              baseUrl,
              documentId,
              undefined,
              captureDocumentIncarnation(documentId),
            );
            const payload: ExportPayload = {
              title: whiteboard.title || 'Untitled',
              mode: whiteboard.mode,
              blocks: whiteboard.blocks,
              settings: normalizeDocumentSettings(whiteboard.settings),
              outline: [],
              psyke: { elements: [] },
              comments: [],
            };
            content = buildExport(id, payload);
            suggested = suggestedExportName(payload.title, def.ext);
          }
        } finally {
          releaseExportInteraction();
          finishExportSnapshot();
        }

        if (noComments) {
          say('ok', 'No comments to export.');
          return;
        }
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
        if (isModalDialogOpen() || isDocumentInteractionLocked()) return;
        if (action.startsWith('import:')) void doImport(action.slice('import:'.length) as ImportFormatId);
        else if (action.startsWith('export:')) void doExport(action.slice('export:'.length) as ExportFormatId);
      }),
    [doImport, doExport],
  );

  return { feedback, clearFeedback, runImport, runExport };
}
