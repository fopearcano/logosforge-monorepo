import type { OutlineNode } from '../outline/outlineModel';
import type { DocumentSettings } from '../whiteboard/documentSettings';
import type { WhiteboardBlock } from '../whiteboard/types';
import {
  recoveryImportIdentityRelationship,
  type ImportResult,
  type RecoveryImportDescriptor,
  type RecoveryImportTarget,
} from './importExportFormats';

export type RecoveryConfirmationStep = 'restore' | 'retarget';

/** Every recovery asks once; unverifiable or mismatched provenance asks twice. */
export async function confirmRecoveryImportSteps(
  recovery: RecoveryImportDescriptor,
  target: RecoveryImportTarget,
  confirm: (step: RecoveryConfirmationStep) => Promise<boolean>,
): Promise<boolean> {
  if (!await confirm('restore')) return false;
  if (recoveryImportIdentityRelationship(
    recovery,
    target.documentId,
    target.incarnation,
  ) === 'same') return true;
  return confirm('retarget');
}

/** Destructive recovery starts only after the captured target is current and
 * every pre-existing write drains. Recheck after the async drain as a defense
 * in depth even though the production caller holds the interaction lock. */
export async function runRecoveryImportAfterPreflight(
  assertTargetStillActive: () => void,
  flushPending: () => Promise<void>,
  apply: () => Promise<void>,
): Promise<void> {
  assertTargetStillActive();
  await flushPending();
  assertTargetStillActive();
  await apply();
}

export interface RecoveryImportActions {
  applySettings: (settings: Partial<DocumentSettings>) => void;
  /** False means the editor is not mounted; no manuscript mutation occurred. */
  loadBlocks: (blocks: WhiteboardBlock[]) => boolean;
  setMode: (mode: string) => Promise<boolean>;
  setTitle: (title: string) => Promise<boolean>;
  markDirty: () => void;
  restoreOutline: (documentId: string, outline: OutlineNode[]) => Promise<void>;
}

/** Apply only recovery content to a caller-captured target. Provenance fields are
 * deliberately absent from the action contract, so they can never become write
 * authority or acknowledge a live conflict receipt. */
export async function applyRecoveryImport(
  parsed: ImportResult,
  targetDocumentId: string,
  actions: RecoveryImportActions,
): Promise<void> {
  if (parsed.recovery?.scope === 'outline') {
    await actions.restoreOutline(targetDocumentId, parsed.outline ?? []);
    return;
  }
  if (parsed.recovery?.scope !== 'whiteboard') {
    throw new Error('The selected file is not a recovery import.');
  }

  // The strict parser guarantees these fields. Install all synchronous views
  // first; the document outbox owns durable retry if either immediate flush fails.
  if (!actions.loadBlocks(parsed.blocks)) {
    throw new Error('The manuscript editor is not ready. Nothing was restored; try again after it loads.');
  }
  actions.applySettings(parsed.settings as Partial<DocumentSettings>);
  actions.markDirty();
  const [titleSaved, modeSaved] = await Promise.all([
    actions.setTitle(parsed.title as string),
    actions.setMode(parsed.mode as string),
  ]);
  if (!titleSaved || !modeSaved) {
    throw new Error(
      'The recovered manuscript remains open and queued, but it could not be saved completely.',
    );
  }
}
